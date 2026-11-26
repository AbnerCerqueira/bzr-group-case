from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Any

from bzr_group_case.limpeza.entrada.normalizacao import (
    converter_valor_monetario,
    normalizar_cnj,
)
from bzr_group_case.limpeza.modelos import (
    CategoriaOcorrencia,
    DadosBrutos,
    ProblemaDiagnostico,
    RegistroOcorrencia,
)


@dataclass(frozen=True)
class RegistroTribunalIndexado:
    """Registro válido de tribunal.csv indexado pela chave CNJ de 20 dígitos."""

    linha: int
    chave_cnj: str
    cnj_formatado: str
    processo_original: str
    ente_devedor: str
    valor_face: Decimal


@dataclass(frozen=True)
class RegistroHubIndexado:
    """Registro válido de hub.csv indexado pela chave CNJ de 20 dígitos."""

    linha: int
    chave_cnj: str
    cnj_formatado: str
    processo_original: str
    ente_devedor: str
    valor_face: Decimal
    apresentado_em: str
    prazo_pagamento: str


@dataclass(frozen=True)
class RegistroApresentacaoIndexado:
    """Registro válido de apresentacoes.json indexado pela chave CNJ de 20 dígitos."""

    indice: int
    chave_cnj: str
    cnj_formatado: str
    processo_original: str
    apresentado_em: str


@dataclass(frozen=True)
class IndicePrecatorios:
    """Bases cadastrais indexadas por CNJ de 20 dígitos e ocorrências da indexação."""

    tribunal: Mapping[str, RegistroTribunalIndexado]
    hub: Mapping[str, RegistroHubIndexado]
    apresentacoes: Mapping[str, RegistroApresentacaoIndexado]
    chaves_duplicadas_conflitantes: frozenset[str]
    ocorrencias: tuple[RegistroOcorrencia, ...]


_RegistroIndexado = (
    RegistroTribunalIndexado | RegistroHubIndexado | RegistroApresentacaoIndexado
)


def registrar_ocorrencia_precatorio(
    ocorrencias: list[RegistroOcorrencia],
    *,
    problema: ProblemaDiagnostico,
    categoria: CategoriaOcorrencia,
    identificador: str,
    origem: str,
    campo: str,
    valor_original: str,
    motivo: str,
    valor_tratado: str | None = None,
) -> None:
    """Anexa uma ocorrência de precatório com campos nomeados e explícitos."""
    ocorrencias.append(
        RegistroOcorrencia(
            problema=problema,
            categoria=categoria,
            entidade="precatorio",
            identificador=identificador,
            origem=origem,
            campo=campo,
            valor_original=valor_original,
            valor_tratado=valor_tratado,
            motivo=motivo,
        )
    )


def _validar_cnj_e_valor(
    arquivo: str,
    linha: int,
    processo_bruto: str,
    valor_bruto: str,
    ocorrencias: list[RegistroOcorrencia],
) -> tuple[str, str, Decimal, bool] | None:
    origem = f"{arquivo} (L{linha})"
    cnj_normalizado = normalizar_cnj(processo_bruto)
    if cnj_normalizado is None:
        registrar_ocorrencia_precatorio(
            ocorrencias,
            problema="P3",
            categoria="descartado",
            identificador=f"{arquivo}#L{linha}",
            origem=origem,
            campo="numero_processo",
            valor_original=processo_bruto,
            motivo=f"CNJ ausente ou inválido em {arquivo}; registro descartado.",
        )
        return None

    chave_cnj, cnj_formatado = cnj_normalizado
    valor_face, precisou_normalizar = converter_valor_monetario(valor_bruto)
    if valor_face is None or valor_face <= 0:
        if not valor_bruto.strip():
            motivo = f"Valor de face ausente em {arquivo}; registro descartado."
        elif valor_face is None:
            motivo = (
                f"Valor de face fora do padrão ({valor_bruto!r}) em {arquivo}; "
                "registro descartado."
            )
        else:
            motivo = (
                f"Valor de face <= 0 ({valor_bruto!r}) em {arquivo}; "
                "registro descartado."
            )
        registrar_ocorrencia_precatorio(
            ocorrencias,
            problema="P3",
            categoria="descartado",
            identificador=cnj_formatado,
            origem=origem,
            campo="valor_face",
            valor_original=valor_bruto,
            motivo=motivo,
        )
        return None

    return chave_cnj, cnj_formatado, valor_face, precisou_normalizar


def _resumo_registro(reg: _RegistroIndexado) -> tuple[str, str, str | None]:
    if isinstance(reg, RegistroTribunalIndexado):
        resumo = f"ente={reg.ente_devedor!r}, valor_face={reg.valor_face:.2f}"
        return f"L{reg.linha}", f"({resumo})", resumo
    if isinstance(reg, RegistroHubIndexado):
        resumo = (
            f"ente={reg.ente_devedor!r}, valor_face={reg.valor_face:.2f}, "
            f"apresentado_em={reg.apresentado_em!r}, prazo={reg.prazo_pagamento!r}"
        )
        return f"L{reg.linha}", f"({resumo})", resumo
    return f"item {reg.indice}", repr(reg.apresentado_em), reg.apresentado_em or None


