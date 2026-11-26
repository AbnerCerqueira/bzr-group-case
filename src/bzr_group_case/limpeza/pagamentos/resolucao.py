from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from decimal import Decimal
from types import MappingProxyType

from bzr_group_case.limpeza.entrada.normalizacao import DUAS_CASAS
from bzr_group_case.limpeza.modelos import (
    DadosBrutos,
    DestinoPagamento,
    PagamentoLimpo,
    ProblemaDiagnostico,
    RastreamentoPagamento,
    RegistroOcorrencia,
    ResultadoLimpezaPagamentos,
)
from bzr_group_case.limpeza.pagamentos.validacao import (
    ItemPagamentoValidado,
    PagamentoInvalido,
    PagamentoValido,
    registrar_ocorrencia_pagamento,
    validar_item_pagamento,
)


def _ordenar_problemas(
    problemas: Sequence[ProblemaDiagnostico],
) -> tuple[ProblemaDiagnostico, ...]:
    return tuple(sorted(set(problemas)))


def _rastrear_item(
    item: ItemPagamentoValidado,
    *,
    destino: DestinoPagamento,
    problemas: Sequence[ProblemaDiagnostico],
    motivo: str,
) -> RastreamentoPagamento:
    if isinstance(item, PagamentoInvalido):
        return RastreamentoPagamento(
            indice=item.indice,
            evento_id=item.evento_id_exibicao,
            numero_processo=item.numero_processo,
            tipo=item.tipo,
            valor_original=item.valor_original,
            data_pagamento=item.data_pagamento,
            atualizado_em=item.atualizado_em,
            destino=destino,
            problemas=_ordenar_problemas(problemas),
            motivo=motivo,
        )
    return RastreamentoPagamento(
        indice=item.indice,
        evento_id=item.evento_id,
        numero_processo=item.cnj_formatado,
        tipo=item.tipo,
        valor_original=item.valor_original,
        data_pagamento=item.data_pagamento,
        atualizado_em=item.atualizado_em,
        destino=destino,
        problemas=_ordenar_problemas(problemas),
        motivo=motivo,
    )


def _descartar_invalido(
    item: PagamentoInvalido,
    *,
    ocorrencias: list[RegistroOcorrencia],
    rastreados: list[RastreamentoPagamento],
) -> None:
    ocorrencias.extend(item.ocorrencias_erro)
    problemas: list[ProblemaDiagnostico] = [oc.problema for oc in item.ocorrencias_erro]
    motivo = "; ".join(oc.motivo for oc in item.ocorrencias_erro)
    rastreados.append(
        _rastrear_item(
            item,
            destino="descartado",
            problemas=problemas,
            motivo=motivo,
        )
    )


def _resumir_versao(item: PagamentoValido) -> str:
    return (
        f"processo={item.cnj_formatado}, tipo={item.tipo}, "
        f"valor={item.valor:.2f}, data={item.data_pagamento}, "
        f"atualizado_em={item.atualizado_em}"
    )


def _resumir_diferenca_retificacao(
    anterior: PagamentoValido,
    vencedor: PagamentoValido,
) -> tuple[str, str]:
    campos_anteriores: list[str] = []
    campos_vencedor: list[str] = []
    pares = (
        ("processo", anterior.cnj_formatado, vencedor.cnj_formatado),
        ("tipo", anterior.tipo, vencedor.tipo),
        ("valor", f"{anterior.valor:.2f}", f"{vencedor.valor:.2f}"),
        ("data_pagamento", anterior.data_pagamento, vencedor.data_pagamento),
    )
    for nome, val_ant, val_venc in pares:
        if val_ant != val_venc:
            campos_anteriores.append(f"{nome}={val_ant}")
            campos_vencedor.append(f"{nome}={val_venc}")
    return (
        f"{', '.join(campos_anteriores)} ({anterior.atualizado_em})",
        f"{', '.join(campos_vencedor)} ({vencedor.atualizado_em})",
    )


