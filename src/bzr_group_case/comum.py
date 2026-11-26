import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

RAIZ_PROJETO = Path(__file__).resolve().parents[2]
DIRETORIO_DADOS = RAIZ_PROJETO / "data" / "raw"
DIRETORIO_SAIDA = RAIZ_PROJETO / "data" / "clean"
FUSO_BRASILIA = ZoneInfo("America/Sao_Paulo")

PADRAO_CNJ = re.compile(r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$", re.ASCII)
PADRAO_DATA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$", re.ASCII)
PADRAO_INSTANTE_ISO_PREFIXO = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}",
    re.ASCII,
)

__all__ = [
    "DIRETORIO_DADOS",
    "DIRETORIO_SAIDA",
    "FUSO_BRASILIA",
    "PADRAO_CNJ",
    "PADRAO_DATA_ISO",
    "PADRAO_INSTANTE_ISO_PREFIXO",
    "RAIZ_PROJETO",
    "calcular_prazo_constitucional",
    "chave_texto_normalizada",
    "converter_instante_iso",
    "extrair_data_civil_brasilia",
    "extrair_digitos_cnj",
    "rotulo_arquivo",
]


def rotulo_arquivo(caminho: Path) -> str:
    """Retorna o caminho relativo à raiz do projeto em POSIX ou o caminho original."""
    try:
        return caminho.resolve().relative_to(RAIZ_PROJETO).as_posix()
    except ValueError:
        return str(caminho)


def extrair_digitos_cnj(texto: str) -> str:
    """Extrai apenas dígitos ASCII de um número de processo."""
    return "".join(
        caractere for caractere in texto if caractere.isascii() and caractere.isdigit()
    )


def chave_texto_normalizada(texto: str) -> str:
    """Remove acentos via NFKD, colapsa espaços e aplica casefold."""
    decomposicao = unicodedata.normalize("NFKD", texto)
    sem_acentos = "".join(
        caractere for caractere in decomposicao if not unicodedata.combining(caractere)
    )
    return " ".join(sem_acentos.split()).casefold()


def converter_instante_iso(valor: Any) -> datetime | None:
    """Converte data/hora ISO com hora obrigatória para datetime ciente de fuso.

    Se a entrada vier sem fuso (naive), assume ``FUSO_BRASILIA`` no retorno.
    """
    if not isinstance(valor, str):
        return None

    texto = valor.strip()
    if not texto or PADRAO_INSTANTE_ISO_PREFIXO.match(texto) is None:
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
    if PADRAO_DATA_ISO.fullmatch(texto) is not None:
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
