from collections import Counter
from dataclasses import fields
from decimal import Decimal
from typing import Any

import pytest

from bzr_group_case.limpeza import (
    DIRETORIO_DADOS,
    DadosBrutos,
    PagamentoLimpo,
    TipoPagamento,
    carregar_dados_brutos,
    conciliar_precatorios,
    limpar_pagamentos,
    resumir_valor_liquido_arquivo,
)

CNJ_1, CHAVE_1 = "0012345-10.2019.8.26.0053", "00123451020198260053"
CNJ_2, CHAVE_2 = "0023456-21.2020.8.26.0053", "00234562120208260053"
CNJ_3, CHAVE_3 = "0034567-32.2018.8.26.0405", "00345673220188260405"
CNJ_4, CHAVE_4 = "0045678-43.2021.5.02.0011", "00456784320215020011"
CNJ_6, CHAVE_6 = "0067890-65.2016.8.26.0053", "00678906520168260053"


def _item(
    indice: int = 1,
    *,
    evento_id: Any = "ev-001",
    processo: Any = CNJ_1,
    valor: Any = Decimal("1000.00"),
    data_pagamento: Any = "2025-03-10",
    tipo: Any = "pagamento",
    atualizado_em: Any = "2025-03-10T10:00:00-03:00",
) -> tuple[int, dict[str, Any]]:
    return indice, {
        "evento_id": evento_id,
        "processo": processo,
        "valor": valor,
        "data_pagamento": data_pagamento,
        "tipo": tipo,
        "atualizado_em": atualizado_em,
    }


def _dados(*itens: tuple[int, dict[str, Any]]) -> DadosBrutos:
    return DadosBrutos((), (), (), tuple(itens), ())


def _pag(
    ev: str,
    chave: str,
    tipo: TipoPagamento,
    valor: str,
    data: str,
    atualizado: str,
) -> PagamentoLimpo:
    return PagamentoLimpo(ev, chave, tipo, Decimal(valor), data, atualizado)


def test_pagamento_limpo_contem_apenas_seis_campos_canonicos() -> None:
    campos = tuple(c.name for c in fields(PagamentoLimpo))
    assert campos == (
        "evento_id",
        "numero_processo",
        "tipo",
        "valor",
        "data_pagamento",
        "atualizado_em",
    )


def test_limpar_pagamentos_dados_reais_completos() -> None:
    dados = carregar_dados_brutos(DIRETORIO_DADOS)
    precatorios = conciliar_precatorios(dados)
    res = limpar_pagamentos(
        dados,
        chaves_hub=precatorios.chaves_hub,
        chaves_tribunal=precatorios.chaves_tribunal,
    )

    assert res.pagamentos == (
        _pag(
            "ev-001",
            CHAVE_1,
            "pagamento",
            "15500.00",
            "2025-03-10",
            "2025-03-11T09:00:00-03:00",
        ),
        _pag(
            "ev-002",
            CHAVE_1,
            "pagamento",
            "2500.50",
            "2025-04-10",
            "2025-04-10T09:00:00-03:00",
        ),
        _pag(
            "ev-003",
            CHAVE_2,
            "pagamento",
            "8000.00",
            "2025-05-02",
            "2025-05-02T11:00:00-03:00",
        ),
        _pag(
            "ev-005",
            CHAVE_2,
            "pagamento",
            "1200.00",
            "2025-06-01",
            "2025-06-01T10:00:00-03:00",
        ),
        _pag(
            "ev-006",
            CHAVE_3,
            "pagamento",
            "5000.00",
            "2025-02-20",
            "2025-02-20T10:00:00-03:00",
        ),
        _pag(
            "ev-007",
            CHAVE_3,
            "estorno",
            "5000.00",
            "2025-02-21",
            "2025-02-21T10:00:00-03:00",
        ),
        _pag(
            "ev-008",
            CHAVE_4,
            "pagamento",
            "3000.00",
            "2025-07-15",
            "2025-07-15T10:00:00-03:00",
        ),
    )

    assert len(res.itens_rastreados) == 13
    assert [item.indice for item in res.itens_rastreados] == list(range(1, 14))
    assert Counter(item.destino for item in res.itens_rastreados) == {
        "mantido": 7,
        "deduplicado": 1,
        "substituido": 1,
        "descartado": 4,
    }
    por_indice = {item.indice: item for item in res.itens_rastreados}
    assert (por_indice[1].destino, por_indice[9].destino) == ("substituido", "mantido")
    assert (por_indice[2].data_pagamento, por_indice[4].destino) == (
        "2025-04-10",
        "deduplicado",
    )
    assert (por_indice[5].valor_original, por_indice[5].destino) == (
        "null",
        "descartado",
    )

    assert all(oc.entidade == "pagamento" for oc in res.ocorrencias)
    assert Counter((oc.problema, oc.categoria) for oc in res.ocorrencias) == {
        ("P1", "corrigido"): 1,
        ("P1", "descartado"): 1,
        ("P2", "corrigido"): 1,
        ("P3", "corrigido"): 3,
        ("P3", "descartado"): 3,
        ("P4", "descartado"): 1,
    }

    p1_ret = [
        oc
        for oc in res.ocorrencias
        if oc.problema == "P1" and oc.categoria == "corrigido"
    ]
    assert len(p1_ret) == 1
    assert p1_ret[0].identificador == "ev-001"
    assert "premissa" in p1_ret[0].motivo.casefold()
    assert "tribunal" in p1_ret[0].motivo.casefold()

    p3_corrigidos = {
        (oc.identificador, oc.campo, oc.origem)
        for oc in res.ocorrencias
        if oc.problema == "P3" and oc.categoria == "corrigido"
    }
    assert p3_corrigidos == {
        ("ev-002", "valor", "pagamentos.json (item 2)"),
        ("ev-002", "data_pagamento", "pagamentos.json (item 2)"),
        ("ev-005", "processo", "pagamentos.json (item 6)"),
    }

    resumo = resumir_valor_liquido_arquivo(res.pagamentos)
    assert resumo == {
        CHAVE_1: Decimal("18000.50"),
        CHAVE_2: Decimal("9200.00"),
        CHAVE_3: Decimal("0.00"),
        CHAVE_4: Decimal("3000.00"),
    }
    assert not resumo[CHAVE_3].is_signed()


