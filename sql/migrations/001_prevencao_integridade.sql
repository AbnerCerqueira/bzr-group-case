-- =============================================================================
-- Migração 001: Prevenção de integridade, idempotência e quarentena
-- SGBD alvo   : PostgreSQL 14+
-- Schema base : data/raw/schema.sql
-- Referência  : docs/DIAGNOSTICO.md (problemas P1, P2, P3 e P4)
--
-- Notas operacionais para execução em produção:
--   1. Esta migração roda em uma transação única (BEGIN ... COMMIT). Se existir
--      algum registro legado inválido (ex.: numero_processo sem 20 dígitos,
--      valor_face <= 0 ou evento_id repetido com dados divergentes), o banco
--      aborta tudo sem deixar estado intermediário.
--   2. Em tabelas muito grandes com requisito de zero-downtime, pode-se aplicar
--      as constraints com NOT VALID + VALIDATE CONSTRAINT e criar índices com
--      CREATE INDEX CONCURRENTLY fora do bloco transacional.
--   3. Datas de apresentação sem horário (ex.: '2025-04-02') devem ser
--      normalizadas pelo importador no fuso America/Sao_Paulo antes do INSERT
--      (ex.: '2025-04-02T00:00:00-03:00') para evitar deslocamento de dia.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. Tabela precatorio: padronização de CNJ, apresentação, prazo e valor > 0
--    Endereça: P2 (prazo), P3 (CHAR(20) e colunas ausentes) e P4
-- -----------------------------------------------------------------------------

-- Troca CHAR(20) por VARCHAR(20), removendo espaços de preenchimento à direita.
ALTER TABLE precatorio
    ALTER COLUMN numero_processo TYPE VARCHAR(20)
    USING btrim(numero_processo);

-- Remove espaços supérfluos no nome do ente devedor antes da validação.
UPDATE precatorio
   SET ente_devedor = btrim(ente_devedor)
 WHERE ente_devedor <> btrim(ente_devedor);

-- Colunas de apresentação e prazo nascem anuláveis para permitir backfill
-- em bases já populadas; após a carga retroativa, aplicar SET NOT NULL.
ALTER TABLE precatorio
    ADD COLUMN apresentado_em  TIMESTAMPTZ,
    ADD COLUMN prazo_pagamento DATE;

ALTER TABLE precatorio
    ADD CONSTRAINT chk_precatorio_numero_processo_20_digitos
        CHECK (numero_processo ~ '^[0-9]{20}$'),
    ADD CONSTRAINT chk_precatorio_ente_devedor_nao_vazio
        CHECK (ente_devedor = btrim(ente_devedor) AND ente_devedor <> ''),
    ADD CONSTRAINT chk_precatorio_valor_face_positivo
        CHECK (valor_face > 0),
    -- Garante consistência estrutural entre apresentação e prazo: ambos nulos
    -- (no legado antes do backfill) ou ambos preenchidos com prazo posterior à
    -- data de apresentação em Brasília. A fórmula de corte constitucional
    -- (02/04) fica na aplicação, pois datas legais podem mudar sem invalidar
    -- registros históricos.
    ADD CONSTRAINT chk_precatorio_datas_prazo
        CHECK (
            (apresentado_em IS NULL AND prazo_pagamento IS NULL)
            OR (
                apresentado_em IS NOT NULL
                AND prazo_pagamento IS NOT NULL
                AND prazo_pagamento > (apresentado_em AT TIME ZONE 'America/Sao_Paulo')::DATE
            )
        );

-- -----------------------------------------------------------------------------
-- 2. Tabela pagamento: retificações, deduplicação legada, unicidade e índice FK
--    Endereça: P1 (duplicidade/retificações na janela de 7 dias e reexecuções)
-- -----------------------------------------------------------------------------

-- Adiciona atualizado_em sem DEFAULT now() para não mascarar ausências futuras
-- nem atribuir o instante da migração a registros históricos.
ALTER TABLE pagamento
    ADD COLUMN atualizado_em TIMESTAMPTZ;

