import csv
from collections.abc import Sequence
from pathlib import Path

from bzr_group_case.limpeza.modelos import PagamentoLimpo, PrecatorioLimpo

NOME_PRECATORIOS_CSV = "precatorios_limpos.csv"
NOME_PAGAMENTOS_CSV = "pagamentos_limpos.csv"
NOME_RELATORIO_MD = "relatorio_limpeza.md"

COLUNAS_PRECATORIOS: tuple[str, ...] = (
    "numero_processo",
    "ente_devedor",
    "valor_face",
    "apresentado_em",
    "prazo_pagamento",
    "status_conciliacao",
)

COLUNAS_PAGAMENTOS: tuple[str, ...] = (
    "evento_id",
    "numero_processo",
    "tipo",
    "valor",
    "data_pagamento",
    "atualizado_em",
)


def _escrever_csv(
    caminho: Path,
    colunas: Sequence[str],
    linhas: Sequence[Sequence[str]],
) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo, delimiter=",", lineterminator="\n")
        escritor.writerow(colunas)
        escritor.writerows(linhas)
    return caminho


def escrever_precatorios_csv(
    precatorios: Sequence[PrecatorioLimpo],
    caminho: Path,
) -> Path:
    """Grava precatorios_limpos.csv em UTF-8 sem BOM, vírgula e decimais com 2 casas."""
    linhas = [
        (
            p.numero_processo,
            p.ente_devedor,
            f"{p.valor_face:.2f}",
            p.apresentado_em,
            p.prazo_pagamento,
            p.status_conciliacao,
        )
        for p in precatorios
    ]
    return _escrever_csv(caminho, COLUNAS_PRECATORIOS, linhas)


def escrever_pagamentos_csv(
    pagamentos: Sequence[PagamentoLimpo],
    caminho: Path,
) -> Path:
    """Grava pagamentos_limpos.csv em UTF-8 sem BOM, vírgula e decimais com 2 casas."""
    linhas = [
        (
            p.evento_id,
            p.numero_processo,
            p.tipo,
            f"{p.valor:.2f}",
            p.data_pagamento,
            p.atualizado_em,
        )
        for p in pagamentos
    ]
    return _escrever_csv(caminho, COLUNAS_PAGAMENTOS, linhas)
