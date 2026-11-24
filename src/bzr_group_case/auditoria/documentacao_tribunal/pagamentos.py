import json
import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from bzr_group_case.auditoria.base import (
    PADRAO_CNJ,
    ResultadoValidacao,
    carregar_eventos_json,
    identificador_evento,
    rotulo_arquivo,
)

ORIGEM_DOC_PAGAMENTOS = "docs/DOCUMENTACAO_TRIBUNAL.md (seção pagamentos.json)"

PADRAO_DATA_ISO = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)
PADRAO_DATA_HORA_ISO = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?",
    re.ASCII,
)


def _eh_numero_json(valor: Any) -> bool:
    return (
        isinstance(valor, (int, float))
        and not isinstance(valor, bool)
        and math.isfinite(valor)
    )


def _eh_data_iso(valor: Any) -> bool:
    if not isinstance(valor, str) or not PADRAO_DATA_ISO.fullmatch(valor):
        return False
    try:
        date.fromisoformat(valor)
    except ValueError:
        return False
    return True


def _eh_data_hora_iso(valor: Any) -> bool:
    if not isinstance(valor, str) or not PADRAO_DATA_HORA_ISO.fullmatch(valor):
        return False
    texto = f"{valor[:-1]}+00:00" if valor.endswith("Z") else valor
    try:
        datetime.fromisoformat(texto)
    except ValueError:
        return False
    return True


def _campos_diferentes(
    primeiro: dict[str, Any],
    atual: dict[str, Any],
) -> list[str]:
    chaves = sorted(set(primeiro) | set(atual))
    return [
        f"{chave}: {primeiro.get(chave)!r} -> {atual.get(chave)!r}"
        for chave in chaves
        if primeiro.get(chave) != atual.get(chave)
    ]


def validar_estrutura_json(caminho: Path) -> ResultadoValidacao:
    """Valida se o arquivo é um JSON UTF-8 contendo uma lista de objetos."""
    evidencias: list[str] = []

    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as erro:
        evidencias.append(f"Erro ao ler JSON: {erro}")
    else:
        if not isinstance(dados, list):
            evidencias.append(f"Esperado lista JSON, encontrado {type(dados).__name__}")
        else:
            for indice, item in enumerate(dados, start=1):
                if not isinstance(item, dict):
                    evidencias.append(
                        f"Item {indice}: esperado objeto JSON, "
                        f"encontrado {type(item).__name__}"
                    )

    return ResultadoValidacao(
        origem=ORIGEM_DOC_PAGAMENTOS,
        validacao="Estrutura: lista de objetos em JSON",
        arquivo=rotulo_arquivo(caminho),
        severidade="ALTA",
        evidencias=evidencias,
    )


def validar_evento_id_unico(caminho: Path) -> ResultadoValidacao:
    """Valida se evento_id é texto não vazio e único no JSON."""
    evidencias: list[str] = []
    primeira_ocorrencia: dict[str, tuple[int, dict[str, Any]]] = {}

    for indice, evento in carregar_eventos_json(caminho):
        if "evento_id" not in evento:
            evidencias.append(f"Item {indice}: campo 'evento_id' ausente")
            continue

        evento_id = evento["evento_id"]
        if not isinstance(evento_id, str) or not evento_id.strip():
            evidencias.append(
                f"Item {indice}: esperado texto não vazio, encontrado {evento_id!r}"
            )
            continue

        if evento_id in primeira_ocorrencia:
            indice_original, evento_original = primeira_ocorrencia[evento_id]
            diferencas = _campos_diferentes(evento_original, evento)
            detalhe = (
                "registro idêntico"
                if not diferencas
                else f"campos divergentes ({'; '.join(diferencas)})"
            )
            evidencias.append(
                f"Item {indice}: evento_id repetido {evento_id!r} "
                f"(primeira ocorrência no item {indice_original}) — {detalhe}"
            )
        else:
            primeira_ocorrencia[evento_id] = (indice, evento)

    return ResultadoValidacao(
        origem=ORIGEM_DOC_PAGAMENTOS,
        validacao="evento_id: texto único",
        arquivo=rotulo_arquivo(caminho),
        severidade="ALTA",
        evidencias=evidencias,
    )


