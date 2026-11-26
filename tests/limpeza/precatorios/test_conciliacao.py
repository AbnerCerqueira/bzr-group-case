from decimal import Decimal
from typing import Any

import pytest

from bzr_group_case.limpeza import (
    DadosBrutos,
    conciliar_precatorios,
)

CNJ_1, CHAVE_1 = "0012345-10.2019.8.26.0053", "00123451020198260053"
CNJ_2, CHAVE_2 = "0023456-21.2020.8.26.0053", "00234562120208260053"
CNJ_3, CHAVE_3 = "0034567-32.2018.8.26.0405", "00345673220188260405"
CNJ_4, CHAVE_4 = "0045678-43.2021.5.02.0011", "00456784320215020011"


def _tribunal(
    linha: int = 2, proc: str = CNJ_1, ente: str = "Ente A", valor: str = "1000.00"
) -> tuple[int, dict[str, str]]:
    return linha, {"numero_processo": proc, "ente_devedor": ente, "valor_face": valor}


def _hub(
    linha: int = 2,
    proc: str = CNJ_1,
    ente: str = "Ente A",
    valor: str = "1000.00",
    apres: str = "2025-04-02",
    prazo: str = "2026-12-31",
) -> tuple[int, dict[str, str]]:
    return linha, {
        "processo": proc,
        "ente": ente,
        "valor_face": valor,
        "apresentado_em": apres,
        "prazo_pagamento": prazo,
    }


def _apresentacao(
    indice: int = 1, proc: Any = CNJ_1, apres: Any = "2025-04-02"
) -> tuple[int, dict[str, Any]]:
    return indice, {"processo": proc, "apresentado_em": apres}


def _dados(
    *,
    tribunal: tuple[tuple[int, dict[str, str]], ...] = (),
    hub: tuple[tuple[int, dict[str, str]], ...] = (),
    apresentacoes: tuple[tuple[int, dict[str, Any]], ...] = (),
) -> DadosBrutos:
    return DadosBrutos(tribunal, hub, apresentacoes, (), ())


def test_duplicatas_identicas_conflitantes_e_recuperacao_apos_invalida() -> None:
    dados = _dados(
        tribunal=(
            _tribunal(2, CNJ_1, "Ente A", "1000.00"),
            _tribunal(3, CNJ_1, "Ente A", "1.000,00"),
            _tribunal(4, CNJ_2, "Ente B", "2000.00"),
            _tribunal(5, CNJ_2, "Ente B", "2.500,00"),
            _tribunal(6, CNJ_2, "Ente B", "2000.00"),
            _tribunal(7, CNJ_3, "Ente C", "3000.00"),
            _tribunal(8, CNJ_4, "Ente D", "4000.00"),
        ),
        hub=(
            _hub(2, CNJ_1, "Ente A", "1000.00", "2025-04-01"),
            _hub(3, CNJ_1, "Ente A", "1000.00", "2025-04-01"),
            _hub(4, CNJ_2, "Ente B", "2000.00", "2025-04-01"),
            _hub(5, CNJ_3, "Ente C", "3000.00", "2025-04-01"),
            _hub(6, CNJ_3, "Ente C Alt", "3000.00", "2025-04-01"),
            _hub(7, CNJ_4, "Ente D", "4000.00", "2025-04-01"),
        ),
        apresentacoes=(
            _apresentacao(1, CNJ_1, "2025-04-01"),
            _apresentacao(2, CNJ_1, "2025-04-01"),
            _apresentacao(3, CNJ_4, "2025-04-01"),
            _apresentacao(4, CNJ_4, "2025-04-05"),
        ),
    )
    res = conciliar_precatorios(dados)
    por = {p.numero_processo: p for p in res.precatorios}
    p2, p3, p4 = por[CHAVE_2], por[CHAVE_3], por[CHAVE_4]
    assert por[CHAVE_1].status_conciliacao == "conciliado"
    assert (p2.valor_face, p2.status_conciliacao) == (Decimal("2000.00"), "em_duvida")
    assert (p3.ente_devedor, p3.status_conciliacao) == ("Ente C", "em_duvida")
    assert (p4.apresentado_em, p4.status_conciliacao) == ("2025-04-01", "em_duvida")

    dups = [oc for oc in res.ocorrencias if oc.campo == "duplicidade"]
    assert all(oc.problema == "P4" for oc in dups)
    assert sum(oc.categoria == "descartado" for oc in dups) == 4
    conflitos = {oc.identificador for oc in dups if oc.categoria == "em_duvida"}
    assert conflitos == {CNJ_2, CNJ_3, CNJ_4}
    assert not any(oc.problema == "P3" for oc in res.ocorrencias)

    rec = conciliar_precatorios(
        _dados(
            tribunal=(_tribunal(2, valor="invalido"), _tribunal(3, valor="2000.00")),
            hub=(_hub(2, valor="2000.00"),),
        )
    ).precatorios[0]
    assert (rec.valor_face, rec.status_conciliacao) == (
        Decimal("2000.00"),
        "conciliado",
    )


