import json
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

from bzr_group_case.comum import (
    DIRETORIO_DADOS,
    MARCADOR_CSS_BASE,
    RAIZ_PROJETO,
    carregar_css_base_painel,
    extrair_digitos_cnj,
    rotulo_arquivo,
)
from bzr_group_case.limpeza.entrada.normalizacao import formatar_cnj
from bzr_group_case.limpeza.modelos import (
    CategoriaOcorrencia,
    DestinoPagamento,
    PagamentoLimpo,
    ProblemaDiagnostico,
    RastreamentoPagamento,
    RegistroOcorrencia,
    ResultadoLimpeza,
)
from bzr_group_case.limpeza.saida.relatorio import (
    coletar_premissas,
    ocorrencia_usa_premissa,
)

CAMINHO_TEMPLATE_HTML = Path(__file__).with_name("painel.html")
CAMINHO_PADRAO_HTML = RAIZ_PROJETO / "docs" / "limpeza.html"
MARCADOR_DADOS = "__DATA__"

_PROBLEMAS: tuple[ProblemaDiagnostico, ...] = ("P1", "P2", "P3", "P4")
_CATEGORIAS: tuple[CategoriaOcorrencia, ...] = (
    "corrigido",
    "descartado",
    "em_duvida",
)
_DESTINOS_PAGAMENTO: tuple[DestinoPagamento, ...] = (
    "mantido",
    "substituido",
    "deduplicado",
    "descartado",
)
_PADRAO_ITEM_PAGAMENTO = re.compile(r"pagamentos\.json \(item (\d+)\)")


def _formatar_decimal(valor: Decimal) -> str:
    return f"{valor:.2f}"


def _extrair_indices_pagamento(origem: str) -> list[int]:
    """Extrai índices 1-based de itens citados em ``pagamentos.json (item N)``."""
    vistos: list[int] = []
    for match in _PADRAO_ITEM_PAGAMENTO.finditer(origem):
        indice = int(match.group(1))
        if indice not in vistos:
            vistos.append(indice)
    return vistos


def _chaves_relacao_pagamentos(
    itens: tuple[RastreamentoPagamento, ...],
) -> dict[int, str]:
    """Identifica vínculos entre eventos repetidos (retificação/duplicata)."""
    por_evento: dict[str, list[RastreamentoPagamento]] = {}
    for item in itens:
        if item.evento_id:
            por_evento.setdefault(item.evento_id, []).append(item)

    relacoes: dict[int, str] = {}
    for grupo in por_evento.values():
        if len(grupo) < 2:
            continue
        mantidos = [g for g in grupo if g.destino == "mantido"]
        nao_substituidos = [
            g for g in grupo if g.destino not in ("substituido", "deduplicado")
        ]
        if mantidos:
            referencia = mantidos[0]
        elif nao_substituidos:
            referencia = nao_substituidos[0]
        else:
            continue

        substituidos = [
            g
            for g in grupo
            if g.destino == "substituido" and g.indice != referencia.indice
        ]
        deduplicados = [
            g
            for g in grupo
            if g.destino == "deduplicado" and g.indice != referencia.indice
        ]

        for item in substituidos:
            relacoes[item.indice] = f"Substituído pelo item #{referencia.indice}"
        for item in deduplicados:
            relacoes[item.indice] = f"Duplicata do item #{referencia.indice}"

        partes_ref: list[str] = []
        if substituidos:
            ids_sub = ", ".join(f"#{s.indice}" for s in substituidos)
            partes_ref.append(f"Retifica {ids_sub}")
        if deduplicados:
            ids_dup = ", ".join(f"#{d.indice}" for d in deduplicados)
            partes_ref.append(f"Duplicata removida: {ids_dup}")
        if partes_ref:
            relacoes[referencia.indice] = " · ".join(partes_ref)

    return relacoes


def _chave_cnj_para_evento(
    item: RastreamentoPagamento,
    chaves_conhecidas: set[str],
) -> str | None:
    """Resolve a chave de 20 dígitos associada a um evento rastreado, se houver."""
    if not item.numero_processo:
        return None
    digitos = extrair_digitos_cnj(item.numero_processo)
    if len(digitos) == 20 and digitos in chaves_conhecidas:
        return digitos
    return None


