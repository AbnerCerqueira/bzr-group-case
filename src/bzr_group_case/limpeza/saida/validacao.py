import csv
import io
import re
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from bzr_group_case.comum import (
    PADRAO_DATA_ISO,
    PADRAO_INSTANTE_ISO_PREFIXO,
    calcular_prazo_constitucional,
)
from bzr_group_case.limpeza.modelos import (
    ResultadoConciliacaoPrecatorios,
    ResultadoLimpezaPagamentos,
    VerificacaoSaida,
)
from bzr_group_case.limpeza.saida.arquivos import (
    COLUNAS_PAGAMENTOS,
    COLUNAS_PRECATORIOS,
    NOME_PAGAMENTOS_CSV,
    NOME_PRECATORIOS_CSV,
)

_PADRAO_CNJ_20 = re.compile(r"^\d{20}$", re.ASCII)
_PADRAO_DECIMAL_2_CASAS = re.compile(r"^\d+\.\d{2}$", re.ASCII)

_STATUS_VALIDOS = frozenset({"conciliado", "em_duvida"})
_TIPOS_VALIDOS = frozenset({"pagamento", "estorno"})


@dataclass(frozen=True)
class _CsvLido:
    nome: str
    cabecalho: tuple[str, ...] | None
    linhas: tuple[tuple[int, dict[str, str]], ...] | None
    erros_formato: tuple[str, ...]


def _ler_csv_saida(caminho: Path, colunas_esperadas: tuple[str, ...]) -> _CsvLido:
    nome = caminho.name
    if not caminho.is_file():
        return _CsvLido(nome, None, None, (f"{nome}: arquivo não encontrado.",))

    conteudo = caminho.read_bytes()
    erros: list[str] = []

    if conteudo.startswith(b"\xef\xbb\xbf"):
        erros.append(f"{nome}: arquivo contém BOM UTF-8 (esperado UTF-8 sem BOM).")
        conteudo = conteudo[3:]

    if b"\r\n" in conteudo or b"\r" in conteudo:
        erros.append(f"{nome}: arquivo contém quebras de linha CRLF/CR (esperado LF).")

    try:
        texto = conteudo.decode("utf-8")
    except UnicodeDecodeError as exc:
        erros.append(f"{nome}: codificação inválida (não é UTF-8: {exc.reason}).")
        return _CsvLido(nome, None, None, tuple(erros))

    leitor = csv.reader(io.StringIO(texto, newline=""), delimiter=",")
    linhas_brutas = list(leitor)
    if not linhas_brutas:
        erros.append(f"{nome}: arquivo CSV vazio (sem cabeçalho).")
        return _CsvLido(nome, None, None, tuple(erros))

    cabecalho = tuple(linhas_brutas[0])
    if cabecalho != colunas_esperadas:
        erros.append(
            f"{nome}: cabeçalho divergente "
            f"(esperado {list(colunas_esperadas)}, encontrado {list(cabecalho)})."
        )

    linhas_dict: list[tuple[int, dict[str, str]]] = []
    for num_linha, valores in enumerate(linhas_brutas[1:], start=2):
        if len(valores) != len(cabecalho):
            erros.append(
                f"{nome} (L{num_linha}): quantidade de colunas ({len(valores)}) "
                f"difere do cabeçalho ({len(cabecalho)})."
            )
            continue
        linhas_dict.append((num_linha, dict(zip(cabecalho, valores, strict=True))))

    return _CsvLido(nome, cabecalho, tuple(linhas_dict), tuple(erros))


def _decimal_positivo_duas_casas(texto: str) -> bool:
    if _PADRAO_DECIMAL_2_CASAS.fullmatch(texto) is None:
        return False
    try:
        return Decimal(texto) > 0
    except InvalidOperation:
        return False


def _data_iso_valida(texto: str) -> bool:
    if PADRAO_DATA_ISO.fullmatch(texto) is None:
        return False
    try:
        date.fromisoformat(texto)
    except ValueError:
        return False
    return True