def test_retificacao_fora_de_ordem_fuso_e_deduplicacao_entre_versoes() -> None:
    dados = _dados(
        _item(
            1,
            evento_id="ev-ordem",
            valor="15500.00",
            atualizado_em="2025-03-11T09:00:00-03:00",
        ),
        _item(
            2,
            evento_id="ev-ordem",
            valor="15000.00",
            atualizado_em="2025-03-10T10:00:00-03:00",
        ),
        _item(
            3,
            evento_id="ev-fuso",
            valor="1000.00",
            atualizado_em="2025-03-10T12:30:00Z",
        ),
        _item(
            4,
            evento_id="ev-fuso",
            valor="1250.00",
            atualizado_em="2025-03-10T10:00:00-03:00",
        ),
        _item(
            5,
            evento_id="ev-empate-igual",
            valor="2.000,00",
            atualizado_em="2025-03-10T13:00:00Z",
        ),
        _item(
            6,
            evento_id="ev-empate-igual",
            valor="2000.00",
            atualizado_em="2025-03-10T10:00:00-03:00",
        ),
        _item(
            7,
            evento_id="ev-antigo-igual",
            valor="500.00",
            atualizado_em="2025-03-10T09:00:00-03:00",
        ),
        _item(
            8,
            evento_id="ev-antigo-igual",
            valor="500.00",
            atualizado_em="2025-03-10T10:00:00-03:00",
        ),
        _item(
            9,
            evento_id="ev-antigo-invalido",
            valor=None,
            atualizado_em="2025-03-10T09:00:00-03:00",
        ),
        _item(
            10,
            evento_id="ev-antigo-invalido",
            valor="750.00",
            atualizado_em="2025-03-10T10:00:00-03:00",
        ),
        _item(
            11,
            evento_id="ev-antigo-invalido",
            valor="750.00",
            atualizado_em="2025-03-10T10:00:00-03:00",
        ),
    )
    res = limpar_pagamentos(dados, chaves_hub={CHAVE_1})
    por_id = {p.evento_id: p.valor for p in res.pagamentos}
    assert por_id == {
        "ev-ordem": Decimal("15500.00"),
        "ev-fuso": Decimal("1250.00"),
        "ev-empate-igual": Decimal("2000.00"),
        "ev-antigo-igual": Decimal("500.00"),
        "ev-antigo-invalido": Decimal("750.00"),
    }
    destinos = {item.indice: item.destino for item in res.itens_rastreados}
    assert destinos == {
        1: "mantido",
        2: "substituido",
        3: "substituido",
        4: "mantido",
        5: "mantido",
        6: "deduplicado",
        7: "deduplicado",
        8: "mantido",
        9: "descartado",
        10: "mantido",
        11: "deduplicado",
    }
    assert any(
        oc.identificador == "ev-antigo-invalido"
        and oc.problema == "P3"
        and oc.categoria == "descartado"
        for oc in res.ocorrencias
    )


