#!/usr/bin/env bash
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGEM="${POSTGRES_IMAGE:-postgres:16-alpine}"
CONTAINER="pg-bzr-check-$$"

if ! command -v docker >/dev/null 2>&1; then
    echo "Erro: Docker não encontrado no PATH." >&2
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    echo "Erro: o daemon do Docker não está em execução. Inicie o serviço (ex.: sudo systemctl start docker) e tente novamente." >&2
    exit 1
fi

limpar() {
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap limpar EXIT

psql_db() {
    local db="$1"
    shift
    docker exec -i "$CONTAINER" psql -U postgres -d "$db" -v ON_ERROR_STOP=1 -q "$@"
}

echo "Subindo PostgreSQL efêmero ($IMAGEM)..."
docker run --rm -d \
    --name "$CONTAINER" \
    -e POSTGRES_PASSWORD=postgres \
    -v "$RAIZ":/work:ro \
    -w /work \
    "$IMAGEM" >/dev/null

for _ in $(seq 1 30); do
    if docker exec "$CONTAINER" pg_isready -U postgres >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

if ! docker exec "$CONTAINER" pg_isready -U postgres >/dev/null 2>&1; then
    echo "Erro: PostgreSQL não ficou pronto a tempo." >&2
    exit 1
fi

# =============================================================================
# Cenário 1: banco limpo + migração + travas, UPSERT, view e quarentena
# =============================================================================
psql_db postgres -c "CREATE DATABASE teste_limpo;"
psql_db teste_limpo -f data/raw/schema.sql
psql_db teste_limpo -f sql/migrations/001_prevencao_integridade.sql

psql_db teste_limpo <<'SQL'
-- 1) Carga dos 6 precatórios limpos (incluindo bordas de 02/04 e UTC)
INSERT INTO precatorio (numero_processo, ente_devedor, valor_face, apresentado_em, prazo_pagamento) VALUES
    ('00123451020198260053', 'Município de São Paulo', 45000.00, '2025-04-02T00:00:00-03:00', '2026-12-31'),
    ('00234562120208260053', 'Município de São Paulo', 31000.00, '2025-04-03T00:00:00-03:00', '2027-12-31'),
    ('00345673220188260405', 'Estado de São Paulo',    12500.00, '2024-02-29T00:00:00-03:00', '2025-12-31'),
    ('00456784320215020011', 'Município de Santos',     9800.00, '2025-04-02T23:30:00-03:00', '2026-12-31'),
    ('00567895420174036100', 'Estado de São Paulo',    22000.00, '2025-04-03T01:00:00Z',      '2026-12-31'),
    ('00678906520168260053', 'Município de São Paulo',  7000.00, '2023-12-31T00:00:00-03:00', '2025-12-31');

-- 2) Rejeição de violações de contrato em precatorio
DO $$
DECLARE
    v_constraint TEXT;