def _instante_iso_com_fuso_valido(texto: str) -> bool:
    if not texto or texto != texto.strip():
        return False
    if PADRAO_INSTANTE_ISO_PREFIXO.match(texto) is None:
        return False
    texto_iso = f"{texto[:-1]}+00:00" if texto.endswith(("Z", "z")) else texto
    try:
        instante = datetime.fromisoformat(texto_iso)
    except ValueError:
        return False
    return instante.tzinfo is not None


def _colunas_presentes(csv_lido: _CsvLido, obrigatorias: tuple[str, ...]) -> bool:
    return (
        csv_lido.linhas is not None
        and csv_lido.cabecalho is not None
        and set(obrigatorias).issubset(csv_lido.cabecalho)
    )


def _validar_formato_csvs(
    csv_precatorios: _CsvLido,
    csv_pagamentos: _CsvLido,
) -> VerificacaoSaida:
    detalhes = (*csv_precatorios.erros_formato, *csv_pagamentos.erros_formato)
    return VerificacaoSaida(
        regra="Codificação UTF-8 sem BOM (LF), delimitador ',' e cabeçalhos exatos",
        ok=not detalhes,
        detalhes=detalhes,
    )


def _validar_integridade_precatorios(
    csv_precatorios: _CsvLido,
) -> tuple[VerificacaoSaida, set[str]]:
    regra = "Integridade cadastral de precatorios_limpos.csv"
    obrigatorias = (
        "numero_processo",
        "ente_devedor",
        "valor_face",
        "status_conciliacao",
    )
    if not _colunas_presentes(csv_precatorios, obrigatorias):
        return (
            VerificacaoSaida(
                regra=regra,
                ok=False,
                detalhes=(
                    f"{csv_precatorios.nome}: leitura ou colunas obrigatórias "
                    "indisponíveis para validação.",
                ),
            ),
            set(),
        )

    assert csv_precatorios.linhas is not None
    detalhes: list[str] = []
    chaves: set[str] = set()

    for num_linha, linha in csv_precatorios.linhas:
        processo = linha["numero_processo"]
        ente_devedor = linha["ente_devedor"]
        valor_face = linha["valor_face"]
        status = linha["status_conciliacao"]

        if _PADRAO_CNJ_20.fullmatch(processo) is None:
            detalhes.append(
                f"L{num_linha}: numero_processo inválido ({processo!r}; "
                "esperados 20 dígitos ASCII)."
            )
        elif processo in chaves:
            detalhes.append(f"L{num_linha}: numero_processo duplicado ({processo!r}).")
        else:
            chaves.add(processo)

        if ente_devedor != ente_devedor.strip():
            detalhes.append(
                f"L{num_linha}: ente_devedor contém espaços nas extremidades "
                f"({ente_devedor!r})."
            )
        elif not ente_devedor and status == "conciliado":
            detalhes.append(f"L{num_linha}: ente_devedor vazio em registro conciliado.")

        if not _decimal_positivo_duas_casas(valor_face):
            detalhes.append(
                f"L{num_linha}: valor_face inválido ({valor_face!r}; "
                "esperado decimal > 0 com 2 casas)."
            )

        if status not in _STATUS_VALIDOS:
            detalhes.append(f"L{num_linha}: status_conciliacao inválido ({status!r}).")

    return VerificacaoSaida(
        regra=regra, ok=not detalhes, detalhes=tuple(detalhes)
    ), chaves


