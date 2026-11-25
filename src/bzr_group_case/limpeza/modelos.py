from dataclasses import dataclass
from typing import Any, Literal

ProblemaDiagnostico = Literal["P1", "P2", "P3", "P4"]
CategoriaOcorrencia = Literal["corrigido", "descartado", "em_duvida"]
EntidadeOcorrencia = Literal["arquivo", "precatorio", "pagamento"]


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
