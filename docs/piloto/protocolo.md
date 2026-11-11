# Protocolo do piloto instrumentado

Define o que é medido e como executar o piloto do processo guiado por agentes (seção 2 do trabalho). As definições foram fixadas antes das execuções para evitar ajustes posteriores.

## Fluxos

Cada fluxo é um serviço com dois ciclos completos. A entrada de cada execução é uma **issue do GitHub**.

| Fluxo | Ciclo | Issue | Passos |
|---|---|---|---|
| Catálogo | Funcionalidade | #2 CAT-FEAT-01 | Refinamento (história e tasks) → G3 → para cada task: Código → Testes → verificações → commit → PR → CI → G5 → Deploy em homologação → G7 |
| Catálogo | Bug | #3 CAT-BUG-01 | Reprodução e patch → Teste de regressão → CI → G5 → Deploy em homologação → G7 |
| Pedidos | Funcionalidade | #4 ORD-FEAT-01 | Igual ao ciclo de funcionalidade |
| Pedidos | Bug | #5 ORD-BUG-01 | Igual ao ciclo de bug |
| Verificação | Guarda-corpo | #6 GRD-01 | Agente de Código recebe um relato com injeção de instrução; sem PR |

### Issue como card de entrada

- O orquestrador só aceita issues **abertas** com o rótulo `piloto`, exatamente um rótulo `fluxo:<catalog|cart|orders>` e um `ciclo:<feature|bug|guardrail>`. Só quem tem acesso de triagem aplica rótulos, então pessoas de fora não conseguem colocar uma issue para rodar no repositório público.
- O título no formato `[ID] título` define o identificador da demanda. Sem isso, o identificador é `ISSUE-<número>`.
- As seções `## Demanda` e, se existir, `## Interface` vão para os agentes, sempre marcadas como dado não confiável. As outras seções (observações, instruções de execução) ficam só para os humanos.
- O PR inclui `Closes #N`, então o merge no G5 fecha a issue. A issue do GRD-01 é fechada manualmente depois da execução.
- Para uma nova demanda, crie uma issue com esses rótulos e rode `--issue <número>`.

### Refinamento em tasks (ciclo de funcionalidade)

O Agente de Requisitos e Refinamento escreve a história em `docs/backlog/<ID>.md` com regra, cenários BDD e uma seção `## Tasks`, com 1 a 6 tasks `### T<n>: <título>`. Cada task traz `Cenários:`, `Arquivos:` e `Pronto quando:`. O supervisor rejeita a história se faltar algum desses elementos. Regras de negócio novas são propostas pelo mesmo agente em `docs/regras-de-negocio.md`. No G3 são aprovadas a história, a quebra em tasks e as regras novas. Cada decisão do G3 é registrada como comentário na issue, com aprovador, comentário, história e regras propostas. O registro fica no card mesmo que a execução falhe depois.

Depois do G3, cada task é executada em sequência: o Agente de Código implementa só aquela task, o Agente de Testes cobre seus cenários, as verificações de qualidade e a suíte da CI (`scripts/ci.sh`) rodam, e o supervisor faz um commit próprio para a task. Se a suíte falhar, o log volta alternadamente para o Agente de Código e para o de Testes, até 3 tentativas. Ao fim das tasks, sai um único PR, com uma CI e um G5 para a história inteira. Isso mantém o número de intervenções humanas comparável entre os ciclos. O trace registra `tasks_planned`, `task_started` e `task_finished`.

O ciclo de bug não passa por refinamento.

## Agentes e limites

| Agente | Atividades | Escrita | Comandos | Turnos | Orçamento (US$) |
|---|---|---|---|---:|---:|
| Requisitos e refinamento | 2, 3 | `docs/backlog/` e `docs/regras-de-negocio.md` (só regras novas) | nenhum | 20 | 1,50 |
| Código | 6, 7 | serviço do fluxo, `libs/events/` e `web/public/` (exceto testes e, sem seção Interface, `styles.css`); `.pilot/repro/` | pytest, node --test, `scripts/ci.sh`, git somente leitura | 50 | 4,00 |
| Testes | 8, 10 | `tests/` do serviço e de `libs/events/`; `web/tests/` | pytest, node --test, `scripts/ci.sh`, git somente leitura | 40 | 3,00 |
| Deploy | 11, 12 | `.pilot/deploy_report.md` | scripts de homologação, compose ps/logs | 20 | 1,00 |

## Guarda-corpos

| Controle | Implementação | Evidência no trace |
|---|---|---|
| Menor privilégio | Ferramentas por agente e hook `PreToolUse` com política própria | `tool_call`, `guardrail_block` |
| Comandos | Lista de permissões; encadeamento, redirecionamento e substituição proibidos | `guardrail_block` |
| Segredos | Bloqueio de `.env`, chaves e `.git`; redação de tokens no trace | regra `secret` |
| Git e produção | Só o supervisor faz commit e push; merge é humano | regras `forbidden_git`, `prod_deploy` |
| Ambiente isolado | Git worktree por execução; sandbox bubblewrap no Bash dos agentes Código e Testes | `run_started` |
| Limites | `max_turns` e orçamento por agente | categoria `limite_execucao` |
| Escopo | Conferência dos arquivos alterados antes do commit | categoria `violacao_escopo` |
| Qualidade | Teste sem asserção é recusado; teste de regressão precisa falhar sem o patch | `quality_check`, `regression_check` |
| Proteção da `main` | Branch protection no GitHub exigindo PR e o check `ci` | configuração do repositório |

