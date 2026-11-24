from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from bzr_group_case.auditoria.base import (
    ResultadoValidacao,
    ler_csv_para_analise,
    rotulo_arquivo,
)

ORIGEM_ENUNCIADO = "docs/ENUNCIADO.md"
FUSO_BRASILIA = timezone(timedelta(hours=-3))


def extrair_data_brasilia(apresentado_em: str) -> date:
    """Converte data ou data/hora ISO para a data civil no horário de Brasília."""
    if len(apresentado_em) == 10:
        return date.fromisoformat(apresentado_em)

    texto = (
        f"{apresentado_em[:-1]}+00:00"
        if apresentado_em.endswith("Z")
        else apresentado_em
    )
    instante = datetime.fromisoformat(texto)
    if instante.tzinfo is not None:
        instante = instante.astimezone(FUSO_BRASILIA)
    return instante.date()


def calcular_prazo_constitucional(apresentado_em: str) -> str:
    """Calcula o prazo constitucional (corte inclusivo em 2 de abril, UTC-3)."""
    data_local = extrair_data_brasilia(apresentado_em)
    ate_2_de_abril = (data_local.month, data_local.day) <= (4, 2)
    ano_prazo = data_local.year + 1 if ate_2_de_abril else data_local.year + 2
    return f"{ano_prazo}-12-31"


def validar_prazo_pagamento_hub(caminho_hub: Path) -> ResultadoValidacao:
    """Valida prazo_pagamento em hub.csv pela regra constitucional de 2 de abril."""
    evidencias: list[str] = []

    for num_linha, linha in ler_csv_para_analise(caminho_hub):
        processo = linha.get("processo") or ""
        apresentado_em = linha.get("apresentado_em") or ""
        prazo_atual = linha.get("prazo_pagamento") or ""

        try:
            data_brasilia = extrair_data_brasilia(apresentado_em)
            prazo_esperado = calcular_prazo_constitucional(apresentado_em)
        except ValueError:
            evidencias.append(
                f"Linha {num_linha} ({processo}): "
                f"apresentado_em inválido {apresentado_em!r}"
            )
            continue

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
        severidade="ALTA",
        evidencias=evidencias,
    )


def auditar_enunciado(caminho_hub: Path) -> list[ResultadoValidacao]:
    """Executa as validações de regras de negócio descritas em docs/ENUNCIADO.md."""
    return [validar_prazo_pagamento_hub(caminho_hub)]