def _resolver_grupo_sem_ordenacao(
    grupo: Sequence[ItemPagamentoValidado],
    *,
    ocorrencias: list[RegistroOcorrencia],
    rastreados: list[RastreamentoPagamento],
) -> None:
    """Descarta grupo multi-item em que algum registro não tem atualizado_em válido."""
    for item in grupo:
        if isinstance(item, PagamentoInvalido):
            _descartar_invalido(item, ocorrencias=ocorrencias, rastreados=rastreados)
            continue
        motivo = (
            "Não foi possível ordenar versões do evento por falta de atualizado_em "
            "válido em outra ocorrência do mesmo evento_id; registro descartado em "
            "dúvida."
        )
        registrar_ocorrencia_pagamento(
            ocorrencias,
            problema="P1",
            categoria="em_duvida",
            identificador=item.evento_id,
            origem=item.origem,
            campo="atualizado_em",
            valor_original=item.atualizado_em,
            motivo=motivo,
        )
        rastreados.append(
            _rastrear_item(
                item,
                destino="descartado",
                problemas=("P1",),
                motivo=motivo,
            )
        )


def _resolver_grupo_mais_recente_invalido(
    grupo: Sequence[ItemPagamentoValidado],
    *,
    ocorrencias: list[RegistroOcorrencia],
    rastreados: list[RastreamentoPagamento],
) -> None:
    """Bloqueia publicação quando a versão mais recente do evento é inválida."""
    for item in grupo:
        if isinstance(item, PagamentoInvalido):
            _descartar_invalido(item, ocorrencias=ocorrencias, rastreados=rastreados)
            continue
        motivo = (
            "Versão mais recente deste evento_id é inválida; versão anterior/irmã "
            "não foi publicada para evitar dado defasado."
        )
        registrar_ocorrencia_pagamento(
            ocorrencias,
            problema="P1",
            categoria="em_duvida",
            identificador=item.evento_id,
            origem=item.origem,
            campo="atualizado_em",
            valor_original=_resumir_versao(item),
            motivo=motivo,
        )
        rastreados.append(
            _rastrear_item(
                item,
                destino="descartado",
                problemas=("P1",),
                motivo=motivo,
            )
        )


def _resolver_empate_conflitante(
    evento_id: str,
    mais_recentes: Sequence[PagamentoValido],
    anteriores: Sequence[ItemPagamentoValidado],
    *,
    ocorrencias: list[RegistroOcorrencia],
    rastreados: list[RastreamentoPagamento],
) -> None:
    """Descarta todo o grupo quando há empate no mesmo atualizado_em com divergência."""
    origens = " x ".join(item.origem for item in mais_recentes)
    resumo_conflito = " | ".join(
        f"item {item.indice}: {_resumir_versao(item)}" for item in mais_recentes
    )
    motivo = (
        f"Empate conflitante no mesmo atualizado_em ({mais_recentes[0].atualizado_em}) "
        "com dados semânticos divergentes; nenhum registro publicado."
    )
    registrar_ocorrencia_pagamento(
        ocorrencias,
        problema="P1",
        categoria="em_duvida",
        identificador=evento_id,
        origem=origens,
        campo="duplicidade",
        valor_original=resumo_conflito,
        motivo=motivo,
    )
    for item in mais_recentes:
        rastreados.append(
            _rastrear_item(
                item,
                destino="descartado",
                problemas=("P1",),
                motivo=motivo,
            )
        )
    for anterior in anteriores:
        if isinstance(anterior, PagamentoInvalido):
            _descartar_invalido(
                anterior, ocorrencias=ocorrencias, rastreados=rastreados
            )
            continue
        rastreados.append(
            _rastrear_item(
                anterior,
                destino="descartado",
                problemas=("P1",),
                motivo=(
                    "Descartado em dúvida devido a empate conflitante na versão "
                    "mais recente do evento."
                ),
            )
        )


