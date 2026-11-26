from collections import Counter
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path

from bzr_group_case.limpeza.entrada.normalizacao import formatar_cnj
from bzr_group_case.limpeza.modelos import (
    CategoriaOcorrencia,
    DadosBrutos,
    PagamentoLimpo,
    PrecatorioLimpo,
    ProblemaDiagnostico,
    RegistroOcorrencia,
    ResultadoConciliacaoPrecatorios,
    ResultadoLimpezaPagamentos,
    VerificacaoSaida,
)

_PROBLEMAS: tuple[ProblemaDiagnostico, ...] = ("P1", "P2", "P3", "P4")
_CATEGORIAS: tuple[tuple[CategoriaOcorrencia, str], ...] = (
    ("corrigido", "Corrigidos"),
    ("descartado", "Descartados (com motivo)"),
    ("em_duvida", "Em dúvida (sem sobrescrever)"),
)
_ROTULO_CATEGORIA_CURTO: Mapping[CategoriaOcorrencia, str] = {
    "corrigido": "corrigido",
    "descartado": "descartado",
    "em_duvida": "em dúvida",
}


def _plural(quantidade: int, singular: str, plural: str) -> str:
    return f"{quantidade} {singular if quantidade == 1 else plural}"


def _celula(texto: str | None) -> str:
    if texto is None or texto == "":
        return "—"
    limpo = texto.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    return limpo.replace("|", "\\|")


def _tabela(
    cabecalhos: Sequence[str],
    linhas: Sequence[Sequence[str]],
) -> list[str]:
    saida = [
        "| " + " | ".join(_celula(c) for c in cabecalhos) + " |",
        "| " + " | ".join("---" for _ in cabecalhos) + " |",
    ]
    for linha in linhas:
        saida.append("| " + " | ".join(_celula(v) for v in linha) + " |")
    return saida


def _formatar_prazo_transicao(prazo_antes: str | None, prazo_depois: str) -> str:
    antes = prazo_antes if prazo_antes else "—"
    depois = prazo_depois if prazo_depois else "—"
    return f"{antes} → {depois}"


def _resumo_ocorrencias_precatorio(
    ocorrencias_proc: Sequence[RegistroOcorrencia],
) -> str:
    if not ocorrencias_proc:
        return "Sem divergências."
    partes = [
        f"{oc.campo} {_ROTULO_CATEGORIA_CURTO[oc.categoria]} ({oc.problema})"
        for oc in ocorrencias_proc
    ]
    return "; ".join(partes)


def _secao_resumo(
    *,
    dados: DadosBrutos,
    precatorios: ResultadoConciliacaoPrecatorios,
    pagamentos: ResultadoLimpezaPagamentos,
    ocorrencias: Sequence[RegistroOcorrencia],
    verificacoes: Sequence[VerificacaoSaida],
) -> list[str]:
    status_prec = Counter(p.status_conciliacao for p in precatorios.precatorios)
    destinos_pag = Counter(item.destino for item in pagamentos.itens_rastreados)
    contagem_oc = Counter((oc.problema, oc.categoria) for oc in ocorrencias)
    total_ok = sum(1 for v in verificacoes if v.ok)
    rotulo_validacao = (
        f"[OK] {total_ok}/{len(verificacoes)} regras aprovadas"
        if verificacoes and total_ok == len(verificacoes)
        else f"[FALHA] {total_ok}/{len(verificacoes)} regras aprovadas"
    )

    linhas_entidades = [
        (
            "Precatórios",
            str(len(precatorios.precatorios)),
            f"{_plural(status_prec['conciliado'], 'conciliado', 'conciliados')}; "
            f"{status_prec['em_duvida']} em dúvida",
        ),
        (
            "Pagamentos (pagamentos.json)",
            str(len(dados.pagamentos)),
            f"{_plural(destinos_pag['mantido'], 'mantido', 'mantidos')}; "
            f"{_plural(destinos_pag['deduplicado'], 'deduplicado', 'deduplicados')}; "
            f"{_plural(destinos_pag['substituido'], 'substituído', 'substituídos')}; "
            f"{_plural(destinos_pag['descartado'], 'descartado', 'descartados')}",
        ),
        (
            'Validação do "Depois"',
            str(len(verificacoes)),
            rotulo_validacao,
        ),
    ]

    linhas_ocorrencias: list[tuple[str, str, str, str, str]] = []
    for problema in _PROBLEMAS:
        corr = contagem_oc[(problema, "corrigido")]
        desc = contagem_oc[(problema, "descartado")]
        duv = contagem_oc[(problema, "em_duvida")]
        linhas_ocorrencias.append(
            (problema, str(corr), str(desc), str(duv), str(corr + desc + duv))
        )
    tot_corr = sum(contagem_oc[(p, "corrigido")] for p in _PROBLEMAS)
    tot_desc = sum(contagem_oc[(p, "descartado")] for p in _PROBLEMAS)
    tot_duv = sum(contagem_oc[(p, "em_duvida")] for p in _PROBLEMAS)
    linhas_ocorrencias.append(
        (
            "Total",
            str(tot_corr),
            str(tot_desc),
            str(tot_duv),
            str(tot_corr + tot_desc + tot_duv),
        )
    )

    return [
        "# Relatório de Limpeza e Conciliação",
        "",
        "## 1. Resumo executivo",
        "",
        *_tabela(("Frente", "Total", "Distribuição / Status"), linhas_entidades),
        "",
        *_tabela(
            ("Problema", "Corrigido", "Descartado", "Em dúvida", "Total"),
            linhas_ocorrencias,
        ),
    ]


