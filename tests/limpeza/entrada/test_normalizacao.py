from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from bzr_group_case.limpeza.entrada.normalizacao import (
    DUAS_CASAS,
    FUSO_BRASILIA,
    calcular_prazo_constitucional,
    chave_texto_normalizada,
    converter_data_pagamento,
    converter_instante_iso,
    converter_valor_monetario,
    extrair_data_civil_brasilia,
    extrair_digitos_cnj,
    formatar_cnj,
    normalizar_cnj,
)


def test_constantes_normalizacao() -> None:
    assert isinstance(FUSO_BRASILIA, ZoneInfo)
    assert FUSO_BRASILIA.key == "America/Sao_Paulo"
    assert isinstance(DUAS_CASAS, Decimal)
    assert Decimal("0.01") == DUAS_CASAS


def test_cnj_extracao_formatacao_e_normalizacao() -> None:
    assert extrair_digitos_cnj("0012345-10.2019.8.26.0053") == "00123451020198260053"
    assert extrair_digitos_cnj("abc-00123\u0660") == "00123"

    assert formatar_cnj("00234562120208260053") == "0023456-21.2020.8.26.0053"
    with pytest.raises(ValueError):
        formatar_cnj("12345")
    with pytest.raises(ValueError):
        formatar_cnj("0023456212020826005\u0663")

    assert normalizar_cnj("0012345-10.2019.8.26.0053") == (
        "00123451020198260053",
        "0012345-10.2019.8.26.0053",
    )
    assert normalizar_cnj(" 00234562120208260053 ") == (
        "00234562120208260053",
        "0023456-21.2020.8.26.0053",
    )

    for invalido in (
        None,
        12345678901234567890,
        "",
        "   ",
        "0012345-10.2019.8.26.005",
        "0012345-10.2019.8.26.00539",
        "0012345-10.2019.8.26.0053X",
        "0012345/10.2019.8.26.0053",
        "0023456212020826005\u0663",
        "0012345--10..2019.8.26.0053",
        "0012345 10 2019 8 26 0053",
        "0012345\n1020198260053",
        "001234-510.2019.8.26.0053",
        "1234567890-1234567890",
    ):
        assert normalizar_cnj(invalido) is None


def test_chave_texto_normalizada() -> None:
    assert chave_texto_normalizada("Município de São Paulo") == "municipio de sao paulo"
    assert (
        chave_texto_normalizada("  MUNICIPIO   DE\tSAO\nPAULO ")
        == "municipio de sao paulo"
    )
    assert chave_texto_normalizada("União") == "uniao"


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("45.000,00", (Decimal("45000.00"), True)),
        ("2.500,50", (Decimal("2500.50"), True)),
        ("2500,50", (Decimal("2500.50"), True)),
        ("-2.500,5", (Decimal("-2500.50"), True)),
        (" 45.000,00 ", (Decimal("45000.00"), True)),
        ("31000.00", (Decimal("31000.00"), False)),
        (" 31000.00 ", (Decimal("31000.00"), True)),
        ("-200", (Decimal("-200.00"), False)),
        ("1200", (Decimal("1200.00"), False)),
        ("12.5", (Decimal("12.50"), False)),
        ("-0.00", (Decimal("0.00"), False)),
        (8000, (Decimal("8000.00"), False)),
        (-200, (Decimal("-200.00"), False)),
        (15000.0, (Decimal("15000.00"), False)),
        (12.55, (Decimal("12.55"), False)),
        (Decimal("15000.0"), (Decimal("15000.00"), False)),
        (Decimal("15000.000"), (Decimal("15000.00"), False)),
        (Decimal("1e2"), (Decimal("100.00"), False)),
        (Decimal("9800.00"), (Decimal("9800.00"), False)),
        (Decimal("-200"), (Decimal("-200.00"), False)),
        (Decimal("-0.00"), (Decimal("0.00"), False)),
    ],
)
def test_converter_valor_monetario_validos(
    entrada: object,
    esperado: tuple[Decimal, bool],
) -> None:
    valor, normalizado = converter_valor_monetario(entrada)
    assert (valor, normalizado) == esperado
    if valor == 0:
        assert not valor.is_signed()
        assert str(valor) == "0.00"


@pytest.mark.parametrize(
    "entrada_invalida",
    [
        None,
        True,
        False,
        "",
        "   ",
        float("nan"),
        float("inf"),
        float("-inf"),
        10.125,
        0.1 + 0.2,
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        Decimal("10.123"),
        "10.123",
        "10.000",
        "1.000",
        "+100.00",
        ".50",
        ",50",
        "2.500,505",
        "2.50,00",
        "R$ 2.500,50",
        "abc",
        [100],
    ],
)
def test_converter_valor_monetario_invalidos(entrada_invalida: object) -> None:
    assert converter_valor_monetario(entrada_invalida) == (None, False)


def test_converter_data_pagamento() -> None:
    assert converter_data_pagamento("2025-03-10") == (date(2025, 3, 10), False)
    assert converter_data_pagamento(" 2025-03-10 ") == (date(2025, 3, 10), True)
    assert converter_data_pagamento("2025-03-10\n") == (date(2025, 3, 10), True)
    assert converter_data_pagamento("10/04/2025") == (date(2025, 4, 10), True)
    assert converter_data_pagamento("29/02/2024") == (date(2024, 2, 29), True)

    for invalida in (
        None,
        20250310,
        "",
        "   ",
        "31/02/2025",
        "29/02/2025",
        "2025-02-30",
        "2025-3-1",
        "1/4/2025",
        "0000-01-01",
        "2025/03/10",
        "10-04-2025",
        "2025-03-10T10:00:00Z",
    ):
        assert converter_data_pagamento(invalida) == (None, False)


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
        ("2025-04-02T23:30:00-03:00", date(2025, 4, 2), date(2026, 12, 31)),
        ("2025-04-03T01:00:00Z", date(2025, 4, 2), date(2026, 12, 31)),
        ("2025-04-03T01:00:00z", date(2025, 4, 2), date(2026, 12, 31)),
        ("2025-04-03T02:59:59Z", date(2025, 4, 2), date(2026, 12, 31)),
        ("2025-04-03T00:30:00+02:00", date(2025, 4, 2), date(2026, 12, 31)),
        ("2025-04-03T03:00:00Z", date(2025, 4, 3), date(2027, 12, 31)),
        ("2025-04-03", date(2025, 4, 3), date(2027, 12, 31)),
        ("2024-02-29", date(2024, 2, 29), date(2025, 12, 31)),
        ("2023-12-31", date(2023, 12, 31), date(2025, 12, 31)),
        # Em janeiro de 2018 havia horário de verão (UTC-2 em America/Sao_Paulo).
        ("2018-01-01T02:30:00Z", date(2018, 1, 1), date(2019, 12, 31)),
        ("2018-01-01T01:30:00Z", date(2017, 12, 31), date(2019, 12, 31)),
    ],
)
def test_calcular_prazo_constitucional_casos_de_borda(
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
