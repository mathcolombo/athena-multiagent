# Skynet Tech: piloto de desenvolvimento guiado por agentes

Monorepo do piloto instrumentado do trabalho "Desenvolvimento de Software Guiado por Agentes de IA" (UniSales).

- `services/`: catálogo, carrinho e pedidos, integrados por eventos no RabbitMQ
- `libs/events/`: contratos de eventos e barramentos
- `web/`: front simples de homologação em http://localhost:8080
- `orchestrator/`: supervisor, agentes (Claude Agent SDK), guarda-corpos, gates e tracing
- `pilot/`: demandas, traces e relatório
- `docs/`: conhecimento do projeto e [protocolo do piloto](docs/piloto/protocolo.md)
- `AGENTS.md`: contexto injetado nos agentes

## Testar o sistema pelo front

```bash
bash scripts/deploy_homolog.sh up
```

Abra http://localhost:8080 para cadastrar produtos, alterar preço e estoque, montar o carrinho, finalizar a compra e acompanhar o status do pedido. A documentação das APIs fica em http://localhost:8001/docs (catálogo), 8002 (carrinho) e 8003 (pedidos). Para derrubar:

```bash
bash scripts/deploy_homolog.sh down
```
