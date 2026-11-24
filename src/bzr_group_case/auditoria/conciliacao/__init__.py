from pathlib import Path

from bzr_group_case.auditoria.base import ResultadoValidacao
from bzr_group_case.auditoria.conciliacao.apresentacoes import (
    ORIGEM_CONCILIACAO_APRESENTACOES,
    validar_apresentacoes_contra_hub,
)
from bzr_group_case.auditoria.conciliacao.cadastro import (
    ORIGEM_CONCILIACAO_CADASTRO,
    auditar_cadastro,
)


def auditar_conciliacao(
    caminho_tribunal: Path,
    caminho_hub: Path,
    caminho_apresentacoes: Path,
) -> list[ResultadoValidacao]:
    """Executa todas as conciliações entre bases."""
    return [
        *auditar_cadastro(caminho_tribunal, caminho_hub),
        validar_apresentacoes_contra_hub(caminho_apresentacoes, caminho_hub),
    ]


__all__ = [
    "ORIGEM_CONCILIACAO_APRESENTACOES",
    "ORIGEM_CONCILIACAO_CADASTRO",
    "auditar_cadastro",
    "auditar_conciliacao",
    "validar_apresentacoes_contra_hub",
]