def _publicar_ou_descartar_vencedor(
    vencedor: PagamentoValido,
    *,
    chaves_hub: AbstractSet[str],
    chaves_tribunal: AbstractSet[str],
    houve_retificacao: bool,
    ocorrencias: list[RegistroOcorrencia],
    pagamentos: list[PagamentoLimpo],
    rastreados: list[RastreamentoPagamento],
) -> None:
    if vencedor.chave_cnj not in chaves_hub:
        if vencedor.chave_cnj in chaves_tribunal:
            motivo = (
                f"Processo {vencedor.cnj_formatado} presente no tribunal.csv, mas "
                "ausente no hub.csv; pagamento descartado aguardando decisão "
                "operacional sobre cadastro automático."
            )
        else:
            motivo = (
                f"Processo {vencedor.cnj_formatado} ausente no hub.csv e no "
                "tribunal.csv; pagamento órfão descartado."
            )
        registrar_ocorrencia_pagamento(
            ocorrencias,
            problema="P4",
            categoria="descartado",
            identificador=vencedor.evento_id,
            origem=vencedor.origem,
            campo="processo",
            valor_original=vencedor.cnj_formatado,
            motivo=motivo,
        )
        rastreados.append(
            _rastrear_item(
                vencedor,
                destino="descartado",
                problemas=("P4",),
                motivo=motivo,
            )
        )
        return

    problemas: list[ProblemaDiagnostico] = []
    detalhes: list[str] = []

    if houve_retificacao:
        problemas.append("P1")
        detalhes.append("versão mais recente mantida como retificação")

    if vencedor.ocorrencias_pendentes:
        ocorrencias.extend(vencedor.ocorrencias_pendentes)
        problemas.extend(oc.problema for oc in vencedor.ocorrencias_pendentes)
        campos = ", ".join(oc.campo for oc in vencedor.ocorrencias_pendentes)
        detalhes.append(f"campos normalizados ({campos})")

    if vencedor.tipo == "estorno":
        motivo_estorno = (
            "Evento preservado como estorno válido com valor positivo "
            f"({vencedor.valor:.2f}), que deve abater no total pago do processo."
        )
        registrar_ocorrencia_pagamento(
            ocorrencias,
            problema="P2",
            categoria="corrigido",
            identificador=vencedor.evento_id,
            origem=vencedor.origem,
            campo="tipo",
            valor_original=vencedor.tipo,
            valor_tratado=f"-{vencedor.valor:.2f}",
            motivo=motivo_estorno,
        )
        problemas.append("P2")
        detalhes.append("estorno preservado para abater no total pago")

    pagamentos.append(
        PagamentoLimpo(
            evento_id=vencedor.evento_id,
            numero_processo=vencedor.chave_cnj,
            tipo=vencedor.tipo,
            valor=vencedor.valor,
            data_pagamento=vencedor.data_pagamento,
            atualizado_em=vencedor.atualizado_em,
        )
    )
    motivo_mantido = (
        f"Mantido ({'; '.join(detalhes)})."
        if detalhes
        else "Pagamento válido mantido sem ajustes."
    )
    rastreados.append(
        _rastrear_item(
            vencedor,
            destino="mantido",
            problemas=problemas,
            motivo=motivo_mantido,
        )
    )


