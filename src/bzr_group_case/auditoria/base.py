import csv
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RAIZ_PROJETO = Path(__file__).resolve().parents[3]
DIRETORIO_DADOS = RAIZ_PROJETO / "data"

PADRAO_CNJ = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", re.ASCII)


@dataclass(frozen=True)
class ResultadoValidacao:
    """Resultado objetivo de uma validação vinculada à sua fonte de verdade."""

    origem: str
    validacao: str
    arquivo: str
    evidencias: list[str]

    @property
    def ok(self) -> bool:
        return not self.evidencias


def rotulo_arquivo(caminho: Path) -> str:
    """Retorna o caminho relativo à raiz do projeto para exibição legível."""
    try:
        return caminho.resolve().relative_to(RAIZ_PROJETO).as_posix()
    except ValueError:
        return str(caminho)


def somente_digitos(texto: str) -> str:
    """Remove pontuação/espaços e mantém apenas dígitos ASCII (chave CNJ)."""
    return "".join(c for c in texto if c.isascii() and c.isdigit())


def identificador_evento(indice: int, evento: dict[str, Any]) -> str:
    """Retorna referência legível de um item JSON ('Item N (ev-XXX)')."""
    evento_id = evento.get("evento_id")
    if isinstance(evento_id, str) and evento_id.strip():
        return f"Item {indice} ({evento_id})"
    return f"Item {indice}"


def carregar_eventos_json(caminho: Path) -> list[tuple[int, dict[str, Any]]]:
    """Carrega objetos de uma lista JSON preservando o índice original (1-based)."""
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return []
    if not isinstance(dados, list):
        return []
    return [
        (indice, item)
        for indice, item in enumerate(dados, start=1)
        if isinstance(item, dict)
    ]


def ler_csv_para_analise(caminho: Path) -> list[tuple[int, dict[str, str | None]]]:
    """Lê linhas de dados de um CSV tolerando BOM, cp1252 e ';' para análise."""
    conteudo_bruto = caminho.read_bytes()
    try:
        texto = conteudo_bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = conteudo_bruto.decode("cp1252", errors="replace")

    buffer = io.StringIO(texto, newline="")
    primeira_linha = buffer.readline()
    delimitador = ";" if ";" in primeira_linha and "," not in primeira_linha else ","
    buffer.seek(0)
    leitor = csv.DictReader(buffer, delimiter=delimitador)
    return list(enumerate(leitor, start=2))
