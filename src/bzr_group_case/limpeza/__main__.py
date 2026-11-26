import argparse
from collections.abc import Sequence

from bzr_group_case.comum import rotulo_arquivo
from bzr_group_case.limpeza.pipeline import executar_limpeza
from bzr_group_case.limpeza.saida import salvar_relatorio_html


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Executa o pipeline de limpeza e conciliação de precatórios."
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="gera também a visualização interativa em docs/limpeza.html",
    )
    args = parser.parse_args(argv)

    resultado = executar_limpeza()

    print("Arquivos gerados:")
    for arquivo in resultado.arquivos_gerados:
        print(f"  - {rotulo_arquivo(arquivo)}")

    if args.html:
        destino = salvar_relatorio_html(resultado)
        print(f"Relatório HTML gerado em {rotulo_arquivo(destino)}")

    print(
        f"Resumo: {len(resultado.precatorios.precatorios)} precatórios, "
        f"{len(resultado.pagamentos.pagamentos)} pagamentos limpos, "
        f"{len(resultado.ocorrencias)} ocorrências registradas."
    )

    print('Validação automática ("Depois"):')
    for verificacao in resultado.verificacoes:
        marca = "[OK]" if verificacao.ok else "[FALHA]"
        print(f"  {marca} {verificacao.regra}")
        for detalhe in verificacao.detalhes:
            print(f"    - {detalhe}")

    return 0 if resultado.todas_verificacoes_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
