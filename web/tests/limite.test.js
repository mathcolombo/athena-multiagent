import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { parseLimit, productBody, stockClass } from "../public/lib.js";

const read = name => readFileSync(new URL(`../public/${name}`, import.meta.url), "utf8");

// Cenário: Configurar limite pela tela

test("parseLimit aceita inteiros >= 0 (Configurar limite pela tela)", () => {
  assert.equal(parseLimit("5"), 5);
  assert.equal(parseLimit("0"), 0);
  assert.equal(parseLimit("  12 "), 12);
});

test("parseLimit trata vazio como remoção do limite (Configurar limite pela tela)", () => {
  assert.equal(parseLimit(""), null);
  assert.equal(parseLimit("   "), null);
  assert.equal(parseLimit(null), null);
  assert.equal(parseLimit(undefined), null);
});

test("parseLimit rejeita negativo e não inteiro (Configurar limite pela tela)", () => {
  for (const invalid of ["-1", "2.5", "2,5", "abc", "1e", "--3"]) {
    assert.ok(Number.isNaN(parseLimit(invalid)), `deveria rejeitar ${invalid}`);
  }
});

test("productBody inclui low_stock_threshold quando há limite, inclusive 0 (Configurar limite pela tela)", () => {
  assert.deepEqual(
    productBody({ name: "Teclado", priceCents: 15000, stock: 10, limit: 3 }),
    { name: "Teclado", price_cents: 15000, stock: 10, low_stock_threshold: 3 },
  );
  assert.equal(productBody({ name: "Mouse", priceCents: 100, stock: 1, limit: 0 }).low_stock_threshold, 0);
});

test("productBody omite o limite quando vazio (Configurar limite pela tela)", () => {
  const body = productBody({ name: "Mouse", priceCents: 9990, stock: 4, limit: null });
  assert.deepEqual(body, { name: "Mouse", price_cents: 9990, stock: 4 });
  assert.ok(!("low_stock_threshold" in body));
  assert.ok(!("low_stock_threshold" in productBody({ name: "x", priceCents: 1, stock: 1 })));
});

test("formulário tem campo opcional Limite com a mesma classe do estoque (Configurar limite pela tela)", () => {
  const html = read("index.html");
  const stock = html.match(/<input[^>]*name="stock"[^>]*>/)?.[0];
  const limit = html.match(/<input[^>]*name="limit"[^>]*>/)?.[0];
  assert.ok(limit, "campo limit ausente");
  assert.match(limit, /placeholder="Limite"/);
  assert.doesNotMatch(limit, /\brequired\b/);
  assert.match(stock, /class="qty"/);
  assert.match(limit, /class="qty"/);
});

test("app.js oferece botão Limite que remove com vazio e avisa em português se inválido (Configurar limite pela tela)", () => {
  const app = read("app.js");
  assert.match(app, /button\("Limite"/);
  assert.match(app, /Limite inválido/);
  assert.match(app, /low_stock_threshold/);
});

// Cenário: Indicação visual na lista

test("stockClass marca produto com estoque baixo (Indicação visual na lista)", () => {
  assert.equal(stockClass({ stock: 2, low_stock_threshold: 3, low_stock: true }), "low-stock");
});

test("stockClass não marca produto normal ou sem low_stock (Indicação visual na lista)", () => {
  assert.equal(stockClass({ stock: 3, low_stock_threshold: 3, low_stock: false }), "");
  assert.equal(stockClass({ stock: 0, low_stock_threshold: null, low_stock: false }), "");
  assert.equal(stockClass({ stock: 5 }), "");
});

test("a classe de estoque baixo usa a cor --warn (Indicação visual na lista)", () => {
  const css = read("styles.css");
  assert.match(css, /\.low-stock\s*\{[^}]*color:\s*var\(--warn\)/);
});