def _resolver_grupo_com_vencedor(
    mais_recentes: Sequence[PagamentoValido],
    anteriores: Sequence[ItemPagamentoValidado],
    *,
    chaves_hub: AbstractSet[str],
    chaves_tribunal: AbstractSet[str],
    ocorrencias: list[RegistroOcorrencia],
    pagamentos: list[PagamentoLimpo],
    rastreados: list[RastreamentoPagamento],
) -> None:
    vencedor = mais_recentes[0]
    vencedor_vinculado = vencedor.chave_cnj in chaves_hub
    houve_retificacao = False

    for copia in mais_recentes[1:]:
        motivo_copia = (
            f"Duplicata idêntica do evento {vencedor.evento_id} "
            f"(repete {vencedor.origem}); descartada."
        )
        registrar_ocorrencia_pagamento(
            ocorrencias,
            problema="P1",
            categoria="descartado",
            identificador=vencedor.evento_id,
            origem=copia.origem,
            campo="duplicidade",
            valor_original=f"item {copia.indice} (idêntico ao item {vencedor.indice})",
            motivo=motivo_copia,
        )
        rastreados.append(
            _rastrear_item(
                copia,
                destino="deduplicado",
                problemas=("P1",),
                motivo=motivo_copia,
            )
        )

    for anterior in anteriores:
        if isinstance(anterior, PagamentoInvalido):
            _descartar_invalido(
                anterior, ocorrencias=ocorrencias, rastreados=rastreados
            )
            continue

        if anterior.chave_semantica == vencedor.chave_semantica:
            motivo_dup = (
                f"Versão anterior idêntica ({anterior.atualizado_em}) superada "
                f"por {vencedor.origem} ({vencedor.atualizado_em}); deduplicada."
            )
            registrar_ocorrencia_pagamento(
                ocorrencias,
                problema="P1",
                categoria="descartado",
                identificador=vencedor.evento_id,
                origem=anterior.origem,
                campo="duplicidade",
                valor_original=(
                    f"item {anterior.indice} (idêntico ao item {vencedor.indice})"
                ),
                motivo=motivo_dup,
            )
            rastreados.append(
                _rastrear_item(
                    anterior,
                    destino="deduplicado",
                    problemas=("P1",),
                    motivo=motivo_dup,
                )
            )
            continue

        valor_anterior, valor_vencedor = _resumir_diferenca_retificacao(
            anterior, vencedor
        )
        if not vencedor_vinculado:
            motivo_ret_orfao = (
                f"Versão anterior ({anterior.origem}, atualizado_em="
                f"{anterior.atualizado_em}) superada por versão mais recente "
                f"({vencedor.origem}, atualizado_em={vencedor.atualizado_em}) "
                "posteriormente descartada por ausência de vínculo no hub.csv (P4)."
            )
            registrar_ocorrencia_pagamento(
                ocorrencias,
                problema="P1",
                categoria="descartado",
                identificador=vencedor.evento_id,
                origem=f"{anterior.origem} -> {vencedor.origem}",
                campo="retificacao",
                valor_original=valor_anterior,
                motivo=motivo_ret_orfao,
            )
            rastreados.append(
                _rastrear_item(
                    anterior,
                    destino="descartado",
                    problemas=("P1", "P4"),
                    motivo=motivo_ret_orfao,
                )
            )
            continue

        houve_retificacao = True
        motivo_retificacao = (
            f"Versão anterior ({anterior.origem}, atualizado_em="
            f"{anterior.atualizado_em}) substituída pela versão mais recente "
            f"({vencedor.origem}, atualizado_em={vencedor.atualizado_em}). "
            "Premissa explícita: maior atualizado_em prevalece como retificação, "
            "sujeita à confirmação do tribunal."
        )
        registrar_ocorrencia_pagamento(
            ocorrencias,
            problema="P1",
            categoria="corrigido",
            identificador=vencedor.evento_id,
            origem=f"{anterior.origem} -> {vencedor.origem}",
            campo="retificacao",
            valor_original=valor_anterior,
            valor_tratado=valor_vencedor,
            motivo=motivo_retificacao,
        )
        rastreados.append(
            _rastrear_item(
                anterior,
                destino="substituido",
                problemas=("P1",),
                motivo=motivo_retificacao,
            )
        )

    _publicar_ou_descartar_vencedor(
        vencedor,
        chaves_hub=chaves_hub,
        chaves_tribunal=chaves_tribunal,
        houve_retificacao=houve_retificacao,
        ocorrencias=ocorrencias,
        pagamentos=pagamentos,
        rastreados=rastreados,
    )


