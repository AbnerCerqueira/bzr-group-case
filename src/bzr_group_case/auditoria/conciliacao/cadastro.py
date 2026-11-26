import re
import unicodedata
from decimal import Decimal
from pathlib import Path

from bzr_group_case.auditoria.base import (
    ResultadoValidacao,
    ler_csv_para_analise,
    rotulo_arquivo,
    somente_digitos,
)

ORIGEM_CONCILIACAO_CADASTRO = "Conciliação (data/raw/tribunal.csv x data/raw/hub.csv)"

PADRAO_MONETARIO_PONTO = re.compile(r"-?\d+(\.\d+)?", re.ASCII)
PADRAO_MONETARIO_BR = re.compile(r"-?\d{1,3}(\.\d{3})*,\d+", re.ASCII)


def _normalizar_texto(texto: str) -> str:
    """Remove acentos e caixa para distinguir grafia de divergência de texto."""
    sem_acentos = "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(caractere)
    )
    return " ".join(sem_acentos.casefold().split())


def _converter_valor_monetario(texto: str) -> Decimal | None:
    """Converte apenas formatos monetários inequívocos (decimal '.' ou pt-BR)."""
    limpo = texto.strip()
    if PADRAO_MONETARIO_PONTO.fullmatch(limpo):
        return Decimal(limpo)
    if PADRAO_MONETARIO_BR.fullmatch(limpo):
        return Decimal(limpo.replace(".", "").replace(",", "."))
    return None


def indexar_csv_por_processo(
    caminho: Path,
    coluna_processo: str,
) -> dict[str, tuple[int, dict[str, str | None]]]:
    """Indexa linhas de um CSV pela chave CNJ normalizada (apenas dígitos)."""
    indice: dict[str, tuple[int, dict[str, str | None]]] = {}
    for num_linha, linha in ler_csv_para_analise(caminho):
        chave = somente_digitos(linha.get(coluna_processo) or "")
        if chave and chave not in indice:
            indice[chave] = (num_linha, linha)
    return indice


def validar_cobertura_processos(
    caminho_tribunal: Path,
    caminho_hub: Path,
) -> ResultadoValidacao:
    """Identifica processos presentes apenas no tribunal ou apenas no hub."""
    tribunal = indexar_csv_por_processo(caminho_tribunal, "numero_processo")
    hub = indexar_csv_por_processo(caminho_hub, "processo")
    rotulo_tribunal = rotulo_arquivo(caminho_tribunal)
    rotulo_hub = rotulo_arquivo(caminho_hub)
    evidencias: list[str] = []

    for chave, (num_linha, linha) in tribunal.items():
        if chave not in hub:
            processo = linha.get("numero_processo") or ""
            evidencias.append(
                f"Processo {processo!r} (linha {num_linha} de {rotulo_tribunal}): "
                f"ausente em {rotulo_hub}"
            )

    for chave, (num_linha, linha) in hub.items():
        if chave not in tribunal:
            processo = linha.get("processo") or ""
            evidencias.append(
                f"Processo {processo!r} (linha {num_linha} de {rotulo_hub}): "
                f"ausente em {rotulo_tribunal}"
            )

    return ResultadoValidacao(
        origem=ORIGEM_CONCILIACAO_CADASTRO,
        validacao="Cobertura de processos (presença nas duas bases)",
        arquivo=f"{rotulo_tribunal} x {rotulo_hub}",
        evidencias=evidencias,
    )


def validar_formato_chave_entre_bases(
    caminho_tribunal: Path,
    caminho_hub: Path,
) -> ResultadoValidacao:
    """Identifica processos iguais escritos com formatação diferente entre as bases."""
    tribunal = indexar_csv_por_processo(caminho_tribunal, "numero_processo")
    hub = indexar_csv_por_processo(caminho_hub, "processo")
    evidencias: list[str] = []

    for chave, (linha_t, reg_t) in tribunal.items():
        if chave not in hub:
            continue
        linha_h, reg_h = hub[chave]
        proc_t = reg_t.get("numero_processo") or ""
        proc_h = reg_h.get("processo") or ""
        if proc_t != proc_h:
            evidencias.append(
                f"tribunal (linha {linha_t})={proc_t!r} vs "
                f"hub (linha {linha_h})={proc_h!r}"
            )

    return ResultadoValidacao(
        origem=ORIGEM_CONCILIACAO_CADASTRO,
        validacao="Formato do número do processo entre bases",
        arquivo=f"{rotulo_arquivo(caminho_tribunal)} x {rotulo_arquivo(caminho_hub)}",
        evidencias=evidencias,
    )


