from pathlib import Path

from bzr_group_case.auditoria.base import ResultadoValidacao
from bzr_group_case.auditoria.documentacao_tribunal.pagamentos import (
    ORIGEM_DOC_PAGAMENTOS,
    auditar_pagamentos,
)
from bzr_group_case.auditoria.documentacao_tribunal.tribunal import (
    ORIGEM_DOC_TRIBUNAL,
    auditar_tribunal,
)


def auditar_documentacao_tribunal(
    caminho_pagamentos: Path,
    caminho_tribunal: Path,
) -> list[ResultadoValidacao]:
    """Executa todas as validações de docs/DOCUMENTACAO_TRIBUNAL.md."""
    return [
        *auditar_pagamentos(caminho_pagamentos),
        *auditar_tribunal(caminho_tribunal),
    ]


__all__ = [
    "ORIGEM_DOC_PAGAMENTOS",
    "ORIGEM_DOC_TRIBUNAL",
    "auditar_documentacao_tribunal",
    "auditar_pagamentos",
    "auditar_tribunal",
]
