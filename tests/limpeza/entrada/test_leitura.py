import hashlib
from decimal import Decimal
from pathlib import Path

import pytest

from bzr_group_case.limpeza.entrada.leitura import (
    DIRETORIO_DADOS,
    carregar_dados_brutos,
)

ARQUIVOS_ENTRADA = (
    "tribunal.csv",
    "hub.csv",
    "apresentacoes.json",
    "pagamentos.json",
)


def _hashes_arquivos(diretorio: Path) -> dict[str, str]:
    return {
        nome: hashlib.sha256((diretorio / nome).read_bytes()).hexdigest()
        for nome in ARQUIVOS_ENTRADA
    }


def test_carregar_dados_brutos_reais_contagens_p3_decimal_e_imutabilidade() -> None:
    hashes_antes = _hashes_arquivos(DIRETORIO_DADOS)

    dados = carregar_dados_brutos(DIRETORIO_DADOS)

    hashes_depois = _hashes_arquivos(DIRETORIO_DADOS)
    assert hashes_depois == hashes_antes

    assert len(dados.tribunal) == 5
    assert len(dados.hub) == 5
    assert len(dados.apresentacoes) == 6
    assert len(dados.pagamentos) == 13

    # Preservação de números de linha (base 2) e acentuação decodificada de cp1252.
    assert [num for num, _ in dados.tribunal] == [2, 3, 4, 5, 6]
    assert dados.tribunal[0][1]["ente_devedor"] == "Município de São Paulo"
    assert [num for num, _ in dados.hub] == [2, 3, 4, 5, 6]

    # Ocorrências P3 de encoding e delimitador em tribunal.csv.
    assert len(dados.ocorrencias_leitura) == 2
    resumo_ocorrencias = {
        (
            oc.problema,
            oc.categoria,
            oc.entidade,
            oc.origem,
            oc.campo,
            oc.valor_original,
            oc.valor_tratado,
        )
        for oc in dados.ocorrencias_leitura
    }
    assert resumo_ocorrencias == {
        ("P3", "corrigido", "arquivo", "tribunal.csv", "encoding", "cp1252", "utf-8"),
        ("P3", "corrigido", "arquivo", "tribunal.csv", "delimitador", ";", ","),
    }
    assert all(oc.motivo for oc in dados.ocorrencias_leitura)

    # Verifica parse_float=Decimal nos itens de pagamentos.json.
    primeiro_pagamento = dados.pagamentos[0][1]
    assert primeiro_pagamento["evento_id"] == "ev-001"
    assert isinstance(primeiro_pagamento["valor"], Decimal)
    assert primeiro_pagamento["valor"] == Decimal("15000.0")


def test_carregar_dados_brutos_descarta_item_json_nao_objeto_e_trata_coluna_extra(
    tmp_path: Path,
) -> None:
    (tmp_path / "tribunal.csv").write_text(
        "numero_processo,ente_devedor,valor_face\n"
        "0012345-10.2019.8.26.0053,Ente A,100.00,extra1,extra2\n",
        encoding="utf-8",
    )
    (tmp_path / "hub.csv").write_text(
        "processo,ente,valor_face,apresentado_em,prazo_pagamento\n"
        "0012345-10.2019.8.26.0053,Ente A,100.00,2025-04-02,2026-12-31\n",
        encoding="utf-8",
    )
    (tmp_path / "apresentacoes.json").write_text(
        '[{"processo": "0012345-10.2019.8.26.0053", '
        '"apresentado_em": "2025-04-02"}, "invalido"]',
        encoding="utf-8",
    )
    (tmp_path / "pagamentos.json").write_text(
        '[{"evento_id": "ev-1", "valor": 10.5}, 123, null]',
        encoding="utf-8",
    )

    dados = carregar_dados_brutos(tmp_path)

    assert len(dados.tribunal) == 1
    assert dados.tribunal[0] == (
        2,
        {
            "numero_processo": "0012345-10.2019.8.26.0053",
            "ente_devedor": "Ente A",
            "valor_face": "100.00",
        },
    )
    assert len(dados.apresentacoes) == 1
    assert len(dados.pagamentos) == 1
    assert isinstance(dados.pagamentos[0][1]["valor"], Decimal)

    descartados = [
        oc for oc in dados.ocorrencias_leitura if oc.categoria == "descartado"
    ]
    assert len(descartados) == 4
    assert all(oc.problema == "P3" for oc in descartados)
    assert {(oc.origem, oc.campo) for oc in descartados} == {
        ("tribunal.csv", "colunas_extras"),
        ("apresentacoes.json", "item"),
        ("pagamentos.json", "item"),
    }