def test_divergencia_e_mesmo_dia_brt_de_apresentado_em() -> None:
    dados = _dados(
        tribunal=(_tribunal(2, CNJ_1), _tribunal(3, CNJ_2), _tribunal(4, CNJ_3)),
        hub=(
            _hub(2, CNJ_1, apres="2025-04-02T23:30:00-03:00"),
            _hub(3, CNJ_2, apres="2025-04-02"),
            _hub(4, CNJ_3, apres="2025-04-02"),
        ),
        apresentacoes=(
            _apresentacao(1, CNJ_1, "2025-04-03T01:00:00Z"),
            _apresentacao(2, CNJ_2, "2025-04-03"),
            _apresentacao(3, CNJ_3, "data-invalida"),
        ),
    )
    res = conciliar_precatorios(dados)
    por = {p.numero_processo: p for p in res.precatorios}
    assert por[CHAVE_1].status_conciliacao == "conciliado"
    for ch in (CHAVE_2, CHAVE_3):
        p = por[ch]
        esperado = ("em_duvida", "2025-04-02", "2026-12-31")
        assert (p.status_conciliacao, p.apresentado_em, p.prazo_pagamento) == esperado
    ids = {
        oc.identificador
        for oc in res.ocorrencias
        if oc.problema == "P4"
        and oc.categoria == "em_duvida"
        and oc.campo == "apresentado_em"
    }
    assert ids == {CNJ_2, CNJ_3}


def test_hub_apresentado_vazio_ou_invalido_e_tipo_nao_string() -> None:
    dados = _dados(
        tribunal=(_tribunal(2, CNJ_1), _tribunal(3, CNJ_2), _tribunal(4, CNJ_3)),
        hub=(
            _hub(2, CNJ_1, apres="", prazo="2027-12-31"),
            _hub(3, CNJ_2, apres="invalida", prazo="2027-12-31"),
        ),
        apresentacoes=(
            _apresentacao(1, CNJ_1, "2025-04-02"),
            _apresentacao(2, CNJ_2, "2025-04-02"),
            _apresentacao(3, CNJ_3, True),
        ),
    )
    res = conciliar_precatorios(dados)
    por = {p.numero_processo: p for p in res.precatorios}
    p1 = por[CHAVE_1]
    assert (p1.apresentado_em, p1.prazo_pagamento, p1.status_conciliacao) == (
        "2025-04-02",
        "2026-12-31",
        "em_duvida",
    )
    ocs_inv = [
        oc
        for oc in res.ocorrencias
        if oc.identificador == CNJ_2 and oc.campo == "apresentado_em"
    ]
    assert len(ocs_inv) == 1 and ocs_inv[0].problema == "P4"
    assert por[CHAVE_3].apresentado_em == ""
    assert any(
        oc.problema == "P3"
        and oc.categoria == "descartado"
        and oc.identificador == CNJ_3
        and oc.campo == "apresentado_em"
        for oc in res.ocorrencias
    )


def test_apresentado_em_ausente_ou_invalido_gera_p2_em_duvida() -> None:
    dados = _dados(
        tribunal=(_tribunal(2, CNJ_1), _tribunal(3, CNJ_2)),
        hub=(_hub(2, CNJ_1, apres="2025-02-30"),),
    )
    res = conciliar_precatorios(dados)
    por = {p.numero_processo: p for p in res.precatorios}
    p1, p2 = por[CHAVE_1], por[CHAVE_2]
    assert (p1.status_conciliacao, p1.apresentado_em, p1.prazo_pagamento) == (
        "em_duvida",
        "2025-02-30",
        "2026-12-31",
    )
    assert (p2.status_conciliacao, p2.apresentado_em, p2.prazo_pagamento) == (
        "em_duvida",
        "",
        "",
    )
    ids_p2 = {
        oc.identificador
        for oc in res.ocorrencias
        if oc.problema == "P2"
        and oc.categoria == "em_duvida"
        and oc.campo == "apresentado_em"
    }
    assert ids_p2 == {CNJ_1, CNJ_2}


