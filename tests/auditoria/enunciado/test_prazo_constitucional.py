from pathlib import Path

from bzr_group_case.auditoria.enunciado.prazo_constitucional import (
    ORIGEM_ENUNCIADO,
    calcular_prazo_constitucional,
    validar_prazo_pagamento_hub,
)


def test_calcular_prazo_constitucional_fronteira_e_fuso() -> None:
    assert calcular_prazo_constitucional("2025-04-02") == "2026-12-31"
    assert calcular_prazo_constitucional("2025-04-03") == "2027-12-31"
    assert calcular_prazo_constitucional("2024-02-29") == "2025-12-31"
    assert calcular_prazo_constitucional("2025-04-02T23:30:00-03:00") == "2026-12-31"
    assert calcular_prazo_constitucional("2025-04-03T01:00:00Z") == "2026-12-31"
    assert calcular_prazo_constitucional("2025-04-03T02:59:59Z") == "2026-12-31"
    assert calcular_prazo_constitucional("2025-04-03T03:00:00Z") == "2027-12-31"
    assert calcular_prazo_constitucional("2025-04-03T04:00:00+02:00") == "2026-12-31"
    assert calcular_prazo_constitucional("2025-04-02T12:00:00") == "2026-12-31"


def test_validar_prazo_pagamento_hub_inclui_data_invalida(tmp_path: Path) -> None:
    hub = tmp_path / "hub.csv"
    hub.write_text(
        "processo,ente,valor_face,apresentado_em,prazo_pagamento\n"
        "0012345-10.2019.8.26.0053,Ente A,100.00,2025-04-02,2027-12-31\n"
        "00234562120208260053,Ente B,100.00,2025-04-03,2027-12-31\n"
        "0056789-54.2017.4.03.6100,Ente C,100.00,2025-04-03T01:00:00Z,2027-12-31\n"
        "0099999-00.2020.8.26.0053,Ente D,100.00,data-invalida,2026-12-31\n",
        encoding="utf-8",
    )

    resultado = validar_prazo_pagamento_hub(hub)

    assert resultado.origem == ORIGEM_ENUNCIADO
    assert resultado.evidencias == [
        "Linha 2 (0012345-10.2019.8.26.0053): apresentado_em='2025-04-02' "
        "(data BRT: 2025-04-02) -> esperado '2026-12-31', encontrado '2027-12-31'",
        "Linha 4 (0056789-54.2017.4.03.6100): apresentado_em='2025-04-03T01:00:00Z' "
        "(data BRT: 2025-04-02) -> esperado '2026-12-31', encontrado '2027-12-31'",
        "Linha 5 (0099999-00.2020.8.26.0053): apresentado_em inválido 'data-invalida'",
    ]
