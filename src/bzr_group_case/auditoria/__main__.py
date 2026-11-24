import argparse

from bzr_group_case.auditoria.base import rotulo_arquivo
from bzr_group_case.auditoria.relatorio import (
    executar_auditoria,
    formatar_relatorio,
    salvar_relatorio_html,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Auditoria dos dados do case.")
    parser.add_argument(
        "--html",
        action="store_true",
        help="gera a visualização da auditoria em docs/auditoria.html",
    )
    args = parser.parse_args(argv)

    resultados = executar_auditoria()
    if args.html:
        destino = salvar_relatorio_html(resultados)
        print(f"Relatório HTML gerado em {rotulo_arquivo(destino)}")
    else:
        print(formatar_relatorio(resultados))


if __name__ == "__main__":
    main()