def _validar_prazos_precatorios(csv_precatorios: _CsvLido) -> VerificacaoSaida:
    regra = "Conformidade do prazo constitucional em precatorios_limpos.csv"
    obrigatorias = (
        "numero_processo",
        "apresentado_em",
        "prazo_pagamento",
        "status_conciliacao",
    )
    if not _colunas_presentes(csv_precatorios, obrigatorias):
        return VerificacaoSaida(
            regra=regra,
            ok=False,
            detalhes=(
                f"{csv_precatorios.nome}: leitura ou colunas obrigatórias "
                "indisponíveis para validação de prazo.",
            ),
        )

    assert csv_precatorios.linhas is not None
    detalhes: list[str] = []

    for num_linha, linha in csv_precatorios.linhas:
        processo = linha["numero_processo"]
        apresentado_em = linha["apresentado_em"]
        prazo_pagamento = linha["prazo_pagamento"]
        status = linha["status_conciliacao"]

        if apresentado_em != apresentado_em.strip():
            detalhes.append(
                f"L{num_linha} ({processo}): apresentado_em com espaços nas "
                f"extremidades ({apresentado_em!r})."
            )
            continue

        if prazo_pagamento != prazo_pagamento.strip():
            detalhes.append(
                f"L{num_linha} ({processo}): prazo_pagamento com espaços nas "
                f"extremidades ({prazo_pagamento!r})."
            )
            continue

        if not apresentado_em:
            if status != "em_duvida":
                detalhes.append(
                    f"L{num_linha} ({processo}): apresentado_em ausente em "
                    "registro conciliado."
                )
            elif prazo_pagamento and not _data_iso_valida(prazo_pagamento):
                detalhes.append(
                    f"L{num_linha} ({processo}): prazo_pagamento inválido "
                    f"({prazo_pagamento!r})."
                )
            continue

        try:
            _, prazo_esperado = calcular_prazo_constitucional(apresentado_em)
        except ValueError:
            detalhes.append(
                f"L{num_linha} ({processo}): apresentado_em inválido "
                f"({apresentado_em!r})."
            )
            if prazo_pagamento and not _data_iso_valida(prazo_pagamento):
                detalhes.append(
                    f"L{num_linha} ({processo}): prazo_pagamento inválido "
                    f"({prazo_pagamento!r})."
                )
            continue

        esperado_iso = prazo_esperado.isoformat()
        if prazo_pagamento != esperado_iso:
            detalhes.append(
                f"L{num_linha} ({processo}): prazo_pagamento "
                f"{prazo_pagamento!r} diverge do esperado {esperado_iso!r} "
                f"para apresentado_em={apresentado_em!r}."
            )

    return VerificacaoSaida(regra=regra, ok=not detalhes, detalhes=tuple(detalhes))


def _validar_integridade_pagamentos(
    csv_pagamentos: _CsvLido,
    chaves_precatorios: set[str],
    chaves_hub: AbstractSet[str],
) -> VerificacaoSaida:
    regra = "Integridade de pagamentos_limpos.csv"
    if not _colunas_presentes(csv_pagamentos, COLUNAS_PAGAMENTOS):
        return VerificacaoSaida(
            regra=regra,
            ok=False,
            detalhes=(
                f"{csv_pagamentos.nome}: leitura ou colunas obrigatórias "
                "indisponíveis para validação.",
            ),
        )

    assert csv_pagamentos.linhas is not None
    detalhes: list[str] = []
    eventos_vistos: set[str] = set()

    for num_linha, linha in csv_pagamentos.linhas:
        evento_id = linha["evento_id"]
        processo = linha["numero_processo"]
        tipo = linha["tipo"]
        valor = linha["valor"]
        data_pagamento = linha["data_pagamento"]
        atualizado_em = linha["atualizado_em"]

        if not evento_id or evento_id != evento_id.strip():
            detalhes.append(
                f"L{num_linha}: evento_id vazio ou com espaços ({evento_id!r})."
            )
        elif evento_id in eventos_vistos:
            detalhes.append(f"L{num_linha}: evento_id duplicado ({evento_id!r}).")
        else:
            eventos_vistos.add(evento_id)

        if _PADRAO_CNJ_20.fullmatch(processo) is None:
            detalhes.append(
                f"L{num_linha} ({evento_id}): numero_processo inválido ({processo!r})."
            )
        elif processo not in chaves_precatorios:
            detalhes.append(
                f"L{num_linha} ({evento_id}): FK inválida — processo {processo!r} "
                "ausente em precatorios_limpos.csv."
            )
        elif processo not in chaves_hub:
            detalhes.append(
                f"L{num_linha} ({evento_id}): FK inválida — processo {processo!r} "
                "ausente no hub.csv."
            )

        if tipo not in _TIPOS_VALIDOS:
            detalhes.append(f"L{num_linha} ({evento_id}): tipo inválido ({tipo!r}).")

        if not _decimal_positivo_duas_casas(valor):
            detalhes.append(
                f"L{num_linha} ({evento_id}): valor inválido ({valor!r}; "
                "esperado decimal > 0 com 2 casas)."
            )

        if not _data_iso_valida(data_pagamento):
            detalhes.append(
                f"L{num_linha} ({evento_id}): data_pagamento ISO inválida "
                f"({data_pagamento!r})."
            )

        if not _instante_iso_com_fuso_valido(atualizado_em):
            detalhes.append(
                f"L{num_linha} ({evento_id}): atualizado_em ISO com fuso inválido "
                f"({atualizado_em!r})."
            )

    return VerificacaoSaida(regra=regra, ok=not detalhes, detalhes=tuple(detalhes))


