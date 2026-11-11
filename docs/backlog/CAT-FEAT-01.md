# CAT-FEAT-01: Aviso de estoque baixo no catálogo

Regra: RN-07

Regra nova (próximo número livre; a incluir em `docs/regras-de-negocio.md`):

- **RN-07**: Cada produto pode ter um limite de estoque baixo opcional (inteiro >= 0). O produto está com estoque baixo quando tem limite e estoque < limite (estoque igual ao limite não é baixo). O catálogo publica `stock.low` uma única vez a cada cruzamento de "normal" para "baixo", qualquer que seja a origem (alteração manual de estoque, alteração do limite ou reserva de pedido). Enquanto continuar baixo não há novo aviso; ao voltar a estoque >= limite (ou sem limite) o produto volta ao normal e um novo cruzamento avisa de novo. Produto sem limite nunca gera aviso.

## História
Como integrante da equipe de compras (e de quem opera a loja), quero que o catálogo avise quando o estoque de um produto cair abaixo do limite configurado para ele, para reagir antes de o produto zerar.

## Critérios de aceitação

Cenário: Cadastrar produto com limite
  Dado que não existe o produto
  Quando crio um produto com estoque 10 e limite 3
  Então o produto é criado com limite 3 e low_stock falso
  E nenhum evento stock.low é publicado

Cenário: Cadastrar produto sem limite
  Dado que não existe o produto
  Quando crio um produto sem informar limite
  Então o limite do produto é nulo e low_stock é falso

Cenário: Cadastrar produto já abaixo do limite
  Dado que não existe o produto
  Quando crio um produto com estoque 2 e limite 5
  Então o produto fica com low_stock verdadeiro
  E um evento stock.low é publicado com estoque 2 e limite 5

Cenário: Alteração manual de estoque cruza o limite
  Dado um produto com estoque 5 e limite 3
  Quando altero o estoque para 2
  Então um evento stock.low é publicado com product_id, nome, estoque 2 e limite 3
  E a consulta do produto mostra low_stock verdadeiro

Cenário: Estoque igual ao limite não é baixo
  Dado um produto com estoque 5 e limite 3
  Quando altero o estoque para 3
  Então nenhum evento stock.low é publicado
  E low_stock é falso

Cenário: Reserva de pedido cruza o limite
  Dado um produto com estoque 5 e limite 3
  Quando chega order.created reservando 3 unidades desse produto
  Então um evento stock.low é publicado com estoque 2 e limite 3, com o correlation_id do pedido
  E stock.reserved também é publicado

Cenário: Reserva de pedido com vários produtos
  Dado dois produtos com limite, ambos prestes a cruzá-lo
  Quando chega order.created reservando os dois
  Então é publicado um stock.low para cada produto que cruzou o limite

Cenário: Reserva rejeitada não avisa
  Dado um produto com estoque 5 e limite 3 e outro sem estoque suficiente no mesmo pedido
  Quando chega order.created e a reserva é rejeitada
  Então nenhum stock.low é publicado e o estoque não muda
  E stock.rejected é publicado

Cenário: Sem repetição enquanto continua baixo
  Dado um produto já com estoque baixo (estoque 2, limite 3)
  Quando o estoque cai para 1 por alteração manual ou por reserva
  Então nenhum novo stock.low é publicado

Cenário: Reposição e novo cruzamento
  Dado um produto com estoque baixo (estoque 2, limite 3)
  Quando o estoque é reposto para 3 ou mais e depois cai de novo abaixo do limite
  Então low_stock volta a falso na reposição
  E um novo stock.low é publicado no segundo cruzamento

Cenário: Configurar limite acima do estoque atual
  Dado um produto com estoque 5 sem limite
  Quando defino o limite como 8
  Então um evento stock.low é publicado com estoque 5 e limite 8
  E low_stock é verdadeiro

Cenário: Aumentar o limite com produto já baixo
  Dado um produto com estoque 2 e limite 3 já em estoque baixo
  Quando altero o limite para 6
  Então nenhum novo stock.low é publicado

