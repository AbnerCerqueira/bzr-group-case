from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from bzr_group_case.auditoria.base import (
    ResultadoValidacao,
    ler_csv_para_analise,
    rotulo_arquivo,
)

ORIGEM_ENUNCIADO = "docs/ENUNCIADO.md"
FUSO_BRASILIA = ZoneInfo("America/Sao_Paulo")


def extrair_data_brasilia(apresentado_em: str) -> date:
    """Converte data ou data/hora ISO para a data civil no horário de Brasília."""
    valor = apresentado_em.strip()
    if len(valor) == 10:
        return date.fromisoformat(valor)

    if valor.endswith(("Z", "z")):
        if "T" not in valor and "t" not in valor and " " not in valor:
            raise ValueError(f"Data/hora ISO inválida: {apresentado_em!r}")
        texto = f"{valor[:-1]}+00:00"
    else:
        texto = valor

    instante = datetime.fromisoformat(texto)
    if instante.tzinfo is not None:
        instante = instante.astimezone(FUSO_BRASILIA)
    return instante.date()


def _prazo_da_data_local(data_local: date) -> str:
    ate_2_de_abril = (data_local.month, data_local.day) <= (4, 2)
    ano_prazo = data_local.year + 1 if ate_2_de_abril else data_local.year + 2
    return f"{ano_prazo}-12-31"


def calcular_prazo_constitucional(apresentado_em: str) -> str:
    """Calcula o prazo constitucional (corte inclusivo em 2 de abril, Brasília)."""
    return _prazo_da_data_local(extrair_data_brasilia(apresentado_em))


def validar_prazo_pagamento_hub(caminho_hub: Path) -> ResultadoValidacao:
    """Valida prazo_pagamento em hub.csv pela regra constitucional de 2 de abril."""
    evidencias: list[str] = []

    for num_linha, linha in ler_csv_para_analise(caminho_hub):
        processo = linha.get("processo") or ""
        apresentado_em = linha.get("apresentado_em") or ""
        prazo_atual = linha.get("prazo_pagamento") or ""

        try:
            data_brasilia = extrair_data_brasilia(apresentado_em)
            prazo_esperado = _prazo_da_data_local(data_brasilia)
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
        evidencias=evidencias,
    )


def auditar_enunciado(caminho_hub: Path) -> list[ResultadoValidacao]:
    """Executa as validações de regras de negócio descritas em docs/ENUNCIADO.md."""
    return [validar_prazo_pagamento_hub(caminho_hub)]
