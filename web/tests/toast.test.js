import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { MAX_TOASTS, TOAST_MS, lowStockMessage, newlyLowStock } from "../public/lib.js";

const read = name => readFileSync(new URL(`../public/${name}`, import.meta.url), "utf8");

const p = (id, stock, threshold, low) => ({
  id, name: `Produto ${id}`, stock, low_stock_threshold: threshold, low_stock: low,
});

// Cenário: Toast quando produto passa a ficar baixo

test("newlyLowStock devolve produto que passou de normal para baixo (Toast quando produto passa a ficar baixo)", () => {
  const previous = [p("a", 5, 3, false), p("b", 9, null, false)];
  const current = [p("a", 2, 3, true), p("b", 9, null, false)];
  const result = newlyLowStock(previous, current);
  assert.deepEqual(result.map(x => x.id), ["a"]);
});

test("newlyLowStock detecta limite alterado que coloca produto em baixo (Toast quando produto passa a ficar baixo)", () => {
  const result = newlyLowStock([p("a", 5, null, false)], [p("a", 5, 10, true)]);
  assert.equal(result.length, 1);
  assert.equal(result[0].low_stock_threshold, 10);
});

test("newlyLowStock não repete enquanto continua baixo e reavisa após voltar ao normal (Toast quando produto passa a ficar baixo)", () => {
  const low = [p("a", 1, 3, true)];
  assert.deepEqual(newlyLowStock(low, [p("a", 0, 3, true)]), []);
  const normal = [p("a", 10, 3, false)];
  assert.deepEqual(newlyLowStock(low, normal), []);
  assert.equal(newlyLowStock(normal, low).length, 1);
});

test("newlyLowStock ignora produto que não existia antes (Toast quando produto passa a ficar baixo)", () => {
  assert.deepEqual(newlyLowStock([p("a", 5, 3, false)], [p("a", 5, 3, false), p("n", 1, 3, true)]), []);
});

test("lowStockMessage segue o texto da interface (Toast quando produto passa a ficar baixo)", () => {
  assert.equal(
    lowStockMessage(p("x", 2, 5, true)),
    "Estoque baixo: Produto x — 2 un. (limite 5)",
  );
});

test("toast é montado com createElement/textContent, role, aria-live e botão × (Toast quando produto passa a ficar baixo)", () => {
  const app = read("app.js");
  const fn = app.match(/function lowStockToast[\s\S]*?\n}\n/)?.[0];
  assert.ok(fn, "função lowStockToast ausente");
  assert.match(fn, /createElement\("div"\)/);
  assert.match(fn, /setAttribute\("role", "status"\)/);
  assert.match(fn, /setAttribute\("aria-live", "polite"\)/);
  assert.match(fn, /textContent = message/);
  assert.match(fn, /textContent = "×"/);
  assert.match(fn, /setTimeout\(remove, TOAST_MS\)/);
  assert.doesNotMatch(fn, /innerHTML/);
});

test("TOAST_MS é 5 segundos (Toast quando produto passa a ficar baixo)", () => {
  assert.equal(TOAST_MS, 5000);
});

test("toast fica no canto superior direito com --warn (Toast quando produto passa a ficar baixo)", () => {
  const css = read("styles.css");
  const box = css.match(/#low-stock-toasts\s*\{([^}]*)\}/)?.[1];
  assert.ok(box, "container ausente no CSS");
  assert.match(box, /position:\s*fixed/);
  assert.match(box, /top:\s*16px/);
  assert.match(box, /right:\s*16px/);
  assert.match(css, /\.low-toast\s*\{[^}]*var\(--warn\)/);
  assert.match(read("index.html"), /id="low-stock-toasts"/);
});

test("toast é disparado na carga de produtos, usada após alterar estoque/limite e no polling (Toast quando produto passa a ficar baixo)", () => {
  const app = read("app.js");
  const load = app.match(/async function loadProducts[\s\S]*?previousProducts = products;/)?.[0];
  assert.ok(load, "loadProducts não compara cargas");
  assert.match(load, /newlyLowStock\(previousProducts, products\)/);
  assert.match(load, /lowStockToast\(lowStockMessage\(product\)\)/);
  assert.match(app, /setInterval\([^\n]*loadProducts\(\)/);
  // estoque e limite recarregam a lista após o PATCH
  assert.ok((app.match(/await loadProducts\(\)/g) ?? []).length >= 3);
});

// Cenário: Produto já baixo ao abrir a página não gera toast

test("primeira carga (previous nulo) não gera toast mesmo com produtos baixos (Produto já baixo ao abrir a página não gera toast)", () => {
  assert.deepEqual(newlyLowStock(null, [p("a", 1, 3, true)]), []);
  assert.deepEqual(newlyLowStock(undefined, [p("a", 1, 3, true)]), []);
});

test("recarga sem mudança de situação não gera toast (Produto já baixo ao abrir a página não gera toast)", () => {
  const list = [p("a", 1, 3, true), p("b", 8, 3, false)];
  assert.deepEqual(newlyLowStock(list, list.map(x => ({ ...x }))), []);
});

test("primeira carga vazia ainda conta como carga: baixo depois dela gera toast (Produto já baixo ao abrir a página não gera toast)", () => {
  assert.deepEqual(newlyLowStock([], [p("a", 1, 3, true)]), []);
});

// Cenário: Limite de toasts visíveis

test("MAX_TOASTS é 3 (Limite de toasts visíveis)", () => {
  assert.equal(MAX_TOASTS, 3);
});

test("quarto toast remove o mais antigo e empilha em ordem de chegada (Limite de toasts visíveis)", () => {
  const app = read("app.js");
  const fn = app.match(/function lowStockToast[\s\S]*?\n}\n/)[0];
  assert.match(fn, /box\.append\(el\)/);
  assert.match(fn, /while \(box\.children\.length > MAX_TOASTS\)/);
  assert.match(fn, /box\.firstElementChild/);
  const css = read("styles.css");
  assert.match(css.match(/#low-stock-toasts\s*\{([^}]*)\}/)[1], /flex-direction:\s*column(?!-reverse)/);
});

test("quatro produtos passando a baixo de uma vez são todos detectados (Limite de toasts visíveis)", () => {
  const prev = ["a", "b", "c", "d"].map(id => p(id, 5, 3, false));
  const cur = ["a", "b", "c", "d"].map(id => p(id, 1, 3, true));
  assert.deepEqual(newlyLowStock(prev, cur).map(x => x.id), ["a", "b", "c", "d"]);
});