BEGIN
    BEGIN
        INSERT INTO precatorio (numero_processo, ente_devedor, valor_face)
        VALUES ('0012345-10.2019.8.26.0053', 'Teste', 100.00);
        RAISE EXCEPTION 'CNJ com 25 caracteres deveria falhar';
    EXCEPTION WHEN string_data_right_truncation THEN NULL;
    END;

    BEGIN
        INSERT INTO precatorio (numero_processo, ente_devedor, valor_face)
        VALUES ('12345', 'Teste', 100.00);
        RAISE EXCEPTION 'CNJ curto deveria falhar';
    EXCEPTION WHEN check_violation THEN
        GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
        IF v_constraint <> 'chk_precatorio_numero_processo_20_digitos' THEN
            RAISE EXCEPTION 'Constraint inesperada: %', v_constraint;
        END IF;
    END;

    BEGIN
        INSERT INTO precatorio (numero_processo, ente_devedor, valor_face)
        VALUES ('99999999999999999999', '   ', 100.00);
        RAISE EXCEPTION 'ente_devedor vazio deveria falhar';
    EXCEPTION WHEN check_violation THEN
        GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
        IF v_constraint <> 'chk_precatorio_ente_devedor_nao_vazio' THEN
            RAISE EXCEPTION 'Constraint inesperada: %', v_constraint;
        END IF;
    END;

    BEGIN
        INSERT INTO precatorio (numero_processo, ente_devedor, valor_face)
        VALUES ('99999999999999999999', ' Teste ', 100.00);
        RAISE EXCEPTION 'ente_devedor com espaços nas pontas deveria falhar';
    EXCEPTION WHEN check_violation THEN
        GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
        IF v_constraint <> 'chk_precatorio_ente_devedor_nao_vazio' THEN
            RAISE EXCEPTION 'Constraint inesperada: %', v_constraint;
        END IF;
    END;

    BEGIN
        INSERT INTO precatorio (numero_processo, ente_devedor, valor_face)
        VALUES ('99999999999999999999', 'Teste', 0);
        RAISE EXCEPTION 'valor_face = 0 deveria falhar';
    EXCEPTION WHEN check_violation THEN
        GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
        IF v_constraint <> 'chk_precatorio_valor_face_positivo' THEN
            RAISE EXCEPTION 'Constraint inesperada: %', v_constraint;
        END IF;
    END;

    BEGIN
        INSERT INTO precatorio (numero_processo, ente_devedor, valor_face, apresentado_em, prazo_pagamento)
        VALUES ('99999999999999999999', 'Teste', 100.00, '2025-04-02T00:00:00-03:00', NULL);
        RAISE EXCEPTION 'apresentado_em preenchido com prazo_pagamento NULL deveria falhar';
    EXCEPTION WHEN check_violation THEN
        GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
        IF v_constraint <> 'chk_precatorio_datas_prazo' THEN
            RAISE EXCEPTION 'Constraint inesperada: %', v_constraint;
        END IF;
    END;

    BEGIN
        INSERT INTO precatorio (numero_processo, ente_devedor, valor_face, apresentado_em, prazo_pagamento)
        VALUES ('99999999999999999999', 'Teste', 100.00, NULL, '2026-12-31');
        RAISE EXCEPTION 'prazo_pagamento preenchido com apresentado_em NULL deveria falhar';
    EXCEPTION WHEN check_violation THEN
        GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
        IF v_constraint <> 'chk_precatorio_datas_prazo' THEN
            RAISE EXCEPTION 'Constraint inesperada: %', v_constraint;
        END IF;
    END;

    BEGIN
        INSERT INTO precatorio (numero_processo, ente_devedor, valor_face, apresentado_em, prazo_pagamento)
        VALUES ('99999999999999999999', 'Teste', 100.00, '2025-04-02T00:00:00-03:00', '2025-04-02');
        RAISE EXCEPTION 'prazo_pagamento igual à data de apresentação deveria falhar';
    EXCEPTION WHEN check_violation THEN
        GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
        IF v_constraint <> 'chk_precatorio_datas_prazo' THEN
            RAISE EXCEPTION 'Constraint inesperada: %', v_constraint;
        END IF;
    END;

    BEGIN
        INSERT INTO precatorio (numero_processo, ente_devedor, valor_face, apresentado_em, prazo_pagamento)
        VALUES ('99999999999999999999', 'Teste', 100.00, '2025-04-03T01:00:00Z', '2025-04-02');
        RAISE EXCEPTION 'prazo_pagamento igual à apresentação em Brasília (03/04T01:00:00Z) deveria falhar';
    EXCEPTION WHEN check_violation THEN
        GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
        IF v_constraint <> 'chk_precatorio_datas_prazo' THEN
            RAISE EXCEPTION 'Constraint inesperada: %', v_constraint;
        END IF;
    END;
END $$;

-- 3) Carga de pagamentos, retificação idempotente (ev-001) e travas
INSERT INTO pagamento (precatorio_id, evento_id, tipo, valor, pago_em, atualizado_em) VALUES
    (1, 'ev-001', 'pagamento', 15000.00, '2025-03-10', '2025-03-10T10:00:00-03:00'),
    (1, 'ev-002', 'pagamento',  2500.50, '2025-04-10', '2025-04-10T09:00:00-03:00'),
    (2, 'ev-003', 'pagamento',  8000.00, '2025-05-02', '2025-05-02T11:00:00-03:00'),
    (2, 'ev-005', 'pagamento',  1200.00, '2025-06-01', '2025-06-01T10:00:00-03:00'),
    (3, 'ev-006', 'pagamento',  5000.00, '2025-02-20', '2025-02-20T10:00:00-03:00'),
    (3, 'ev-007', 'estorno',    5000.00, '2025-02-21', '2025-02-21T10:00:00-03:00'),
    (4, 'ev-008', 'pagamento',  3000.00, '2025-07-15', '2025-07-15T10:00:00-03:00');

