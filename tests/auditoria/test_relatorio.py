import json
import re
from pathlib import Path

from bzr_group_case.auditoria import (
    ResultadoValidacao,
    executar_auditoria,
    formatar_relatorio,
    formatar_relatorio_html,
    salvar_relatorio_html,
)
from bzr_group_case.auditoria.conciliacao import (
    ORIGEM_CONCILIACAO_APRESENTACOES,
    ORIGEM_CONCILIACAO_CADASTRO,
)
from bzr_group_case.auditoria.documentacao_tribunal import (
    ORIGEM_DOC_PAGAMENTOS,
    ORIGEM_DOC_TRIBUNAL,
)
from bzr_group_case.auditoria.enunciado import ORIGEM_ENUNCIADO
from bzr_group_case.auditoria.schema_banco import ORIGEM_SCHEMA


def test_executar_auditoria_nos_dados_reais_do_case() -> None:
    resultados = executar_auditoria()
    por_chave = {(r.origem, r.validacao, r.arquivo): r for r in resultados}

    assert len(resultados) == 23

    # Origem: DOCUMENTACAO_TRIBUNAL.md (pagamentos.json)
    assert (
        por_chave[
            (
                ORIGEM_DOC_PAGAMENTOS,
                "Estrutura: lista de objetos em JSON",
                "data/pagamentos.json",
            )
        ].ok
        is True
    )
    assert por_chave[
        (ORIGEM_DOC_PAGAMENTOS, "evento_id: texto único", "data/pagamentos.json")
    ].evidencias == [
        "Item 4: evento_id repetido 'ev-002' (primeira ocorrência no item 2) "
        "— registro idêntico",
        "Item 9: evento_id repetido 'ev-001' (primeira ocorrência no item 1) "
        "— campos divergentes (atualizado_em: '2025-03-10T10:00:00-03:00' -> "
        "'2025-03-11T09:00:00-03:00'; valor: 15000.0 -> 15500.0)",
    ]
    assert por_chave[
        (
            ORIGEM_DOC_PAGAMENTOS,
            "processo: formato CNJ (NNNNNNN-DD.AAAA.J.TR.OOOO)",
            "data/pagamentos.json",
        )
    ].evidencias == [
        "Item 6 (ev-005): encontrado '00234562120208260053'",
        "Item 12 (ev-010): encontrado ''",
    ]
    assert por_chave[
        (ORIGEM_DOC_PAGAMENTOS, "valor: número", "data/pagamentos.json")
    ].evidencias == [
        "Item 2 (ev-002): encontrado '2.500,50' (tipo str)",
        "Item 4 (ev-002): encontrado '2.500,50' (tipo str)",
        "Item 5 (ev-004): encontrado None (tipo NoneType)",
    ]
    assert por_chave[
        (
            ORIGEM_DOC_PAGAMENTOS,
            "data_pagamento: formato AAAA-MM-DD",
            "data/pagamentos.json",
        )
    ].evidencias == [
        "Item 2 (ev-002): encontrado '10/04/2025'",
        "Item 4 (ev-002): encontrado '10/04/2025'",
    ]
    assert por_chave[
        (ORIGEM_DOC_PAGAMENTOS, "tipo: sempre 'pagamento'", "data/pagamentos.json")
    ].evidencias == [
        "Item 8 (ev-007): esperado 'pagamento', encontrado 'estorno'",
    ]
    assert (
        por_chave[
            (
                ORIGEM_DOC_PAGAMENTOS,
                "atualizado_em: data e hora válida",
                "data/pagamentos.json",
            )
        ].ok
        is True
    )

    # Origem: DOCUMENTACAO_TRIBUNAL.md (tribunal.csv)
    assert [
        ev.split(":")[0]
        for ev in por_chave[
            (ORIGEM_DOC_TRIBUNAL, "Codificação UTF-8", "data/tribunal.csv")
        ].evidencias
    ] == ["Linha 2", "Linha 3", "Linha 4", "Linha 5", "Linha 6"]
    assert por_chave[
        (
            ORIGEM_DOC_TRIBUNAL,
            "Delimitador vírgula (',') e colunas esperadas",
            "data/tribunal.csv",
        )
    ].evidencias == [
        "Esperado  : ['numero_processo', 'ente_devedor', 'valor_face']",
        "Encontrado: ['numero_processo;ente_devedor;valor_face']",
    ]
    assert por_chave[
        (
            ORIGEM_DOC_TRIBUNAL,
            "valor_face: número com ponto decimal",
            "data/tribunal.csv",
        )
    ].evidencias == [
        "Linha 2: encontrado '45.000,00'",
        "Linha 3: encontrado '30.000,00'",
        "Linha 4: encontrado '12.500,00'",
        "Linha 5: encontrado '9.800,00'",
        "Linha 6: encontrado '7.000,00'",
    ]

    # Origem: schema.sql
    assert (
        len(
            por_chave[
                (
                    ORIGEM_SCHEMA,
                    "precatorio.numero_processo: até 20 caracteres (CHAR(20))",
                    "data/tribunal.csv",
                )
            ].evidencias
        )
        == 5
    )
    assert (
        len(
            por_chave[
                (
                    ORIGEM_SCHEMA,
                    "precatorio.numero_processo: até 20 caracteres (CHAR(20))",
                    "data/hub.csv",
                )
            ].evidencias
        )
        == 4
    )
    assert por_chave[
        (ORIGEM_SCHEMA, "pagamento.valor: CHECK (valor > 0)", "data/pagamentos.json")
    ].evidencias == ["Item 11 (ev-009): encontrado -200 (esperado > 0)"]
    assert (
        por_chave[
            (
                ORIGEM_SCHEMA,
                "pagamento.tipo: CHECK (tipo IN ('pagamento', 'estorno'))",
                "data/pagamentos.json",
            )
        ].ok
        is True
    )
    assert por_chave[
        (
            ORIGEM_SCHEMA,
            "pagamento.precatorio_id: processo existente na base interna",
            "data/pagamentos.json",
        )
    ].evidencias == [
        "Item 12 (ev-010): processo '' não encontrado em data/hub.csv",
        "Item 13 (ev-011): processo '0067890-65.2016.8.26.0053' "
        "não encontrado em data/hub.csv",
    ]

    # Origem: docs/ENUNCIADO.md
    assert por_chave[
        (
            ORIGEM_ENUNCIADO,
            "Regra constitucional de prazo_pagamento (corte em 02/04, BRT)",
            "data/hub.csv",
        )
    ].evidencias == [
        "Linha 2 (0012345-10.2019.8.26.0053): apresentado_em='2025-04-02' "
        "(data BRT: 2025-04-02) -> esperado '2026-12-31', encontrado '2027-12-31'",
        "Linha 6 (0056789-54.2017.4.03.6100): apresentado_em='2025-04-03T01:00:00Z' "
        "(data BRT: 2025-04-02) -> esperado '2026-12-31', encontrado '2027-12-31'",
    ]

    # Origem: Conciliação (tribunal.csv x hub.csv)
    par_cadastro = "data/tribunal.csv x data/hub.csv"
    assert por_chave[
        (
            ORIGEM_CONCILIACAO_CADASTRO,
            "Cobertura de processos (presença nas duas bases)",
            par_cadastro,
        )
    ].evidencias == [
        "Processo '0067890-65.2016.8.26.0053' (linha 6 de data/tribunal.csv): "
        "ausente em data/hub.csv",
        "Processo '0056789-54.2017.4.03.6100' (linha 6 de data/hub.csv): "
        "ausente em data/tribunal.csv",
    ]
    assert por_chave[
        (
            ORIGEM_CONCILIACAO_CADASTRO,
            "Formato do número do processo entre bases",
            par_cadastro,
        )
    ].evidencias == [
        "tribunal (linha 3)='0023456-21.2020.8.26.0053' vs "
        "hub (linha 3)='00234562120208260053'"
    ]
    assert por_chave[
        (ORIGEM_CONCILIACAO_CADASTRO, "Ente devedor entre bases", par_cadastro)
    ].evidencias == [
        "0012345-10.2019.8.26.0053 (tribunal L2 x hub L2): "
        "tribunal='Município de São Paulo' vs hub='MUNICIPIO DE SAO PAULO' "
        "(mesmo texto sem acento/caixa)",
        "0045678-43.2021.5.02.0011 (tribunal L5 x hub L5): "
        "tribunal='União' vs hub='Município de Santos' "
        "(textos diferentes mesmo sem acento/caixa)",
    ]
    assert por_chave[
        (ORIGEM_CONCILIACAO_CADASTRO, "Valor de face entre bases", par_cadastro)
    ].evidencias == [
        "0023456-21.2020.8.26.0053 (tribunal L3 x hub L3): "
        "tribunal=30000.00 vs hub=31000.00 (diferença hub - tribunal: +1000.00)"
    ]

    # Origem: Conciliação (apresentacoes.json x hub.csv)
    assert por_chave[
        (
            ORIGEM_CONCILIACAO_APRESENTACOES,
            "Cobertura e datas de apresentação entre bases",
            "data/apresentacoes.json x data/hub.csv",
        )
    ].evidencias == [
        "Item 6 (0067890-65.2016.8.26.0053): apresentado_em='2023-12-31' "
        "ausente em data/hub.csv"
    ]


