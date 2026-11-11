import assert from "node:assert/strict";
import { test } from "node:test";

import {
  errorMessage,
  formatMoney,
  nextQuantity,
  orderStatusClass,
  parseMoneyToCents,
  parseQuantity,
  requestInit,
} from "../public/lib.js";

test("formatMoney formata centavos em reais", () => {
  assert.equal(formatMoney(15000).replace(/\s/g, " "), "R$ 150,00");
});

test("parseMoneyToCents aceita formatos brasileiro e com ponto decimal", () => {
  assert.equal(parseMoneyToCents("150"), 15000);
  assert.equal(parseMoneyToCents("149,9"), 14990);
  assert.equal(parseMoneyToCents("1.234,56"), 123456);
  assert.equal(parseMoneyToCents("150.50"), 15050);
  assert.equal(parseMoneyToCents("R$ 10,00"), 1000);
});

test("parseMoneyToCents rejeita texto inválido", () => {
  assert.ok(Number.isNaN(parseMoneyToCents("abc")));
  assert.ok(Number.isNaN(parseMoneyToCents("-5")));
  assert.ok(Number.isNaN(parseMoneyToCents("1,234.56")));
});

test("parseQuantity aceita apenas inteiros não negativos", () => {
  assert.equal(parseQuantity("3"), 3);
  assert.ok(Number.isNaN(parseQuantity("2.5")));
  assert.ok(Number.isNaN(parseQuantity("-1")));
});

test("nextQuantity soma um ao item existente ou começa em um", () => {
  const cart = { items: [{ product_id: "p1", quantity: 2 }] };

  assert.equal(nextQuantity(cart, "p1"), 3);
  assert.equal(nextQuantity(cart, "p2"), 1);
});

test("errorMessage usa o detalhe da API quando existe", () => {
  assert.equal(errorMessage(404, { detail: "produto não encontrado" }), "produto não encontrado");
  assert.equal(errorMessage(500, null), "HTTP 500");
});

test("requestInit serializa o corpo apenas quando informado", () => {
  assert.equal(requestInit().body, undefined);
  assert.equal(requestInit("PUT", { quantity: 1 }).body, '{"quantity":1}');
  assert.equal(orderStatusClass("CONFIRMED"), "status-CONFIRMED");
});