-- Retificação mais recente atualiza ev-001
INSERT INTO pagamento (precatorio_id, evento_id, tipo, valor, pago_em, atualizado_em)
VALUES (1, 'ev-001', 'pagamento', 15500.00, '2025-03-10', '2025-03-11T09:00:00-03:00')
ON CONFLICT (evento_id) DO UPDATE
   SET valor         = EXCLUDED.valor,
       atualizado_em = EXCLUDED.atualizado_em
 WHERE EXCLUDED.atualizado_em > pagamento.atualizado_em;

-- Reenvio mais antigo não sobrescreve
INSERT INTO pagamento (precatorio_id, evento_id, tipo, valor, pago_em, atualizado_em)
VALUES (1, 'ev-001', 'pagamento', 15000.00, '2025-03-10', '2025-03-10T10:00:00-03:00')
ON CONFLICT (evento_id) DO UPDATE
   SET valor         = EXCLUDED.valor,
       atualizado_em = EXCLUDED.atualizado_em
 WHERE EXCLUDED.atualizado_em > pagamento.atualizado_em;

DO $$
DECLARE
    v_constraint TEXT;
    v_valor      NUMERIC(15,2);
    v_row        RECORD;
BEGIN
    SELECT valor INTO v_valor FROM pagamento WHERE evento_id = 'ev-001';
    IF v_valor <> 15500.00 THEN
        RAISE EXCEPTION 'ev-001 esperado 15500.00, encontrado %', v_valor;
    END IF;

    BEGIN
        INSERT INTO pagamento (precatorio_id, evento_id, tipo, valor, pago_em, atualizado_em)
        VALUES (1, 'ev-002', 'pagamento', 2500.50, '2025-04-10', '2025-04-10T09:00:00-03:00');
        RAISE EXCEPTION 'evento_id duplicado deveria falhar';
    EXCEPTION WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
        IF v_constraint <> 'uq_pagamento_evento_id' THEN
            RAISE EXCEPTION 'Constraint inesperada: %', v_constraint;
        END IF;
    END;

    BEGIN
        INSERT INTO pagamento (precatorio_id, evento_id, tipo, valor, pago_em)
        VALUES (1, 'ev-999', 'pagamento', 100.00, '2025-04-10');
        RAISE EXCEPTION 'atualizado_em omitido deveria falhar';
    EXCEPTION WHEN not_null_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO pagamento (precatorio_id, evento_id, tipo, valor, pago_em, atualizado_em)
        VALUES (1, '   ', 'pagamento', 100.00, '2025-04-10', '2025-04-10T09:00:00-03:00');
        RAISE EXCEPTION 'evento_id vazio deveria falhar';
    EXCEPTION WHEN check_violation THEN
        GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
        IF v_constraint <> 'chk_pagamento_evento_id_nao_vazio' THEN
            RAISE EXCEPTION 'Constraint inesperada: %', v_constraint;
        END IF;
    END;

    BEGIN
        INSERT INTO pagamento (precatorio_id, evento_id, tipo, valor, pago_em, atualizado_em)
        VALUES (1, 'ev-001 ', 'pagamento', 100.00, '2025-04-10', '2025-04-10T09:00:00-03:00');
        RAISE EXCEPTION 'evento_id com espaço nas pontas deveria falhar';
    EXCEPTION WHEN check_violation THEN
        GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
        IF v_constraint <> 'chk_pagamento_evento_id_nao_vazio' THEN
            RAISE EXCEPTION 'Constraint inesperada: %', v_constraint;
        END IF;
    END;

    -- 4) Conferência da view vw_precatorio_saldo
    SELECT * INTO v_row FROM vw_precatorio_saldo WHERE numero_processo = '00123451020198260053';
    IF v_row.numero_processo_cnj <> '0012345-10.2019.8.26.0053'
       OR v_row.total_pago_liquido <> 18000.50
       OR v_row.saldo_a_receber <> 26999.50
       OR v_row.qtd_eventos <> 2 THEN
        RAISE EXCEPTION 'Saldo incorreto para 0012345-10.2019.8.26.0053: %', v_row;
    END IF;

    SELECT * INTO v_row FROM vw_precatorio_saldo WHERE numero_processo = '00345673220188260405';
    IF v_row.total_pagamentos <> 5000.00
       OR v_row.total_estornos <> 5000.00
       OR v_row.total_pago_liquido <> 0.00
       OR v_row.saldo_a_receber <> 12500.00 THEN
        RAISE EXCEPTION 'Estorno incorreto para 0034567-32.2018.8.26.0405: %', v_row;
    END IF;

    SELECT * INTO v_row FROM vw_precatorio_saldo WHERE numero_processo = '00567895420174036100';
    IF v_row.total_pago_liquido <> 0.00
       OR v_row.saldo_a_receber <> 22000.00
       OR v_row.qtd_eventos <> 0 THEN
        RAISE EXCEPTION 'Saldo zerado incorreto para 0056789-54.2017.4.03.6100: %', v_row;
    END IF;
