---
id: CAT-BUG-01
flow: catalog
cycle: bug
title: alteração de preço não chega ao carrinho
issue: 3
---
Chamado do suporte: o time comercial alterou o preço de um produto pelo `PATCH /products/{id}`. A consulta no catálogo mostra o preço novo, mas clientes que colocam o produto no carrinho continuam vendo e pagando o preço antigo, mesmo horas depois. Não houve erro em nenhum serviço, e o RabbitMQ estava saudável.

Passos: criar um produto, aguardar o carrinho conhecê-lo, alterar o preço pelo PATCH e consultar um carrinho com esse produto.
Esperado: carrinho com o preço novo (RN-02). Observado: preço antigo.
