from bzr_group_case.auditoria.relatorio import executar_auditoria, formatar_relatorio


def main() -> None:
    resultados = executar_auditoria()
    print(formatar_relatorio(resultados))


if __name__ == "__main__":
    main()
