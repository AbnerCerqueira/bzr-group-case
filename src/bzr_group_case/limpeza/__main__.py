import argparse
from collections.abc import Sequence
from pathlib import Path

from bzr_group_case.limpeza.entrada.leitura import DIRETORIO_DADOS, RAIZ_PROJETO
from bzr_group_case.limpeza.pipeline import DIRETORIO_SAIDA, executar_limpeza


def _rotulo_caminho(caminho: Path) -> str:
    try:
        return str(caminho.resolve().relative_to(RAIZ_PROJETO.resolve()))
    except ValueError:
        return str(caminho)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Executa o pipeline de limpeza e conciliação de precatórios."
    )
    parser.add_argument(
        "--entrada",
        type=Path,
        default=DIRETORIO_DADOS,
        help="diretório com os arquivos brutos (padrão: data/raw)",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=DIRETORIO_SAIDA,
        help="diretório de destino dos arquivos limpos (padrão: data/clean)",
    )
    args = parser.parse_args(argv)

    try:
        resultado = executar_limpeza(
            diretorio_dados=args.entrada,
            diretorio_saida=args.saida,
        )
    except ValueError as erro:
        parser.error(str(erro))

    print("Arquivos gerados:")
    for arquivo in resultado.arquivos_gerados:
        print(f"  - {_rotulo_caminho(arquivo)}")

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
