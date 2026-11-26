from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from bzr_group_case.limpeza.entrada.normalizacao import (
    converter_data_pagamento,
    converter_instante_iso,
    converter_valor_monetario,
    normalizar_cnj,
)
from bzr_group_case.limpeza.modelos import (
    CategoriaOcorrencia,
    ProblemaDiagnostico,
    RegistroOcorrencia,
    TipoPagamento,
)


@dataclass(frozen=True)
class PagamentoValido:
    """Item de pagamentos.json validado e normalizado, pronto para resolução."""

    indice: int
    origem: str
    evento_id: str
    chave_cnj: str
    cnj_formatado: str
    tipo: TipoPagamento
    valor: Decimal
    valor_original: str
    data_pagamento: str
    atualizado_em: str
    instante: datetime
    ocorrencias_pendentes: tuple[RegistroOcorrencia, ...]

    @property
    def chave_semantica(self) -> tuple[str, TipoPagamento, Decimal, str]:
        """Campos de negócio usados para detectar duplicatas exatas vs retificações."""
        return (self.chave_cnj, self.tipo, self.valor, self.data_pagamento)


@dataclass(frozen=True)
class PagamentoInvalido:
    """Item de pagamentos.json reprovado na validação de contrato/campos."""

    indice: int
    origem: str
    evento_id: str | None
    evento_id_exibicao: str
    numero_processo: str
    tipo: str
    valor_original: str
    data_pagamento: str
    atualizado_em: str
    instante: datetime | None
    ocorrencias_erro: tuple[RegistroOcorrencia, ...]


ItemPagamentoValidado = PagamentoValido | PagamentoInvalido


def registrar_ocorrencia_pagamento(
    ocorrencias: list[RegistroOcorrencia],
    *,
    problema: ProblemaDiagnostico,
    categoria: CategoriaOcorrencia,
    identificador: str,
    origem: str,
    campo: str,
    valor_original: str,
    motivo: str,
    valor_tratado: str | None = None,
) -> None:
    """Anexa uma ocorrência de pagamento com campos nomeados e explícitos."""
    ocorrencias.append(
        RegistroOcorrencia(
            problema=problema,
            categoria=categoria,
            entidade="pagamento",
            identificador=identificador,
            origem=origem,
            campo=campo,
            valor_original=valor_original,
            valor_tratado=valor_tratado,
            motivo=motivo,
        )
    )


def _texto_bruto(valor: Any, *, rotulo_nulo: str = "") -> str:
    if valor is None:
        return rotulo_nulo
    return valor if isinstance(valor, str) else str(valor)


def _validar_evento_id(
    valor_bruto: Any,
    *,
    indice: int,
    origem: str,
    erros: list[RegistroOcorrencia],
    pendentes: list[RegistroOcorrencia],
) -> tuple[str | None, str, str]:
    """Retorna (evento_id_valido, evento_id_exibicao, identificador_ocorrencia)."""
    if not isinstance(valor_bruto, str) or not valor_bruto.strip():
        exibicao = _texto_bruto(valor_bruto)
        identificador = f"pagamentos.json#item-{indice}"
        registrar_ocorrencia_pagamento(
            erros,
            problema="P3",
            categoria="descartado",
            identificador=identificador,
            origem=origem,
            campo="evento_id",
            valor_original=exibicao,
            motivo="evento_id ausente, vazio ou fora do tipo texto; descartado.",
        )
        return None, exibicao, identificador

    limpo = valor_bruto.strip()
    if limpo != valor_bruto:
        registrar_ocorrencia_pagamento(
            pendentes,
            problema="P3",
            categoria="corrigido",
            identificador=limpo,
            origem=origem,
            campo="evento_id",
            valor_original=valor_bruto,
            valor_tratado=limpo,
            motivo="Espaços nas extremidades de evento_id removidos.",
        )
    return limpo, limpo, limpo


def _validar_processo(
    valor_bruto: Any,
    *,
    identificador: str,
    origem: str,
    erros: list[RegistroOcorrencia],
    pendentes: list[RegistroOcorrencia],
) -> tuple[str | None, str]:
    """Retorna (chave_cnj_20_digitos | None, numero_processo_exibicao)."""
    normalizado = normalizar_cnj(valor_bruto)
    if normalizado is None:
        exibicao = _texto_bruto(valor_bruto)
        registrar_ocorrencia_pagamento(
            erros,
            problema="P3",
            categoria="descartado",
            identificador=identificador,
            origem=origem,
            campo="processo",
            valor_original=exibicao,
            motivo="Número de processo CNJ ausente ou inválido; descartado.",
        )
        return None, exibicao

    chave_cnj, cnj_formatado = normalizado
    if valor_bruto != cnj_formatado:
        registrar_ocorrencia_pagamento(
            pendentes,
            problema="P3",
            categoria="corrigido",
            identificador=identificador,
            origem=origem,
            campo="processo",
            valor_original=str(valor_bruto),
            valor_tratado=chave_cnj,
            motivo=(
                f"Processo ({valor_bruto!r}) veio fora do padrão CNJ documentado "
                f"({cnj_formatado}); vinculado pela chave canônica de 20 dígitos."
            ),
        )
    return chave_cnj, cnj_formatado