Cenário: Reduzir o limite tira o produto de estoque baixo
  Dado um produto com estoque 2 e limite 3
  Quando altero o limite para 2
  Então low_stock é falso e nenhum evento é publicado

Cenário: Remover o limite
  Dado um produto com limite 3 e estoque baixo
  Quando envio o limite nulo
  Então o limite passa a nulo e low_stock é falso
  E nenhum evento é publicado

Cenário: Alteração sem mencionar o limite preserva o limite
  Dado um produto com limite 3
  Quando altero apenas o preço
  Então o limite continua 3

Cenário: Produto sem limite nunca avisa
  Dado um produto sem limite
  Quando o estoque cai a zero por alteração manual ou por reserva
  Então nenhum stock.low é publicado e low_stock é falso

Cenário: Limite inválido
  Dado um produto existente
  Quando informo limite negativo (no cadastro ou na alteração)
  Então a API responde 422 e nada muda

Cenário: Reentrega de order.created não duplica aviso
  Dado um order.created já processado que gerou stock.low
  Quando o mesmo evento é entregue de novo
  Então nenhum evento adicional é publicado

Cenário: Consulta informa limite e situação
  Dado produtos com e sem limite, alguns abaixo dele
  Quando listo ou consulto produtos
  Então cada produto traz low_stock_threshold (inteiro ou nulo) e low_stock (booleano)

Cenário: Toast quando produto passa a ficar baixo
  Dado a tela aberta com um produto normal
  Quando uma alteração de estoque ou limite, ou a atualização periódica, mostra que ele passou a estar baixo
  Então aparece um toast no canto superior direito: "Estoque baixo: <nome> — <estoque> un. (limite <limite>)"
  E ele tem role="status" e aria-live="polite", usa --warn, some após 5 segundos e tem botão "×"

Cenário: Produto já baixo ao abrir a página não gera toast
  Dado um produto já em estoque baixo quando a página abre
  Quando a lista é carregada e atualizada sem mudança de situação
  Então nenhum toast é exibido

Cenário: Limite de toasts visíveis
  Dado 3 toasts visíveis
  Quando um quarto produto passa a ficar baixo
  Então o toast mais antigo sai e no máximo 3 ficam visíveis, empilhados de cima para baixo

Cenário: Configurar limite pela tela
  Dado a lista do catálogo
  Quando clico em "Limite" e informo um número
  Então o limite é salvo; se deixo vazio, o limite é removido
  E se informo valor inválido (negativo ou não inteiro), vejo erro em português e nada muda

Cenário: Indicação visual na lista
  Dado um produto com estoque baixo
  Quando vejo a lista
  Então o número do estoque aparece na cor --warn

## Eventos
| Tipo | Campos | Novo ou alterado |
|---|---|---|
| `stock.low` | `product_id: str`, `name: str`, `stock: int`, `threshold: int` (envelope com `correlation_id`, `producer=catalog`, `VERSION=1`) | Novo (`StockLow`) |
| `product.created` | sem alteração (limite não faz parte do contrato) | Inalterado |

## Questões em aberto
- Nome do evento na classe: `StockLow` com `EVENT_TYPE = "stock.low"`, campos `stock` e `threshold` (em inglês, conforme convenção). Confirmar no G3.
- Nomes dos campos da API: `low_stock_threshold` e `low_stock`. Confirmar no G3.
- Alteração manual (PATCH) não tem correlation_id de origem; o evento usa um novo, como `ProductPriceChanged`. Confirmar.
- Estado de "estoque baixo" a persistir ou derivar? Proposta: derivar comparando antes e depois de cada mudança, sem coluna extra. Confirmar.
- Produtos já abaixo do limite em bancos existentes (migração da coluna nova, nula por padrão): sem aviso retroativo. Confirmar.
- O toast da atualização periódica depende de a tela já ter polling; verificar `web/public/app.js`. Se não houver, definir o intervalo (fora da `<interface>`).
- Mensagem de erro de limite inválido na tela e rótulo do prompt "Limite": texto livre da equipe técnica.

## Tasks

