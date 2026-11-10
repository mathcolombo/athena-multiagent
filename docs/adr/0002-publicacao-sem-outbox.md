# ADR 0002: publicação direta, sem outbox

**Status:** aceito para o estágio atual

## Contexto
O padrão outbox evita perda de eventos entre o commit no banco e a publicação no broker, mas adiciona tabela e processo de despacho.

## Decisão
Publicar logo após o commit local. O risco é aceito porque o sistema é de escopo reduzido.

## Consequências
Uma queda entre commit e publicação perde o evento. Adotar outbox é pré-requisito para produção com tráfego real.
