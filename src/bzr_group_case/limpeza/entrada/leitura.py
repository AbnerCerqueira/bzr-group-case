import csv
import io
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from bzr_group_case.limpeza.modelos import DadosBrutos, RegistroOcorrencia

RAIZ_PROJETO = Path(__file__).resolve().parents[4]
DIRETORIO_DADOS = RAIZ_PROJETO / "data" / "raw"


def _rejeitar_constante_json(constante: str) -> Any:
    raise ValueError(f"Constante JSON fora da RFC 8259 não permitida: {constante!r}")


def _ler_csv(
    caminho: Path,
    ocorrencias: list[RegistroOcorrencia],
) -> tuple[tuple[int, dict[str, str]], ...]:
    """Lê um CSV preservando números físicos de linha e registrando ocorrências P3."""
    nome_arquivo = caminho.name
    conteudo_bruto = caminho.read_bytes()

    try:
        texto = conteudo_bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            texto = conteudo_bruto.decode("cp1252")
            encoding_origem = "cp1252"
        except UnicodeDecodeError:
            texto = conteudo_bruto.decode("latin-1")
            encoding_origem = "latin-1"
        ocorrencias.append(
            RegistroOcorrencia(
                problema="P3",
                categoria="corrigido",
                entidade="arquivo",
                identificador=nome_arquivo,
                origem=nome_arquivo,
                campo="encoding",
                valor_original=encoding_origem,
                valor_tratado="utf-8",
                motivo=(
                    f"Arquivo CSV decodificado em {encoding_origem} "
                    "após falha em UTF-8."
                ),
            )
        )

    primeira_linha_nao_vazia = next(
        (linha for linha in texto.splitlines() if linha.strip()),
        "",
    )
    if ";" in primeira_linha_nao_vazia and "," not in primeira_linha_nao_vazia:
        delimitador = ";"
        ocorrencias.append(
            RegistroOcorrencia(
                problema="P3",
                categoria="corrigido",
                entidade="arquivo",
                identificador=nome_arquivo,
                origem=nome_arquivo,
                campo="delimitador",
                valor_original=";",
                valor_tratado=",",
                motivo="Arquivo CSV usa ponto e vírgula (';') em vez de vírgula (',').",
            )
        )
    else:
        delimitador = ","

    buffer = io.StringIO(texto, newline="")
    leitor = csv.DictReader(buffer, delimiter=delimitador)
    registros: list[tuple[int, dict[str, str]]] = []

    for linha in leitor:
        num_linha = leitor.line_num
        linha_limpa: dict[str, str] = {}
        colunas_faltantes: list[str] = []
        tem_conteudo = False

        for chave, valor in linha.items():
            if chave is None:
                extras = (
                    [str(item).strip() for item in valor]
                    if isinstance(valor, list)
                    else [str(valor)]
                )
                if any(extras):
                    tem_conteudo = True
                ocorrencias.append(
                    RegistroOcorrencia(
                        problema="P3",
                        categoria="descartado",
                        entidade="arquivo",
                        identificador=f"{nome_arquivo}#linha-{num_linha}",
                        origem=nome_arquivo,
                        campo="colunas_extras",
                        valor_original=repr(extras),
                        valor_tratado=None,
                        motivo=(
                            "Colunas extras além do cabeçalho foram ignoradas "
                            "na leitura do CSV."
                        ),
                    )
                )
                continue

            chave_limpa = chave.strip()
            if not chave_limpa:
                valor_sem_cabecalho = valor.strip() if isinstance(valor, str) else ""
                if valor_sem_cabecalho:
                    tem_conteudo = True
                    ocorrencias.append(
                        RegistroOcorrencia(
                            problema="P3",
                            categoria="descartado",
                            entidade="arquivo",
                            identificador=f"{nome_arquivo}#linha-{num_linha}",
                            origem=nome_arquivo,
                            campo="coluna_sem_cabecalho",
                            valor_original=repr(valor_sem_cabecalho),
                            valor_tratado=None,
                            motivo=(
                                "Valor em coluna sem nome no cabeçalho foi "
                                "descartado na leitura do CSV."
                            ),
                        )
                    )
                continue

            if valor is None:
                colunas_faltantes.append(chave_limpa)
                linha_limpa[chave_limpa] = ""
                continue

            valor_limpo = valor.strip()
            if valor_limpo:
                tem_conteudo = True
            linha_limpa[chave_limpa] = valor_limpo

        if not tem_conteudo:
            ocorrencias.append(
                RegistroOcorrencia(
                    problema="P3",
                    categoria="descartado",
                    entidade="arquivo",
                    identificador=f"{nome_arquivo}#linha-{num_linha}",
                    origem=nome_arquivo,
                    campo="linha_vazia",
                    valor_original=repr(linha_limpa),
                    valor_tratado=None,
                    motivo="Linha sem dados úteis descartada na leitura do CSV.",
                )
            )
            continue

        if colunas_faltantes:
            ocorrencias.append(
                RegistroOcorrencia(
                    problema="P3",
                    categoria="em_duvida",
                    entidade="arquivo",
                    identificador=f"{nome_arquivo}#linha-{num_linha}",
                    origem=nome_arquivo,
                    campo="colunas_faltantes",
                    valor_original=repr(colunas_faltantes),
                    valor_tratado=None,
                    motivo=(
                        "Linha do CSV com menos colunas que o cabeçalho; "
                        "campos ausentes preenchidos como vazios."
                    ),
                )
            )

        registros.append((num_linha, linha_limpa))

    return tuple(registros)