def validar_ente_devedor_entre_bases(
    caminho_tribunal: Path,
    caminho_hub: Path,
) -> ResultadoValidacao:
    """Compara ente_devedor (tribunal) x ente (hub) nos processos em comum."""
    tribunal = indexar_csv_por_processo(caminho_tribunal, "numero_processo")
    hub = indexar_csv_por_processo(caminho_hub, "processo")
    evidencias: list[str] = []

    for chave, (linha_t, reg_t) in tribunal.items():
        if chave not in hub:
            continue
        linha_h, reg_h = hub[chave]
        processo = reg_t.get("numero_processo") or ""
        ente_t = reg_t.get("ente_devedor") or ""
        ente_h = reg_h.get("ente") or ""

        if ente_t == ente_h:
            continue

        mesmo_normalizado = _normalizar_texto(ente_t) == _normalizar_texto(ente_h)
        detalhe = (
            "mesmo texto sem acento/caixa"
            if mesmo_normalizado
            else "textos diferentes mesmo sem acento/caixa"
        )
        evidencias.append(
            f"{processo} (tribunal L{linha_t} x hub L{linha_h}): "
            f"tribunal={ente_t!r} vs hub={ente_h!r} ({detalhe})"
        )

    return ResultadoValidacao(
        origem=ORIGEM_CONCILIACAO_CADASTRO,
        validacao="Ente devedor entre bases",
        arquivo=f"{rotulo_arquivo(caminho_tribunal)} x {rotulo_arquivo(caminho_hub)}",
        evidencias=evidencias,
    )


def validar_valor_face_entre_bases(
    caminho_tribunal: Path,
    caminho_hub: Path,
) -> ResultadoValidacao:
    """Compara valor_face numericamente entre tribunal.csv e hub.csv."""
    tribunal = indexar_csv_por_processo(caminho_tribunal, "numero_processo")
    hub = indexar_csv_por_processo(caminho_hub, "processo")
    evidencias: list[str] = []

    for chave, (linha_t, reg_t) in tribunal.items():
        if chave not in hub:
            continue
        linha_h, reg_h = hub[chave]
        processo = reg_t.get("numero_processo") or ""
        bruto_t = reg_t.get("valor_face") or ""
        bruto_h = reg_h.get("valor_face") or ""
        val_t = _converter_valor_monetario(bruto_t)
        val_h = _converter_valor_monetario(bruto_h)

        if val_t is None or val_h is None:
            evidencias.append(
                f"{processo} (tribunal L{linha_t} x hub L{linha_h}): "
                f"valor não numérico (tribunal={bruto_t!r} vs hub={bruto_h!r})"
            )
        elif val_t != val_h:
            diferenca = val_h - val_t
            evidencias.append(
                f"{processo} (tribunal L{linha_t} x hub L{linha_h}): "
                f"tribunal={val_t:.2f} vs hub={val_h:.2f} "
                f"(diferença hub - tribunal: {diferenca:+.2f})"
            )

    return ResultadoValidacao(
        origem=ORIGEM_CONCILIACAO_CADASTRO,
        validacao="Valor de face entre bases",
        arquivo=f"{rotulo_arquivo(caminho_tribunal)} x {rotulo_arquivo(caminho_hub)}",
        evidencias=evidencias,
    )


def auditar_cadastro(
    caminho_tribunal: Path,
    caminho_hub: Path,
) -> list[ResultadoValidacao]:
    """Executa todas as conciliações cadastrais entre tribunal.csv e hub.csv."""
    return [
        validar_cobertura_processos(caminho_tribunal, caminho_hub),
        validar_formato_chave_entre_bases(caminho_tribunal, caminho_hub),
        validar_ente_devedor_entre_bases(caminho_tribunal, caminho_hub),
        validar_valor_face_entre_bases(caminho_tribunal, caminho_hub),
    ]
