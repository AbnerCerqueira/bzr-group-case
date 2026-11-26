import re
import unicodedata
from datetime import date
from decimal import Decimal
from types import MappingProxyType

from bzr_group_case.limpeza.entrada.normalizacao import (
    calcular_prazo_constitucional,
    chave_texto_normalizada,
    extrair_data_civil_brasilia,
    formatar_cnj,
)
from bzr_group_case.limpeza.modelos import (
    DadosBrutos,
    PrecatorioLimpo,
    RegistroOcorrencia,
    ResultadoConciliacaoPrecatorios,
    StatusConciliacao,
)
from bzr_group_case.limpeza.precatorios.indexacao import (
    RegistroApresentacaoIndexado,
    RegistroHubIndexado,
    RegistroTribunalIndexado,
    indexar_precatorios,
    registrar_ocorrencia_precatorio,
)

_DATA_PURA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$", re.ASCII)
_FUSO_ISO = re.compile(r"(?:[Zz]|[+-]\d{2}:\d{2})$", re.ASCII)


def _sem_fuso_explicito(texto: str) -> bool:
    limpo = texto.strip()
    return (
        _DATA_PURA_ISO.fullmatch(limpo) is not None or _FUSO_ISO.search(limpo) is None
    )


def _tem_acento(texto: str) -> bool:
    return any(
        unicodedata.combining(caractere)
        for caractere in unicodedata.normalize("NFKD", texto)
    )


def _extrair_data_segura(texto: str) -> date | None:
    try:
        return extrair_data_civil_brasilia(texto)
    except ValueError:
        return None


def _registrar_cobertura(
    reg_tribunal: RegistroTribunalIndexado | None,
    reg_hub: RegistroHubIndexado | None,
    reg_apresentacao: RegistroApresentacaoIndexado | None,
    cnj_formatado: str,
    ocorrencias: list[RegistroOcorrencia],
) -> bool:
    if reg_tribunal is not None and reg_hub is not None:
        if reg_tribunal.processo_original != reg_hub.processo_original:
            registrar_ocorrencia_precatorio(
                ocorrencias,
                problema="P4",
                categoria="corrigido",
                identificador=cnj_formatado,
                origem=(
                    f"tribunal.csv (L{reg_tribunal.linha}) x hub.csv (L{reg_hub.linha})"
                ),
                campo="numero_processo",
                valor_original=(
                    f"tribunal={reg_tribunal.processo_original!r} | "
                    f"hub={reg_hub.processo_original!r}"
                ),
                valor_tratado=reg_tribunal.chave_cnj,
                motivo="Falso divergente de CNJ eliminado pela chave de 20 dígitos.",
            )
        return False

    if reg_hub is not None:
        registrar_ocorrencia_precatorio(
            ocorrencias,
            problema="P4",
            categoria="em_duvida",
            identificador=cnj_formatado,
            origem=f"hub.csv (L{reg_hub.linha})",
            campo="cobertura",
            valor_original="presente apenas no hub.csv",
            motivo="Presente apenas no hub.csv; dados preservados em dúvida.",
        )
        return True

    assert reg_tribunal is not None
    origem_tribunal = f"tribunal.csv (L{reg_tribunal.linha})"
    origem = (
        f"{origem_tribunal}, apresentacoes.json (item {reg_apresentacao.indice})"
        if reg_apresentacao is not None
        else origem_tribunal
    )
    registrar_ocorrencia_precatorio(
        ocorrencias,
        problema="P4",
        categoria="em_duvida",
        identificador=cnj_formatado,
        origem=origem,
        campo="cobertura",
        valor_original="presente apenas no tribunal.csv",
        motivo="Presente apenas no tribunal.csv; incluído em dúvida.",
    )
    return True


