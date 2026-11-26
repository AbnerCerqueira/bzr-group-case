from datetime import date
from decimal import Decimal

import pytest

from bzr_group_case.limpeza.entrada.normalizacao import (
    DUAS_CASAS,
    converter_data_pagamento,
    converter_valor_monetario,
    formatar_cnj,
    normalizar_cnj,
)


def test_constantes_normalizacao() -> None:
    assert isinstance(DUAS_CASAS, Decimal)
    assert Decimal("0.01") == DUAS_CASAS


def test_cnj_formatacao_e_normalizacao() -> None:
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
