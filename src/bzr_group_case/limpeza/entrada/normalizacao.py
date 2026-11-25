import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

FUSO_BRASILIA = ZoneInfo("America/Sao_Paulo")
DUAS_CASAS = Decimal("0.01")

_PADRAO_CNJ_DIGITOS = re.compile(r"^\d{20}$", re.ASCII)
_PADRAO_CNJ_FORMATADO = re.compile(
    r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$",
    re.ASCII,
)
_PADRAO_DECIMAL_PONTO = re.compile(r"^-?\d+(?:\.\d{1,2})?$", re.ASCII)
_PADRAO_DECIMAL_BR = re.compile(
    r"^-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{1,2}$",
    re.ASCII,
)
_PADRAO_DATA_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$", re.ASCII)
_PADRAO_DATA_BR = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$", re.ASCII)
_PADRAO_INSTANTE_ISO_PREFIXO = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}",
    re.ASCII,
)


def extrair_digitos_cnj(texto: str) -> str:
    """Extrai apenas dígitos ASCII de um número de processo."""
    return "".join(
        caractere for caractere in texto if caractere.isascii() and caractere.isdigit()
    )


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
    if _PADRAO_CNJ_FORMATADO.fullmatch(limpo):
        digitos = extrair_digitos_cnj(limpo)
        return digitos, limpo
    return None


def chave_texto_normalizada(texto: str) -> str:
    """Remove acentos via NFKD, colapsa espaços e aplica casefold."""
    decomposicao = unicodedata.normalize("NFKD", texto)
    sem_acentos = "".join(
        caractere for caractere in decomposicao if not unicodedata.combining(caractere)
    )
    return " ".join(sem_acentos.split()).casefold()


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
    casamento_iso = _PADRAO_DATA_ISO.fullmatch(texto)
    if casamento_iso is not None:
        ano, mes, dia = (
            int(casamento_iso.group(1)),
            int(casamento_iso.group(2)),
            int(casamento_iso.group(3)),
        )
        try:
            return date(ano, mes, dia), tinha_espacos
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


def converter_instante_iso(valor: Any) -> datetime | None:
    """Converte data/hora ISO com hora obrigatória para datetime ciente de fuso.

    Se a entrada vier sem fuso (naive), assume ``FUSO_BRASILIA`` no retorno.
    """
    if not isinstance(valor, str):
        return None

    texto = valor.strip()
    if not texto or _PADRAO_INSTANTE_ISO_PREFIXO.match(texto) is None:
        return None

    if texto.endswith(("Z", "z")):
        texto = f"{texto[:-1]}+00:00"

    try:
        instante = datetime.fromisoformat(texto)
    except ValueError:
        return None

    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=FUSO_BRASILIA)
    return instante


def extrair_data_civil_brasilia(apresentado_em: str) -> date:
    """Converte data ou data/hora ISO para a data civil no horário de Brasília."""
    if not isinstance(apresentado_em, str):
        raise ValueError(f"Data/hora de apresentação inválida: {apresentado_em!r}")

    texto = apresentado_em.strip()
    if _PADRAO_DATA_ISO.fullmatch(texto) is not None:
        return date.fromisoformat(texto)

    instante = converter_instante_iso(texto)
    if instante is None:
        raise ValueError(f"Data/hora de apresentação inválida: {apresentado_em!r}")

    return instante.astimezone(FUSO_BRASILIA).date()


def calcular_prazo_constitucional(apresentado_em: str) -> tuple[date, date]:
    """Calcula (data_civil_brasilia, data_prazo) com corte inclusivo em 02/04."""
    data_civil = extrair_data_civil_brasilia(apresentado_em)
    ate_2_de_abril = (data_civil.month, data_civil.day) <= (4, 2)
    ano_prazo = data_civil.year + 1 if ate_2_de_abril else data_civil.year + 2
    return data_civil, date(ano_prazo, 12, 31)