def _ler_json_lista(
    caminho: Path,
    ocorrencias: list[RegistroOcorrencia],
) -> tuple[tuple[int, dict[str, Any]], ...]:
    """Lê uma lista JSON usando Decimal para floats e descartando itens não-objeto."""
    nome_arquivo = caminho.name
    conteudo = json.loads(
        caminho.read_text(encoding="utf-8-sig"),
        parse_float=Decimal,
        parse_constant=_rejeitar_constante_json,
    )

    if not isinstance(conteudo, list):
        raise ValueError(
            f"Raiz JSON inválida em {nome_arquivo}: "
            f"esperado list, obtido {type(conteudo).__name__}."
        )

    itens: list[tuple[int, dict[str, Any]]] = []
    for indice, item in enumerate(conteudo, start=1):
        if not isinstance(item, dict):
            ocorrencias.append(
                RegistroOcorrencia(
                    problema="P3",
                    categoria="descartado",
                    entidade="arquivo",
                    identificador=f"{nome_arquivo}#item-{indice}",
                    origem=nome_arquivo,
                    campo="item",
                    valor_original=repr(item),
                    valor_tratado=None,
                    motivo=(
                        f"Item {indice} descartado por não ser objeto JSON "
                        f"(tipo {type(item).__name__})."
                    ),
                )
            )
            continue
        itens.append((indice, item))

    return tuple(itens)


def carregar_dados_brutos(diretorio_dados: Path = DIRETORIO_DADOS) -> DadosBrutos:
    """Carrega os 4 arquivos de entrada em modo somente leitura e coleta P3."""
    ocorrencias: list[RegistroOcorrencia] = []

    tribunal = _ler_csv(diretorio_dados / "tribunal.csv", ocorrencias)
    hub = _ler_csv(diretorio_dados / "hub.csv", ocorrencias)
    apresentacoes = _ler_json_lista(diretorio_dados / "apresentacoes.json", ocorrencias)
    pagamentos = _ler_json_lista(diretorio_dados / "pagamentos.json", ocorrencias)

    return DadosBrutos(
        tribunal=tribunal,
        hub=hub,
        apresentacoes=apresentacoes,
        pagamentos=pagamentos,
        ocorrencias_leitura=tuple(ocorrencias),
    )
