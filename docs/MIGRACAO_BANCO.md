# Migração do Banco de Dados

Este documento parte do que existe hoje em [schema.sql](../data/raw/schema.sql), mostra quais problemas esse banco deixa passar e explica o porquê de cada mudança feita na migração [001_prevencao_integridade.sql](../sql/migrations/001_prevencao_integridade.sql) (PostgreSQL 14+).

> Os problemas de negócio (`P1` a `P4`) e as evidências nos dados brutos estão detalhados no [DIAGNOSTICO.md](./DIAGNOSTICO.md).

## 1. O banco hoje vs. depois da migração

Hoje, o banco do sistema tem apenas duas tabelas simples:

- **`precatorio`:** guarda `numero_processo` (em `CHAR(20)`), `ente_devedor` e `valor_face`. Não tem colunas para apresentação nem prazo de pagamento, e aceita `valor_face` zerado ou negativo.
- **`pagamento`:** guarda `evento_id`, `precatorio_id`, `tipo` (`pagamento` ou `estorno`), `valor`, `pago_em` e `criado_em`. Porém, não impede o mesmo `evento_id` de entrar duas vezes e não guarda `atualizado_em` para acompanhar retificações do tribunal.

Com a migração, essas duas tabelas ganham proteções e o banco passa a contar com duas peças novas:

| Elemento | Antes | Depois da migração |
| --- | --- | --- |
| `precatorio` | `numero_processo` em `CHAR(20)`, sem apresentação/prazo e sem trava em `valor_face` | `numero_processo` padronizado em 20 dígitos, `ente_devedor` sem texto em branco, `valor_face > 0`, `apresentado_em` e `prazo_pagamento` consistentes |
| `pagamento` | Aceitava `evento_id` repetido e não guardava `atualizado_em` | `evento_id` único, `atualizado_em` obrigatório para retificações e índice em `precatorio_id` |
| `vw_precatorio_saldo` | Não existia (o script ia somando em um total) | View que soma pagamentos, subtrai estornos, calcula `saldo_a_receber` e formata o CNJ apenas na exibição |
| `pagamento_rejeitado` | Não existia (erros sumiam em silêncio) | Tabela de quarentena com motivo e JSON original, sem disparar alertas repetidos durante os 7 dias de reenvio |

---

## 2. Por que cada decisão foi tomada

### 2.1. Padronizar `numero_processo` em 20 dígitos puros *(P3 e P4)*

**O problema hoje:** os arquivos do tribunal trazem o processo com máscara CNJ (25 caracteres, como `0012345-10.2019.8.26.0053`), enquanto `precatorio.numero_processo` foi definido como `CHAR(20)`. Além de não caber o formato com pontuação, `CHAR(20)` preenche valores menores com espaços à direita, o que favorece falsos divergentes nas comparações.

**A decisão:** trocar para `VARCHAR(20)` (removendo espaços extras nas pontas) e exigir exatamente 20 dígitos numéricos. A máscara CNJ deixa de ser gravada na tabela e passa a ser montada só na hora da exibição, em `vw_precatorio_saldo`.

**Por que assim:** guardar apenas os 20 dígitos evita que o mesmo processo apareça de dois jeitos diferentes nas buscas e cruzamentos. Na mesma etapa, o cadastro limpa espaços extras em `ente_devedor`, impede nome em branco ou com espaços nas pontas e exige `valor_face > 0`.

### 2.2. Guardar `apresentado_em` e `prazo_pagamento` com consistência no banco *(P2 e P3)*

**O problema hoje:** o sistema calcula e exporta `apresentado_em` e `prazo_pagamento` no cadastro interno, mas essas colunas não existem no banco original. Além disso, o cálculo atual errou o prazo de dois processos na borda de 2 de abril: um veio sem horário (`2025-04-02`) e outro veio em UTC (`2025-04-03T01:00:00Z`, que ainda é 22h do dia 2 em Brasília).

**A decisão:** adicionar `apresentado_em` (`TIMESTAMPTZ`) e `prazo_pagamento` (`DATE`) em `precatorio`, com uma trava estrutural garantindo que as duas colunas fiquem coerentes (ambas nulas no legado antes do backfill, ou ambas preenchidas com `prazo_pagamento` posterior à data de apresentação em Brasília).

**Por que deixar a fórmula de corte (02/04) na aplicação e não no `CHECK`:** a data de corte constitucional é uma regra legal que pode mudar ao longo do tempo (como ocorreu na EC 114/2021, que alterou o corte de 1º de julho para 2 de abril). Travar a fórmula fixa na tabela dificultaria conviver com precatórios históricos regidos por regras diferentes; o banco garante integridade estrutural e a aplicação concentra o cálculo da regra constitucional.

