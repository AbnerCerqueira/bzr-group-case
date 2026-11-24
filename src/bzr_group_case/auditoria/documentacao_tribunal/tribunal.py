import csv
import re
from pathlib import Path

from bzr_group_case.auditoria.base import (
    PADRAO_CNJ,
    ResultadoValidacao,
    ler_csv_para_analise,
    rotulo_arquivo,
)

ORIGEM_DOC_TRIBUNAL = "docs/DOCUMENTACAO_TRIBUNAL.md (seção tribunal.csv)"
COLUNAS_TRIBUNAL = ["numero_processo", "ente_devedor", "valor_face"]
PADRAO_NUMERO_DECIMAL = re.compile(r"-?\d+(\.\d+)?", re.ASCII)


def validar_codificacao_utf8(caminho: Path) -> ResultadoValidacao:
    """Valida se todas as linhas do arquivo podem ser decodificadas como UTF-8."""
    evidencias: list[str] = []

    for num_linha, linha_bytes in enumerate(caminho.read_bytes().splitlines(), start=1):
        try:
            linha_bytes.decode("utf-8")
        except UnicodeDecodeError:
            texto = linha_bytes.decode("utf-8", errors="replace")
            evidencias.append(f"Linha {num_linha}: {texto}")

    return ResultadoValidacao(
        origem=ORIGEM_DOC_TRIBUNAL,
        validacao="Codificação UTF-8",
        arquivo=rotulo_arquivo(caminho),
        evidencias=evidencias,
    )


def validar_delimitador_e_colunas(
    caminho: Path,
    colunas_esperadas: list[str] = COLUNAS_TRIBUNAL,
) -> ResultadoValidacao:
    """Valida se o CSV usa vírgula, tem o cabeçalho esperado e colunas consistentes."""
    evidencias: list[str] = []

    with caminho.open(encoding="utf-8", errors="replace", newline="") as arquivo:
        leitor = csv.reader(arquivo, delimiter=",")
        cabecalho = next(leitor, [])

        if cabecalho != colunas_esperadas:
            evidencias.extend(
                [
                    f"Esperado  : {colunas_esperadas}",
                    f"Encontrado: {cabecalho}",
                ]
            )
        else:
            for num_linha, linha in enumerate(leitor, start=2):
                if len(linha) != len(colunas_esperadas):
                    evidencias.append(
                        f"Linha {num_linha}: esperadas {len(colunas_esperadas)} "
                        f"colunas, encontradas {len(linha)}"
                    )

    return ResultadoValidacao(
        origem=ORIGEM_DOC_TRIBUNAL,
        validacao="Delimitador vírgula (',') e colunas esperadas",
        arquivo=rotulo_arquivo(caminho),
        evidencias=evidencias,
    )


def validar_processo_cnj_csv(caminho: Path) -> ResultadoValidacao:
    """Valida se numero_processo segue o padrão CNJ em cada linha do CSV."""
    evidencias: list[str] = []

    for num_linha, linha in ler_csv_para_analise(caminho):
        processo = linha.get("numero_processo") or ""
        if not PADRAO_CNJ.fullmatch(processo):
            evidencias.append(f"Linha {num_linha}: encontrado {processo!r}")

    return ResultadoValidacao(
        origem=ORIGEM_DOC_TRIBUNAL,
        validacao="numero_processo: formato CNJ (NNNNNNN-DD.AAAA.J.TR.OOOO)",
        arquivo=rotulo_arquivo(caminho),
        evidencias=evidencias,
    )


def validar_ente_devedor_csv(caminho: Path) -> ResultadoValidacao:
    """Valida se ente_devedor é um texto não vazio em cada linha do CSV."""
    evidencias: list[str] = []

    for num_linha, linha in ler_csv_para_analise(caminho):
        ente = linha.get("ente_devedor") or ""
        if not ente.strip():
            evidencias.append(f"Linha {num_linha}: valor vazio")

    return ResultadoValidacao(
        origem=ORIGEM_DOC_TRIBUNAL,
        validacao="ente_devedor: texto não vazio",
        arquivo=rotulo_arquivo(caminho),
        evidencias=evidencias,
    )


def validar_valor_face_decimal_csv(caminho: Path) -> ResultadoValidacao:
    """Valida se valor_face usa número com ponto como separador decimal."""
    evidencias: list[str] = []

    for num_linha, linha in ler_csv_para_analise(caminho):
        valor = linha.get("valor_face") or ""
        if not PADRAO_NUMERO_DECIMAL.fullmatch(valor):
            evidencias.append(f"Linha {num_linha}: encontrado {valor!r}")

    return ResultadoValidacao(
        origem=ORIGEM_DOC_TRIBUNAL,
        validacao="valor_face: número com ponto decimal",
        arquivo=rotulo_arquivo(caminho),
        evidencias=evidencias,
    )


def auditar_tribunal(caminho: Path) -> list[ResultadoValidacao]:
    """Executa todas as validações da seção tribunal.csv."""
    return [
        validar_codificacao_utf8(caminho),
        validar_delimitador_e_colunas(caminho),
        validar_processo_cnj_csv(caminho),
        validar_ente_devedor_csv(caminho),
        validar_valor_face_decimal_csv(caminho),
    ]