END $$;

-- 5) Quarentena: deduplicação na janela de 7 dias e reabertura após resolução
DO $$
DECLARE
    v_payload    TEXT := '{"evento_id":"ev-004","valor":null}';
    v_hash       TEXT := encode(sha256(convert_to(v_payload, 'UTF8')), 'hex');
    v_count      INTEGER;
    v_ocorrencia INTEGER;
    v_constraint TEXT;
BEGIN
    FOR i IN 1..2 LOOP
        INSERT INTO pagamento_rejeitado (
            evento_id, processo_informado, motivo_codigo, motivo_detalhe,
            payload_original, payload_hash
        )
        VALUES ('ev-004', '0023456-21.2020.8.26.0053', 'valor_nulo', 'Valor nulo', v_payload::jsonb, v_hash)
        ON CONFLICT (COALESCE(evento_id, ''), motivo_codigo, payload_hash)
            WHERE status = 'pendente'
        DO UPDATE
           SET ocorrencias          = pagamento_rejeitado.ocorrencias + 1,
               ultima_ocorrencia_em = now();
    END LOOP;

    SELECT COUNT(*), MAX(ocorrencias)
      INTO v_count, v_ocorrencia
      FROM pagamento_rejeitado
     WHERE evento_id = 'ev-004';
    IF v_count <> 1 OR v_ocorrencia <> 2 THEN
        RAISE EXCEPTION 'Deduplicação da quarentena falhou: linhas=%, ocorrencias=%', v_count, v_ocorrencia;
    END IF;

    BEGIN
        UPDATE pagamento_rejeitado SET status = 'resolvido' WHERE evento_id = 'ev-004';
        RAISE EXCEPTION 'Resolver sem resolvido_em deveria falhar';
    EXCEPTION WHEN check_violation THEN
        GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
        IF v_constraint <> 'chk_pagamento_rejeitado_resolucao' THEN
            RAISE EXCEPTION 'Constraint inesperada: %', v_constraint;
        END IF;
    END;

    UPDATE pagamento_rejeitado
       SET status = 'resolvido', resolvido_em = now()
     WHERE evento_id = 'ev-004';

    INSERT INTO pagamento_rejeitado (
        evento_id, processo_informado, motivo_codigo, motivo_detalhe,
        payload_original, payload_hash
    )
    VALUES ('ev-004', '0023456-21.2020.8.26.0053', 'valor_nulo', 'Valor nulo', v_payload::jsonb, v_hash)
    ON CONFLICT (COALESCE(evento_id, ''), motivo_codigo, payload_hash)
        WHERE status = 'pendente'
    DO UPDATE
       SET ocorrencias          = pagamento_rejeitado.ocorrencias + 1,
           ultima_ocorrencia_em = now();

    SELECT COUNT(*) INTO v_count FROM pagamento_rejeitado WHERE evento_id = 'ev-004';
    IF v_count <> 2 THEN
        RAISE EXCEPTION 'Reabertura após resolução falhou: linhas=%', v_count;
    END IF;
