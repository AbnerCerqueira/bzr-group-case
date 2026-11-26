# Relatório de Limpeza e Conciliação

> Para filtrar e cruzar ocorrências por problema (`P1`–`P4`), destino, processo ou evento, gere o painel interativo com `make clean-html` (`docs/limpeza.html`).

**Navegação rápida:** [1. Resumo](#1-resumo-executivo) · [2. Premissas](#2-premissas-explícitas-adotadas) · [3. Precatórios](#3-visão-1-para-1-dos-precatórios-6-processos) · [4. Pagamentos](#4-visão-1-para-1-dos-eventos-de-pagamento-13-itens-de-pagamentosjson) · [5. Ocorrências](#5-detalhamento-das-ocorrências-por-destino) · [6. Efeito líquido](#6-efeito-líquido-apenas-dos-eventos-deste-arquivo-por-processo) · [7. Validação](#7-validação-automática-da-base-limpa-depois)

## 1. Resumo executivo

| Frente | Total | Distribuição / Status |
| --- | --- | --- |
| Precatórios | 6 | 2 conciliados; 4 em dúvida |
| Pagamentos (pagamentos.json) | 13 | 7 mantidos; 1 deduplicado; 1 substituído; 4 descartados |
| Validação do "Depois" | 5 | [OK] 5/5 regras aprovadas |

| Problema | Corrigido | Descartado | Em dúvida | Total |
| --- | --- | --- | --- | --- |
| P1 | 1 | 1 | 0 | 2 |
| P2 | 3 | 0 | 0 | 3 |
| P3 | 10 | 3 | 0 | 13 |
| P4 | 2 | 1 | 4 | 7 |
| Total | 16 | 5 | 4 | 25 |

## 2. Premissas explícitas adotadas

- **Fuso horário de Brasília (`America/Sao_Paulo`) para datas sem hora na borda de `02/04`:** valores de `apresentado_em` sem horário ou sem fuso explícito são interpretados no horário oficial de Brasília para aplicação do corte constitucional inclusivo em `02/04`. Aplicada neste lote em: `0012345-10.2019.8.26.0053` (2027-12-31 → 2026-12-31). **Sujeita à confirmação da operação antes de produção.**
- **Retificação de pagamento pelo maior `atualizado_em`:** quando o mesmo `evento_id` aparece múltiplas vezes com dados divergentes, prevalece a versão mais recente como retificação. Aplicada neste lote em: `ev-001` (valor=15000.00 (2025-03-10T10:00:00-03:00) → valor=15500.00 (2025-03-11T09:00:00-03:00)). **Sujeita à confirmação do tribunal antes de produção.**

## 3. Visão 1-para-1 dos precatórios (6 processos)

| CNJ formatado | Ente devedor | Valor de face | Prazo (antes → depois) | Status | Problemas (cadastro) |
| --- | --- | --- | --- | --- | --- |
| 0012345-10.2019.8.26.0053 | Município de São Paulo | 45000.00 | 2027-12-31 → 2026-12-31 | conciliado | P2, P3, P4 |
| 0023456-21.2020.8.26.0053 | Município de São Paulo | 31000.00 | 2027-12-31 → 2027-12-31 | em_duvida | P3, P4 |
| 0034567-32.2018.8.26.0405 | Estado de São Paulo | 12500.00 | 2025-12-31 → 2025-12-31 | conciliado | P3 |
| 0045678-43.2021.5.02.0011 | Município de Santos | 9800.00 | 2026-12-31 → 2026-12-31 | em_duvida | P3, P4 |
| 0056789-54.2017.4.03.6100 | Estado de São Paulo | 22000.00 | 2027-12-31 → 2026-12-31 | em_duvida | P2, P4 |
| 0067890-65.2016.8.26.0053 | Município de São Paulo | 7000.00 | — → 2025-12-31 | em_duvida | P3, P4 |

<details>
<summary>Ver chave canônica, apresentação e resumo por processo (6)</summary>

- **`0012345-10.2019.8.26.0053`** (chave `00123451020198260053`) · Município de São Paulo · apresentado em `2025-04-02` · valor_face corrigido (P3); ente_devedor corrigido (P4); prazo_pagamento corrigido (P2)
- **`0023456-21.2020.8.26.0053`** (chave `00234562120208260053`) · Município de São Paulo · apresentado em `2025-04-03` · valor_face corrigido (P3); numero_processo corrigido (P4); valor_face em dúvida (P4)
- **`0034567-32.2018.8.26.0405`** (chave `00345673220188260405`) · Estado de São Paulo · apresentado em `2024-02-29` · valor_face corrigido (P3)
- **`0045678-43.2021.5.02.0011`** (chave `00456784320215020011`) · Município de Santos · apresentado em `2025-04-02T23:30:00-03:00` · valor_face corrigido (P3); ente_devedor em dúvida (P4)
- **`0056789-54.2017.4.03.6100`** (chave `00567895420174036100`) · Estado de São Paulo · apresentado em `2025-04-03T01:00:00Z` · cobertura em dúvida (P4); prazo_pagamento corrigido (P2)
- **`0067890-65.2016.8.26.0053`** (chave `00678906520168260053`) · Município de São Paulo · apresentado em `2023-12-31` · valor_face corrigido (P3); cobertura em dúvida (P4)

</details>

## 4. Visão 1-para-1 dos eventos de pagamento (13 itens de `pagamentos.json`)

| # | evento_id | Processo | Tipo | Valor bruto | Data | Destino | Problemas |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | ev-001 | 0012345-10.2019.8.26.0053 | pagamento | 15000.0 | 2025-03-10 | substituido | P1 |
| 2 | ev-002 | 0012345-10.2019.8.26.0053 | pagamento | 2.500,50 | 2025-04-10 | mantido | P3 |
| 3 | ev-003 | 0023456-21.2020.8.26.0053 | pagamento | 8000 | 2025-05-02 | mantido | — |
| 4 | ev-002 | 0012345-10.2019.8.26.0053 | pagamento | 2.500,50 | 2025-04-10 | deduplicado | P1 |
| 5 | ev-004 | 0023456-21.2020.8.26.0053 | pagamento | null | 2025-05-03 | descartado | P3 |
| 6 | ev-005 | 0023456-21.2020.8.26.0053 | pagamento | 1200.0 | 2025-06-01 | mantido | P3 |
| 7 | ev-006 | 0034567-32.2018.8.26.0405 | pagamento | 5000 | 2025-02-20 | mantido | — |
| 8 | ev-007 | 0034567-32.2018.8.26.0405 | estorno | 5000 | 2025-02-21 | mantido | P2 |
| 9 | ev-001 | 0012345-10.2019.8.26.0053 | pagamento | 15500.0 | 2025-03-10 | mantido | P1 |
| 10 | ev-008 | 0045678-43.2021.5.02.0011 | pagamento | 3000 | 2025-07-15 | mantido | — |
| 11 | ev-009 | 0056789-54.2017.4.03.6100 | pagamento | -200 | 2025-07-20 | descartado | P3 |
| 12 | ev-010 | — | pagamento | 750 | 2025-08-01 | descartado | P3 |
| 13 | ev-011 | 0067890-65.2016.8.26.0053 | pagamento | 4000 | 2025-08-10 | descartado | P4 |

<details>
<summary>Ver motivos detalhados dos eventos (13 itens)</summary>

- **#1 `ev-001`** (substituido · P1): Versão anterior (pagamentos.json (item 1), atualizado_em=2025-03-10T10:00:00-03:00) substituída pela versão mais recente (pagamentos.json (item 9), atualizado_em=2025-03-11T09:00:00-03:00). Premissa explícita: maior atualizado_em prevalece como retificação, sujeita à confirmação do tribunal.
- **#2 `ev-002`** (mantido · P3): Mantido (campos normalizados (valor, data_pagamento)).
- **#3 `ev-003`** (mantido): Pagamento válido mantido sem ajustes.
- **#4 `ev-002`** (deduplicado · P1): Duplicata idêntica do evento ev-002 (repete pagamentos.json (item 2)); descartada.
- **#5 `ev-004`** (descartado · P3): Valor nulo/ausente; pagamento descartado.
- **#6 `ev-005`** (mantido · P3): Mantido (campos normalizados (processo)).
- **#7 `ev-006`** (mantido): Pagamento válido mantido sem ajustes.
- **#8 `ev-007`** (mantido · P2): Mantido (estorno preservado para abater no total pago).
- **#9 `ev-001`** (mantido · P1): Mantido (versão mais recente mantida como retificação).
- **#10 `ev-008`** (mantido): Pagamento válido mantido sem ajustes.
- **#11 `ev-009`** (descartado · P3): Valor -200 viola a restrição valor > 0 e não é convertido silenciosamente em estorno sem confirmação do tribunal.
- **#12 `ev-010`** (descartado · P3): Número de processo CNJ ausente ou inválido; descartado.
- **#13 `ev-011`** (descartado · P4): Processo 0067890-65.2016.8.26.0053 presente no tribunal.csv, mas ausente no hub.csv; pagamento descartado aguardando decisão operacional sobre cadastro automático.

</details>

## 5. Detalhamento das ocorrências por destino

### Corrigidos (16)

<details>
<summary>Ver todas as 16 correções aplicadas</summary>

- **`[P3]` `tribunal.csv`** · `encoding` (arquivo · tribunal.csv): `cp1252` → `utf-8` — Arquivo CSV decodificado em cp1252 após falha em UTF-8.
- **`[P3]` `tribunal.csv`** · `delimitador` (arquivo · tribunal.csv): `;` → `,` — Arquivo CSV usa ponto e vírgula (';') em vez de vírgula (',').
- **`[P3]` `0012345-10.2019.8.26.0053`** · `valor_face` (precatorio · tribunal.csv (L2)): `45.000,00` → `45000.00` — Valor de face ('45.000,00') convertido para decimal padrão (45000.00).
- **`[P3]` `0023456-21.2020.8.26.0053`** · `valor_face` (precatorio · tribunal.csv (L3)): `30.000,00` → `30000.00` — Valor de face ('30.000,00') convertido para decimal padrão (30000.00).
- **`[P3]` `0034567-32.2018.8.26.0405`** · `valor_face` (precatorio · tribunal.csv (L4)): `12.500,00` → `12500.00` — Valor de face ('12.500,00') convertido para decimal padrão (12500.00).
- **`[P3]` `0045678-43.2021.5.02.0011`** · `valor_face` (precatorio · tribunal.csv (L5)): `9.800,00` → `9800.00` — Valor de face ('9.800,00') convertido para decimal padrão (9800.00).
- **`[P3]` `0067890-65.2016.8.26.0053`** · `valor_face` (precatorio · tribunal.csv (L6)): `7.000,00` → `7000.00` — Valor de face ('7.000,00') convertido para decimal padrão (7000.00).
- **`[P4]` `0012345-10.2019.8.26.0053`** · `ente_devedor` (precatorio · tribunal.csv (L2) x hub.csv (L2)): `MUNICIPIO DE SAO PAULO` → `Município de São Paulo` — Falso divergente de grafia/acento; padronizada a grafia do tribunal.
- **`[P2]` `0012345-10.2019.8.26.0053`** · `prazo_pagamento` (precatorio · hub.csv (L2)): `2027-12-31` → `2026-12-31` — Prazo constitucional recalculado para 2026-12-31 (2025-04-02 BRT, corte inclusivo em 02/04). Premissa explícita: data/hora sem fuso interpretada em Brasília (America/Sao_Paulo), sujeita à confirmação da operação.
- **`[P4]` `0023456-21.2020.8.26.0053`** · `numero_processo` (precatorio · tribunal.csv (L3) x hub.csv (L3)): `tribunal='0023456-21.2020.8.26.0053' | hub='00234562120208260053'` → `00234562120208260053` — Falso divergente de CNJ eliminado pela chave de 20 dígitos.
- **`[P2]` `0056789-54.2017.4.03.6100`** · `prazo_pagamento` (precatorio · hub.csv (L6)): `2027-12-31` → `2026-12-31` — Prazo constitucional recalculado para 2026-12-31 (2025-04-02 BRT, corte inclusivo em 02/04).
- **`[P1]` `ev-001`** · `retificacao` (pagamento · pagamentos.json (item 1) -> pagamentos.json (item 9)): `valor=15000.00 (2025-03-10T10:00:00-03:00)` → `valor=15500.00 (2025-03-11T09:00:00-03:00)` — Versão anterior (pagamentos.json (item 1), atualizado_em=2025-03-10T10:00:00-03:00) substituída pela versão mais recente (pagamentos.json (item 9), atualizado_em=2025-03-11T09:00:00-03:00). Premissa explícita: maior atualizado_em prevalece como retificação, sujeita à confirmação do tribunal.
- **`[P3]` `ev-002`** · `valor` (pagamento · pagamentos.json (item 2)): `2.500,50` → `2500.50` — Valor monetário ('2.500,50') convertido para decimal padrão (2500.50).
- **`[P3]` `ev-002`** · `data_pagamento` (pagamento · pagamentos.json (item 2)): `10/04/2025` → `2025-04-10` — Data de pagamento ('10/04/2025') convertida para ISO (2025-04-10).
- **`[P3]` `ev-005`** · `processo` (pagamento · pagamentos.json (item 6)): `00234562120208260053` → `00234562120208260053` — Processo ('00234562120208260053') veio fora do padrão CNJ documentado (0023456-21.2020.8.26.0053); vinculado pela chave canônica de 20 dígitos.
- **`[P2]` `ev-007`** · `tipo` (pagamento · pagamentos.json (item 8)): `estorno` → `-5000.00` — Evento preservado como estorno válido com valor positivo (5000.00), que deve abater no total pago do processo.

</details>

### Descartados (com motivo) (5)

- **`[P1]` `ev-002`** · `duplicidade` (pagamento · pagamentos.json (item 4)): `item 4 (idêntico ao item 2)` → — — Duplicata idêntica do evento ev-002 (repete pagamentos.json (item 2)); descartada.
- **`[P3]` `ev-004`** · `valor` (pagamento · pagamentos.json (item 5)): `null` → — — Valor nulo/ausente; pagamento descartado.
- **`[P3]` `ev-009`** · `valor` (pagamento · pagamentos.json (item 11)): `-200` → — — Valor -200 viola a restrição valor > 0 e não é convertido silenciosamente em estorno sem confirmação do tribunal.
- **`[P3]` `ev-010`** · `processo` (pagamento · pagamentos.json (item 12)): — → — — Número de processo CNJ ausente ou inválido; descartado.
- **`[P4]` `ev-011`** · `processo` (pagamento · pagamentos.json (item 13)): `0067890-65.2016.8.26.0053` → — — Processo 0067890-65.2016.8.26.0053 presente no tribunal.csv, mas ausente no hub.csv; pagamento descartado aguardando decisão operacional sobre cadastro automático.

### Em dúvida (sem sobrescrever) (4)

- **`[P4]` `0023456-21.2020.8.26.0053`** · `valor_face` (precatorio · tribunal.csv (L3) x hub.csv (L3)): `hub=31000.00 | tribunal=30000.00` → `31000.00` — Valor de face diverge entre hub e tribunal; valor do hub preservado.
- **`[P4]` `0045678-43.2021.5.02.0011`** · `ente_devedor` (precatorio · tribunal.csv (L5) x hub.csv (L5)): `hub='Município de Santos' | tribunal='União'` → `Município de Santos` — Ente devedor diverge entre hub e tribunal; valor do hub preservado.
- **`[P4]` `0056789-54.2017.4.03.6100`** · `cobertura` (precatorio · hub.csv (L6)): `presente apenas no hub.csv` → — — Presente apenas no hub.csv; dados preservados em dúvida.
- **`[P4]` `0067890-65.2016.8.26.0053`** · `cobertura` (precatorio · tribunal.csv (L6), apresentacoes.json (item 6)): `presente apenas no tribunal.csv` → — — Presente apenas no tribunal.csv; incluído em dúvida.

## 6. Efeito líquido apenas dos eventos deste arquivo por processo

> **Atenção:** os valores abaixo refletem **apenas o efeito líquido (`pagamentos - estornos`) dos eventos de `pagamentos.json`** (janela móvel de 7 dias) e **não representam o saldo histórico acumulado no banco de dados**. Por isso, `total_pago` e `saldo_a_receber` não são gravados em `precatorios_limpos.csv`.

| CNJ formatado | Eventos mantidos no arquivo | Efeito líquido no arquivo |
| --- | --- | --- |
| 0012345-10.2019.8.26.0053 | ev-001 (+15500.00), ev-002 (+2500.50) | 18000.50 |
| 0023456-21.2020.8.26.0053 | ev-003 (+8000.00), ev-005 (+1200.00) | 9200.00 |
| 0034567-32.2018.8.26.0405 | ev-006 (+5000.00), ev-007 (-5000.00 estorno) | 0.00 |
| 0045678-43.2021.5.02.0011 | ev-008 (+3000.00) | 3000.00 |

Processos do cadastro sem eventos mantidos neste arquivo (efeito líquido `0.00` no lote): `0056789-54.2017.4.03.6100`, `0067890-65.2016.8.26.0053`.

## 7. Validação automática da base limpa ("Depois")

| Status | Regra | Detalhes |
| --- | --- | --- |
| [OK] | Codificação UTF-8 sem BOM (LF), delimitador ',' e cabeçalhos exatos | Conforme |
| [OK] | Integridade cadastral de precatorios_limpos.csv | Conforme |
| [OK] | Conformidade do prazo constitucional em precatorios_limpos.csv | Conforme |
| [OK] | Integridade de pagamentos_limpos.csv | Conforme |
| [OK] | Conservação 1-para-1 entre entrada e saída | Conforme |
