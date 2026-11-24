from pathlib import Path

from bzr_group_case.auditoria.base import DIRETORIO_DADOS, ResultadoValidacao
from bzr_group_case.auditoria.conciliacao import auditar_conciliacao
from bzr_group_case.auditoria.documentacao_tribunal import (
    auditar_documentacao_tribunal,
)
from bzr_group_case.auditoria.enunciado import auditar_enunciado
from bzr_group_case.auditoria.schema_banco import auditar_schema


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
            status = "OK" if item.ok else "FALHA"
            linhas.append(f"  [{status}] {item.validacao}")
            linhas.append(f"    Arquivo: {item.arquivo}")
            for evidencia in item.evidencias:
                linhas.append(f"      - {evidencia}")
            linhas.append("")

    total = len(resultados)
    total_ok = sum(1 for r in resultados if r.ok)
    total_falha = total - total_ok
    linhas.extend(
        [
            separador,
            f"Resumo: {total} validação(ões) | {total_ok} OK | {total_falha} FALHA",
            separador,
        ]
    )
    return "\n".join(linhas)
