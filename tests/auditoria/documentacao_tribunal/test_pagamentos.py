import json
from pathlib import Path

from bzr_group_case.auditoria.documentacao_tribunal.pagamentos import (
    ORIGEM_DOC_PAGAMENTOS,
    validar_atualizado_em_iso,
    validar_data_pagamento_iso,
    validar_estrutura_json,
    validar_evento_id_unico,
    validar_processo_cnj_json,
    validar_tipo_pagamento,
    validar_valor_numerico_json,
)


def _escrever_json(caminho: Path, conteudo: object) -> Path:
    caminho.write_text(json.dumps(conteudo), encoding="utf-8")
    return caminho


def test_validar_estrutura_json_raiz_e_itens(tmp_path: Path) -> None:
    raiz_objeto = _escrever_json(tmp_path / "objeto.json", {"a": 1})
    item_invalido = _escrever_json(
        tmp_path / "misto.json",
        [{"evento_id": "ev-001"}, None, {"evento_id": "ev-002"}],
    )
    malformado = tmp_path / "quebrado.json"
    malformado.write_text("{invalido", encoding="utf-8")

    assert validar_estrutura_json(raiz_objeto).evidencias == [
        "Esperado lista JSON, encontrado dict"
    ]
    assert validar_estrutura_json(item_invalido).evidencias == [
        "Item 2: esperado objeto JSON, encontrado NoneType"
    ]
    assert validar_estrutura_json(malformado).ok is False


def test_validar_evento_id_unico_casos_validos_e_invalidos(tmp_path: Path) -> None:
    valido = _escrever_json(
        tmp_path / "valido.json",
        [{"evento_id": "ev-001"}, {"evento_id": "ev-002"}],
    )
    invalido = _escrever_json(
        tmp_path / "invalido.json",
        [
            {"evento_id": "ev-001", "valor": 100},
            None,
            {"evento_id": "ev-001", "valor": 100},
            {"evento_id": "ev-001", "valor": 150},
            {"evento_id": "   "},
            {"evento_id": 123},
            {},
        ],
    )

    assert validar_evento_id_unico(valido).ok is True

    resultado = validar_evento_id_unico(invalido)
    assert resultado.origem == ORIGEM_DOC_PAGAMENTOS
    assert resultado.evidencias == [
        "Item 3: evento_id repetido 'ev-001' (primeira ocorrência no item 1) "
        "— registro idêntico",
        "Item 4: evento_id repetido 'ev-001' (primeira ocorrência no item 1) "
        "— campos divergentes (valor: 100 -> 150)",
        "Item 5: esperado texto não vazio, encontrado '   '",
        "Item 6: esperado texto não vazio, encontrado 123",
        "Item 7: campo 'evento_id' ausente",
    ]


def test_validar_processo_cnj_json_rejeita_sem_mascara_vazio_e_quebra_linha(
    tmp_path: Path,
) -> None:
    arquivo = _escrever_json(
        tmp_path / "pagamentos.json",
        [
            {"evento_id": "ev-001", "processo": "0012345-10.2019.8.26.0053"},
            {"evento_id": "ev-002", "processo": "00234562120208260053"},
            {"evento_id": "ev-003", "processo": ""},
            {"evento_id": "ev-004", "processo": "0012345-10.2019.8.26.0053\n"},
            {"evento_id": "ev-005"},
        ],
    )

    assert validar_processo_cnj_json(arquivo).evidencias == [
        "Item 2 (ev-002): encontrado '00234562120208260053'",
        "Item 3 (ev-003): encontrado ''",
        "Item 4 (ev-004): encontrado '0012345-10.2019.8.26.0053\\n'",
        "Item 5 (ev-005): campo 'processo' ausente",
    ]


def test_validar_valor_numerico_json(tmp_path: Path) -> None:
    arquivo = tmp_path / "pagamentos.json"
    arquivo.write_text(
        '[{"evento_id": "ev-001", "valor": 1500.5},'
        ' {"evento_id": "ev-002", "valor": 0},'
        ' {"evento_id": "ev-003", "valor": -200},'
        ' {"evento_id": "ev-004", "valor": "2.500,50"},'
        ' {"evento_id": "ev-005", "valor": null},'
        ' {"evento_id": "ev-006", "valor": true},'
        ' {"evento_id": "ev-007", "valor": NaN},'
        ' {"evento_id": "ev-008"}]',
        encoding="utf-8",
    )

    assert validar_valor_numerico_json(arquivo).evidencias == [
        "Item 4 (ev-004): encontrado '2.500,50' (tipo str)",
        "Item 5 (ev-005): encontrado None (tipo NoneType)",
        "Item 6 (ev-006): encontrado True (tipo bool)",
        "Item 7 (ev-007): encontrado nan (tipo float)",
        "Item 8 (ev-008): campo 'valor' ausente",
    ]


def test_validar_data_pagamento_iso(tmp_path: Path) -> None:
    arquivo = _escrever_json(
        tmp_path / "pagamentos.json",
        [
            {"evento_id": "ev-001", "data_pagamento": "2025-03-10"},
            {"evento_id": "ev-002", "data_pagamento": "10/04/2025"},
            {"evento_id": "ev-003", "data_pagamento": "2025-02-30"},
            {"evento_id": "ev-004"},
        ],
    )

    assert validar_data_pagamento_iso(arquivo).evidencias == [
        "Item 2 (ev-002): encontrado '10/04/2025'",
        "Item 3 (ev-003): encontrado '2025-02-30'",
        "Item 4 (ev-004): campo 'data_pagamento' ausente",
    ]


def test_validar_tipo_pagamento(tmp_path: Path) -> None:
    arquivo = _escrever_json(
        tmp_path / "pagamentos.json",
        [
            {"evento_id": "ev-001", "tipo": "pagamento"},
            {"evento_id": "ev-002", "tipo": "estorno"},
            {"evento_id": "ev-003"},
        ],
    )

    assert validar_tipo_pagamento(arquivo).evidencias == [
        "Item 2 (ev-002): esperado 'pagamento', encontrado 'estorno'",
        "Item 3 (ev-003): campo 'tipo' ausente",
    ]


def test_validar_atualizado_em_iso(tmp_path: Path) -> None:
    arquivo = _escrever_json(
        tmp_path / "pagamentos.json",
        [
            {"evento_id": "ev-001", "atualizado_em": "2025-03-10T10:00:00-03:00"},
            {"evento_id": "ev-002", "atualizado_em": "2025-03-10T10:00:00Z"},
            {"evento_id": "ev-003", "atualizado_em": "2025-03-10"},
            {"evento_id": "ev-004", "atualizado_em": "2025-03-10T10"},
        ],
    )

    assert validar_atualizado_em_iso(arquivo).evidencias == [
        "Item 3 (ev-003): encontrado '2025-03-10'",
        "Item 4 (ev-004): encontrado '2025-03-10T10'",
    ]