def _validar_tipo(
    valor_bruto: Any,
    *,
    identificador: str,
    origem: str,
    erros: list[RegistroOcorrencia],
    pendentes: list[RegistroOcorrencia],
) -> tuple[TipoPagamento | None, str]:
    if not isinstance(valor_bruto, str):
        exibicao = _texto_bruto(valor_bruto)
        registrar_ocorrencia_pagamento(
            erros,
            problema="P3",
            categoria="descartado",
            identificador=identificador,
            origem=origem,
            campo="tipo",
            valor_original=exibicao,
            motivo=f"Tipo de evento fora do tipo texto ({valor_bruto!r}); descartado.",
        )
        return None, exibicao

    normalizado = valor_bruto.strip().lower()
    if normalizado not in ("pagamento", "estorno"):
        registrar_ocorrencia_pagamento(
            erros,
            problema="P3",
            categoria="descartado",
            identificador=identificador,
            origem=origem,
            campo="tipo",
            valor_original=valor_bruto,
            motivo=(
                f"Tipo de evento inválido ({valor_bruto!r}); esperado "
                "'pagamento' ou 'estorno'."
            ),
        )
        return None, valor_bruto

    tipo: TipoPagamento = "pagamento" if normalizado == "pagamento" else "estorno"
    if valor_bruto != tipo:
        registrar_ocorrencia_pagamento(
            pendentes,
            problema="P3",
            categoria="corrigido",
            identificador=identificador,
            origem=origem,
            campo="tipo",
            valor_original=valor_bruto,
            valor_tratado=tipo,
            motivo=f"Tipo de evento normalizado de {valor_bruto!r} para {tipo!r}.",
        )
    return tipo, tipo


def _validar_valor(
    valor_bruto: Any,
    *,
    tipo: TipoPagamento | None,
    identificador: str,
    origem: str,
    erros: list[RegistroOcorrencia],
    pendentes: list[RegistroOcorrencia],
) -> tuple[Decimal | None, str]:
    valor_original = _texto_bruto(valor_bruto, rotulo_nulo="null")
    valor, precisou_normalizar = converter_valor_monetario(valor_bruto)
    if valor is None:
        if valor_bruto is None or (
            isinstance(valor_bruto, str) and not valor_bruto.strip()
        ):
            motivo = "Valor nulo/ausente; pagamento descartado."
        else:
            motivo = (
                f"Valor fora do padrão monetário ({valor_bruto!r}); "
                "pagamento descartado."
            )
        registrar_ocorrencia_pagamento(
            erros,
            problema="P3",
            categoria="descartado",
            identificador=identificador,
            origem=origem,
            campo="valor",
            valor_original=valor_original,
            motivo=motivo,
        )
        return None, valor_original

    if valor <= 0:
        if valor == 0:
            motivo = "Valor 0 viola a restrição valor > 0; pagamento descartado."
        elif tipo == "estorno":
            motivo = (
                f"Valor negativo ({valor_original}) em estorno viola a restrição "
                "valor > 0; descartado sem inverter o sinal automaticamente."
            )
        else:
            motivo = (
                f"Valor {valor_original} viola a restrição valor > 0 e não é "
                "convertido silenciosamente em estorno sem confirmação do tribunal."
            )
        registrar_ocorrencia_pagamento(
            erros,
            problema="P3",
            categoria="descartado",
            identificador=identificador,
            origem=origem,
            campo="valor",
            valor_original=valor_original,
            motivo=motivo,
        )
        return None, valor_original

    if precisou_normalizar:
        valor_formatado = f"{valor:.2f}"
        registrar_ocorrencia_pagamento(
            pendentes,
            problema="P3",
            categoria="corrigido",
            identificador=identificador,
            origem=origem,
            campo="valor",
            valor_original=valor_original,
            valor_tratado=valor_formatado,
            motivo=(
                f"Valor monetário ({valor_original!r}) convertido para decimal "
                f"padrão ({valor_formatado})."
            ),
        )
    return valor, valor_original


def _validar_data_pagamento(
    valor_bruto: Any,
    *,
    identificador: str,
    origem: str,
    erros: list[RegistroOcorrencia],
    pendentes: list[RegistroOcorrencia],
) -> tuple[str | None, str]:
    data, precisou_normalizar = converter_data_pagamento(valor_bruto)
    if data is None:
        exibicao = _texto_bruto(valor_bruto)
        registrar_ocorrencia_pagamento(
            erros,
            problema="P3",
            categoria="descartado",
            identificador=identificador,
            origem=origem,
            campo="data_pagamento",
            valor_original=exibicao,
            motivo=f"Data de pagamento ausente ou inválida ({valor_bruto!r}).",
        )
        return None, exibicao

    data_iso = data.isoformat()
    if precisou_normalizar:
        registrar_ocorrencia_pagamento(
            pendentes,
            problema="P3",
            categoria="corrigido",
            identificador=identificador,
            origem=origem,
            campo="data_pagamento",
            valor_original=str(valor_bruto),
            valor_tratado=data_iso,
            motivo=(
                f"Data de pagamento ({valor_bruto!r}) convertida para ISO ({data_iso})."
            ),
        )
    return data_iso, data_iso


