import math
from pathlib import Path

from bzr_group_case.auditoria.base import (
    ResultadoValidacao,
    carregar_eventos_json,
    identificador_evento,
    ler_csv_para_analise,
    rotulo_arquivo,
    somente_digitos,
)

ORIGEM_SCHEMA = "data/raw/schema.sql"
TIPOS_ACEITOS_BANCO = {"pagamento", "estorno"}


def validar_tamanho_numero_processo_char20(
    caminho: Path,
    coluna: str,
) -> ResultadoValidacao:
    """Valida restrição precatorio.numero_processo CHAR(20) (máximo 20 chars)."""
    evidencias: list[str] = []

    for num_linha, linha in ler_csv_para_analise(caminho):
        processo = linha.get(coluna) or ""
        if len(processo) > 20:
            evidencias.append(
                f"Linha {num_linha}: encontrado {processo!r} ({len(processo)} chars)"
            )

    return ResultadoValidacao(
        origem=ORIGEM_SCHEMA,
        validacao="precatorio.numero_processo: até 20 caracteres (CHAR(20))",
        arquivo=rotulo_arquivo(caminho),
        evidencias=evidencias,
    )


def validar_valor_positivo_pagamento(caminho_pagamentos: Path) -> ResultadoValidacao:
    """Valida restrição pagamento.valor CHECK (valor > 0) nos valores numéricos."""
    evidencias: list[str] = []

    for indice, evento in carregar_eventos_json(caminho_pagamentos):
        valor = evento.get("valor")
        if (
            isinstance(valor, (int, float))
            and not isinstance(valor, bool)
            and math.isfinite(valor)
            and valor <= 0
        ):
            ref = identificador_evento(indice, evento)
            evidencias.append(f"{ref}: encontrado {valor!r} (esperado > 0)")

    return ResultadoValidacao(
        origem=ORIGEM_SCHEMA,
        validacao="pagamento.valor: CHECK (valor > 0)",
        arquivo=rotulo_arquivo(caminho_pagamentos),
        evidencias=evidencias,
    )


def validar_tipo_aceito_banco(caminho_pagamentos: Path) -> ResultadoValidacao:
    """Valida restrição pagamento.tipo CHECK (tipo IN ('pagamento', 'estorno'))."""
    evidencias: list[str] = []

    for indice, evento in carregar_eventos_json(caminho_pagamentos):
        tipo = evento.get("tipo")
        if tipo not in TIPOS_ACEITOS_BANCO:
            ref = identificador_evento(indice, evento)
            evidencias.append(
                f"{ref}: encontrado {tipo!r} (aceito: 'pagamento' ou 'estorno')"
            )

    return ResultadoValidacao(
        origem=ORIGEM_SCHEMA,
        validacao="pagamento.tipo: CHECK (tipo IN ('pagamento', 'estorno'))",
        arquivo=rotulo_arquivo(caminho_pagamentos),
        evidencias=evidencias,
    )


def validar_referencia_precatorio_no_hub(
    caminho_pagamentos: Path,
    caminho_hub: Path,
) -> ResultadoValidacao:
    """Valida FK pagamento.precatorio_id REFERENCES precatorio(id) contra hub.csv."""
    chaves_hub = {
        somente_digitos(linha.get("processo") or "")
        for _, linha in ler_csv_para_analise(caminho_hub)
        if somente_digitos(linha.get("processo") or "")
    }
    rotulo_hub = rotulo_arquivo(caminho_hub)
    evidencias: list[str] = []

    for indice, evento in carregar_eventos_json(caminho_pagamentos):
        processo = evento.get("processo")
        chave = somente_digitos(processo) if isinstance(processo, str) else ""
        if not chave or chave not in chaves_hub:
            ref = identificador_evento(indice, evento)
            evidencias.append(
                f"{ref}: processo {processo!r} não encontrado em {rotulo_hub}"
            )

    return ResultadoValidacao(
        origem=ORIGEM_SCHEMA,
        validacao="pagamento.precatorio_id: processo existente na base interna",
        arquivo=rotulo_arquivo(caminho_pagamentos),
        evidencias=evidencias,
    )


def auditar_schema(
    caminho_tribunal: Path,
    caminho_hub: Path,
    caminho_pagamentos: Path,
) -> list[ResultadoValidacao]:
    """Executa todas as validações originadas em schema.sql."""
    return [
        validar_tamanho_numero_processo_char20(caminho_tribunal, "numero_processo"),
        validar_tamanho_numero_processo_char20(caminho_hub, "processo"),
        validar_valor_positivo_pagamento(caminho_pagamentos),
        validar_tipo_aceito_banco(caminho_pagamentos),
        validar_referencia_precatorio_no_hub(caminho_pagamentos, caminho_hub),
    ]