END $$;
SQL
echo "[OK] Cenário 1: banco limpo, travas de contrato, UPSERT, vw_precatorio_saldo e quarentena"

# =============================================================================
# Cenário 2: banco legado com espaços extras e duplicatas idênticas
# =============================================================================
psql_db postgres -c "CREATE DATABASE teste_legado;"
psql_db teste_legado -f data/raw/schema.sql

psql_db teste_legado <<'SQL'
INSERT INTO precatorio (numero_processo, ente_devedor, valor_face) VALUES
    ('00123451020198260053', '  Município de São Paulo  ', 45000.00);

INSERT INTO pagamento (precatorio_id, evento_id, tipo, valor, pago_em, criado_em) VALUES
    (1, 'ev-001',  'pagamento', 15000.00, '2025-03-10', '2025-03-10T10:00:00-03:00'),
    (1, 'ev-001 ', 'pagamento', 15000.00, '2025-03-10', '2025-03-11T09:00:00-03:00'),
    (1, 'ev-002',  'pagamento',  2500.50, '2025-04-10', '2025-04-10T09:00:00-03:00'),
    (1, 'ev-002',  'pagamento',  2500.50, '2025-04-10', '2025-04-10T09:00:00-03:00');
SQL

psql_db teste_legado -f sql/migrations/001_prevencao_integridade.sql

psql_db teste_legado <<'SQL'
DO $$
DECLARE
    v_ente     TEXT;
    v_count    INTEGER;
    v_valor    NUMERIC(15,2);
    v_backfill BOOLEAN;
BEGIN
    SELECT ente_devedor INTO v_ente FROM precatorio WHERE numero_processo = '00123451020198260053';
    IF v_ente <> 'Município de São Paulo' THEN
        RAISE EXCEPTION 'btrim de ente_devedor falhou: %', v_ente;
    END IF;

    SELECT COUNT(*) INTO v_count FROM pagamento;
    IF v_count <> 2 THEN
        RAISE EXCEPTION 'Deduplicação legada esperada=2, obtida=%', v_count;
    END IF;

    SELECT valor, (atualizado_em = criado_em)
      INTO v_valor, v_backfill
      FROM pagamento
     WHERE evento_id = 'ev-001';
    IF v_valor <> 15000.00 OR NOT v_backfill THEN
        RAISE EXCEPTION 'ev-001 pós-migração inválido: valor=%, backfill=%', v_valor, v_backfill;
    END IF;
END $$;
SQL
echo "[OK] Cenário 2: saneamento de espaços, deduplicação de cópias idênticas e backfill de atualizado_em"

# =============================================================================
# Cenário 3: banco legado com duplicata divergente aborta sem perder dados
# =============================================================================
psql_db postgres -c "CREATE DATABASE teste_legado_conflito;"
psql_db teste_legado_conflito -f data/raw/schema.sql

psql_db teste_legado_conflito <<'SQL'
INSERT INTO precatorio (numero_processo, ente_devedor, valor_face) VALUES
    ('00123451020198260053', 'Município de São Paulo', 45000.00);

INSERT INTO pagamento (precatorio_id, evento_id, tipo, valor, pago_em, criado_em) VALUES
    (1, 'ev-001', 'pagamento', 15000.00, '2025-03-10', '2025-03-10T10:00:00-03:00'),
    (1, 'ev-001', 'pagamento', 15500.00, '2025-03-10', '2025-03-11T09:00:00-03:00');
SQL

if psql_db teste_legado_conflito -f sql/migrations/001_prevencao_integridade.sql >/dev/null 2>&1; then
    echo "Erro: migração deveria abortar diante de duplicata legada divergente." >&2
    exit 1
fi

psql_db teste_legado_conflito <<'SQL'
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_count FROM pagamento WHERE evento_id = 'ev-001';
    IF v_count <> 2 THEN
        RAISE EXCEPTION 'Rollback atômico falhou: esperadas 2 linhas intactas, obtidas %', v_count;
    END IF;
END $$;
SQL
echo "[OK] Cenário 3: duplicata legada divergente aborta a migração com rollback atômico"
echo "Validação concluída com sucesso em PostgreSQL ($IMAGEM)."