def _chave_cnj_para_ocorrencia(
    ocorrencia: RegistroOcorrencia,
    pagamento_indices: list[int],
    chaves_conhecidas: set[str],
    indice_para_chave: dict[int, str],
    evento_para_chave: dict[str, str],
) -> str | None:
    """Resolve a chave de 20 dígitos associada a uma ocorrência, se aplicável."""
    if ocorrencia.entidade == "precatorio":
        digitos = extrair_digitos_cnj(ocorrencia.identificador)
        return digitos if len(digitos) == 20 and digitos in chaves_conhecidas else None
    if ocorrencia.entidade == "pagamento":
        # Em retificações ("item 1 -> item 9"), o último índice é o vencedor.
        for indice in reversed(pagamento_indices):
            chave = indice_para_chave.get(indice)
            if chave:
                return chave
        return evento_para_chave.get(ocorrencia.identificador)
    return None


def serializar_resultado_limpeza(resultado: ResultadoLimpeza) -> dict[str, Any]:
    """Serializa ``ResultadoLimpeza`` para estrutura JSON-ready (HTML, JSON, etc.)."""
    precatorios = resultado.precatorios.precatorios
    itens_pag = resultado.pagamentos.itens_rastreados
    pags_limpos = resultado.pagamentos.pagamentos
    ocorrencias = resultado.ocorrencias
    verificacoes = resultado.verificacoes

    chaves_conhecidas = {p.numero_processo for p in precatorios}
    pags_limpos_por_evento = {p.evento_id: p for p in pags_limpos}
    pags_limpos_por_chave: dict[str, list[PagamentoLimpo]] = {}
    for ev in pags_limpos:
        pags_limpos_por_chave.setdefault(ev.numero_processo, []).append(ev)

    relacoes_pag = _chaves_relacao_pagamentos(itens_pag)

    indice_para_chave: dict[int, str] = {}
    evento_para_chave: dict[str, str] = {}
    evento_tem_mantido: set[str] = set()
    for item in itens_pag:
        chave = _chave_cnj_para_evento(item, chaves_conhecidas)
        if not chave:
            continue
        indice_para_chave[item.indice] = chave
        if item.evento_id:
            if item.destino == "mantido":
                evento_para_chave[item.evento_id] = chave
                evento_tem_mantido.add(item.evento_id)
            elif item.evento_id not in evento_tem_mantido:
                evento_para_chave.setdefault(item.evento_id, chave)

    status_prec = Counter(p.status_conciliacao for p in precatorios)
    destinos_pag = Counter(item.destino for item in itens_pag)
    contagem_oc = Counter((oc.problema, oc.categoria) for oc in ocorrencias)
    total_ok = sum(1 for v in verificacoes if v.ok)

    matriz = []
    for problema in _PROBLEMAS:
        corr = contagem_oc[(problema, "corrigido")]
        desc = contagem_oc[(problema, "descartado")]
        duv = contagem_oc[(problema, "em_duvida")]
        matriz.append(
            {
                "problema": problema,
                "corrigido": corr,
                "descartado": desc,
                "em_duvida": duv,
                "total": corr + desc + duv,
            }
        )

    ocorrencias_serializadas: list[dict[str, Any]] = []
    oc_ids_por_pagamento: dict[int, list[int]] = {}
    indices_valor_normalizado: set[int] = set()

    for idx, oc in enumerate(ocorrencias, start=1):
        pagamento_indices = (
            _extrair_indices_pagamento(oc.origem) if oc.entidade == "pagamento" else []
        )
        chave_cnj = _chave_cnj_para_ocorrencia(
            oc,
            pagamento_indices,
            chaves_conhecidas,
            indice_para_chave,
            evento_para_chave,
        )
        for pag_idx in pagamento_indices:
            oc_ids_por_pagamento.setdefault(pag_idx, []).append(idx)
            if oc.campo == "valor" and oc.categoria == "corrigido":
                indices_valor_normalizado.add(pag_idx)

        ocorrencias_serializadas.append(
            {
                "id": idx,
                "problema": oc.problema,
                "categoria": oc.categoria,
                "entidade": oc.entidade,
                "identificador": oc.identificador,
                "chave_cnj": chave_cnj,
                "pagamento_indices": pagamento_indices,
                "origem": oc.origem,
                "campo": oc.campo,
                "antes": oc.valor_original,
                "depois": oc.valor_tratado,
                "motivo": oc.motivo,
                "usa_premissa": ocorrencia_usa_premissa(oc),
            }
        )

    prazos_sem_fuso, retificacoes = coletar_premissas(ocorrencias)

    def _serializar_afetado(oc: RegistroOcorrencia) -> dict[str, Any]:
        pag_indices = (
            _extrair_indices_pagamento(oc.origem) if oc.entidade == "pagamento" else []
        )
        chave_cnj = _chave_cnj_para_ocorrencia(
            oc,
            pag_indices,
            chaves_conhecidas,
            indice_para_chave,
            evento_para_chave,
        )
        return {
            "entidade": oc.entidade,
            "identificador": oc.identificador,
            "chave_cnj": chave_cnj,
            "antes": oc.valor_original,
            "depois": oc.valor_tratado,
        }

    premissas = [
        {
            "id": "fuso_brasilia_borda_02_04",
            "titulo": (
                "Fuso horário de Brasília (America/Sao_Paulo) para datas sem hora "
                "na borda de 02/04"
            ),
            "descricao": (
                "Valores de apresentado_em sem horário ou sem fuso explícito são "
                "interpretados no horário oficial de Brasília para aplicação do corte "
                "constitucional inclusivo em 02/04."
            ),
            "confirmar_com": "Operação",
            "afetados": [_serializar_afetado(oc) for oc in prazos_sem_fuso],
        },
        {
            "id": "retificacao_maior_atualizado_em",
            "titulo": "Retificação de pagamento pelo maior atualizado_em",
            "descricao": (
                "Quando o mesmo evento_id aparece múltiplas vezes com dados "
                "divergentes, prevalece a versão mais recente como retificação."
            ),
            "confirmar_com": "Tribunal",
            "afetados": [_serializar_afetado(oc) for oc in retificacoes],
        },
    ]

    pagamentos_serializados: list[dict[str, Any]] = []
    for item in itens_pag:
        chave_cnj = indice_para_chave.get(item.indice)
        limpo = (
            pags_limpos_por_evento.get(item.evento_id)
            if item.destino == "mantido"
            else None
        )
        pagamentos_serializados.append(
            {
                "indice": item.indice,
                "evento_id": item.evento_id,
                "processo": item.numero_processo,
                "chave_cnj": chave_cnj,
                "tipo": item.tipo,
                "valor_original": item.valor_original,
                "valor_limpo": _formatar_decimal(limpo.valor) if limpo else None,
                "valor_normalizado": item.indice in indices_valor_normalizado,
                "data_pagamento": item.data_pagamento,
                "atualizado_em": item.atualizado_em,
                "destino": item.destino,
                "problemas": list(item.problemas),
                "ocorrencia_ids": oc_ids_por_pagamento.get(item.indice, []),
                "motivo": item.motivo,
                "relacao": relacoes_pag.get(item.indice),
            }
        )

    ocs_por_chave: dict[str, list[dict[str, Any]]] = {}
    for oc_dict in ocorrencias_serializadas:
        if oc_dict["chave_cnj"]:
            ocs_por_chave.setdefault(oc_dict["chave_cnj"], []).append(oc_dict)

    pags_por_chave: dict[str, list[dict[str, Any]]] = {}
    for pag_dict in pagamentos_serializados:
        if pag_dict["chave_cnj"]:
            pags_por_chave.setdefault(pag_dict["chave_cnj"], []).append(pag_dict)

    precatorios_serializados: list[dict[str, Any]] = []
    for p in precatorios:
        cnj = formatar_cnj(p.numero_processo)
        prazo_antes = resultado.precatorios.prazos_hub_originais.get(p.numero_processo)
        ocs_proc = ocs_por_chave.get(p.numero_processo, [])
        pags_proc = pags_por_chave.get(p.numero_processo, [])
        problemas_proc = sorted(
            {
                *(oc["problema"] for oc in ocs_proc),
                *(prob for pag in pags_proc for prob in pag["problemas"]),
            }
        )
        efeito_liq = resultado.valor_liquido_arquivo.get(
            p.numero_processo, Decimal("0.00")
        )
        em_hub = p.numero_processo in resultado.precatorios.chaves_hub
        em_tribunal = p.numero_processo in resultado.precatorios.chaves_tribunal
        if em_hub and em_tribunal:
            cobertura = "ambas"
        elif em_hub:
            cobertura = "somente_hub"
        elif em_tribunal:
            cobertura = "somente_tribunal"
        else:
            cobertura = "desconhecida"

        precatorios_serializados.append(
            {
                "cnj": cnj,
                "chave": p.numero_processo,
                "ente_devedor": p.ente_devedor,
                "valor_face": _formatar_decimal(p.valor_face),
                "apresentado_em": p.apresentado_em,
                "prazo_antes": prazo_antes,
                "prazo_depois": p.prazo_pagamento,
                "prazo_alterado": prazo_antes is not None
                and prazo_antes != p.prazo_pagamento,
                "status": p.status_conciliacao,
                "cobertura": cobertura,
                "problemas": problemas_proc,
                "efeito_liquido": _formatar_decimal(efeito_liq),
                "total_eventos_mantidos": sum(
                    1 for pag in pags_proc if pag["destino"] == "mantido"
                ),
                "total_eventos": len(pags_proc),
                "usa_premissa": any(oc["usa_premissa"] for oc in ocs_proc),
            }
        )

    efeito_liquido_lista = []
    for p in precatorios:
        pags_mantidos = pags_limpos_por_chave.get(p.numero_processo, [])
        total_proc = resultado.valor_liquido_arquivo.get(
            p.numero_processo, Decimal("0.00")
        )
        efeito_liquido_lista.append(
            {
                "cnj": formatar_cnj(p.numero_processo),
                "chave": p.numero_processo,
                "eventos": [
                    {
                        "evento_id": ev.evento_id,
                        "tipo": ev.tipo,
                        "valor": _formatar_decimal(ev.valor),
                        "sinal": "+" if ev.tipo == "pagamento" else "-",
                    }
                    for ev in pags_mantidos
                ],
                "efeito_liquido": _formatar_decimal(total_proc),
            }
        )

    return {
        "resumo": {
            "precatorios": {
                "total": len(precatorios),
                "conciliado": status_prec["conciliado"],
                "em_duvida": status_prec["em_duvida"],
            },
            "pagamentos": {
                "total": len(itens_pag),
                **{destino: destinos_pag[destino] for destino in _DESTINOS_PAGAMENTO},
            },
            "ocorrencias": {
                "total": len(ocorrencias),
                **{
                    cat: sum(contagem_oc[(p, cat)] for p in _PROBLEMAS)
                    for cat in _CATEGORIAS
                },
                "com_premissa": sum(
                    1 for oc in ocorrencias_serializadas if oc["usa_premissa"]
                ),
            },
            "validacao": {
                "total": len(verificacoes),
                "ok": total_ok,
                "falhas": len(verificacoes) - total_ok,
                "todas_ok": resultado.todas_verificacoes_ok,
            },
            "total_premissas": len(premissas),
            "arquivos_gerados": [rotulo_arquivo(a) for a in resultado.arquivos_gerados],
        },
        "matriz": matriz,
        "premissas": premissas,
        "precatorios": precatorios_serializados,
        "pagamentos": pagamentos_serializados,
        "ocorrencias": ocorrencias_serializadas,
        "efeito_liquido": efeito_liquido_lista,
        "validacoes": [
            {
                "regra": v.regra,
                "ok": v.ok,
                "detalhes": list(v.detalhes),
            }
            for v in verificacoes
        ],
    }


