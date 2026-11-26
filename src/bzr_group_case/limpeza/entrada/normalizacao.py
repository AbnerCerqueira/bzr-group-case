import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from bzr_group_case.comum import (
    FUSO_BRASILIA,
    PADRAO_CNJ,
    PADRAO_DATA_ISO,
    calcular_prazo_constitucional,
    chave_texto_normalizada,
    converter_instante_iso,
    extrair_data_civil_brasilia,
    extrair_digitos_cnj,
)

DUAS_CASAS = Decimal("0.01")

_PADRAO_CNJ_DIGITOS = re.compile(r"^\d{20}$", re.ASCII)
_PADRAO_DECIMAL_PONTO = re.compile(r"^-?\d+(?:\.\d{1,2})?$", re.ASCII)
_PADRAO_DECIMAL_BR = re.compile(
    r"^-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{1,2}$",
    re.ASCII,
)
_PADRAO_DATA_BR = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$", re.ASCII)

__all__ = [
    "DUAS_CASAS",
    "FUSO_BRASILIA",
    "PADRAO_CNJ",
    "PADRAO_DATA_ISO",
    "calcular_prazo_constitucional",
    "chave_texto_normalizada",
    "converter_data_pagamento",
    "converter_instante_iso",
    "converter_valor_monetario",
    "extrair_data_civil_brasilia",
    "extrair_digitos_cnj",
    "formatar_cnj",
    "normalizar_cnj",
]


def formatar_cnj(digitos: str) -> str:
    """Formata 20 dígitos ASCII no padrão CNJ NNNNNNN-DD.AAAA.J.TR.OOOO."""
    if len(digitos) != 20 or not (digitos.isascii() and digitos.isdigit()):
        raise ValueError(
            f"Número CNJ deve conter exatamente 20 dígitos ASCII: {digitos!r}"
        )
    return (
        f"{digitos[0:7]}-{digitos[7:9]}.{digitos[9:13]}."
        f"{digitos[13:14]}.{digitos[14:16]}.{digitos[16:20]}"
    )


def normalizar_cnj(texto: Any) -> tuple[str, str] | None:
    """Valida e normaliza um número CNJ (20 dígitos puros ou máscara canônica)."""
    if not isinstance(texto, str):
        return None
    limpo = texto.strip()
    if _PADRAO_CNJ_DIGITOS.fullmatch(limpo):
        return limpo, formatar_cnj(limpo)
    if PADRAO_CNJ.fullmatch(limpo):
        digitos = extrair_digitos_cnj(limpo)
        return digitos, limpo
    return None


def _quantizar_duas_casas_exato(numero: Decimal) -> Decimal | None:
    """Converte Decimal finito para 2 casas sem permitir arredondamento silencioso."""
    if not numero.is_finite():
        return None
    try:
        quantizado = numero.quantize(DUAS_CASAS)
    except InvalidOperation:
        return None
    if quantizado != numero:
        return None
    if quantizado == 0:
        return Decimal("0.00")
    return quantizado


def converter_valor_monetario(valor: Any) -> tuple[Decimal | None, bool]:
    """Converte valor monetário para Decimal(2 casas) sem arredondar silenciosamente.

    Retorna (valor_quantizado, precisou_normalizar), sendo precisou_normalizar=True
    quando a entrada usou formato brasileiro ou tinha espaços nas pontas.
    """
    if valor is None or isinstance(valor, bool):
        return None, False

    if isinstance(valor, Decimal):
        return _quantizar_duas_casas_exato(valor), False

    if isinstance(valor, int):
        return _quantizar_duas_casas_exato(Decimal(valor)), False

    if isinstance(valor, float):
        try:
            numero = Decimal(str(valor))
        except InvalidOperation:
            return None, False
        return _quantizar_duas_casas_exato(numero), False

    if isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            return None, False
        tinha_espacos = texto != valor

        if _PADRAO_DECIMAL_PONTO.fullmatch(texto):
            try:
                numero = Decimal(texto)
            except InvalidOperation:
                return None, False
            quantizado = _quantizar_duas_casas_exato(numero)
            if quantizado is None:
                return None, False
            return quantizado, tinha_espacos

        if _PADRAO_DECIMAL_BR.fullmatch(texto):
            texto_normalizado = texto.replace(".", "").replace(",", ".")
            try:
                numero = Decimal(texto_normalizado)
            except InvalidOperation:
                return None, False
            quantizado = _quantizar_duas_casas_exato(numero)
            if quantizado is None:
                return None, False
            return quantizado, True

        return None, False

    return None, False


def converter_data_pagamento(valor: Any) -> tuple[date | None, bool]:
    """Converte data ISO (AAAA-MM-DD) ou brasileira (DD/MM/AAAA) válida.

    Retorna (data, precisou_normalizar), sendo precisou_normalizar=True quando
    a entrada veio em formato brasileiro ou com espaços/quebras nas extremidades.
    """
    if not isinstance(valor, str):
        return None, False

    texto = valor.strip()
    tinha_espacos = texto != valor
    if PADRAO_DATA_ISO.fullmatch(texto) is not None:
        try:
            return date.fromisoformat(texto), tinha_espacos
        except ValueError:
            return None, False

    casamento_br = _PADRAO_DATA_BR.fullmatch(texto)
    if casamento_br is not None:
        dia, mes, ano = (
            int(casamento_br.group(1)),
            int(casamento_br.group(2)),
            int(casamento_br.group(3)),
        )
        try:
            return date(ano, mes, dia), True
        except ValueError:
            return None, False

    return None, False
