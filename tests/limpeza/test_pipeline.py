import csv
import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from bzr_group_case.limpeza import (
    DIRETORIO_DADOS,
    VerificacaoSaida,
    executar_limpeza,
)
from bzr_group_case.limpeza.__main__ import main
from bzr_group_case.limpeza.saida import (
    COLUNAS_PAGAMENTOS,
    COLUNAS_PRECATORIOS,
    NOME_PAGAMENTOS_CSV,
    NOME_PRECATORIOS_CSV,
    NOME_RELATORIO_MD,
    validar_base_limpa,
)


def _hashes_diretorio(diretorio: Path) -> dict[str, str]:
    return {
        arquivo.name: hashlib.sha256(arquivo.read_bytes()).hexdigest()
        for arquivo in sorted(diretorio.iterdir())
        if arquivo.is_file()
    }


def _ler_csv(caminho: Path) -> tuple[list[str], list[dict[str, str]]]:
    conteudo = caminho.read_bytes()
    assert not conteudo.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in conteudo
    texto = conteudo.decode("utf-8")
    leitor = csv.reader(texto.splitlines(), delimiter=",")
    cabecalho = next(leitor)
    linhas = [dict(zip(cabecalho, linha, strict=True)) for linha in leitor]
    return cabecalho, linhas


def test_pipeline_end_to_end_dados_reais_e_preserva_raw(tmp_path: Path) -> None:
    hashes_antes = _hashes_diretorio(DIRETORIO_DADOS)

    resultado = executar_limpeza(
        diretorio_dados=DIRETORIO_DADOS,
        diretorio_saida=tmp_path,
    )

    assert _hashes_diretorio(DIRETORIO_DADOS) == hashes_antes
    assert resultado.todas_verificacoes_ok is True
    assert len(resultado.verificacoes) == 5

    nomes_gerados = sorted(p.name for p in tmp_path.iterdir())
    assert nomes_gerados == sorted(
        [NOME_PAGAMENTOS_CSV, NOME_PRECATORIOS_CSV, NOME_RELATORIO_MD]
    )
    assert tuple(p.name for p in resultado.arquivos_gerados) == (
        NOME_PRECATORIOS_CSV,
        NOME_PAGAMENTOS_CSV,
        NOME_RELATORIO_MD,
    )

    cab_prec, linhas_prec = _ler_csv(tmp_path / NOME_PRECATORIOS_CSV)
    assert tuple(cab_prec) == COLUNAS_PRECATORIOS
    assert len(linhas_prec) == 6
    por_processo = {linha["numero_processo"]: linha for linha in linhas_prec}
    assert por_processo["00123451020198260053"]["prazo_pagamento"] == "2026-12-31"
    assert por_processo["00123451020198260053"]["status_conciliacao"] == "conciliado"
    assert por_processo["00567895420174036100"]["prazo_pagamento"] == "2026-12-31"
    assert por_processo["00678906520168260053"]["status_conciliacao"] == "em_duvida"

    cab_pag, linhas_pag = _ler_csv(tmp_path / NOME_PAGAMENTOS_CSV)
    assert tuple(cab_pag) == COLUNAS_PAGAMENTOS
    assert len(linhas_pag) == 7
    por_evento = {linha["evento_id"]: linha for linha in linhas_pag}
    assert por_evento["ev-001"]["valor"] == "15500.00"
    assert por_evento["ev-002"]["data_pagamento"] == "2025-04-10"
    assert por_evento["ev-007"]["tipo"] == "estorno"
    assert por_evento["ev-007"]["valor"] == "5000.00"

    relatorio = (tmp_path / NOME_RELATORIO_MD).read_text(encoding="utf-8")
    for trecho in (
        "## 1. Resumo executivo",
        "## 2. Premissas explícitas adotadas",
        "0012345-10.2019.8.26.0053",
        "## 3. Visão 1-para-1 dos precatórios (6 processos)",
        "## 4. Visão 1-para-1 dos eventos de pagamento",
        "## 5. Detalhamento das ocorrências por destino",
        "### Corrigidos",
        "### Descartados (com motivo)",
        "### Em dúvida (sem sobrescrever)",
        "## 6. Efeito líquido apenas dos eventos deste arquivo por processo",
        "não representam o saldo histórico acumulado",
        "0034567-32.2018.8.26.0405",
        "0056789-54.2017.4.03.6100",
        "0067890-65.2016.8.26.0053",
        "ev-007",
        '## 7. Validação automática da base limpa ("Depois")',
        "[OK]",
    ):
        assert trecho in relatorio
    assert "[FALHA]" not in relatorio


def test_pipeline_deterministico_byte_a_byte(tmp_path: Path) -> None:
    saida_a = tmp_path / "exec_a"
    saida_b = tmp_path / "exec_b"

    executar_limpeza(diretorio_dados=DIRETORIO_DADOS, diretorio_saida=saida_a)
    executar_limpeza(diretorio_dados=DIRETORIO_DADOS, diretorio_saida=saida_b)

    for nome in (NOME_PRECATORIOS_CSV, NOME_PAGAMENTOS_CSV, NOME_RELATORIO_MD):
        assert (saida_a / nome).read_bytes() == (saida_b / nome).read_bytes()


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


def _sub_bytes(alvo: bytes, antigo: bytes, novo: bytes) -> bytes:
    return alvo.replace(antigo, novo, 1)