def gerar_relatorio_html(resultado: ResultadoLimpeza) -> str:
    """Gera a página HTML autocontida da limpeza a partir de ``painel.html``."""
    template = CAMINHO_TEMPLATE_HTML.read_text(encoding="utf-8")
    dados = json.dumps(serializar_resultado_limpeza(resultado), ensure_ascii=False)
    # Escapa <, > e & no JSON embutido para neutralizar </script> e <!-- em HTML5.
    dados_seguros = (
        dados.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    )
    return template.replace(MARCADOR_CSS_BASE, carregar_css_base_painel()).replace(
        MARCADOR_DADOS, dados_seguros
    )


def salvar_relatorio_html(
    resultado: ResultadoLimpeza,
    destino: Path = CAMINHO_PADRAO_HTML,
) -> Path:
    """Grava a página HTML da limpeza em ``destino`` (UTF-8 LF) e retorna o caminho."""
    destino_resolvido = destino.resolve()
    if destino_resolvido.is_relative_to(DIRETORIO_DADOS.resolve()):
        raise ValueError(
            "O destino do painel HTML não pode estar dentro do diretório "
            "de dados brutos."
        )
    if destino.exists() and destino.is_dir():
        raise ValueError(f"O destino do painel HTML é um diretório: {destino}")

    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8", newline="\n") as arquivo:
        arquivo.write(gerar_relatorio_html(resultado))
    return destino