def _resolver_ente(
    reg_tribunal: RegistroTribunalIndexado | None,
    reg_hub: RegistroHubIndexado | None,
    cnj_formatado: str,
    ocorrencias: list[RegistroOcorrencia],
) -> tuple[str, bool]:
    if reg_tribunal is None or reg_hub is None:
        base = reg_hub if reg_hub is not None else reg_tribunal
        assert base is not None
        ente = base.ente_devedor
        origem = (
            f"hub.csv (L{reg_hub.linha})"
            if reg_hub is not None
            else f"tribunal.csv (L{base.linha})"
        )
    elif reg_hub.ente_devedor == reg_tribunal.ente_devedor:
        ente = reg_hub.ente_devedor
        origem = f"tribunal.csv (L{reg_tribunal.linha}) x hub.csv (L{reg_hub.linha})"
    else:
        origem = f"tribunal.csv (L{reg_tribunal.linha}) x hub.csv (L{reg_hub.linha})"
        ente_hub = reg_hub.ente_devedor
        ente_tribunal = reg_tribunal.ente_devedor
        if (
            ente_hub
            and ente_tribunal
            and chave_texto_normalizada(ente_hub)
            == chave_texto_normalizada(ente_tribunal)
        ):
            preferir_hub = _tem_acento(ente_hub) and not _tem_acento(ente_tribunal)
            ente_final, valor_original, fonte = (
                (ente_hub, ente_tribunal, "hub")
                if preferir_hub
                else (ente_tribunal, ente_hub, "tribunal")
            )
            registrar_ocorrencia_precatorio(
                ocorrencias,
                problema="P4",
                categoria="corrigido",
                identificador=cnj_formatado,
                origem=origem,
                campo="ente_devedor",
                valor_original=valor_original,
                valor_tratado=ente_final,
                motivo=(
                    f"Falso divergente de grafia/acento; padronizada a grafia "
                    f"do {fonte}."
                ),
            )
            return ente_final, False

        if not ente_hub or not ente_tribunal:
            base_vazia = "hub.csv" if not ente_hub else "tribunal.csv"
            motivo = (
                f"Ente devedor vazio em {base_vazia}; valor do hub preservado "
                "em dúvida."
            )
        else:
            motivo = (
                "Ente devedor diverge entre hub e tribunal; valor do hub preservado."
            )
        registrar_ocorrencia_precatorio(
            ocorrencias,
            problema="P4",
            categoria="em_duvida",
            identificador=cnj_formatado,
            origem=origem,
            campo="ente_devedor",
            valor_original=f"hub={ente_hub!r} | tribunal={ente_tribunal!r}",
            valor_tratado=ente_hub or None,
            motivo=motivo,
        )
        return ente_hub, True

    if not ente:
        registrar_ocorrencia_precatorio(
            ocorrencias,
            problema="P3",
            categoria="em_duvida",
            identificador=cnj_formatado,
            origem=origem,
            campo="ente_devedor",
            valor_original="",
            motivo="Ente devedor vazio após conciliação; processo marcado em dúvida.",
        )
        return "", True
    return ente, False


def _resolver_valor_face(
    reg_tribunal: RegistroTribunalIndexado | None,
    reg_hub: RegistroHubIndexado | None,
    cnj_formatado: str,
    ocorrencias: list[RegistroOcorrencia],
) -> tuple[Decimal, bool]:
    if reg_hub is None:
        assert reg_tribunal is not None
        return reg_tribunal.valor_face, False

    if reg_tribunal is not None and reg_hub.valor_face != reg_tribunal.valor_face:
        registrar_ocorrencia_precatorio(
            ocorrencias,
            problema="P4",
            categoria="em_duvida",
            identificador=cnj_formatado,
            origem=f"tribunal.csv (L{reg_tribunal.linha}) x hub.csv (L{reg_hub.linha})",
            campo="valor_face",
            valor_original=(
                f"hub={reg_hub.valor_face:.2f} | tribunal={reg_tribunal.valor_face:.2f}"
            ),
            valor_tratado=f"{reg_hub.valor_face:.2f}",
            motivo=(
                "Valor de face diverge entre hub e tribunal; valor do hub preservado."
            ),
        )
        return reg_hub.valor_face, True
    return reg_hub.valor_face, False


