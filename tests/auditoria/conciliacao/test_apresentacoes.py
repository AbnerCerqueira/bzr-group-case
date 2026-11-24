import json
from pathlib import Path

from bzr_group_case.auditoria.conciliacao.apresentacoes import (
    ORIGEM_CONCILIACAO_APRESENTACOES,
    validar_apresentacoes_contra_hub,
)


def test_validar_apresentacoes_contra_hub_bidirecional_e_malformado(
    tmp_path: Path,
) -> None:
    hub = tmp_path / "hub.csv"
    hub.write_text(
        "processo,ente,valor_face,apresentado_em,prazo_pagamento\n"
        "00234562120208260053,Ente A,100.00,2025-04-03,2027-12-31\n"
        "0056789-54.2017.4.03.6100,Ente B,100.00,2025-04-02,2026-12-31\n",
        encoding="utf-8",
    )
    apresentacoes = tmp_path / "apresentacoes.json"
    apresentacoes.write_text(
        json.dumps(
            [
                {
                    "processo": "0023456-21.2020.8.26.0053",
                    "apresentado_em": "2025-04-04",
                },
                {
                    "processo": "0067890-65.2016.8.26.0053",
                    "apresentado_em": "2023-12-31",
                },
            ]
        ),
        encoding="utf-8",
    )
    malformado = tmp_path / "quebrado.json"
    malformado.write_text("{}", encoding="utf-8")

    resultado = validar_apresentacoes_contra_hub(apresentacoes, hub)
    assert resultado.origem == ORIGEM_CONCILIACAO_APRESENTACOES
    assert len(resultado.evidencias) == 3
    assert "apresentacoes='2025-04-04' vs hub='2025-04-03'" in resultado.evidencias[0]
    assert "0067890-65.2016.8.26.0053" in resultado.evidencias[1]
    assert "0056789-54.2017.4.03.6100" in resultado.evidencias[2]

    assert validar_apresentacoes_contra_hub(malformado, hub).evidencias == [
        "Esperado lista JSON, encontrado dict"
    ]