def _secao_premissas(ocorrencias: Sequence[RegistroOcorrencia]) -> list[str]:
    prazos_sem_fuso = [
        oc
        for oc in ocorrencias
        if oc.campo == "prazo_pagamento"
        and oc.categoria == "corrigido"
        and "premissa" in oc.motivo.casefold()
    ]
    retificacoes = [
        oc
        for oc in ocorrencias
        if oc.campo == "retificacao" and oc.categoria == "corrigido"
    ]

    if prazos_sem_fuso:
        afetados_fuso = ", ".join(
            f"`{oc.identificador}` ({oc.valor_original} → {oc.valor_tratado})"
            for oc in prazos_sem_fuso
        )
        detalhe_fuso = f"Aplicada neste lote em: {afetados_fuso}."
    else:
        detalhe_fuso = "Nenhuma ocorrência afetada neste lote."

    if retificacoes:
        afetados_ret = ", ".join(
            f"`{oc.identificador}` ({oc.valor_original} → {oc.valor_tratado})"
            for oc in retificacoes
        )
        detalhe_ret = f"Aplicada neste lote em: {afetados_ret}."
    else:
        detalhe_ret = "Nenhuma ocorrência afetada neste lote."

    return [
        "## 2. Premissas explícitas adotadas",
        "",
        "- **Fuso horário de Brasília (`America/Sao_Paulo`) para datas sem hora "
        "na borda de `02/04`:** valores de `apresentado_em` sem horário ou sem "
        "fuso explícito são interpretados no horário oficial de Brasília para "
        f"aplicação do corte constitucional inclusivo em `02/04`. {detalhe_fuso} "
        "**Sujeita à confirmação da operação antes de produção.**",
        "- **Retificação de pagamento pelo maior `atualizado_em`:** quando o "
        "mesmo `evento_id` aparece múltiplas vezes com dados divergentes, "
        f"prevalece a versão mais recente como retificação. {detalhe_ret} "
        "**Sujeita à confirmação do tribunal antes de produção.**",
    ]


def _secao_precatorios(precatorios: ResultadoConciliacaoPrecatorios) -> list[str]:
    por_cnj: dict[str, list[RegistroOcorrencia]] = {}
    for oc in precatorios.ocorrencias:
        por_cnj.setdefault(oc.identificador, []).append(oc)

    linhas: list[tuple[str, ...]] = []
    for p in precatorios.precatorios:
        cnj = formatar_cnj(p.numero_processo)
        ocs = por_cnj.get(cnj, [])
        problemas = ", ".join(sorted({oc.problema for oc in ocs})) or "—"
        prazo_antes = precatorios.prazos_hub_originais.get(p.numero_processo)
        linhas.append(
            (
                cnj,
                p.numero_processo,
                p.ente_devedor,
                f"{p.valor_face:.2f}",
                p.apresentado_em,
                _formatar_prazo_transicao(prazo_antes, p.prazo_pagamento),
                p.status_conciliacao,
                problemas,
                _resumo_ocorrencias_precatorio(ocs),
            )
        )

    total = len(precatorios.precatorios)
    return [
        f"## 3. Visão 1-para-1 dos precatórios ({total} processos)",
        "",
        *_tabela(
            (
                "CNJ formatado",
                "Chave (20 dígitos)",
                "Ente devedor",
                "Valor de face",
                "Apresentado em",
                "Prazo (antes → depois)",
                "Status",
                "Problemas",
                "Resumo",
            ),
            linhas,
        ),
    ]


def _secao_pagamentos(pagamentos: ResultadoLimpezaPagamentos) -> list[str]:
    linhas = [
        (
            str(item.indice),
            item.evento_id,
            item.numero_processo,
            item.tipo,
            item.valor_original,
            item.data_pagamento,
            item.destino,
            ", ".join(item.problemas) or "—",
            item.motivo,
        )
        for item in pagamentos.itens_rastreados
    ]
    total = len(pagamentos.itens_rastreados)
    return [
        f"## 4. Visão 1-para-1 dos eventos de pagamento "
        f"({total} itens de `pagamentos.json`)",
        "",
        *_tabela(
            (
                "#",
                "evento_id",
                "Processo",
                "Tipo",
                "Valor bruto",
                "Data",
                "Destino",
                "Problemas",
                "Motivo",
            ),
            linhas,
        ),
    ]


