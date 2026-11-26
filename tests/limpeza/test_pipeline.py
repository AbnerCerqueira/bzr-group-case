import json
from pathlib import Path

import pytest

from bzr_group_case.limpeza import DIRETORIO_DADOS, executar_limpeza
from bzr_group_case.limpeza.saida import (
    NOME_PAGAMENTOS_CSV,
    NOME_PRECATORIOS_CSV,
    NOME_RELATORIO_MD,
)


def test_smoke_pipeline_limpeza(tmp_path: Path) -> None:
    resultado = executar_limpeza(
        diretorio_dados=DIRETORIO_DADOS,
        diretorio_saida=tmp_path,
    )
    assert resultado.todas_verificacoes_ok is True
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        [NOME_PAGAMENTOS_CSV, NOME_PRECATORIOS_CSV, NOME_RELATORIO_MD]
    )


def test_pipeline_protege_entrada_e_subdiretorios(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="dados brutos"):
        executar_limpeza(diretorio_dados=tmp_path, diretorio_saida=tmp_path)

    with pytest.raises(ValueError, match="dados brutos"):
        executar_limpeza(diretorio_dados=tmp_path, diretorio_saida=tmp_path / "sub")

    with pytest.raises(ValueError, match="dados brutos"):
        executar_limpeza(
            diretorio_dados=tmp_path,
            diretorio_saida=DIRETORIO_DADOS / "sub",
        )


def test_pipeline_sintetico_sem_apresentado_em_nao_gera_falso_positivo_nem_vaza_ids(
    tmp_path: Path,
) -> None:
    entrada = tmp_path / "raw"
    saida = tmp_path / "clean"
    entrada.mkdir()
    (entrada / "tribunal.csv").write_text(
        "numero_processo,ente_devedor,valor_face\n"
        "0099999-11.2020.8.26.0053,Estado de São Paulo,1000.00\n",
        encoding="utf-8",
        newline="\n",
    )
    (entrada / "hub.csv").write_text(
        "processo,ente,valor_face,apresentado_em,prazo_pagamento\n",
        encoding="utf-8",
        newline="\n",
    )
    (entrada / "apresentacoes.json").write_text(json.dumps([]), encoding="utf-8")
    (entrada / "pagamentos.json").write_text(json.dumps([]), encoding="utf-8")

    resultado = executar_limpeza(diretorio_dados=entrada, diretorio_saida=saida)
    assert resultado.todas_verificacoes_ok is True

    relatorio = (saida / NOME_RELATORIO_MD).read_text(encoding="utf-8")
    assert "Nenhuma ocorrência afetada neste lote." in relatorio
    assert "ev-001" not in relatorio
    assert "0012345-10.2019.8.26.0053" not in relatorio