def _validar_atualizado_em(
    valor_bruto: Any,
    *,
    identificador: str,
    origem: str,
    erros: list[RegistroOcorrencia],
    pendentes: list[RegistroOcorrencia],
) -> tuple[datetime | None, str]:
    instante = converter_instante_iso(valor_bruto)
    if instante is None or not isinstance(valor_bruto, str):
        exibicao = _texto_bruto(valor_bruto)
        registrar_ocorrencia_pagamento(
            erros,
            problema="P3",
            categoria="descartado",
            identificador=identificador,
            origem=origem,
            campo="atualizado_em",
            valor_original=exibicao,
            motivo=f"Data/hora atualizado_em ausente ou inválida ({valor_bruto!r}).",
        )
        return None, exibicao

    limpo = valor_bruto.strip()
    tinha_espacos = limpo != valor_bruto
    texto_iso = f"{limpo[:-1]}+00:00" if limpo.endswith(("Z", "z")) else limpo
    sem_fuso = datetime.fromisoformat(texto_iso).tzinfo is None

    if sem_fuso or tinha_espacos:
        normalizado = instante.isoformat() if sem_fuso else limpo
        motivo = (
            "Instante atualizado_em sem fuso explícito interpretado em Brasília "
            f"(America/Sao_Paulo) como {normalizado}."
            if sem_fuso
            else f"Espaços nas extremidades de atualizado_em removidos ({normalizado})."
        )
        registrar_ocorrencia_pagamento(
            pendentes,
            problema="P3",
            categoria="corrigido",
            identificador=identificador,
            origem=origem,
            campo="atualizado_em",
            valor_original=valor_bruto,
            valor_tratado=normalizado,
            motivo=motivo,
        )
        return instante, normalizado

    return instante, limpo


def validar_item_pagamento(
    indice: int,
    registro: Mapping[str, Any],
) -> ItemPagamentoValidado:
    """Valida e normaliza um item de pagamentos.json sem perder atualizado_em."""
    origem = f"pagamentos.json (item {indice})"
    erros: list[RegistroOcorrencia] = []
    pendentes: list[RegistroOcorrencia] = []

    evento_id, evento_id_exibicao, identificador = _validar_evento_id(
        registro.get("evento_id"),
        indice=indice,
        origem=origem,
        erros=erros,
        pendentes=pendentes,
    )
    chave_cnj, processo_exibicao = _validar_processo(
        registro.get("processo"),
        identificador=identificador,
        origem=origem,
        erros=erros,
        pendentes=pendentes,
    )
    tipo, tipo_exibicao = _validar_tipo(
        registro.get("tipo"),
        identificador=identificador,
        origem=origem,
        erros=erros,
        pendentes=pendentes,
    )
    valor, valor_original = _validar_valor(
        registro.get("valor"),
        tipo=tipo,
        identificador=identificador,
        origem=origem,
        erros=erros,
        pendentes=pendentes,
    )
    data_pagamento, data_exibicao = _validar_data_pagamento(
        registro.get("data_pagamento"),
        identificador=identificador,
        origem=origem,
        erros=erros,
        pendentes=pendentes,
    )
    instante, atualizado_exibicao = _validar_atualizado_em(
        registro.get("atualizado_em"),
        identificador=identificador,
        origem=origem,
        erros=erros,
        pendentes=pendentes,
    )

    if (
        erros
        or evento_id is None
        or chave_cnj is None
        or tipo is None
        or valor is None
        or data_pagamento is None
        or instante is None
    ):
        return PagamentoInvalido(
            indice=indice,
            origem=origem,
            evento_id=evento_id,
            evento_id_exibicao=evento_id_exibicao,
            numero_processo=processo_exibicao,
            tipo=tipo_exibicao,
            valor_original=valor_original,
            data_pagamento=data_exibicao,
            atualizado_em=atualizado_exibicao,
            instante=instante,
            ocorrencias_erro=tuple(erros),
        )

    return PagamentoValido(
        indice=indice,
        origem=origem,
        evento_id=evento_id,
        chave_cnj=chave_cnj,
        cnj_formatado=processo_exibicao,
        tipo=tipo,
        valor=valor,
        valor_original=valor_original,
        data_pagamento=data_pagamento,
        atualizado_em=atualizado_exibicao,
        instante=instante,
        ocorrencias_pendentes=tuple(pendentes),
    )
