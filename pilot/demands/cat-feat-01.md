---
id: CAT-FEAT-01
flow: catalog
cycle: feature
title: alerta de estoque baixo
---
A equipe de compras só descobre que um produto está acabando quando ele zera. Queremos que o catálogo avise quando o estoque de um produto cair abaixo de um limite configurado para aquele produto, para que outros sistemas possam reagir.

O limite é opcional por produto. O aviso deve sair como um evento novo, `stock.low`, com produto, estoque atual e limite. Compras não quer receber repetição do mesmo aviso enquanto o produto continuar abaixo do limite; depois que o estoque for reposto acima do limite, um novo cruzamento volta a avisar.