### T1: Contrato do evento `stock.low` e RN-07
Cenários: Nenhum cenário de comportamento direto (contrato validado por testes de contrato).
Arquivos: `libs/events/skynet_events/contracts.py`, `libs/events/skynet_events/__init__.py`, `libs/events/tests/`, `docs/regras-de-negocio.md`
Pronto quando: `StockLow` (EVENT_TYPE `stock.low`, VERSION 1) existe, está exportado, é codificado e decodificado em teste do envelope, RN-07 está na tabela e `pytest libs/events/tests` passa.

### T2: Limite por produto no cadastro, na alteração e na consulta
Cenários: Cadastrar produto com limite; Cadastrar produto sem limite; Alteração sem mencionar o limite preserva o limite; Remover o limite; Limite inválido; Consulta informa limite e situação
Arquivos: `services/catalog/catalog_service/db.py`, `services/catalog/catalog_service/app.py`, `services/catalog/tests/test_catalog.py`
Pronto quando: coluna `low_stock_threshold` (nula, CHECK >= 0, com migração para bancos existentes); POST aceita o limite opcional; PATCH distingue limite ausente de nulo (`model_fields_set`); GET retorna `low_stock_threshold` e `low_stock`; `pytest services/catalog/tests` passa.

### T3: Aviso por alteração manual de estoque ou de limite
Cenários: Cadastrar produto já abaixo do limite; Alteração manual de estoque cruza o limite; Estoque igual ao limite não é baixo; Sem repetição enquanto continua baixo; Reposição e novo cruzamento; Configurar limite acima do estoque atual; Aumentar o limite com produto já baixo; Reduzir o limite tira o produto de estoque baixo; Produto sem limite nunca avisa
Arquivos: `services/catalog/catalog_service/app.py`, `services/catalog/catalog_service/db.py`, `services/catalog/tests/test_catalog.py`
Pronto quando: POST e PATCH publicam `stock.low` somente na transição de não-baixo para baixo (comparando antes e depois), e os cenários acima passam com `InMemoryBus.published`.

### T4: Aviso na reserva de estoque de pedidos
Cenários: Reserva de pedido cruza o limite; Reserva de pedido com vários produtos; Reserva rejeitada não avisa; Reentrega de order.created não duplica aviso; Sem repetição enquanto continua baixo
Arquivos: `services/catalog/catalog_service/db.py`, `services/catalog/catalog_service/app.py`, `services/catalog/tests/test_catalog.py`
Pronto quando: `reserve_stock` informa quais produtos cruzaram o limite (só quando a reserva é confirmada); `on_order_created` publica um `stock.low` por produto com o `correlation_id` do evento, depois de `stock.reserved`; a reentrega via `InMemoryBus.deliver` não publica nada novo; `bash scripts/ci.sh catalog` passa.

### T5: Front: configurar limite e indicar estoque baixo
Cenários: Configurar limite pela tela; Indicação visual na lista
Arquivos: `web/public/index.html`, `web/public/app.js`, `web/public/lib.js`, `web/public/styles.css`, `web/tests/lib.test.js`
Pronto quando: o formulário tem o campo opcional "Limite" (mesmo tamanho do estoque); a lista tem o botão "Limite" ao lado de "Estoque" (vazio remove, inválido mostra erro); o estoque baixo aparece em `--warn`; a lógica pura (validação do limite e entrada para o payload) está em `lib.js` com testes; `node --test "web/tests/*.test.js"` passa.

### T6: Front: toast de estoque baixo
Cenários: Toast quando produto passa a ficar baixo; Produto já baixo ao abrir a página não gera toast; Limite de toasts visíveis
Arquivos: `web/public/app.js`, `web/public/lib.js`, `web/public/styles.css`, `web/public/index.html`, `web/tests/lib.test.js`
Pronto quando: função pura em `lib.js` compara listas anteriores e atuais e devolve os produtos que passaram a ficar baixos (ignorando a primeira carga); o toast é montado com `createElement`/`textContent`, no canto superior direito, com `role="status"`, `aria-live="polite"`, `--warn`, botão "×", fechamento em 5 s e máximo de 3 visíveis; disparado após alterar estoque ou limite e na atualização periódica; `node --test "web/tests/*.test.js"` passa.