def _resolver_apresentacao(
    reg_tribunal: RegistroTribunalIndexado | None,
    reg_hub: RegistroHubIndexado | None,
    reg_apresentacao: RegistroApresentacaoIndexado | None,
    cnj_formatado: str,
    ocorrencias: list[RegistroOcorrencia],
) -> tuple[str, str, bool]:
    """Resolve apresentado_em entre hub.csv e apresentacoes.json.

    Retorna (apresentado_em, origem_apresentacao, apresentacao_em_duvida).
    """
    if reg_hub is None:
        assert reg_tribunal is not None
        if reg_apresentacao is not None:
            return (
                reg_apresentacao.apresentado_em,
                f"apresentacoes.json (item {reg_apresentacao.indice})",
                False,
            )
        return "", f"tribunal.csv (L{reg_tribunal.linha})", False

    origem_hub = f"hub.csv (L{reg_hub.linha})"
    if reg_apresentacao is None:
        return reg_hub.apresentado_em, origem_hub, False

    data_hub = _extrair_data_segura(reg_hub.apresentado_em)
    data_apres = _extrair_data_segura(reg_apresentacao.apresentado_em)
    apresentado_final = reg_hub.apresentado_em

    if data_hub is not None and data_apres is not None:
        if data_hub == data_apres:
            return apresentado_final, origem_hub, False
        motivo = (
            f"Apresentação diverge em Brasília: hub ({data_hub}) x "
            f"apresentacoes ({data_apres}); valor do hub preservado."
        )
    elif not reg_hub.apresentado_em and data_apres is not None:
        apresentado_final = reg_apresentacao.apresentado_em
        motivo = (
            "Apresentação ausente no hub; usada data de apresentacoes.json "
            "para cálculo do prazo em dúvida."
        )
    elif reg_hub.apresentado_em == reg_apresentacao.apresentado_em:
        return apresentado_final, origem_hub, False
    elif data_hub is None and data_apres is None:
        motivo = "Apresentação inválida em hub e apresentacoes.json; hub preservado."
    else:
        fonte = "hub.csv" if data_hub is None else "apresentacoes.json"
        motivo = f"Apresentação inválida/ausente em {fonte}; valor do hub preservado."

    registrar_ocorrencia_precatorio(
        ocorrencias,
        problema="P4",
        categoria="em_duvida",
        identificador=cnj_formatado,
        origem=f"{origem_hub} x apresentacoes.json (item {reg_apresentacao.indice})",
        campo="apresentado_em",
        valor_original=(
            f"hub={reg_hub.apresentado_em!r} | "
            f"apresentacoes={reg_apresentacao.apresentado_em!r}"
        ),
        valor_tratado=apresentado_final or None,
        motivo=motivo,
    )
    return apresentado_final, origem_hub, True


def _resolver_prazo(
    *,
    cnj_formatado: str,
    apresentado_em: str,
    prazo_hub_original: str | None,
    origem_hub: str | None,
    origem_apresentacao: str,
    apresentacao_em_duvida: bool,
    ocorrencias: list[RegistroOcorrencia],
) -> tuple[str, bool]:
    try:
        data_civil, data_prazo = calcular_prazo_constitucional(apresentado_em)
    except ValueError:
        prazo_mantido = prazo_hub_original or ""
        if not apresentacao_em_duvida:
            registrar_ocorrencia_precatorio(
                ocorrencias,
                problema="P2",
                categoria="em_duvida",
                identificador=cnj_formatado,
                origem=origem_apresentacao,
                campo="apresentado_em",
                valor_original=apresentado_em,
                valor_tratado=prazo_mantido or None,
                motivo=(
                    "Apresentação ausente/inválida; prazo constitucional "
                    "não recalculado."
                ),
            )
        return prazo_mantido, True

    prazo_calculado = data_prazo.isoformat()
    if prazo_hub_original is not None and prazo_hub_original != prazo_calculado:
        assert origem_hub is not None
        acao = "preenchido" if prazo_hub_original == "" else "recalculado"
        motivo = (
            f"Prazo constitucional {acao} para {prazo_calculado} "
            f"({data_civil} BRT, corte inclusivo em 02/04)."
        )
        if _sem_fuso_explicito(apresentado_em):
            motivo += (
                " Premissa explícita: data/hora sem fuso interpretada em Brasília "
                "(America/Sao_Paulo), sujeita à confirmação da operação."
            )
        registrar_ocorrencia_precatorio(
            ocorrencias,
            problema="P2",
            categoria="corrigido",
            identificador=cnj_formatado,
            origem=origem_hub,
            campo="prazo_pagamento",
            valor_original=prazo_hub_original,
            valor_tratado=prazo_calculado,
            motivo=motivo,
        )
    return prazo_calculado, False


