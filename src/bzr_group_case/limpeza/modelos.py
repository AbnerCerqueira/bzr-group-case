from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

ProblemaDiagnostico = Literal["P1", "P2", "P3", "P4"]
CategoriaOcorrencia = Literal["corrigido", "descartado", "em_duvida"]
EntidadeOcorrencia = Literal["arquivo", "precatorio", "pagamento"]
StatusConciliacao = Literal["conciliado", "em_duvida"]
TipoPagamento = Literal["pagamento", "estorno"]
DestinoPagamento = Literal["mantido", "deduplicado", "substituido", "descartado"]


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


@dataclass(frozen=True)
class PagamentoLimpo:
    """Evento financeiro limpo pronto para carga na tabela pagamento."""

    evento_id: str
    numero_processo: str
    tipo: TipoPagamento
    valor: Decimal
    data_pagamento: str
    atualizado_em: str


@dataclass(frozen=True)
class RastreamentoPagamento:
    """Rastreamento 1-para-1 de cada item lido de pagamentos.json."""

    indice: int
    evento_id: str
    numero_processo: str
    tipo: str
    valor_original: str
    data_pagamento: str
    atualizado_em: str
    destino: DestinoPagamento
    problemas: tuple[ProblemaDiagnostico, ...]
    motivo: str


@dataclass(frozen=True)
class ResultadoLimpezaPagamentos:
    """Resultado da limpeza de pagamentos, rastreamento 1-para-1 e ocorrências."""

    pagamentos: tuple[PagamentoLimpo, ...]
    itens_rastreados: tuple[RastreamentoPagamento, ...]
    ocorrencias: tuple[RegistroOcorrencia, ...]


@dataclass(frozen=True)
class VerificacaoSaida:
    """Resultado de uma regra de validação automática sobre os CSVs gerados."""

    regra: str
    ok: bool
    detalhes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResultadoLimpeza:
    """Resultado completo do pipeline de limpeza, validação e geração de saída."""

    precatorios: ResultadoConciliacaoPrecatorios
    pagamentos: ResultadoLimpezaPagamentos
    ocorrencias: tuple[RegistroOcorrencia, ...]
    valor_liquido_arquivo: Mapping[str, Decimal]
    verificacoes: tuple[VerificacaoSaida, ...]
    arquivos_gerados: tuple[Path, ...]

    @property
    def todas_verificacoes_ok(self) -> bool:
        return bool(self.verificacoes) and all(v.ok for v in self.verificacoes)