def _secao_ocorrencias(ocorrencias: Sequence[RegistroOcorrencia]) -> list[str]:
    linhas_md = ["## 5. Detalhamento das ocorrências por destino", ""]
    cabecalhos = (
        "Problema",
        "Entidade",
        "Identificador",
        "Origem",
        "Campo",
        "Antes",
        "Depois",
        "Motivo",
    )

    for categoria, titulo in _CATEGORIAS:
        filtradas = [oc for oc in ocorrencias if oc.categoria == categoria]
        linhas_md.append(f"### {titulo} ({len(filtradas)})")
        linhas_md.append("")
        if not filtradas:
            linhas_md.append("_Nenhuma ocorrência registrada._")
            linhas_md.append("")
            continue
        linhas_tabela = [
            (
                oc.problema,
                oc.entidade,
                oc.identificador,
                oc.origem,
                oc.campo,
                oc.valor_original,
                oc.valor_tratado if oc.valor_tratado is not None else "—",
                oc.motivo,
            )
            for oc in filtradas
        ]
        linhas_md.extend(_tabela(cabecalhos, linhas_tabela))
        linhas_md.append("")

    return linhas_md[:-1]


def _secao_valor_liquido(
    precatorios: Sequence[PrecatorioLimpo],
    pagamentos: Sequence[PagamentoLimpo],
    valor_liquido_arquivo: Mapping[str, Decimal],
) -> list[str]:
    eventos_por_processo: dict[str, list[PagamentoLimpo]] = {}
    for pagamento in pagamentos:
        eventos_por_processo.setdefault(pagamento.numero_processo, []).append(pagamento)

    linhas: list[tuple[str, ...]] = []
    for chave_cnj, total_liquido in valor_liquido_arquivo.items():
        eventos = eventos_por_processo.get(chave_cnj, [])
        composicao = ", ".join(
            f"{ev.evento_id} ({'+' if ev.tipo == 'pagamento' else '-'}{ev.valor:.2f}"
            f"{' estorno' if ev.tipo == 'estorno' else ''})"
            for ev in eventos
        )
        linhas.append(
            (
                formatar_cnj(chave_cnj),
                chave_cnj,
                composicao or "—",
                f"{total_liquido:.2f}",
            )
        )

    corpo = (
        _tabela(
            (
                "CNJ formatado",
                "Chave (20 dígitos)",
                "Eventos mantidos no arquivo",
                "Efeito líquido no arquivo",
            ),
            linhas,
        )
        if linhas
        else ["_Nenhum pagamento mantido neste arquivo._"]
    )

    sem_eventos = [
        formatar_cnj(p.numero_processo)
        for p in precatorios
        if p.numero_processo not in valor_liquido_arquivo
    ]
    nota_sem_eventos = (
        [
            "",
            "Processos do cadastro sem eventos mantidos neste arquivo "
            "(efeito líquido `0.00` no lote): "
            + ", ".join(f"`{cnj}`" for cnj in sem_eventos)
            + ".",
        ]
        if sem_eventos
        else []
    )

    return [
        "## 6. Efeito líquido apenas dos eventos deste arquivo por processo",
        "",
        "> **Atenção:** os valores abaixo refletem **apenas o efeito líquido "
        "(`pagamentos - estornos`) dos eventos de `pagamentos.json`** "
        "(janela móvel de 7 dias) e **não representam o saldo histórico acumulado "
        "no banco de dados**. Por isso, `total_pago` e `saldo_a_receber` não são "
        "gravados em `precatorios_limpos.csv`.",
        "",
        *corpo,
        *nota_sem_eventos,
    ]


def _secao_validacao(verificacoes: Sequence[VerificacaoSaida]) -> list[str]:
    linhas = [
        (
            "[OK]" if v.ok else "[FALHA]",
            v.regra,
            "; ".join(v.detalhes) if v.detalhes else "Conforme",
        )
        for v in verificacoes
    ]
    return [
        '## 7. Validação automática da base limpa ("Depois")',
        "",
        *_tabela(("Status", "Regra", "Detalhes"), linhas),
    ]


def gerar_relatorio_markdown(
    *,
    dados: DadosBrutos,
    precatorios: ResultadoConciliacaoPrecatorios,
    pagamentos: ResultadoLimpezaPagamentos,
    ocorrencias: Sequence[RegistroOcorrencia],
    valor_liquido_arquivo: Mapping[str, Decimal],
    verificacoes: Sequence[VerificacaoSaida],
) -> str:
    """Gera o relatório auditável de limpeza e conciliação em Markdown."""
    secoes = (
        _secao_resumo(
            dados=dados,
            precatorios=precatorios,
            pagamentos=pagamentos,
            ocorrencias=ocorrencias,
            verificacoes=verificacoes,
        ),
        _secao_premissas(ocorrencias),
        _secao_precatorios(precatorios),
        _secao_pagamentos(pagamentos),
        _secao_ocorrencias(ocorrencias),
        _secao_valor_liquido(
            precatorios.precatorios, pagamentos.pagamentos, valor_liquido_arquivo
        ),
        _secao_validacao(verificacoes),
    )
    return "\n\n".join("\n".join(secao) for secao in secoes) + "\n"


def escrever_relatorio_markdown(conteudo: str, caminho: Path) -> Path:
    """Grava relatorio_limpeza.md em UTF-8 sem BOM com quebras LF."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8", newline="\n") as arquivo:
        arquivo.write(conteudo)
    return caminho
