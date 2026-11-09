# Skynet Tech: piloto de desenvolvimento guiado por agentes

Monorepo do piloto instrumentado do trabalho "Desenvolvimento de Software Guiado por Agentes de IA" (UniSales).

- `services/`: catálogo, carrinho e pedidos, integrados por eventos no RabbitMQ
- `libs/events/`: contratos de eventos e barramentos
- `orchestrator/`: supervisor, agentes (Claude Agent SDK), guarda-corpos, gates e tracing
- `pilot/`: demandas, traces e relatório
- `docs/`: conhecimento do projeto e [protocolo do piloto](docs/piloto/protocolo.md)
- `AGENTS.md`: contexto injetado nos agentes