-- Preenche o histórico legado a partir de criado_em antes de exigir NOT NULL.
UPDATE pagamento
   SET atualizado_em = criado_em
 WHERE atualizado_em IS NULL;

ALTER TABLE pagamento
    ALTER COLUMN atualizado_em SET NOT NULL;

-- Normaliza espaços laterais em evento_id antes da deduplicação e da trava UNIQUE.
UPDATE pagamento
   SET evento_id = btrim(evento_id)
 WHERE evento_id <> btrim(evento_id);

-- Saneamento defensivo apenas de duplicatas legadas estritamente idênticas:
-- agrupa pelas colunas de negócio e mantém apenas o registro de maior id.
-- Duplicatas com dados divergentes não são apagadas; nesse caso, a criação da
-- constraint UNIQUE abaixo aborta a transação inteira para revisão humana.
DELETE FROM pagamento
 WHERE id NOT IN (
     SELECT MAX(id)
       FROM pagamento
      GROUP BY precatorio_id, evento_id, tipo, valor, pago_em
 );

ALTER TABLE pagamento
    ADD CONSTRAINT chk_pagamento_evento_id_nao_vazio
        CHECK (evento_id = btrim(evento_id) AND evento_id <> ''),
    ADD CONSTRAINT uq_pagamento_evento_id
        UNIQUE (evento_id);

-- Índice na chave estrangeira para acelerar junções e cálculo de saldo.
CREATE INDEX idx_pagamento_precatorio_id
    ON pagamento (precatorio_id);

-- -----------------------------------------------------------------------------
-- 3. View de saldo líquido por precatório (pagamentos - estornos)
--    Endereça: P1 (fonte única de verdade), P2 (abatimento de estornos) e P3
-- -----------------------------------------------------------------------------

CREATE OR REPLACE VIEW vw_precatorio_saldo AS
SELECT
    p.id AS precatorio_id,
    p.numero_processo,
    substr(p.numero_processo, 1, 7)
        || '-' || substr(p.numero_processo, 8, 2)
        || '.' || substr(p.numero_processo, 10, 4)
        || '.' || substr(p.numero_processo, 14, 1)
        || '.' || substr(p.numero_processo, 15, 2)
        || '.' || substr(p.numero_processo, 17, 4) AS numero_processo_cnj,
    p.ente_devedor,
    p.valor_face,
    p.apresentado_em,
    p.prazo_pagamento,
    COALESCE(
        SUM(CASE WHEN pg.tipo = 'pagamento' THEN pg.valor ELSE 0 END),
        0
    )::NUMERIC(15,2) AS total_pagamentos,
    COALESCE(
        SUM(CASE WHEN pg.tipo = 'estorno' THEN pg.valor ELSE 0 END),
        0
    )::NUMERIC(15,2) AS total_estornos,
    COALESCE(
        SUM(
            CASE
                WHEN pg.tipo = 'pagamento' THEN pg.valor
                WHEN pg.tipo = 'estorno'   THEN -pg.valor
                ELSE 0
            END
        ),
        0
    )::NUMERIC(15,2) AS total_pago_liquido,
    (
        p.valor_face
        - COALESCE(
            SUM(
                CASE
                    WHEN pg.tipo = 'pagamento' THEN pg.valor
                    WHEN pg.tipo = 'estorno'   THEN -pg.valor
                    ELSE 0
                END
            ),
            0
        )
    )::NUMERIC(15,2) AS saldo_a_receber,
    COUNT(pg.id) AS qtd_eventos
FROM precatorio p
LEFT JOIN pagamento pg
       ON pg.precatorio_id = p.id
GROUP BY
    p.id,
    p.numero_processo,
    p.ente_devedor,
    p.valor_face,
    p.apresentado_em,
    p.prazo_pagamento;

