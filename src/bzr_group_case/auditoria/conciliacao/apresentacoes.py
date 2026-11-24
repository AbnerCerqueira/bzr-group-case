import json
from pathlib import Path

from bzr_group_case.auditoria.base import (
    ResultadoValidacao,
    rotulo_arquivo,
    somente_digitos,
)
from bzr_group_case.auditoria.conciliacao.cadastro import indexar_csv_por_processo

ORIGEM_CONCILIACAO_APRESENTACOES = (
    "Conciliação (data/apresentacoes.json x data/hub.csv)"
)


def validar_apresentacoes_contra_hub(
    caminho_apresentacoes: Path,
    caminho_hub: Path,
) -> ResultadoValidacao:
    """Valida consistência bidirecional entre apresentacoes.json e hub.csv."""
    rotulo_apres = rotulo_arquivo(caminho_apresentacoes)
    rotulo_hub = rotulo_arquivo(caminho_hub)
    evidencias: list[str] = []

    try:
        dados = json.loads(caminho_apresentacoes.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as erro:
        return ResultadoValidacao(
            origem=ORIGEM_CONCILIACAO_APRESENTACOES,
            validacao="Cobertura e datas de apresentação entre bases",
            arquivo=f"{rotulo_apres} x {rotulo_hub}",
            severidade="MEDIA",
            evidencias=[f"Erro ao ler {rotulo_apres}: {erro}"],
        )

    if not isinstance(dados, list):
        return ResultadoValidacao(
            origem=ORIGEM_CONCILIACAO_APRESENTACOES,
            validacao="Cobertura e datas de apresentação entre bases",
            arquivo=f"{rotulo_apres} x {rotulo_hub}",
            severidade="MEDIA",
            evidencias=[f"Esperado lista JSON, encontrado {type(dados).__name__}"],
        )

    hub = indexar_csv_por_processo(caminho_hub, "processo")
    chaves_apresentacoes: set[str] = set()

    for indice, registro in enumerate(dados, start=1):
        if not isinstance(registro, dict):
            evidencias.append(
                f"Item {indice}: esperado objeto JSON, "
                f"encontrado {type(registro).__name__}"
            )
            continue

        processo = str(registro.get("processo") or "")
        apresentado_em = str(registro.get("apresentado_em") or "")
        chave = somente_digitos(processo)
        if chave:
            chaves_apresentacoes.add(chave)

        if chave not in hub:
            evidencias.append(
                f"Item {indice} ({processo}): apresentado_em={apresentado_em!r} "
                f"ausente em {rotulo_hub}"
            )
            continue

        linha_h, reg_h = hub[chave]
        apresentado_hub = reg_h.get("apresentado_em") or ""
        if apresentado_hub != apresentado_em:
            evidencias.append(
                f"Item {indice} ({processo}, hub L{linha_h}): "
                f"apresentacoes={apresentado_em!r} vs hub={apresentado_hub!r}"
            )

    for chave, (linha_h, reg_h) in hub.items():
        if chave not in chaves_apresentacoes:
            processo = reg_h.get("processo") or ""
            evidencias.append(
                f"Linha {linha_h} de {rotulo_hub} ({processo}): "
                f"ausente em {rotulo_apres}"
            )

    return ResultadoValidacao(
        origem=ORIGEM_CONCILIACAO_APRESENTACOES,
        validacao="Cobertura e datas de apresentação entre bases",
        arquivo=f"{rotulo_apres} x {rotulo_hub}",
        severidade="MEDIA",
        evidencias=evidencias,
    )
