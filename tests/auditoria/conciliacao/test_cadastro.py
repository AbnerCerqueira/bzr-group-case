from pathlib import Path

from bzr_group_case.auditoria.conciliacao.cadastro import (
    ORIGEM_CONCILIACAO_CADASTRO,
    validar_cobertura_processos,
    validar_ente_devedor_entre_bases,
    validar_formato_chave_entre_bases,
    validar_valor_face_entre_bases,
)


def _criar_bases_exemplo(tmp_path: Path) -> tuple[Path, Path]:
    tribunal = tmp_path / "tribunal.csv"
    tribunal.write_bytes(
        (
            "numero_processo;ente_devedor;valor_face\r\n"
            "0012345-10.2019.8.26.0053;Município de São Paulo;45.000,00\r\n"
            "0023456-21.2020.8.26.0053;Município de São Paulo;30.000,00\r\n"
            "0045678-43.2021.5.02.0011;União;9.800,00\r\n"
            "0067890-65.2016.8.26.0053;Município de São Paulo;7.000,00\r\n"
        ).encode("cp1252")
    )
    hub = tmp_path / "hub.csv"
    linhas_hub = [
        "processo,ente,valor_face,apresentado_em,prazo_pagamento",
        (
            "0012345-10.2019.8.26.0053,MUNICIPIO DE SAO PAULO,"
            "45000.00,2025-04-02,2027-12-31"
        ),
        "00234562120208260053,Município de São Paulo,31000.00,2025-04-03,2027-12-31",
        "0045678-43.2021.5.02.0011,Município de Santos,9800.00,2025-04-02,2026-12-31",
        "0056789-54.2017.4.03.6100,Estado de São Paulo,22000.00,2025-04-03,2027-12-31",
    ]
    hub.write_text("\n".join(linhas_hub) + "\n", encoding="utf-8")
    return tribunal, hub


def test_validar_cobertura_processos(tmp_path: Path) -> None:
    tribunal, hub = _criar_bases_exemplo(tmp_path)

    resultado = validar_cobertura_processos(tribunal, hub)

    assert resultado.origem == ORIGEM_CONCILIACAO_CADASTRO
    assert len(resultado.evidencias) == 2
    assert "0067890-65.2016.8.26.0053" in resultado.evidencias[0]
    assert "0056789-54.2017.4.03.6100" in resultado.evidencias[1]


def test_validar_formato_chave_entre_bases(tmp_path: Path) -> None:
    tribunal, hub = _criar_bases_exemplo(tmp_path)

    resultado = validar_formato_chave_entre_bases(tribunal, hub)

    assert resultado.evidencias == [
        "tribunal (linha 3)='0023456-21.2020.8.26.0053' vs "
        "hub (linha 3)='00234562120208260053'"
    ]


def test_validar_ente_devedor_entre_bases(tmp_path: Path) -> None:
    tribunal, hub = _criar_bases_exemplo(tmp_path)

    resultado = validar_ente_devedor_entre_bases(tribunal, hub)

    assert resultado.evidencias == [
        "0012345-10.2019.8.26.0053 (tribunal L2 x hub L2): "
        "tribunal='Município de São Paulo' vs hub='MUNICIPIO DE SAO PAULO' "
        "(mesmo texto sem acento/caixa)",
        "0045678-43.2021.5.02.0011 (tribunal L4 x hub L4): "
        "tribunal='União' vs hub='Município de Santos' "
        "(textos diferentes mesmo sem acento/caixa)",
    ]


def test_validar_valor_face_entre_bases_e_formatos_ambiguos(tmp_path: Path) -> None:
    tribunal = tmp_path / "tribunal.csv"
    tribunal.write_text(
        "numero_processo;ente_devedor;valor_face\n"
        "0012345-10.2019.8.26.0053;A;30.000,00\n"
        "0023456-21.2020.8.26.0053;B;10.000,50\n"
        "0034567-32.2018.8.26.0405;C;45,000.00\n"
        "0045678-43.2021.5.02.0011;D;NaN\n",
        encoding="utf-8",
    )
    hub = tmp_path / "hub.csv"
    hub.write_text(
        "processo,ente,valor_face\n"
        "0012345-10.2019.8.26.0053,A,31000.00\n"
        "0023456-21.2020.8.26.0053,B,9500.25\n"
        "0034567-32.2018.8.26.0405,C,45000.00\n"
        "0045678-43.2021.5.02.0011,D,100.00\n",
        encoding="utf-8",
    )

    resultado = validar_valor_face_entre_bases(tribunal, hub)

    assert resultado.evidencias == [
        "0012345-10.2019.8.26.0053 (tribunal L2 x hub L2): "
        "tribunal=30000.00 vs hub=31000.00 (diferença hub - tribunal: +1000.00)",
        "0023456-21.2020.8.26.0053 (tribunal L3 x hub L3): "
        "tribunal=10000.50 vs hub=9500.25 (diferença hub - tribunal: -500.25)",
        "0034567-32.2018.8.26.0405 (tribunal L4 x hub L4): "
        "valor não numérico (tribunal='45,000.00' vs hub='45000.00')",
        "0045678-43.2021.5.02.0011 (tribunal L5 x hub L5): "
        "valor não numérico (tribunal='NaN' vs hub='100.00')",
    ]