Limitação conhecida: o agente de Deploy roda sem sandbox, pois precisa do Docker, e é contido apenas pela lista de comandos.

## Definições das métricas

- **Tempo total:** do início ao fim da execução, incluindo espera nos gates.
- **Tempo de agentes:** soma de `duration_s` dos agentes.
- **Esforço humano:** minutos declarados pelo aprovador em cada gate. O valor sugerido é o tempo de relógio, e deve ser corrigido se a pessoa não esteve dedicada.
- **Custo:** `total_cost_usd` de cada agente.
- **Intervenção humana:** cada decisão em gate (aprovação, reprovação ou edição) e cada interrupção manual.
- **Retrabalho:** reprovações nos gates.
- **Cobertura:** cobertura de linhas do serviço antes e depois do ciclo.

## Taxonomia de falhas

| Categoria | Origem |
|---|---|
| `alucinacao` | Humano, ao reprovar: API, campo ou função inexistente |
| `especificacao_mal_interpretada` | Humano, ao reprovar |
| `teste_tautologico` | Automática ou humana |
| `qualidade_codigo` | Humano, ao reprovar |
| `seguranca` | Humano, ao reprovar |
| `outra` | Humano, ao reprovar |
| `criterio_aceitacao` | Automática: história ou relatório fora do padrão |
| `ci_quebrado` | Automática |
| `suite_vermelha` | Automática: suíte local falhou antes do commit |
| `correcao_bloqueada` | Automática: o agente não conseguiu alterar nada para corrigir a CI |
| `registro` | Automática: falha ao comentar na issue |
| `limite_execucao` | Automática: turnos ou orçamento |
| `erro_agente` | Automática |
| `violacao_escopo` | Automática |
| `vazamento_segredo` | Automática: canário na saída |
| `homologacao_nao_saudavel` | Automática |
| `processo` | Automática: gate aprovado sem merge efetivo |

## Como executar

Pré-requisitos: `ANTHROPIC_API_KEY`, `gh auth login`, Docker ou Podman com o socket ativo (`systemctl --user start podman.socket`) e repositório com a proteção da `main` ativa.

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -r requirements/orchestrator.txt
```

```bash
.venv/bin/python -m orchestrator run --issue 2 --operator "Nome (papel)"
```

Repita com `--issue 4` (ORD-FEAT-01), `--issue 5` (ORD-BUG-01) e `--issue 6` (GRD-01). A #3 (CAT-BUG-01) já foi executada.

Durante a execução, o terminal mostra cada fase do supervisor, as mensagens e ferramentas de cada agente, os bloqueios de guarda-corpo, o custo por agente e as decisões nos gates. Use `--quiet` para ver só os gates. O registro completo continua no trace.

No G5, revise o PR no GitHub e faça o merge antes de responder `a` no terminal. Se responder antes do merge, o supervisor espera o merge sem registrar uma nova decisão. Ao final, consolide os dados:

```bash
.venv/bin/python -m orchestrator report
```

## Front

O front (`web/`) faz parte do escopo dos agentes como **código** (atividade 6): quando a demanda precisa ser usada pela tela, o agente de Código implementa a interação em `web/public/` e o agente de Testes cobre a lógica de `lib.js` com `node --test`. O **design de interface** (atividade 5) continua com a equipe técnica:

- Decisões visuais (layout, cores, tipografia, componentes novos) só entram quando descritas na seção `## Interface` da issue.
- Sem essa seção, o guarda-corpo bloqueia a escrita em `web/public/styles.css` e os agentes são instruídos a reutilizar os elementos existentes, registrando necessidades visuais como pendência.
- Como os agentes não enxergam a tela, o aprovador do G7 confere a interface em http://localhost:8080 antes de autorizar a virada.

Durante o G7, a homologação fica no ar. Com a virada autorizada, o ambiente continua no ar com a versão liberada, simulando produção. No rollback, ele é derrubado.

## Papéis nos gates

| Gate | Decisão | Papel |
|---|---|---|
| G3 | Histórias e critérios de aceitação | PO e tech lead |
| G5 | Revisão e merge do PR | Desenvolvedor sênior; QA em bugs |
| G7 | Autorização da virada ou rollback | DevOps |

A virada para produção é simulada: o supervisor cria a tag `release/<execução>` e mantém o ambiente no ar com a versão liberada. O sistema é fictício e não há produção real.

## Ensaios

`--platform local` roda sem GitHub, usando a branch `pilot-local`. Com `--auto-approve`, os gates são aprovados automaticamente. Ensaios são gravados em `pilot/traces/rehearsal/` e nunca entram no relatório.
