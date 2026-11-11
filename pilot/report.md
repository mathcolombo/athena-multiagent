# Relatório do piloto

Gerado por `python -m orchestrator report` a partir de `pilot/traces/*.jsonl`. Ensaios ficam fora.

## Métricas por execução

| Demanda | Ciclo | Status | Tempo total (h) | Agentes (min) | Humano (min) | Custo (US$) | Intervenções | Reprovações | Edições | Falhas de CI | Cobertura antes → depois |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| CAT-BUG-01 | bug | completed | 0.12 | 1.8 | 6.8 | 0.38 | 4 | 0 | 0 | 1 | 64% → 77% |

## Totais por fluxo

| Fluxo | Execuções | Custo (US$) | Humano (min) | Agentes (min) | Intervenções |
|---|---:|---:|---:|---:|---:|
| catalog | 1 | 0.38 | 6.8 | 1.8 | 4 |

## Falhas observadas

| Categoria | Ocorrências |
|---|---:|
| processo | 2 |
| ci_quebrado | 1 |

## Bloqueios de guarda-corpo

| Regra | Ocorrências |
|---|---:|
| shell_metachar | 2 |
| command_not_allowed | 1 |