def _registrar_duplicidade(
    arquivo: str,
    existente: _RegistroIndexado,
    novo: _RegistroIndexado,
    igual: bool,
    ocorrencias: list[RegistroOcorrencia],
    chaves_conflitantes: set[str],
) -> None:
    ref_existente, resumo_existente, valor_mantido = _resumo_registro(existente)
    ref_novo, resumo_novo, _ = _resumo_registro(novo)
    cnj_formatado = existente.cnj_formatado

    if igual:
        rotulo_igual = (
            f"{ref_novo} (idêntico ao {ref_existente})"
            if ref_novo.startswith("item ")
            else f"{ref_novo} (idêntica a {ref_existente})"
        )
        registrar_ocorrencia_precatorio(
            ocorrencias,
            problema="P4",
            categoria="descartado",
            identificador=cnj_formatado,
            origem=f"{arquivo} ({ref_novo})",
            campo="duplicidade",
            valor_original=rotulo_igual,
            motivo=(
                f"Duplicata idêntica em {arquivo} ({ref_novo} repete "
                f"{ref_existente}); primeira ocorrência mantida."
            ),
        )
        return

    chaves_conflitantes.add(existente.chave_cnj)
    registrar_ocorrencia_precatorio(
        ocorrencias,
        problema="P4",
        categoria="em_duvida",
        identificador=cnj_formatado,
        origem=f"{arquivo} ({ref_existente}) x {arquivo} ({ref_novo})",
        campo="duplicidade",
        valor_original=(
            f"{ref_existente}={resumo_existente} | {ref_novo}={resumo_novo}"
        ),
        valor_tratado=valor_mantido,
        motivo=(
            f"Duplicata conflitante em {arquivo} ({ref_existente} x {ref_novo}); "
            "primeira ocorrência mantida sem sobrescrever em dúvida."
        ),
    )


def _registrar_valor_face_normalizado(
    arquivo: str,
    linha: int,
    cnj_formatado: str,
    valor_bruto: str,
    valor_face: Decimal,
    ocorrencias: list[RegistroOcorrencia],
) -> None:
    valor_formatado = f"{valor_face:.2f}"
    registrar_ocorrencia_precatorio(
        ocorrencias,
        problema="P3",
        categoria="corrigido",
        identificador=cnj_formatado,
        origem=f"{arquivo} (L{linha})",
        campo="valor_face",
        valor_original=valor_bruto,
        valor_tratado=valor_formatado,
        motivo=(
            f"Valor de face ({valor_bruto!r}) convertido para decimal padrão "
            f"({valor_formatado})."
        ),
    )


def _indexar_tribunal(
    registros: tuple[tuple[int, dict[str, str]], ...],
    ocorrencias: list[RegistroOcorrencia],
    chaves_conflitantes: set[str],
) -> dict[str, RegistroTribunalIndexado]:
    indice: dict[str, RegistroTribunalIndexado] = {}
    for linha, registro in registros:
        processo_bruto = registro.get("numero_processo", "")
        valor_bruto = registro.get("valor_face", "")
        validado = _validar_cnj_e_valor(
            "tribunal.csv", linha, processo_bruto, valor_bruto, ocorrencias
        )
        if validado is None:
            continue

        chave_cnj, cnj_formatado, valor_face, precisou_normalizar = validado
        ente = registro.get("ente_devedor", "").strip()
        novo = RegistroTribunalIndexado(
            linha=linha,
            chave_cnj=chave_cnj,
            cnj_formatado=cnj_formatado,
            processo_original=processo_bruto.strip(),
            ente_devedor=ente,
            valor_face=valor_face,
        )
        if (existente := indice.get(chave_cnj)) is not None:
            igual = (existente.ente_devedor, existente.valor_face) == (ente, valor_face)
            _registrar_duplicidade(
                "tribunal.csv",
                existente,
                novo,
                igual,
                ocorrencias,
                chaves_conflitantes,
            )
            continue

        if precisou_normalizar:
            _registrar_valor_face_normalizado(
                "tribunal.csv",
                linha,
                cnj_formatado,
                valor_bruto,
                valor_face,
                ocorrencias,
            )
        indice[chave_cnj] = novo
    return indice