def test_formatar_relatorio_agrupa_todas_as_origens() -> None:
    relatorio = formatar_relatorio(executar_auditoria())

    assert f"Origem: {ORIGEM_DOC_PAGAMENTOS}" in relatorio
    assert f"Origem: {ORIGEM_DOC_TRIBUNAL}" in relatorio
    assert f"Origem: {ORIGEM_SCHEMA}" in relatorio
    assert f"Origem: {ORIGEM_ENUNCIADO}" in relatorio
    assert f"Origem: {ORIGEM_CONCILIACAO_CADASTRO}" in relatorio
    assert f"Origem: {ORIGEM_CONCILIACAO_APRESENTACOES}" in relatorio
    assert "  [OK] " in relatorio
    assert "  [FALHA] " in relatorio
    assert "[FALHA | " not in relatorio
    assert "Resumo: 23 validação(ões) | 5 OK | 18 FALHA\n" in relatorio


def test_formatar_e_salvar_relatorio_html(tmp_path: Path) -> None:
    resultados = executar_auditoria()
    html = formatar_relatorio_html(resultados)

    assert html.lstrip().lower().startswith("<!doctype html>")
    assert "__DATA__" not in html
    assert html.count("</script>") == 1
    assert "Validações e evidências" in html
    assert "Evidências por contrato / origem" in html
    assert "Evidências por arquivo / comparação" not in html
    assert "ordenadas pelo nome do arquivo" in html
    assert 'type="search"' in html
    assert "criticidade" not in html.lower()
    assert "severidade" not in html.lower()

    embutido = re.search(r"const D = (.*?);\nconst R =", html, re.S)
    assert embutido is not None
    dados = json.loads(embutido.group(1))
    assert dados["resumo"] == {
        "total_validacoes": 23,
        "ok": 5,
        "falhas": 18,
        "total_evidencias": sum(len(r.evidencias) for r in resultados),
    }
    assert all("severidade" not in item for item in dados["resultados"])

    destino = salvar_relatorio_html(resultados, tmp_path / "auditoria.html")
    assert destino.read_text(encoding="utf-8") == html


def test_formatar_relatorio_html_escapa_fechamento_de_script() -> None:
    html = formatar_relatorio_html(
        [
            ResultadoValidacao(
                origem="teste",
                validacao="regra",
                arquivo="data/teste.csv",
                evidencias=["valor suspeito </script><script>alert(1)</script>"],
            )
        ]
    )
    assert html.count("</script>") == 1