def validar_processo_cnj_json(caminho: Path) -> ResultadoValidacao:
    """Valida se o campo processo segue o padrão CNJ."""
    evidencias: list[str] = []

    for indice, evento in carregar_eventos_json(caminho):
        ref = identificador_evento(indice, evento)
        if "processo" not in evento:
            evidencias.append(f"{ref}: campo 'processo' ausente")
            continue

        processo = evento["processo"]
        if not isinstance(processo, str) or not PADRAO_CNJ.fullmatch(processo):
            evidencias.append(f"{ref}: encontrado {processo!r}")

    return ResultadoValidacao(
        origem=ORIGEM_DOC_PAGAMENTOS,
        validacao="processo: formato CNJ (NNNNNNN-DD.AAAA.J.TR.OOOO)",
        arquivo=rotulo_arquivo(caminho),
        severidade="MEDIA",
        evidencias=evidencias,
    )


def validar_valor_numerico_json(caminho: Path) -> ResultadoValidacao:
    """Valida se o campo valor é um número JSON."""
    evidencias: list[str] = []

    for indice, evento in carregar_eventos_json(caminho):
        ref = identificador_evento(indice, evento)
        if "valor" not in evento:
            evidencias.append(f"{ref}: campo 'valor' ausente")
            continue

        valor = evento["valor"]
        if not _eh_numero_json(valor):
            evidencias.append(
                f"{ref}: encontrado {valor!r} (tipo {type(valor).__name__})"
            )

    return ResultadoValidacao(
        origem=ORIGEM_DOC_PAGAMENTOS,
        validacao="valor: número",
        arquivo=rotulo_arquivo(caminho),
        severidade="ALTA",
        evidencias=evidencias,
    )


def validar_data_pagamento_iso(caminho: Path) -> ResultadoValidacao:
    """Valida se data_pagamento está no formato AAAA-MM-DD."""
    evidencias: list[str] = []

    for indice, evento in carregar_eventos_json(caminho):
        ref = identificador_evento(indice, evento)
        if "data_pagamento" not in evento:
            evidencias.append(f"{ref}: campo 'data_pagamento' ausente")
            continue

        data_pagamento = evento["data_pagamento"]
        if not _eh_data_iso(data_pagamento):
            evidencias.append(f"{ref}: encontrado {data_pagamento!r}")

    return ResultadoValidacao(
        origem=ORIGEM_DOC_PAGAMENTOS,
        validacao="data_pagamento: formato AAAA-MM-DD",
        arquivo=rotulo_arquivo(caminho),
        severidade="MEDIA",
        evidencias=evidencias,
    )


def validar_tipo_pagamento(caminho: Path) -> ResultadoValidacao:
    """Valida se o campo tipo é sempre 'pagamento'."""
    evidencias: list[str] = []

    for indice, evento in carregar_eventos_json(caminho):
        ref = identificador_evento(indice, evento)
        if "tipo" not in evento:
            evidencias.append(f"{ref}: campo 'tipo' ausente")
            continue

        tipo = evento["tipo"]
        if tipo != "pagamento":
            evidencias.append(f"{ref}: esperado 'pagamento', encontrado {tipo!r}")

    return ResultadoValidacao(
        origem=ORIGEM_DOC_PAGAMENTOS,
        validacao="tipo: sempre 'pagamento'",
        arquivo=rotulo_arquivo(caminho),
        severidade="ALTA",
        evidencias=evidencias,
    )


def validar_atualizado_em_iso(caminho: Path) -> ResultadoValidacao:
    """Valida se atualizado_em é uma data e hora válida."""
    evidencias: list[str] = []

    for indice, evento in carregar_eventos_json(caminho):
        ref = identificador_evento(indice, evento)
        if "atualizado_em" not in evento:
            evidencias.append(f"{ref}: campo 'atualizado_em' ausente")
            continue

        atualizado_em = evento["atualizado_em"]
        if not _eh_data_hora_iso(atualizado_em):
            evidencias.append(f"{ref}: encontrado {atualizado_em!r}")

    return ResultadoValidacao(
        origem=ORIGEM_DOC_PAGAMENTOS,
        validacao="atualizado_em: data e hora válida",
        arquivo=rotulo_arquivo(caminho),
        severidade="MEDIA",
        evidencias=evidencias,
    )


def auditar_pagamentos(caminho: Path) -> list[ResultadoValidacao]:
    """Executa todas as validações da seção pagamentos.json."""
    return [
        validar_estrutura_json(caminho),
        validar_evento_id_unico(caminho),
        validar_processo_cnj_json(caminho),
        validar_valor_numerico_json(caminho),
        validar_data_pagamento_iso(caminho),
        validar_tipo_pagamento(caminho),
        validar_atualizado_em_iso(caminho),
    ]
