from pathlib import Path

from bzr_group_case.auditoria.base import (
    ResultadoValidacao,
    ler_csv_para_analise,
    rotulo_arquivo,
)
from bzr_group_case.comum import calcular_prazo_constitucional

ORIGEM_ENUNCIADO = "docs/ENUNCIADO.md"

__all__ = [
    "ORIGEM_ENUNCIADO",
    "auditar_enunciado",
    "validar_prazo_pagamento_hub",
]


def validar_prazo_pagamento_hub(caminho_hub: Path) -> ResultadoValidacao:
    """Valida prazo_pagamento em hub.csv pela regra constitucional de 2 de abril."""
    evidencias: list[str] = []

    for num_linha, linha in ler_csv_para_analise(caminho_hub):
        processo = linha.get("processo") or ""
        apresentado_em = linha.get("apresentado_em") or ""
        prazo_atual = linha.get("prazo_pagamento") or ""

        try:
            data_brasilia, data_prazo = calcular_prazo_constitucional(apresentado_em)
        except ValueError:
            evidencias.append(
                f"Linha {num_linha} ({processo}): "
                f"apresentado_em inválido {apresentado_em!r}"
            )
            continue

        prazo_esperado = data_prazo.isoformat()
        if prazo_atual != prazo_esperado:
            evidencias.append(
                f"Linha {num_linha} ({processo}): apresentado_em={apresentado_em!r} "
                f"(data BRT: {data_brasilia.isoformat()}) -> "
                f"esperado {prazo_esperado!r}, encontrado {prazo_atual!r}"
            )

    return ResultadoValidacao(
        origem=ORIGEM_ENUNCIADO,
        validacao="Regra constitucional de prazo_pagamento (corte em 02/04, BRT)",
        arquivo=rotulo_arquivo(caminho_hub),
        evidencias=evidencias,
    )


def auditar_enunciado(caminho_hub: Path) -> list[ResultadoValidacao]:
    """Executa as validações de regras de negócio descritas em docs/ENUNCIADO.md."""
    return [validar_prazo_pagamento_hub(caminho_hub)]