def limpar_pagamentos(
    dados: DadosBrutos,
    *,
    chaves_hub: AbstractSet[str],
    chaves_tribunal: AbstractSet[str] = frozenset(),
) -> ResultadoLimpezaPagamentos:
    """Valida, deduplica, resolve retificações e vincula pagamentos ao hub."""
    ocorrencias: list[RegistroOcorrencia] = []
    pagamentos: list[PagamentoLimpo] = []
    rastreados: list[RastreamentoPagamento] = []
    grupos: dict[str, list[ItemPagamentoValidado]] = {}

    for indice, registro in dados.pagamentos:
        validado = validar_item_pagamento(indice, registro)
        if validado.evento_id is None:
            assert isinstance(validado, PagamentoInvalido)
            _descartar_invalido(
                validado, ocorrencias=ocorrencias, rastreados=rastreados
            )
            continue
        grupos.setdefault(validado.evento_id, []).append(validado)

    for evento_id, grupo in grupos.items():
        if len(grupo) == 1 and isinstance(grupo[0], PagamentoInvalido):
            _descartar_invalido(
                grupo[0], ocorrencias=ocorrencias, rastreados=rastreados
            )
            continue

        if len(grupo) > 1 and any(item.instante is None for item in grupo):
            _resolver_grupo_sem_ordenacao(
                grupo, ocorrencias=ocorrencias, rastreados=rastreados
            )
            continue

        instantes = [item.instante for item in grupo if item.instante is not None]
        max_instante = max(instantes)
        mais_recentes = [item for item in grupo if item.instante == max_instante]
        anteriores = [
            item
            for item in grupo
            if item.instante is not None and item.instante < max_instante
        ]

        if any(isinstance(item, PagamentoInvalido) for item in mais_recentes):
            _resolver_grupo_mais_recente_invalido(
                grupo, ocorrencias=ocorrencias, rastreados=rastreados
            )
            continue

        mais_recentes_validos = [
            item for item in mais_recentes if isinstance(item, PagamentoValido)
        ]
        chaves_semanticas = {item.chave_semantica for item in mais_recentes_validos}
        if len(chaves_semanticas) > 1:
            _resolver_empate_conflitante(
                evento_id,
                mais_recentes_validos,
                anteriores,
                ocorrencias=ocorrencias,
                rastreados=rastreados,
            )
            continue

        _resolver_grupo_com_vencedor(
            mais_recentes_validos,
            anteriores,
            chaves_hub=chaves_hub,
            chaves_tribunal=chaves_tribunal,
            ocorrencias=ocorrencias,
            pagamentos=pagamentos,
            rastreados=rastreados,
        )

    pagamentos_ordenados = tuple(
        sorted(
            pagamentos,
            key=lambda p: (p.numero_processo, p.data_pagamento, p.evento_id),
        )
    )
    rastreados_ordenados = tuple(sorted(rastreados, key=lambda item: item.indice))
    return ResultadoLimpezaPagamentos(
        pagamentos=pagamentos_ordenados,
        itens_rastreados=rastreados_ordenados,
        ocorrencias=tuple(ocorrencias),
    )


def resumir_valor_liquido_arquivo(
    pagamentos: Sequence[PagamentoLimpo],
) -> Mapping[str, Decimal]:
    """Calcula o efeito líquido (pagamentos - estornos) apenas dos eventos do arquivo.

    Não representa o saldo histórico acumulado no banco de dados. Retorna valores com
    duas casas decimais ordenados por ``numero_processo``, preservando resultados
    negativos caso os estornos superem os pagamentos no arquivo.
    """
    totais: dict[str, Decimal] = {}
    for pagamento in pagamentos:
        acumulado = totais.get(pagamento.numero_processo, Decimal("0.00"))
        delta = pagamento.valor if pagamento.tipo == "pagamento" else -pagamento.valor
        total = (acumulado + delta).quantize(DUAS_CASAS)
        totais[pagamento.numero_processo] = Decimal("0.00") if total == 0 else total
    return MappingProxyType({chave: totais[chave] for chave in sorted(totais)})