**Dois cuidados importantes nessa escolha:**
- **As colunas nascem opcionais em par:** em um banco já populado, exigir preenchimento imediato faria a migração falhar. Elas nascem aceitando nulo apenas quando **ambas** estão nulas (impedindo gravar `apresentado_em` sem `prazo_pagamento`, ou vice-versa) até o preenchimento retroativo dos registros antigos, podendo passar a `NOT NULL` em uma migração futura.
- **Preservação de fuso horário:** usar `TIMESTAMPTZ` em `apresentado_em` preserva o instante exato de registros vindos em UTC. Já datas que chegam sem horário precisam ser normalizadas pelo importador em `America/Sao_Paulo` antes de gravar, evitando que uma sessão em UTC recue o dia por engano.

### 2.3. Adicionar `atualizado_em` sem `DEFAULT now()` *(P1)*

**O problema hoje:** todo dia o tribunal reenvia os pagamentos dos últimos 7 dias, e o mesmo evento pode voltar corrigido no dia seguinte (como `ev-001`, que foi de R$ 15.000 para R$ 15.500). A tabela `pagamento` só tinha `criado_em`, sem guardar quando o tribunal alterou o registro.

**A decisão:** criar `atualizado_em` (`TIMESTAMPTZ`) sem valor padrão automático. Nos registros legados, a migração copia `criado_em` para `atualizado_em` e só depois ativa `NOT NULL`.

**Por que não usar `DEFAULT now()`:** se a coluna nascesse com a data atual como padrão, todos os pagamentos antigos ficariam marcados com o horário da migração. Isso faria registros antigos parecerem mais recentes do que correções reais enviadas pelo tribunal, bloqueando retificações legítimas e ainda escondendo falhas caso o importador esquecesse de preencher o campo.

### 2.4. Limpar cópias idênticas e barrar divergências antes de ativar `UNIQUE (evento_id)` *(P1)*

**O problema hoje:** como `pagamento.evento_id` não tinha trava de unicidade, um banco já em produção provavelmente acumula lançamentos duplicados por reenvios ou reexecuções manuais. Ativar `UNIQUE` direto sobre uma tabela assim faria a migração falhar.

**A decisão:** antes de criar a trava de unicidade, a migração remove espaços laterais em `evento_id`, exclui automaticamente apenas **cópias estritamente idênticas** (mesmo processo, evento, tipo, valor e data) e bloqueia espaços nas pontas na nova constraint (evitando que `'ev-001 '` fure a unicidade no futuro).

