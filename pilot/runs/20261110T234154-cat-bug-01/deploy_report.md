# Relatório de deploy em homologação

## Versão
`f9d7f51 Merge pull request #8 from mathcolombo:pilot/20261110T234154-cat-bug-01`

## Resultado dos passos

1. `bash scripts/deploy_homolog.sh up`: sucesso. As imagens de catalog, cart e orders foram construídas, quase todas a partir de cache. Os containers catalog e web foram recriados. rabbitmq, cart e orders já estavam em execução. Todos ficaram `Healthy`.
2. `python scripts/healthcheck.py`: sucesso.
   - OK saúde http://localhost:8001
   - OK saúde http://localhost:8002
   - OK saúde http://localhost:8003
   - OK front http://localhost:8080
   - OK evento product.created
   - OK saga de pedido confirmada

## Anomalias nos logs

Examinei apenas os logs do serviço `catalog` (últimas 100 linhas). Não há erros nem avisos: startup normal, `/health` e `/products` com 200 e `POST /products` com 201. Os logs de cart, orders, web e rabbitmq não foram examinados, porque o healthcheck passou e o procedimento só pede logs em caso de falha.

## Observações

- A imagem base é `python:3.14-slim`, enquanto o AGENTS.md fala em Python 3.12+. Não é uma falha, mas vale confirmar que a versão é intencional.
- Não foi feito nenhum rollback nem qualquer ação em produção.

## Recomendação ao aprovador

Homologação saudável e com a saga de pedido validada de ponta a ponta. Recomendo seguir para a decisão do gate G7.

STATUS: OK