def _indexar_hub(
    registros: tuple[tuple[int, dict[str, str]], ...],
    ocorrencias: list[RegistroOcorrencia],
    chaves_conflitantes: set[str],
) -> dict[str, RegistroHubIndexado]:
    indice: dict[str, RegistroHubIndexado] = {}
    for linha, registro in registros:
        processo_bruto = registro.get("processo", "")
        valor_bruto = registro.get("valor_face", "")
        validado = _validar_cnj_e_valor(
            "hub.csv", linha, processo_bruto, valor_bruto, ocorrencias
        )
        if validado is None:
            continue

        chave_cnj, cnj_formatado, valor_face, precisou_normalizar = validado
        ente = registro.get("ente", "").strip()
        apresentado_em = registro.get("apresentado_em", "").strip()
        prazo_pagamento = registro.get("prazo_pagamento", "").strip()
        novo = RegistroHubIndexado(
            linha=linha,
            chave_cnj=chave_cnj,
            cnj_formatado=cnj_formatado,
            processo_original=processo_bruto.strip(),
            ente_devedor=ente,
            valor_face=valor_face,
            apresentado_em=apresentado_em,
            prazo_pagamento=prazo_pagamento,
        )
        if (existente := indice.get(chave_cnj)) is not None:
            igual = (
                existente.ente_devedor,
                existente.valor_face,
                existente.apresentado_em,
                existente.prazo_pagamento,
            ) == (ente, valor_face, apresentado_em, prazo_pagamento)
            _registrar_duplicidade(
                "hub.csv",
                existente,
                novo,
                igual,
                ocorrencias,
                chaves_conflitantes,
            )
            continue

        if precisou_normalizar:
            _registrar_valor_face_normalizado(
                "hub.csv", linha, cnj_formatado, valor_bruto, valor_face, ocorrencias
            )
        indice[chave_cnj] = novo
    return indice


def _indexar_apresentacoes(
    registros: tuple[tuple[int, dict[str, Any]], ...],
    ocorrencias: list[RegistroOcorrencia],
    chaves_conflitantes: set[str],
) -> dict[str, RegistroApresentacaoIndexado]:
    indice: dict[str, RegistroApresentacaoIndexado] = {}
    for indice_item, registro in registros:
        origem = f"apresentacoes.json (item {indice_item})"
        processo_bruto = registro.get("processo")
        cnj_normalizado = normalizar_cnj(processo_bruto)
        if cnj_normalizado is None:
            registrar_ocorrencia_precatorio(
                ocorrencias,
                problema="P3",
                categoria="descartado",
                identificador=f"apresentacoes.json#item-{indice_item}",
                origem=origem,
                campo="numero_processo",
                valor_original="" if processo_bruto is None else str(processo_bruto),
                motivo="CNJ ausente ou inválido em apresentacoes.json; descartado.",
            )
            continue

        chave_cnj, cnj_formatado = cnj_normalizado
        apresentado_bruto = registro.get("apresentado_em")
        if apresentado_bruto is not None and not isinstance(apresentado_bruto, str):
            registrar_ocorrencia_precatorio(
                ocorrencias,
                problema="P3",
                categoria="descartado",
                identificador=cnj_formatado,
                origem=origem,
                campo="apresentado_em",
                valor_original=repr(apresentado_bruto),
                motivo=(
                    "Campo apresentado_em fora do tipo texto em apresentacoes.json "
                    f"({type(apresentado_bruto).__name__}); registro descartado."
                ),
            )
            continue

        apresentado_em = "" if apresentado_bruto is None else apresentado_bruto.strip()
        novo = RegistroApresentacaoIndexado(
            indice=indice_item,
            chave_cnj=chave_cnj,
            cnj_formatado=cnj_formatado,
            processo_original=str(processo_bruto).strip(),
            apresentado_em=apresentado_em,
        )
        if (existente := indice.get(chave_cnj)) is not None:
            igual = existente.apresentado_em == apresentado_em
            _registrar_duplicidade(
                "apresentacoes.json",
                existente,
                novo,
                igual,
                ocorrencias,
                chaves_conflitantes,
            )
            continue

        indice[chave_cnj] = novo
    return indice


def indexar_precatorios(dados: DadosBrutos) -> IndicePrecatorios:
    """Indexa tribunal.csv, hub.csv e apresentacoes.json pela chave CNJ (20 dígitos)."""
    ocorrencias: list[RegistroOcorrencia] = []
    chaves_conflitantes: set[str] = set()
    return IndicePrecatorios(
        tribunal=MappingProxyType(
            _indexar_tribunal(dados.tribunal, ocorrencias, chaves_conflitantes)
        ),
        hub=MappingProxyType(_indexar_hub(dados.hub, ocorrencias, chaves_conflitantes)),
        apresentacoes=MappingProxyType(
            _indexar_apresentacoes(
                dados.apresentacoes, ocorrencias, chaves_conflitantes
            )
        ),
        chaves_duplicadas_conflitantes=frozenset(chaves_conflitantes),
        ocorrencias=tuple(ocorrencias),
    )
