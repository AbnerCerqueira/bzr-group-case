import json
from pathlib import Path

from bzr_group_case.auditoria.schema_banco.restricoes import (
    ORIGEM_SCHEMA,
    validar_referencia_precatorio_no_hub,
    validar_tamanho_numero_processo_char20,
    validar_tipo_aceito_banco,
    validar_valor_positivo_pagamento,
)


def _escrever_json(caminho: Path, conteudo: object) -> Path:
    caminho.write_text(json.dumps(conteudo), encoding="utf-8")
    return caminho


def test_validar_tamanho_numero_processo_char20(tmp_path: Path) -> None:
    arquivo = tmp_path / "hub.csv"
    arquivo.write_text(
        "processo,ente\n"
        "00234562120208260053,Município de São Paulo\n"
        "12345,Município de Santos\n"
        "0012345-10.2019.8.26.0053,Município de São Paulo\n",
        encoding="utf-8",
    )

    resultado = validar_tamanho_numero_processo_char20(arquivo, "processo")

    assert resultado.origem == ORIGEM_SCHEMA
    assert resultado.evidencias == [
        "Linha 4: encontrado '0012345-10.2019.8.26.0053' (25 chars)"
    ]


def test_validar_valor_positivo_pagamento(tmp_path: Path) -> None:
    arquivo = tmp_path / "pagamentos.json"
    arquivo.write_text(
        '[{"evento_id": "ev-001", "valor": 100.0},'
        ' {"evento_id": "ev-002", "valor": 0},'
        ' {"evento_id": "ev-003", "valor": -200},'
        ' {"evento_id": "ev-004", "valor": null},'
        ' {"evento_id": "ev-005", "valor": "2.500,50"},'
        ' {"evento_id": "ev-006", "valor": false},'
        ' {"evento_id": "ev-007", "valor": NaN},'
        ' {"evento_id": "ev-008", "valor": -Infinity}]',
        encoding="utf-8",
    )

    resultado = validar_valor_positivo_pagamento(arquivo)

    assert resultado.evidencias == [
        "Item 2 (ev-002): encontrado 0 (esperado > 0)",
        "Item 3 (ev-003): encontrado -200 (esperado > 0)",
    ]


def test_validar_tipo_aceito_banco(tmp_path: Path) -> None:
    valido = _escrever_json(
        tmp_path / "valido.json",
        [
            {"evento_id": "ev-001", "tipo": "pagamento"},
            {"evento_id": "ev-002", "tipo": "estorno"},
        ],
    )
    invalido = _escrever_json(
        tmp_path / "invalido.json",
        [{"evento_id": "ev-003", "tipo": "cancelamento"}],
    )

    assert validar_tipo_aceito_banco(valido).ok is True
    assert validar_tipo_aceito_banco(invalido).evidencias == [
        "Item 1 (ev-003): encontrado 'cancelamento' (aceito: 'pagamento' ou 'estorno')"
    ]


def test_validar_referencia_precatorio_no_hub(tmp_path: Path) -> None:
    hub = tmp_path / "hub.csv"
    hub.write_text(
        "processo,ente\n00234562120208260053,Município de São Paulo\n",
        encoding="utf-8",
    )
    pagamentos = _escrever_json(
        tmp_path / "pagamentos.json",
        [
            {"evento_id": "ev-001", "processo": "0023456-21.2020.8.26.0053"},
            {"evento_id": "ev-002", "processo": ""},
            {"evento_id": "ev-003", "processo": "0067890-65.2016.8.26.0053"},
            {"evento_id": "ev-004", "processo": None},
            {"evento_id": "ev-005"},
        ],
    )

    resultado = validar_referencia_precatorio_no_hub(pagamentos, hub)

    assert len(resultado.evidencias) == 4
    assert resultado.evidencias[0].startswith("Item 2 (ev-002): processo ''")
    assert resultado.evidencias[1].startswith(
        "Item 3 (ev-003): processo '0067890-65.2016.8.26.0053'"
    )
    assert resultado.evidencias[2].startswith("Item 4 (ev-004): processo None")
    assert resultado.evidencias[3].startswith("Item 5 (ev-005): processo None")
