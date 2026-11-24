import json
from pathlib import Path
from typing import Any

from bzr_group_case.auditoria.base import (
    DIRETORIO_DADOS,
    RAIZ_PROJETO,
    ResultadoValidacao,
)
from bzr_group_case.auditoria.conciliacao import auditar_conciliacao
from bzr_group_case.auditoria.documentacao_tribunal import (
    auditar_documentacao_tribunal,
)
from bzr_group_case.auditoria.enunciado import auditar_enunciado
from bzr_group_case.auditoria.schema_banco import auditar_schema

CAMINHO_TEMPLATE_HTML = Path(__file__).with_name("painel.html")
CAMINHO_PADRAO_HTML = RAIZ_PROJETO / "docs" / "auditoria.html"
MARCADOR_DADOS = "__DATA__"


def executar_auditoria(
    diretorio_dados: Path = DIRETORIO_DADOS,
) -> list[ResultadoValidacao]:
    """Executa todas as validações de auditoria agrupáveis por origem."""
    pagamentos = diretorio_dados / "pagamentos.json"
    tribunal = diretorio_dados / "tribunal.csv"
    hub = diretorio_dados / "hub.csv"
    apresentacoes = diretorio_dados / "apresentacoes.json"

    return [
        *auditar_documentacao_tribunal(pagamentos, tribunal),
        *auditar_schema(tribunal, hub, pagamentos),
        *auditar_enunciado(hub),
        *auditar_conciliacao(tribunal, hub, apresentacoes),
    ]


def formatar_relatorio(resultados: list[ResultadoValidacao]) -> str:
    """Formata o relatório agrupando todas as evidências pela origem."""
    separador = "=" * 72
    subseparador = "-" * 72
    linhas = [
        separador,
        "AUDITORIA DE DADOS — Evidências por origem",
        separador,
        "",
    ]

    grupos: dict[str, list[ResultadoValidacao]] = {}
    for resultado in resultados:
        grupos.setdefault(resultado.origem, []).append(resultado)

    for origem, itens in grupos.items():
        linhas.extend([f"Origem: {origem}", subseparador])
        for item in itens:
            rotulo_status = "OK" if item.ok else f"FALHA | {item.severidade}"
            linhas.append(f"  [{rotulo_status}] {item.validacao}")
            linhas.append(f"    Arquivo: {item.arquivo}")
            for evidencia in item.evidencias:
                linhas.append(f"      - {evidencia}")
            linhas.append("")

    total = len(resultados)
    falhas = [r for r in resultados if not r.ok]
    total_ok = total - len(falhas)
    alta = sum(1 for r in falhas if r.severidade == "ALTA")
    media = sum(1 for r in falhas if r.severidade == "MEDIA")
    baixa = sum(1 for r in falhas if r.severidade == "BAIXA")
    linhas.extend(
        [
            separador,
            (
                f"Resumo: {total} validação(ões) | {total_ok} OK | "
                f"{len(falhas)} FALHA (ALTA: {alta}, MEDIA: {media}, BAIXA: {baixa})"
            ),
            separador,
        ]
    )
    return "\n".join(linhas)


def _serializar_dados(resultados: list[ResultadoValidacao]) -> dict[str, Any]:
    falhas = [r for r in resultados if not r.ok]
    return {
        "resumo": {
            "total_validacoes": len(resultados),
            "ok": len(resultados) - len(falhas),
            "falhas": len(falhas),
            "falhas_por_severidade": {
                severidade: sum(1 for r in falhas if r.severidade == severidade)
                for severidade in ("ALTA", "MEDIA", "BAIXA")
            },
            "total_evidencias": sum(len(r.evidencias) for r in resultados),
        },
        "resultados": [
            {
                "origem": r.origem,
                "validacao": r.validacao,
                "arquivo": r.arquivo,
                "severidade": r.severidade,
                "status": "OK" if r.ok else "FALHA",
                "total_evidencias": len(r.evidencias),
                "evidencias": list(r.evidencias),
            }
            for r in resultados
        ],
    }


def formatar_relatorio_html(resultados: list[ResultadoValidacao]) -> str:
    """Gera a página HTML autocontida da auditoria a partir de ``painel.html``."""
    template = CAMINHO_TEMPLATE_HTML.read_text(encoding="utf-8")
    dados = json.dumps(_serializar_dados(resultados), ensure_ascii=False)
    # "</" escapado evita que alguma evidência feche a tag <script>.
    return template.replace(MARCADOR_DADOS, dados.replace("</", "<\\/"))


def salvar_relatorio_html(
    resultados: list[ResultadoValidacao],
    destino: Path = CAMINHO_PADRAO_HTML,
) -> Path:
    """Grava a página HTML da auditoria em ``destino`` e retorna o caminho."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(formatar_relatorio_html(resultados), encoding="utf-8")
    return destino