def conciliar_precatorios(dados: DadosBrutos) -> ResultadoConciliacaoPrecatorios:
    """Concilia cadastros de precatórios (tribunal, hub e apresentações) e prazos."""
    indice = indexar_precatorios(dados)
    ocorrencias = list(indice.ocorrencias)
    precatorios: list[PrecatorioLimpo] = []
    prazos_hub_originais: dict[str, str | None] = {}

    chaves = sorted(set(indice.tribunal) | set(indice.hub) | set(indice.apresentacoes))
    for chave_cnj in chaves:
        reg_tribunal = indice.tribunal.get(chave_cnj)
        reg_hub = indice.hub.get(chave_cnj)
        reg_apresentacao = indice.apresentacoes.get(chave_cnj)

        if reg_tribunal is None and reg_hub is None:
            assert reg_apresentacao is not None
            registrar_ocorrencia_precatorio(
                ocorrencias,
                problema="P4",
                categoria="em_duvida",
                identificador=reg_apresentacao.cnj_formatado,
                origem=f"apresentacoes.json (item {reg_apresentacao.indice})",
                campo="cobertura",
                valor_original=reg_apresentacao.apresentado_em,
                motivo=(
                    "Processo só em apresentacoes.json; precatório incompleto "
                    "não criado."
                ),
            )
            continue

        cnj_formatado = formatar_cnj(chave_cnj)
        prazo_hub = reg_hub.prazo_pagamento if reg_hub is not None else None
        origem_hub = f"hub.csv (L{reg_hub.linha})" if reg_hub is not None else None

        duvida_cobertura = _registrar_cobertura(
            reg_tribunal, reg_hub, reg_apresentacao, cnj_formatado, ocorrencias
        )
        ente_devedor, duvida_ente = _resolver_ente(
            reg_tribunal, reg_hub, cnj_formatado, ocorrencias
        )
        valor_face, duvida_valor = _resolver_valor_face(
            reg_tribunal, reg_hub, cnj_formatado, ocorrencias
        )
        apresentado_em, origem_apresentacao, apresentacao_em_duvida = (
            _resolver_apresentacao(
                reg_tribunal, reg_hub, reg_apresentacao, cnj_formatado, ocorrencias
            )
        )
        prazo_pagamento, duvida_prazo = _resolver_prazo(
            cnj_formatado=cnj_formatado,
            apresentado_em=apresentado_em,
            prazo_hub_original=prazo_hub,
            origem_hub=origem_hub,
            origem_apresentacao=origem_apresentacao,
            apresentacao_em_duvida=apresentacao_em_duvida,
            ocorrencias=ocorrencias,
        )

        tem_duvida = any(
            (
                chave_cnj in indice.chaves_duplicadas_conflitantes,
                duvida_cobertura,
                duvida_ente,
                duvida_valor,
                apresentacao_em_duvida,
                duvida_prazo,
            )
        )
        status: StatusConciliacao = "em_duvida" if tem_duvida else "conciliado"
        prazos_hub_originais[chave_cnj] = prazo_hub
        precatorios.append(
            PrecatorioLimpo(
                numero_processo=chave_cnj,
                ente_devedor=ente_devedor,
                valor_face=valor_face,
                apresentado_em=apresentado_em,
                prazo_pagamento=prazo_pagamento,
                status_conciliacao=status,
            )
        )

    return ResultadoConciliacaoPrecatorios(
        precatorios=tuple(precatorios),
        chaves_hub=frozenset(indice.hub),
        chaves_tribunal=frozenset(indice.tribunal),
        prazos_hub_originais=MappingProxyType(prazos_hub_originais),
        ocorrencias=tuple(ocorrencias),
    )