def _validar_conservacao(
    csv_precatorios: _CsvLido,
    csv_pagamentos: _CsvLido,
    *,
    precatorios: ResultadoConciliacaoPrecatorios,
    pagamentos: ResultadoLimpezaPagamentos,
    total_pagamentos_brutos: int,
) -> VerificacaoSaida:
    regra = "Conservação 1-para-1 entre entrada e saída"
    detalhes: list[str] = []

    if csv_precatorios.linhas is None:
        detalhes.append(f"{csv_precatorios.nome}: não foi possível contar linhas.")
    elif len(csv_precatorios.linhas) != len(precatorios.precatorios):
        detalhes.append(
            f"{csv_precatorios.nome}: gravadas {len(csv_precatorios.linhas)} linhas, "
            f"esperadas {len(precatorios.precatorios)}."
        )

    if csv_pagamentos.linhas is None:
        detalhes.append(f"{csv_pagamentos.nome}: não foi possível contar linhas.")
    elif len(csv_pagamentos.linhas) != len(pagamentos.pagamentos):
        detalhes.append(
            f"{csv_pagamentos.nome}: gravadas {len(csv_pagamentos.linhas)} linhas, "
            f"esperadas {len(pagamentos.pagamentos)}."
        )

    if len(pagamentos.itens_rastreados) != total_pagamentos_brutos:
        detalhes.append(
            f"Rastreamento de pagamentos ({len(pagamentos.itens_rastreados)}) difere "
            f"do total bruto ({total_pagamentos_brutos})."
        )

    total_mantidos = sum(
        1 for item in pagamentos.itens_rastreados if item.destino == "mantido"
    )
    if total_mantidos != len(pagamentos.pagamentos):
        detalhes.append(
            f"Itens mantidos no rastreamento ({total_mantidos}) diferem dos "
            f"pagamentos limpos ({len(pagamentos.pagamentos)})."
        )

    return VerificacaoSaida(regra=regra, ok=not detalhes, detalhes=tuple(detalhes))


def validar_base_limpa(
    diretorio_saida: Path,
    *,
    precatorios: ResultadoConciliacaoPrecatorios,
    pagamentos: ResultadoLimpezaPagamentos,
    total_pagamentos_brutos: int,
) -> tuple[VerificacaoSaida, ...]:
    """Lê os CSVs gravados em disco e executa as 5 verificações do 'Depois'."""
    csv_precatorios = _ler_csv_saida(
        diretorio_saida / NOME_PRECATORIOS_CSV, COLUNAS_PRECATORIOS
    )
    csv_pagamentos = _ler_csv_saida(
        diretorio_saida / NOME_PAGAMENTOS_CSV, COLUNAS_PAGAMENTOS
    )

    check_formato = _validar_formato_csvs(csv_precatorios, csv_pagamentos)
    check_precatorios, chaves_precatorios = _validar_integridade_precatorios(
        csv_precatorios
    )
    check_prazos = _validar_prazos_precatorios(csv_precatorios)
    check_pagamentos = _validar_integridade_pagamentos(
        csv_pagamentos,
        chaves_precatorios,
        precatorios.chaves_hub,
    )
    check_conservacao = _validar_conservacao(
        csv_precatorios,
        csv_pagamentos,
        precatorios=precatorios,
        pagamentos=pagamentos,
        total_pagamentos_brutos=total_pagamentos_brutos,
    )

    return (
        check_formato,
        check_precatorios,
        check_prazos,
        check_pagamentos,
        check_conservacao,
    )
