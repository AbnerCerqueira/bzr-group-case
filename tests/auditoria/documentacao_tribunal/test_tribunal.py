from pathlib import Path

from bzr_group_case.auditoria.documentacao_tribunal.tribunal import (
    ORIGEM_DOC_TRIBUNAL,
    validar_codificacao_utf8,
    validar_delimitador_e_colunas,
    validar_ente_devedor_csv,
    validar_processo_cnj_csv,
    validar_valor_face_decimal_csv,
)


def test_validar_codificacao_utf8_valido_e_invalido(tmp_path: Path) -> None:
    valido = tmp_path / "valido.csv"
    valido.write_text(
        "numero_processo,ente_devedor,valor_face\n"
        "0012345-10.2019.8.26.0053,Município de São Paulo,45000.00\n",
        encoding="utf-8",
    )
    invalido = tmp_path / "invalido.csv"
    invalido.write_bytes(
        "numero_processo;ente_devedor;valor_face\n"
        "0012345-10.2019.8.26.0053;Município de São Paulo;45.000,00\n".encode("cp1252")
    )

    assert validar_codificacao_utf8(valido).ok is True

    res_invalido = validar_codificacao_utf8(invalido)
    assert res_invalido.ok is False
    assert res_invalido.origem == ORIGEM_DOC_TRIBUNAL
    assert len(res_invalido.evidencias) == 1
    assert res_invalido.evidencias[0].startswith("Linha 2: ")


def test_validar_delimitador_e_colunas_cabecalho_e_linhas(tmp_path: Path) -> None:
    valido = tmp_path / "valido.csv"
    valido.write_text(
        "numero_processo,ente_devedor,valor_face\n"
        "0012345-10.2019.8.26.0053,União,45000.00\n",
        encoding="utf-8",
    )
    ponto_virgula = tmp_path / "ponto_virgula.csv"
    ponto_virgula.write_text(
        "numero_processo;ente_devedor;valor_face\n", encoding="utf-8"
    )
    coluna_extra = tmp_path / "coluna_extra.csv"
    coluna_extra.write_text(
        "numero_processo,ente_devedor,valor_face\n"
        "0012345-10.2019.8.26.0053,União,45000.00,sobra\n",
        encoding="utf-8",
    )

    assert validar_delimitador_e_colunas(valido).ok is True
    assert validar_delimitador_e_colunas(ponto_virgula).evidencias == [
        "Esperado  : ['numero_processo', 'ente_devedor', 'valor_face']",
        "Encontrado: ['numero_processo;ente_devedor;valor_face']",
    ]
    assert validar_delimitador_e_colunas(coluna_extra).evidencias == [
        "Linha 2: esperadas 3 colunas, encontradas 4"
    ]


def test_validar_campos_csv_tribunal_com_virgula_e_ponto_e_virgula(
    tmp_path: Path,
) -> None:
    valido_virgula = tmp_path / "valido.csv"
    valido_virgula.write_text(
        "numero_processo,ente_devedor,valor_face\n"
        "0012345-10.2019.8.26.0053,União,45000.00\n",
        encoding="utf-8",
    )
    invalido_ponto_virgula = tmp_path / "invalido.csv"
    invalido_ponto_virgula.write_text(
        "numero_processo;ente_devedor;valor_face\n"
        "0012345-10.2019.8.26.0053;União;45000.00\n"
        "00234562120208260053; ;30.000,00\n",
        encoding="utf-8",
    )

    assert validar_processo_cnj_csv(valido_virgula).ok is True
    assert validar_ente_devedor_csv(valido_virgula).ok is True
    assert validar_valor_face_decimal_csv(valido_virgula).ok is True

    assert validar_processo_cnj_csv(invalido_ponto_virgula).evidencias == [
        "Linha 3: encontrado '00234562120208260053'"
    ]
    assert validar_ente_devedor_csv(invalido_ponto_virgula).evidencias == [
        "Linha 3: valor vazio"
    ]
    assert validar_valor_face_decimal_csv(invalido_ponto_virgula).evidencias == [
        "Linha 3: encontrado '30.000,00'"
    ]