@pytest.mark.parametrize(
    ("arquivo", "transformar", "indice_regra"),
    [
        (NOME_PRECATORIOS_CSV, lambda b: b"\xef\xbb\xbf" + b, 0),
        (NOME_PRECATORIOS_CSV, lambda b: b.replace(b"\n", b"\r\n"), 0),
        (NOME_PRECATORIOS_CSV, lambda b: b.replace(b",", b";"), 0),
        (
            NOME_PRECATORIOS_CSV,
            lambda b: _sub_bytes(
                b, b"status_conciliacao\n", b"status_conciliacao,total_pago\n"
            ),
            0,
        ),
        (
            NOME_PRECATORIOS_CSV,
            lambda b: _sub_bytes(b, b",conciliado\n", b",conciliado,extra\n"),
            0,
        ),
        (
            NOME_PRECATORIOS_CSV,
            lambda b: _sub_bytes(
                b, b"00123451020198260053", b"0012345-10.2019.8.26.0053"
            ),
            1,
        ),
        (
            NOME_PRECATORIOS_CSV,
            lambda b: _sub_bytes(b, b",45000.00,", b',"45.000,00",'),
            1,
        ),
        (
            NOME_PRECATORIOS_CSV,
            lambda b: _sub_bytes(b, "Município de São Paulo".encode(), b""),
            1,
        ),
        (
            NOME_PRECATORIOS_CSV,
            lambda b: _sub_bytes(b, b"2025-04-02,2026-12-31", b"2025-04-02,2027-12-31"),
            2,
        ),
        (
            NOME_PRECATORIOS_CSV,
            lambda b: _sub_bytes(b, b"2025-04-02,2026-12-31", b"lixo,2026-12-31"),
            2,
        ),
        (
            NOME_PRECATORIOS_CSV,
            lambda b: _sub_bytes(b, b"2025-04-02,2026-12-31", b",2026-12-31"),
            2,
        ),
        (NOME_PAGAMENTOS_CSV, lambda b: _sub_bytes(b, b"ev-002,", b"ev-001,"), 3),
        (
            NOME_PAGAMENTOS_CSV,
            lambda b: _sub_bytes(
                b,
                b"ev-008,00456784320215020011",
                b"ev-008,99999999999999999999",
            ),
            3,
        ),
        (
            NOME_PAGAMENTOS_CSV,
            lambda b: _sub_bytes(b, b",2025-03-10,", b",10/03/2025,"),
            3,
        ),
        (
            NOME_PAGAMENTOS_CSV,
            lambda b: _sub_bytes(
                b, b"2025-03-11T09:00:00-03:00", b"2025-03-11T09:00:00"
            ),
            3,
        ),
        (
            NOME_PAGAMENTOS_CSV,
            lambda b: b"\n".join(b.splitlines()[:-1]) + b"\n",
            4,
        ),
    ],
)
def test_validacao_depois_detecta_adulteracoes(
    tmp_path: Path,
    arquivo: str,
    transformar: Callable[[bytes], bytes],
    indice_regra: int,
) -> None:
    resultado = executar_limpeza(
        diretorio_dados=DIRETORIO_DADOS,
        diretorio_saida=tmp_path,
    )
    alvo = tmp_path / arquivo
    original = alvo.read_bytes()
    adulterado = transformar(original)
    assert adulterado != original
    alvo.write_bytes(adulterado)

    verificacoes = validar_base_limpa(
        tmp_path,
        precatorios=resultado.precatorios,
        pagamentos=resultado.pagamentos,
        total_pagamentos_brutos=len(resultado.pagamentos.itens_rastreados),
    )
    assert verificacoes[indice_regra].ok is False
    assert verificacoes[indice_regra].detalhes


def test_validacao_depois_detecta_arquivo_ausente(tmp_path: Path) -> None:
    resultado = executar_limpeza(
        diretorio_dados=DIRETORIO_DADOS,
        diretorio_saida=tmp_path,
    )
    (tmp_path / NOME_PAGAMENTOS_CSV).unlink()

    verificacoes = validar_base_limpa(
        tmp_path,
        precatorios=resultado.precatorios,
        pagamentos=resultado.pagamentos,
        total_pagamentos_brutos=len(resultado.pagamentos.itens_rastreados),
    )
    assert verificacoes[0].ok is False
    assert verificacoes[3].ok is False
    assert verificacoes[4].ok is False


def test_cli_main_sucesso_falha_validacao_e_erro_diretorio(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codigo = main(["--saida", str(tmp_path)])
    saida = capsys.readouterr().out

    assert codigo == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        [NOME_PAGAMENTOS_CSV, NOME_PRECATORIOS_CSV, NOME_RELATORIO_MD]
    )
    assert "[OK]" in saida
    assert "[FALHA]" not in saida

    with pytest.raises(SystemExit) as exc:
        main(["--saida", str(DIRETORIO_DADOS)])
    assert exc.value.code == 2
    assert "dados brutos" in capsys.readouterr().err

    resultado_real = executar_limpeza(
        diretorio_dados=DIRETORIO_DADOS,
        diretorio_saida=tmp_path / "falha",
    )
    resultado_falho = type(resultado_real)(
        precatorios=resultado_real.precatorios,
        pagamentos=resultado_real.pagamentos,
        ocorrencias=resultado_real.ocorrencias,
        valor_liquido_arquivo=resultado_real.valor_liquido_arquivo,
        verificacoes=(VerificacaoSaida("Regra simulada", False, ("erro",)),),
        arquivos_gerados=resultado_real.arquivos_gerados,
    )
    monkeypatch.setattr(
        "bzr_group_case.limpeza.__main__.executar_limpeza",
        lambda **_: resultado_falho,
    )
    assert main(["--saida", str(tmp_path / "falha")]) == 1
    assert "[FALHA]" in capsys.readouterr().out
