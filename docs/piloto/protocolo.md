# Protocolo do piloto instrumentado

Define o que é medido e como executar o piloto do processo guiado por agentes (seção 2 do trabalho). As definições foram fixadas antes das execuções para evitar ajustes posteriores.

## Fluxos

Cada fluxo é um serviço com dois ciclos completos.

| Fluxo | Ciclo | Demanda | Passos |
|---|---|---|---|
| Catálogo | Funcionalidade | CAT-FEAT-01 | Requisitos → G3 → Código → Testes → CI → G5 → Deploy em homologação → G7 |
| Catálogo | Bug | CAT-BUG-01 | Reprodução e patch → Teste de regressão → CI → G5 → Deploy em homologação → G7 |
| Pedidos | Funcionalidade | ORD-FEAT-01 | Igual ao ciclo de funcionalidade |
| Pedidos | Bug | ORD-BUG-01 | Igual ao ciclo de bug |
| Verificação | Guarda-corpo | GRD-01 | Agente de Código recebe um relato com injeção de instrução; sem PR |

Cada demanda tem uma issue no GitHub (#2 a #6), indicada no campo `issue:` do arquivo da demanda. O PR aberto pelo orquestrador inclui `Closes #N`, então o merge no G5 fecha a issue. A issue do GRD-01 é fechada manualmente depois da execução, com o resultado registrado no trace.

## Agentes e limites

| Agente | Atividades | Escrita | Comandos | Turnos | Orçamento (US$) |
|---|---|---|---|---:|---:|
| Requisitos | 2, 3 | `docs/backlog/` | nenhum | 20 | 1,50 |
| Código | 6, 7 | serviço do fluxo e `libs/events/`, exceto `tests/`; `.pilot/repro/` | pytest, git somente leitura | 50 | 4,00 |
| Testes | 8, 10 | `tests/` do serviço e de `libs/events/` | pytest, git somente leitura | 40 | 3,00 |
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
.venv/bin/python -m orchestrator run --flow catalog --cycle feature --operator "Nome (papel)"
```

Repita com `--flow catalog --cycle bug`, `--flow orders --cycle feature`, `--flow orders --cycle bug` e `--flow catalog --cycle guardrail`.

No G5, revise o PR no GitHub e faça o merge antes de responder `a` no terminal. Se responder antes do merge, o supervisor espera o merge sem registrar uma nova decisão. Ao final, consolide os dados:

```bash
.venv/bin/python -m orchestrator report
```

## Front de homologação

Durante o G7, a homologação fica no ar em http://localhost:8080 para o aprovador conferir o comportamento antes de autorizar a virada. Com a virada autorizada, o ambiente continua no ar com a versão liberada, simulando produção. No rollback, ele é derrubado. O front está fora do escopo dos agentes; funcionalidades novas sem tela, como o cancelamento de pedido, são conferidas pelas APIs em `/docs`.

## Papéis nos gates

| Gate | Decisão | Papel |
|---|---|---|
| G3 | Histórias e critérios de aceitação | PO e tech lead |
| G5 | Revisão e merge do PR | Desenvolvedor sênior; QA em bugs |
| G7 | Autorização da virada ou rollback | DevOps |

A virada para produção é simulada: o supervisor cria a tag `release/<execução>` e mantém o ambiente no ar com a versão liberada. O sistema é fictício e não há produção real.

## Ensaios

`--platform local` roda sem GitHub, usando a branch `pilot-local`. Com `--auto-approve`, os gates são aprovados automaticamente. Ensaios são gravados em `pilot/traces/rehearsal/` e nunca entram no relatório.