def test_prazo_vazio_invalido_naive_e_valor_ptbr_no_hub() -> None:
    dados = _dados(
        tribunal=(_tribunal(2, CNJ_1), _tribunal(3, CNJ_2), _tribunal(4, CNJ_3)),
        hub=(
            _hub(2, CNJ_1, valor="1.000,00", apres="2025-04-02", prazo=""),
            _hub(3, CNJ_2, apres="2025-04-02T23:30:00", prazo="invalido"),
        ),
        apresentacoes=(_apresentacao(1, CNJ_3, "2025-04-02"),),
    )
    res = conciliar_precatorios(dados)
    por = {p.numero_processo: p for p in res.precatorios}
    assert por[CHAVE_1].prazo_pagamento == "2026-12-31"
    assert por[CHAVE_2].prazo_pagamento == "2026-12-31"
    assert res.prazos_hub_originais == {CHAVE_1: "", CHAVE_2: "invalido", CHAVE_3: None}
    p2 = {
        oc.identificador: oc
        for oc in res.ocorrencias
        if oc.problema == "P2" and oc.categoria == "corrigido"
    }
    assert set(p2) == {CNJ_1, CNJ_2}
    assert all("premissa" in oc.motivo.casefold() for oc in p2.values())
    assert any(
        oc.problema == "P3"
        and oc.categoria == "corrigido"
        and oc.origem == "hub.csv (L2)"
        and oc.campo == "valor_face"
        for oc in res.ocorrencias
    )


def test_ente_devedor_vazio_em_uma_ou_ambas_bases_sem_duplicar_alerta() -> None:
    dados = _dados(
        tribunal=(
            _tribunal(2, CNJ_1, ente=""),
            _tribunal(3, CNJ_2, ente="Município de São Paulo"),
            _tribunal(4, CNJ_3, ente=""),
        ),
        hub=(
            _hub(2, CNJ_1, ente=""),
            _hub(3, CNJ_2, ente=""),
            _hub(4, CNJ_3, ente="Estado de São Paulo"),
        ),
    )
    res = conciliar_precatorios(dados)
    assert all(p.status_conciliacao == "em_duvida" for p in res.precatorios)
    assert res.precatorios[0].ente_devedor == ""
    for cnj, prob in ((CNJ_1, "P3"), (CNJ_2, "P4"), (CNJ_3, "P4")):
        ocs = [
            oc
            for oc in res.ocorrencias
            if oc.identificador == cnj and oc.campo == "ente_devedor"
        ]
        assert len(ocs) == 1
        assert (ocs[0].problema, ocs[0].categoria) == (prob, "em_duvida")


@pytest.mark.parametrize(
    ("dados", "campo"),
    [
        (_dados(tribunal=(_tribunal(2, proc=""),)), "numero_processo"),
        (_dados(tribunal=(_tribunal(2, proc="123"),)), "numero_processo"),
        (_dados(tribunal=(_tribunal(2, valor=""),)), "valor_face"),
        (_dados(tribunal=(_tribunal(2, valor="abc"),)), "valor_face"),
        (_dados(tribunal=(_tribunal(2, valor="0.00"),)), "valor_face"),
        (_dados(tribunal=(_tribunal(2, valor="-50.00"),)), "valor_face"),
        (_dados(hub=(_hub(2, proc="cnj-invalido"),)), "numero_processo"),
        (_dados(hub=(_hub(2, valor="-10.00"),)), "valor_face"),
        (_dados(apresentacoes=(_apresentacao(1, proc=None),)), "numero_processo"),
    ],
)
def test_cnj_e_valor_face_invalidos_descartados_com_p3(
    dados: DadosBrutos, campo: str
) -> None:
    res = conciliar_precatorios(dados)
    assert res.precatorios == () and len(res.ocorrencias) == 1
    oc = res.ocorrencias[0]
    esperado = ("P3", "descartado", "precatorio", campo)
    assert (oc.problema, oc.categoria, oc.entidade, oc.campo) == esperado


def test_processo_orfao_apenas_em_apresentacoes_nao_cria_precatorio() -> None:
    cnj = "0099999-10.2022.8.26.0053"
    res = conciliar_precatorios(_dados(apresentacoes=(_apresentacao(1, cnj),)))
    assert res.precatorios == () and len(res.ocorrencias) == 1
    oc = res.ocorrencias[0]
    esperado = ("P4", "em_duvida", cnj, "apresentacoes.json (item 1)", "cobertura")
    assert (
        oc.problema,
        oc.categoria,
        oc.identificador,
        oc.origem,
        oc.campo,
    ) == esperado