def test_protecoes_conflito_mais_recente_invalido_e_sem_timestamp() -> None:
    dados = _dados(
        _item(
            1,
            evento_id="ev-conflito",
            valor="900.00",
            atualizado_em="2025-03-09T10:00:00-03:00",
        ),
        _item(
            2,
            evento_id="ev-conflito",
            valor="1000.00",
            atualizado_em="2025-03-10T13:00:00Z",
        ),
        _item(
            3,
            evento_id="ev-conflito",
            valor="1500.00",
            atualizado_em="2025-03-10T10:00:00-03:00",
        ),
        _item(
            4,
            evento_id="ev-novo-invalido",
            valor="1000.00",
            atualizado_em="2025-03-10T10:00:00-03:00",
        ),
        _item(
            5,
            evento_id="ev-novo-invalido",
            valor=None,
            atualizado_em="2025-03-11T10:00:00-03:00",
        ),
        _item(
            6,
            evento_id="ev-empate-invalido",
            valor="1000.00",
            atualizado_em="2025-03-10T10:00:00-03:00",
        ),
        _item(
            7,
            evento_id="ev-empate-invalido",
            valor=None,
            atualizado_em="2025-03-10T10:00:00-03:00",
        ),
        _item(
            8,
            evento_id="ev-sem-ts",
            valor="1000.00",
            atualizado_em="2025-03-10T10:00:00-03:00",
        ),
        _item(
            9,
            evento_id="ev-sem-ts",
            valor="1100.00",
            atualizado_em="",
        ),
    )
    res = limpar_pagamentos(dados, chaves_hub={CHAVE_1})
    assert res.pagamentos == ()
    assert all(item.destino == "descartado" for item in res.itens_rastreados)

    p1_duvida = {
        oc.identificador
        for oc in res.ocorrencias
        if oc.problema == "P1" and oc.categoria == "em_duvida"
    }
    assert p1_duvida == {
        "ev-conflito",
        "ev-novo-invalido",
        "ev-empate-invalido",
        "ev-sem-ts",
    }

    p3_descarte = {
        (oc.identificador, oc.campo)
        for oc in res.ocorrencias
        if oc.problema == "P3" and oc.categoria == "descartado"
    }
    assert p3_descarte == {
        ("ev-novo-invalido", "valor"),
        ("ev-empate-invalido", "valor"),
        ("ev-sem-ts", "atualizado_em"),
    }


def test_retificacao_com_vencedor_orfao_nao_registra_corrigido() -> None:
    dados = _dados(
        _item(
            1,
            evento_id="ev-orfao",
            processo=CNJ_1,
            valor="1000.00",
            atualizado_em="2025-03-10T10:00:00-03:00",
        ),
        _item(
            2,
            evento_id="ev-orfao",
            processo=CNJ_6,
            valor="1200.00",
            atualizado_em="2025-03-11T10:00:00-03:00",
        ),
    )
    res = limpar_pagamentos(dados, chaves_hub={CHAVE_1}, chaves_tribunal={CHAVE_6})
    assert res.pagamentos == ()
    assert all(item.destino == "descartado" for item in res.itens_rastreados)
    assert res.itens_rastreados[0].problemas == ("P1", "P4")
    assert res.itens_rastreados[1].problemas == ("P4",)
    assert Counter((oc.problema, oc.categoria) for oc in res.ocorrencias) == {
        ("P1", "descartado"): 1,
        ("P4", "descartado"): 1,
    }


