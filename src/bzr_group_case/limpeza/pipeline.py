from pathlib import Path

from bzr_group_case.limpeza.entrada.leitura import (
    DIRETORIO_DADOS,
    RAIZ_PROJETO,
    carregar_dados_brutos,
)
from bzr_group_case.limpeza.modelos import ResultadoLimpeza
from bzr_group_case.limpeza.pagamentos import (
    limpar_pagamentos,
    resumir_valor_liquido_arquivo,
)
from bzr_group_case.limpeza.precatorios import conciliar_precatorios
from bzr_group_case.limpeza.saida import (
    NOME_PAGAMENTOS_CSV,
    NOME_PRECATORIOS_CSV,
    NOME_RELATORIO_MD,
    escrever_pagamentos_csv,
    escrever_precatorios_csv,
    escrever_relatorio_markdown,
    gerar_relatorio_markdown,
    validar_base_limpa,
)

DIRETORIO_SAIDA = RAIZ_PROJETO / "data" / "clean"


def executar_limpeza(
    diretorio_dados: Path = DIRETORIO_DADOS,
    diretorio_saida: Path = DIRETORIO_SAIDA,
) -> ResultadoLimpeza:
    """Executa leitura, conciliação, limpeza, escrita e validação do 'Depois'."""
    dados_resolvido = diretorio_dados.resolve()
    saida_resolvida = diretorio_saida.resolve()
    raw_padrao = DIRETORIO_DADOS.resolve()
    if saida_resolvida.is_relative_to(
        dados_resolvido
    ) or saida_resolvida.is_relative_to(raw_padrao):
        raise ValueError(
            "O diretório de saída não pode ser igual nem estar dentro do "
            "diretório de dados brutos."
        )

    dados = carregar_dados_brutos(diretorio_dados)
    precatorios = conciliar_precatorios(dados)
    pagamentos = limpar_pagamentos(
        dados,
        chaves_hub=precatorios.chaves_hub,
        chaves_tribunal=precatorios.chaves_tribunal,
    )
    valor_liquido = resumir_valor_liquido_arquivo(pagamentos.pagamentos)
    ocorrencias = (
        dados.ocorrencias_leitura + precatorios.ocorrencias + pagamentos.ocorrencias
    )

    diretorio_saida.mkdir(parents=True, exist_ok=True)
    caminho_precatorios = escrever_precatorios_csv(
        precatorios.precatorios,
        diretorio_saida / NOME_PRECATORIOS_CSV,
    )
    caminho_pagamentos = escrever_pagamentos_csv(
        pagamentos.pagamentos,
        diretorio_saida / NOME_PAGAMENTOS_CSV,
    )
    verificacoes = validar_base_limpa(
        diretorio_saida,
        precatorios=precatorios,
        pagamentos=pagamentos,
        total_pagamentos_brutos=len(dados.pagamentos),
    )
    conteudo_relatorio = gerar_relatorio_markdown(
        dados=dados,
        precatorios=precatorios,
        pagamentos=pagamentos,
        ocorrencias=ocorrencias,
        valor_liquido_arquivo=valor_liquido,
        verificacoes=verificacoes,
    )
    caminho_relatorio = escrever_relatorio_markdown(
        conteudo_relatorio,
        diretorio_saida / NOME_RELATORIO_MD,
    )

    return ResultadoLimpeza(
        precatorios=precatorios,
        pagamentos=pagamentos,
        ocorrencias=ocorrencias,
        valor_liquido_arquivo=valor_liquido,
        verificacoes=verificacoes,
        arquivos_gerados=(caminho_precatorios, caminho_pagamentos, caminho_relatorio),
    )