-- -----------------------------------------------------------------------------
-- 4. Tabela de quarentena para eventos rejeitados sem descarte silencioso
--    Endereça: P1 (fim do descarte silencioso), P3 (dados inválidos) e P4 (órfãos)
-- -----------------------------------------------------------------------------

CREATE TABLE pagamento_rejeitado (
    id                     BIGSERIAL   PRIMARY KEY,
    evento_id              TEXT,
    processo_informado     TEXT,
    motivo_codigo          TEXT        NOT NULL CHECK (btrim(motivo_codigo) <> ''),
    motivo_detalhe         TEXT        NOT NULL CHECK (btrim(motivo_detalhe) <> ''),
    payload_original       JSONB       NOT NULL,
    payload_hash           TEXT        NOT NULL CHECK (btrim(payload_hash) <> ''),
    ocorrencias            INTEGER     NOT NULL DEFAULT 1 CHECK (ocorrencias >= 1),
    status                 TEXT        NOT NULL DEFAULT 'pendente'
        CHECK (status IN ('pendente', 'resolvido', 'descartado')),
    primeira_ocorrencia_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    ultima_ocorrencia_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    notificado_em          TIMESTAMPTZ,
    resolvido_em           TIMESTAMPTZ,
    CONSTRAINT chk_pagamento_rejeitado_datas
        CHECK (ultima_ocorrencia_em >= primeira_ocorrencia_em),
    CONSTRAINT chk_pagamento_rejeitado_resolucao
        CHECK (
            (status = 'pendente' AND resolvido_em IS NULL)
            OR (status <> 'pendente' AND resolvido_em IS NOT NULL)
        )
);

-- Evita registros e alertas duplicados enquanto o mesmo evento inválido se
-- repete na janela móvel de 7 dias, sem impedir novo registro se o problema
-- voltar após ter sido marcado como resolvido/descartado.
CREATE UNIQUE INDEX uq_pagamento_rejeitado_pendente
    ON pagamento_rejeitado (COALESCE(evento_id, ''), motivo_codigo, payload_hash)
    WHERE status = 'pendente';

COMMIT;

-- =============================================================================
-- Referência de uso no script de importação (não executado pela migração)
-- =============================================================================
--
-- 1) Carga idempotente de pagamento com suporte a retificação (ex.: ev-001):
--    Nota: o DO UPDATE abaixo pressupõe confirmação com o tribunal de que uma
--    versão mais recente do mesmo evento_id substitui a anterior (Dúvida #1).
--    Caso o tribunal defina outra política, conflitos de valor devem ser
--    encaminhados para pagamento_rejeitado em vez de sobrescritos.
--    INSERT INTO pagamento (
--        precatorio_id, evento_id, tipo, valor, pago_em, atualizado_em
--    )
--    VALUES ($1, $2, $3, $4, $5, $6)
--    ON CONFLICT (evento_id) DO UPDATE
--       SET precatorio_id = EXCLUDED.precatorio_id,
--           tipo          = EXCLUDED.tipo,
--           valor         = EXCLUDED.valor,
--           pago_em       = EXCLUDED.pago_em,
--           atualizado_em = EXCLUDED.atualizado_em
--     WHERE EXCLUDED.atualizado_em > pagamento.atualizado_em;
--
-- 2) Registro idempotente na quarentena sem gerar alertas repetidos em 7 dias:
--    INSERT INTO pagamento_rejeitado (
--        evento_id, processo_informado, motivo_codigo, motivo_detalhe,
--        payload_original, payload_hash
--    )
--    VALUES ($1, $2, $3, $4, $5, $6)
--    ON CONFLICT (COALESCE(evento_id, ''), motivo_codigo, payload_hash)
--        WHERE status = 'pendente'
--    DO UPDATE
--       SET ocorrencias          = pagamento_rejeitado.ocorrencias + 1,
--           ultima_ocorrencia_em = now();
-- =============================================================================
