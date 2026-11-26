from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

ProblemaDiagnostico = Literal["P1", "P2", "P3", "P4"]
CategoriaOcorrencia = Literal["corrigido", "descartado", "em_duvida"]
EntidadeOcorrencia = Literal["arquivo", "precatorio", "pagamento"]
StatusConciliacao = Literal["conciliado", "em_duvida"]


@dataclass(frozen=True)
class RegistroOcorrencia:
    """Registro rastreável de uma anomalia tratada durante a limpeza."""

    problema: ProblemaDiagnostico
    categoria: CategoriaOcorrencia
    entidade: EntidadeOcorrencia
    identificador: str
    origem: str
    campo: str
    valor_original: str
    valor_tratado: str | None
    motivo: str


@dataclass(frozen=True)
class DadosBrutos:
    """Conjunto imutável de registros lidos da camada de entrada e ocorrências P3."""

    tribunal: tuple[tuple[int, dict[str, str]], ...]
    hub: tuple[tuple[int, dict[str, str]], ...]
    apresentacoes: tuple[tuple[int, dict[str, Any]], ...]
    pagamentos: tuple[tuple[int, dict[str, Any]], ...]
    ocorrencias_leitura: tuple[RegistroOcorrencia, ...]


@dataclass(frozen=True)
class PrecatorioLimpo:
    """Cadastro limpo de um precatório após conciliação (apenas campos cadastrais)."""

    numero_processo: str
    ente_devedor: str
    valor_face: Decimal
    apresentado_em: str
    prazo_pagamento: str
    status_conciliacao: StatusConciliacao


@dataclass(frozen=True)
class ResultadoConciliacaoPrecatorios:
    """Resultado da conciliação cadastral de precatórios e cálculo de prazos."""

    precatorios: tuple[PrecatorioLimpo, ...]
    chaves_hub: frozenset[str]
    chaves_tribunal: frozenset[str]
    prazos_hub_originais: Mapping[str, str | None]
    ocorrencias: tuple[RegistroOcorrencia, ...]