**Por que não apagar duplicatas divergentes automaticamente:** como o banco original não guardava `atualizado_em`, não há garantia de que a última linha inserida (`criado_em`/`id`) seja a versão mais recente do tribunal — e a política de retificação ainda depende de confirmação (Dúvida #1 no [DIAGNOSTICO.md](./DIAGNOSTICO.md)). Se existir `evento_id` repetido com dados divergentes, a migração **aborta com erro** dentro da transação única (`BEGIN ... COMMIT`), preservando todos os dados para revisão ou arquivamento prévio, assim como em qualquer outra violação legada (ex.: `valor_face <= 0` ou processo corrompido).

*(Em tabelas de produção muito grandes, onde bloquear escrita durante a migração derrubaria o sistema, as mesmas travas e índices podem ser aplicados sem parada: primeiro registrando as constraints com `NOT VALID` para validar depois, e criando os índices com `CONCURRENTLY` fora da transação.)*

### 2.5. Índice em `precatorio_id` e saldo calculado em `vw_precatorio_saldo` *(P1 e P2)*

**O problema hoje:** pelo fluxo descrito no enunciado, o script soma cada valor importado em um total pago. Quando o arquivo roda duas vezes ou chega um estorno (como `ev-007`, de R$ 5.000), esse saldo fica errado e um estorno acaba dobrando o valor pago em vez de abater.

**A decisão:** criar um índice em `pagamento(precatorio_id)` e expor a view `vw_precatorio_saldo`, que sempre calcula a partir do histórico `total_pagamentos`, `total_estornos`, `total_pago_liquido` e `saldo_a_receber`.

**Por que assim:** no PostgreSQL, chaves estrangeiras não recebem índice automaticamente; sem ele, o banco precisaria ler toda a tabela `pagamento` para calcular o saldo de um processo. Além disso, derivar o saldo dos eventos evita que reexecuções ou estornos tirem o total de sincronia com o histórico.

### 2.6. Quarentena em `pagamento_rejeitado` sem alertas repetidos *(P1, P3 e P4)*

**O problema hoje:** quando um evento chega inválido (valor nulo, valor negativo, processo vazio ou processo ausente no cadastro interno), o fluxo atual ignora o erro sem avisar ninguém. No fluxo descrito, é assim que um pagamento válido de R$ 4.000 (`ev-011`) de um processo fora do cadastro sumiria sem aviso.

**A decisão:** criar a tabela `pagamento_rejeitado`, guardando motivo, `evento_id` (quando existir), processo informado e o `payload_original` completo em `JSONB` para auditoria e reprocessamento.

**Como evitar alertas repetidos nos 7 dias de reenvio:** como o tribunal reenvia os mesmos eventos por 7 dias seguidos, um registro quebrado geraria alerta toda manhã. Para evitar isso, um índice único parcial agrupa repetições enquanto o `status` estiver `pendente`, somando no contador `ocorrencias` e atualizando `ultima_ocorrencia_em` em vez de inserir uma nova linha:

- usa `payload_hash` (SHA-256 do conteúdo original) junto com `evento_id` e o código do motivo, o que funciona mesmo se um evento corrompido chegar sem `evento_id` e ainda diferencia caso o mesmo evento mude de erro;
- vale apenas enquanto `status = 'pendente'`; depois que a operação marca o item como `resolvido` ou `descartado` (exigindo `resolvido_em`), um retorno futuro do mesmo problema abre um novo alerta.

---

## 3. Como o script de importação conversa com esse banco

Com essas travas no lugar, reexecutar o mesmo arquivo várias vezes passa a ser seguro:

- **Ao importar um pagamento:** se `evento_id` ainda não existe, a linha é inserida. Se já existe, o banco só atualiza o registro quando o `atualizado_em` recebido for maior que o gravado; reenvios iguais ou atrasados são ignorados sem erro *(o `DO UPDATE` pressupõe confirmação da Dúvida #1 com o tribunal; caso contrário, conflitos de valor devem ser enviados para `pagamento_rejeitado`)*.
- **Ao rejeitar um evento:** o registro vai para `pagamento_rejeitado`. Se o mesmo erro ainda estiver `pendente` de dias anteriores, o banco apenas incrementa `ocorrencias` sem gerar novo alerta.

<details>
<summary>Ver exemplos de consulta SQL esperados no importador</summary>

```sql
-- Carga idempotente de pagamento (aceita retificação apenas se for mais recente)
INSERT INTO pagamento (
    precatorio_id, evento_id, tipo, valor, pago_em, atualizado_em
)
VALUES ($1, $2, $3, $4, $5, $6)
ON CONFLICT (evento_id) DO UPDATE
   SET precatorio_id = EXCLUDED.precatorio_id,
       tipo          = EXCLUDED.tipo,
       valor         = EXCLUDED.valor,
       pago_em       = EXCLUDED.pago_em,
       atualizado_em = EXCLUDED.atualizado_em
 WHERE EXCLUDED.atualizado_em > pagamento.atualizado_em;

-- Registro na quarentena sem duplicar alertas enquanto o item estiver pendente
INSERT INTO pagamento_rejeitado (
    evento_id, processo_informado, motivo_codigo, motivo_detalhe,
    payload_original, payload_hash
)
VALUES ($1, $2, $3, $4, $5, $6)
ON CONFLICT (COALESCE(evento_id, ''), motivo_codigo, payload_hash)
    WHERE status = 'pendente'
DO UPDATE
   SET ocorrencias          = pagamento_rejeitado.ocorrencias + 1,
       ultima_ocorrencia_em = now();
```

</details>

---

## 4. Organização dos arquivos e como validar

Os arquivos de banco ficaram separados por papel para não misturar entrada original, saída da limpeza e código de banco:

- [data/raw/schema.sql](../data/raw/schema.sql): mantido intacto como veio no case (referência do "antes").
- [sql/migrations/001_prevencao_integridade.sql](../sql/migrations/001_prevencao_integridade.sql): migração versionada ("depois").
- [sql/tests/validar_migracao.sh](../sql/tests/validar_migracao.sh): teste automatizado em PostgreSQL oficial via Docker.

Para rodar a validação localmente (com o Docker em execução):

```bash
make test-sql
```

O script sobe um PostgreSQL temporário (`postgres:16-alpine`), remove o container automaticamente ao final e testa três cenários independentes:

1. **Banco limpo:** aplica `schema.sql` e a migração, carrega os 6 precatórios limpos do case e confirma que o banco bloqueia dados inválidos (`numero_processo` fora do padrão, `ente_devedor` vazio ou com espaços nas pontas, `apresentado_em` sem `prazo_pagamento`, `prazo_pagamento` anterior ou igual à apresentação em Brasília, `valor_face` zerado, `evento_id` duplicado ou com espaços nas pontas e `atualizado_em` ausente), aplica retificações, abate estornos em `vw_precatorio_saldo` e agrupa repetições em `pagamento_rejeitado`.
2. **Banco legado com duplicatas idênticas:** insere registros antigos com espaços extras e cópias idênticas de `evento_id` antes de rodar a migração e confirma que a limpeza prévia, a remoção de duplicatas idênticas e o preenchimento retroativo de `atualizado_em` funcionam sem quebrar.
3. **Banco legado com duplicata divergente:** insere o mesmo `evento_id` com valores diferentes antes da migração e confirma que ela aborta com rollback atômico, preservando as linhas intactas para revisão humana.

*(Se quiser testar em outra versão do PostgreSQL, basta informar a imagem: `POSTGRES_IMAGE=postgres:17-alpine make test-sql`.)*