def test_normalizacao_de_espacos_caixa_e_atualizado_em_com_e_sem_fuso() -> None:
    dados = _dados(
        _item(
            1,
            evento_id=" ev-norm ",
            processo=CHAVE_1,
            tipo=" ESTORNO ",
            valor="1.250,50",
            data_pagamento="10/04/2025",
            atualizado_em="2025-04-10T09:00:00",
        ),
        _item(
            2,
            evento_id="ev-z-espaco",
            atualizado_em=" 2025-04-10T12:00:00Z ",
        ),
        _item(
            3,
            evento_id="ev-offset-seg",
            atualizado_em="2025-04-10T09:00:00-03:00:00",
        ),
    )
    res = limpar_pagamentos(dados, chaves_hub={CHAVE_1})
    por_id = {p.evento_id: p for p in res.pagamentos}
    assert por_id["ev-norm"] == _pag(
        "ev-norm",
        CHAVE_1,
        "estorno",
        "1250.50",
        "2025-04-10",
        "2025-04-10T09:00:00-03:00",
    )
    assert por_id["ev-z-espaco"].atualizado_em == "2025-04-10T12:00:00Z"
    assert por_id["ev-offset-seg"].atualizado_em == "2025-04-10T09:00:00-03:00:00"

    p3_por_id = {
        (oc.identificador, oc.campo)
        for oc in res.ocorrencias
        if oc.problema == "P3" and oc.categoria == "corrigido"
    }
    assert p3_por_id == {
        ("ev-norm", "evento_id"),
        ("ev-norm", "processo"),
        ("ev-norm", "tipo"),
        ("ev-norm", "valor"),
        ("ev-norm", "data_pagamento"),
        ("ev-norm", "atualizado_em"),
        ("ev-z-espaco", "atualizado_em"),
    }
    assert any(
        oc.identificador == "ev-norm"
        and oc.problema == "P2"
        and oc.categoria == "corrigido"
        for oc in res.ocorrencias
    )


@pytest.mark.parametrize(
    ("kwargs", "chaves_tribunal", "problema", "campo", "deve_conter", "nao_conter"),
    [
        ({"valor": None}, frozenset(), "P3", "valor", "nulo", ""),
        ({"valor": 0}, frozenset(), "P3", "valor", "valor > 0", "estorno"),
        (
            {"valor": -200, "tipo": "pagamento"},
            frozenset(),
            "P3",
            "valor",
            "estorno",
            "",
        ),
        ({"valor": -50, "tipo": "estorno"}, frozenset(), "P3", "valor", "inverter", ""),
        ({"tipo": "ajuste"}, frozenset(), "P3", "tipo", "inválido", ""),
        ({"data_pagamento": "2025-02-30"}, frozenset(), "P3", "data_pagamento", "", ""),
        ({"evento_id": "   "}, frozenset(), "P3", "evento_id", "", ""),
        ({"processo": ""}, frozenset(), "P3", "processo", "", ""),
        ({"processo": "12345"}, frozenset(), "P3", "processo", "", ""),
        (
            {"processo": CNJ_6},
            frozenset({CHAVE_6}),
            "P4",
            "processo",
            "tribunal.csv",
            "",
        ),
        (
            {"processo": CNJ_6},
            frozenset(),
            "P4",
            "processo",
            "ausente no hub.csv e no tribunal.csv",
            "",
        ),
    ],
)
def test_descartes_obrigatorios_por_contrato_ou_vinculo(
    kwargs: dict[str, Any],
    chaves_tribunal: frozenset[str],
    problema: str,
    campo: str,
    deve_conter: str,
    nao_conter: str,
) -> None:
    res = limpar_pagamentos(
        _dados(_item(1, **kwargs)),
        chaves_hub={CHAVE_1},
        chaves_tribunal=chaves_tribunal,
    )
    assert res.pagamentos == ()
    assert len(res.itens_rastreados) == 1
    assert res.itens_rastreados[0].destino == "descartado"
    assert len(res.ocorrencias) == 1
    oc = res.ocorrencias[0]
    assert (oc.problema, oc.categoria, oc.campo) == (problema, "descartado", campo)
    if deve_conter:
        assert deve_conter in oc.motivo.casefold()
    if nao_conter:
        assert nao_conter not in oc.motivo.casefold()


def test_resumir_valor_liquido_arquivo_abate_estornos_e_preserva_negativo() -> None:
    pagamentos = (
        _pag(
            "ev-1",
            CHAVE_2,
            "pagamento",
            "5000.00",
            "2025-02-20",
            "2025-02-20T10:00:00-03:00",
        ),
        _pag(
            "ev-2",
            CHAVE_2,
            "estorno",
            "5000.00",
            "2025-02-21",
            "2025-02-21T10:00:00-03:00",
        ),
        _pag(
            "ev-3",
            CHAVE_1,
            "pagamento",
            "1000.00",
            "2025-03-01",
            "2025-03-01T10:00:00-03:00",
        ),
        _pag(
            "ev-4",
            CHAVE_1,
            "estorno",
            "1250.50",
            "2025-03-02",
            "2025-03-02T10:00:00-03:00",
        ),
    )
    resumo = resumir_valor_liquido_arquivo(pagamentos)
    assert list(resumo.items()) == [
        (CHAVE_1, Decimal("-250.50")),
        (CHAVE_2, Decimal("0.00")),
    ]
    assert not resumo[CHAVE_2].is_signed()
