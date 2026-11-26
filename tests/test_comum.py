from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from bzr_group_case.comum import (
    DIRETORIO_DADOS,
    DIRETORIO_SAIDA,
    FUSO_BRASILIA,
    PADRAO_CNJ,
    PADRAO_DATA_ISO,
    PADRAO_INSTANTE_ISO_PREFIXO,
    RAIZ_PROJETO,
    calcular_prazo_constitucional,
    chave_texto_normalizada,
    converter_instante_iso,
    extrair_data_civil_brasilia,
    extrair_digitos_cnj,
    rotulo_arquivo,
)


def test_caminhos_fuso_e_padroes_compartilhados(tmp_path: Path) -> None:
    assert (RAIZ_PROJETO / "pyproject.toml").is_file()
    assert DIRETORIO_DADOS == RAIZ_PROJETO / "data" / "raw"
    assert DIRETORIO_SAIDA == RAIZ_PROJETO / "data" / "clean"
    assert isinstance(FUSO_BRASILIA, ZoneInfo)
    assert FUSO_BRASILIA.key == "America/Sao_Paulo"

    assert rotulo_arquivo(DIRETORIO_DADOS / "hub.csv") == "data/raw/hub.csv"
    caminho_externo = tmp_path / "fora.csv"
    assert rotulo_arquivo(caminho_externo) == str(caminho_externo)

    assert PADRAO_CNJ.fullmatch("0012345-10.2019.8.26.0053") is not None
    assert PADRAO_CNJ.fullmatch("00123451020198260053") is None
    assert PADRAO_DATA_ISO.fullmatch("2025-04-02") is not None
    assert PADRAO_DATA_ISO.fullmatch("2025-4-2") is None
    assert PADRAO_INSTANTE_ISO_PREFIXO.match("2025-04-03T01:00:00Z") is not None
    assert PADRAO_INSTANTE_ISO_PREFIXO.match("2025-04-03") is None


def test_extrair_digitos_cnj_e_chave_texto_normalizada() -> None:
    assert extrair_digitos_cnj("0012345-10.2019.8.26.0053") == "00123451020198260053"
    assert extrair_digitos_cnj("abc-00123\u0660") == "00123"

    assert chave_texto_normalizada("Município de São Paulo") == "municipio de sao paulo"
    assert (
        chave_texto_normalizada("  MUNICIPIO   DE\tSAO\nPAULO ")
        == "municipio de sao paulo"
    )
    assert chave_texto_normalizada("União") == "uniao"


def test_converter_instante_iso() -> None:
    instante_z = converter_instante_iso("2025-04-03T01:00:00Z")
    assert instante_z == datetime(2025, 4, 3, 1, 0, 0, tzinfo=timezone.utc)

    instante_z_min = converter_instante_iso(" 2025-04-03t01:00:00z ")
    assert instante_z_min == datetime(2025, 4, 3, 1, 0, 0, tzinfo=timezone.utc)

    instante_offset = converter_instante_iso("2025-04-02 23:30:00-03:00")
    assert instante_offset is not None
    assert instante_offset.astimezone(FUSO_BRASILIA).date() == date(2025, 4, 2)

    instante_naive = converter_instante_iso("2025-04-02T12:00:00")
    assert instante_naive == datetime(2025, 4, 2, 12, 0, 0, tzinfo=FUSO_BRASILIA)

    for invalido in (
        None,
        12345,
        "",
        "   ",
        "2025-04-02",
        "2025-04-02Z",
        "2025-04-02z",
        "2025-04-02X10:00:00Z",
        "2025-02-30T10:00:00Z",
    ):
        assert converter_instante_iso(invalido) is None


@pytest.mark.parametrize(
    ("apresentado_em", "data_civil_esperada", "prazo_esperado"),
    [
        ("2025-04-02", date(2025, 4, 2), date(2026, 12, 31)),
        (" 2025-04-02 ", date(2025, 4, 2), date(2026, 12, 31)),
        ("2025-04-02T12:00:00", date(2025, 4, 2), date(2026, 12, 31)),
        ("2025-04-02T23:30:00-03:00", date(2025, 4, 2), date(2026, 12, 31)),
        ("2025-04-03T01:00:00Z", date(2025, 4, 2), date(2026, 12, 31)),
        (" 2025-04-03T01:00:00z ", date(2025, 4, 2), date(2026, 12, 31)),
        ("2025-04-03T02:59:59Z", date(2025, 4, 2), date(2026, 12, 31)),
        ("2025-04-03T04:00:00+02:00", date(2025, 4, 2), date(2026, 12, 31)),
        ("2025-04-03T03:00:00Z", date(2025, 4, 3), date(2027, 12, 31)),
        ("2025-04-03T03:00:00z", date(2025, 4, 3), date(2027, 12, 31)),
        ("2025-04-03", date(2025, 4, 3), date(2027, 12, 31)),
        ("2024-02-29", date(2024, 2, 29), date(2025, 12, 31)),
        ("2023-12-31", date(2023, 12, 31), date(2025, 12, 31)),
        # Em janeiro de 2018 havia horário de verão (UTC-2 em America/Sao_Paulo).
        ("2018-01-01T02:30:00Z", date(2018, 1, 1), date(2019, 12, 31)),
        ("2018-01-01T01:30:00Z", date(2017, 12, 31), date(2019, 12, 31)),
    ],
)
def test_extrair_data_civil_e_calcular_prazo_constitucional(
    apresentado_em: str,
    data_civil_esperada: date,
    prazo_esperado: date,
) -> None:
    assert extrair_data_civil_brasilia(apresentado_em) == data_civil_esperada
    assert calcular_prazo_constitucional(apresentado_em) == (
        data_civil_esperada,
        prazo_esperado,
    )


@pytest.mark.parametrize(
    "entrada_invalida",
    ["", "   ", "2025-04-02Z", "2025-02-29", "2025-02-30", "data-invalida"],
)
def test_extrair_data_civil_e_prazo_rejeitam_invalidos(entrada_invalida: str) -> None:
    with pytest.raises(ValueError):
        extrair_data_civil_brasilia(entrada_invalida)
    with pytest.raises(ValueError):
        calcular_prazo_constitucional(entrada_invalida)