def test_carregar_dados_brutos_rejeita_json_raiz_nao_lista(tmp_path: Path) -> None:
    (tmp_path / "tribunal.csv").write_text(
        "numero_processo,ente_devedor,valor_face\n",
        encoding="utf-8",
    )
    (tmp_path / "hub.csv").write_text(
        "processo,ente,valor_face,apresentado_em,prazo_pagamento\n",
        encoding="utf-8",
    )
    (tmp_path / "apresentacoes.json").write_text('{"invalido": true}', encoding="utf-8")
    (tmp_path / "pagamentos.json").write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="Raiz JSON inválida"):
        carregar_dados_brutos(tmp_path)


def test_carregar_dados_brutos_preserva_linha_fisica_trata_bom_e_anomalias_csv(
    tmp_path: Path,
) -> None:
    # tribunal.csv com BOM UTF-8, linha em branco, linha só espaços, coluna faltante
    # e delimitador sobrando no cabeçalho.
    (tmp_path / "tribunal.csv").write_bytes(
        (
            "numero_processo,ente_devedor,valor_face,\n"
            "0012345-10.2019.8.26.0053,Ente A,100.00,sobra\n"
            "\n"
            "   \n"
            "0023456-21.2020.8.26.0053,Ente B\n"
        ).encode("utf-8-sig")
    )
    # hub.csv salvo em cp1252 com ';'
    (tmp_path / "hub.csv").write_bytes(
        (
            "processo;ente;valor_face;apresentado_em;prazo_pagamento\n"
            "0012345-10.2019.8.26.0053;Município de São Paulo;"
            "100.00;2025-04-02;2026-12-31\n"
        ).encode("cp1252")
    )
    # JSON com BOM UTF-8 e lista vazia
    (tmp_path / "apresentacoes.json").write_bytes("[]".encode("utf-8-sig"))
    (tmp_path / "pagamentos.json").write_bytes("[]".encode("utf-8-sig"))

    dados = carregar_dados_brutos(tmp_path)

    # Linha 2 e linha física 5 (após linha em branco 3 e linha de espaços 4).
    assert [num for num, _ in dados.tribunal] == [2, 5]
    assert dados.tribunal[1][1]["valor_face"] == ""
    assert dados.hub[0][1]["ente"] == "Município de São Paulo"

    campos_por_origem = {
        (oc.origem, oc.campo, oc.categoria) for oc in dados.ocorrencias_leitura
    }
    assert ("tribunal.csv", "coluna_sem_cabecalho", "descartado") in campos_por_origem
    assert ("tribunal.csv", "linha_vazia", "descartado") in campos_por_origem
    assert ("tribunal.csv", "colunas_faltantes", "em_duvida") in campos_por_origem
    assert ("hub.csv", "encoding", "corrigido") in campos_por_origem
    assert ("hub.csv", "delimitador", "corrigido") in campos_por_origem


def test_carregar_dados_brutos_rejeita_json_malformado_e_constante_nan(
    tmp_path: Path,
) -> None:
    (tmp_path / "tribunal.csv").write_text(
        "numero_processo,ente_devedor,valor_face\n",
        encoding="utf-8",
    )
    (tmp_path / "hub.csv").write_text(
        "processo,ente,valor_face,apresentado_em,prazo_pagamento\n",
        encoding="utf-8",
    )
    (tmp_path / "apresentacoes.json").write_text("[]", encoding="utf-8")
    (tmp_path / "pagamentos.json").write_text('[{"valor": NaN}]', encoding="utf-8")

    with pytest.raises(ValueError, match="RFC 8259"):
        carregar_dados_brutos(tmp_path)

    (tmp_path / "pagamentos.json").write_text("[{", encoding="utf-8")
    with pytest.raises(ValueError):
        carregar_dados_brutos(tmp_path)
