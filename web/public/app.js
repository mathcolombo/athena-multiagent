import {
  CART_OPEN,
  errorMessage,
  formatMoney as money,
  nextQuantity,
  orderStatusClass,
  parseMoneyToCents,
  parseQuantity,
  requestInit,
  shortId,
} from "./lib.js";

const $ = id => document.getElementById(id);
const customer = () => $("customer").value.trim() || "cliente-demo";
const CART_KEY = "skynet-cart-id";

function storedCart() { try { return localStorage.getItem(CART_KEY); } catch { return null; } }
function storeCart(id) { try { id ? localStorage.setItem(CART_KEY, id) : localStorage.removeItem(CART_KEY); } catch {} }

function toast(message) {
  const el = $("toast");
  el.textContent = message;
  el.style.display = "block";
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (el.style.display = "none"), 4000);
}

async function api(service, path, { method = "GET", body } = {}) {
  const response = await fetch(`/api/${service}${path}`, requestInit(method, body));
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(errorMessage(response.status, data));
  return data;
}

function cell(text, className) {
  const td = document.createElement("td");
  td.textContent = text;
  if (className) td.className = className;
  return td;
}

function button(label, onClick, ghost = true) {
  const b = document.createElement("button");
  b.textContent = label;
  if (ghost) b.className = "ghost";
  b.addEventListener("click", onClick);
  return b;
}

async function loadProducts() {
  const products = await api("catalog", "/products");
  const body = $("products");
  body.replaceChildren();
  for (const product of products) {
    const row = document.createElement("tr");
    row.append(cell(product.name), cell(money(product.price_cents), "num"), cell(product.stock, "num"));
    const actions = document.createElement("td");
    actions.className = "row-actions";
    actions.append(
      button("Adicionar", () => addToCart(product.id)),
      button("Alterar preço", () => changePrice(product)),
      button("Estoque", () => changeStock(product)),
    );
    row.append(actions);
    body.append(row);
  }
  if (!products.length) body.innerHTML = '<tr><td colspan="4" class="muted">Nenhum produto cadastrado.</td></tr>';
}

async function ensureCart() {
  let id = storedCart();
  if (id) {
    try {
      const cart = await api("cart", `/carts/${id}`);
      if (cart.status === CART_OPEN) return id;
    } catch {}
  }
  id = (await api("cart", "/carts", { method: "POST", body: { customer_id: customer() } })).id;
  storeCart(id);
  return id;
}

async function loadCart() {
  const id = storedCart();
  const body = $("cart-items");
  body.replaceChildren();
  if (!id) { $("cart-info").textContent = "Nenhum carrinho aberto."; $("cart-total").textContent = money(0); return; }
  let cart;
  try { cart = await api("cart", `/carts/${id}`); } catch { storeCart(null); return loadCart(); }
  $("cart-info").textContent = `Carrinho ${shortId(id)} · ${cart.status === CART_OPEN ? "aberto" : "finalizado"}`;
  for (const item of cart.items) {
    const row = document.createElement("tr");
    row.append(cell(item.name), cell(item.quantity, "num"), cell(money(item.unit_price_cents), "num"));
    const actions = document.createElement("td");
    if (cart.status === CART_OPEN) actions.append(button("Remover", () => removeItem(item.product_id)));
    row.append(actions);
    body.append(row);
  }
  $("cart-total").textContent = money(cart.total_cents);
}

async function loadOrders() {
  const orders = await api("orders", `/orders?customer_id=${encodeURIComponent(customer())}`);
  const body = $("orders");
  body.replaceChildren();
  for (const order of orders) {
    const row = document.createElement("tr");
    row.append(cell(shortId(order.id)), cell(order.status, orderStatusClass(order.status)), cell(money(order.total_cents), "num"));
    if (order.rejection_reason) row.title = order.rejection_reason;
    body.append(row);
  }
  if (!orders.length) body.innerHTML = '<tr><td colspan="3" class="muted">Nenhum pedido deste cliente.</td></tr>';
}

async function addToCart(productId) {
  try {
    const id = await ensureCart();
    const cart = await api("cart", `/carts/${id}`);
    await api("cart", `/carts/${id}/items`, { method: "PUT", body: { product_id: productId, quantity: nextQuantity(cart, productId) } });
    await loadCart();
  } catch (error) { toast(`Não foi possível adicionar: ${error.message}`); }
}

async function removeItem(productId) {
  try {
    await api("cart", `/carts/${storedCart()}/items/${productId}`, { method: "DELETE" });
    await loadCart();
  } catch (error) { toast(error.message); }
}

async function changePrice(product) {
  const answer = prompt(`Novo preço de ${product.name} (R$)`, (product.price_cents / 100).toFixed(2).replace(".", ","));
  if (answer === null) return;
  const priceCents = parseMoneyToCents(answer);
  if (Number.isNaN(priceCents)) return toast("Preço inválido. Use, por exemplo, 149,90.");
  try {
    await api("catalog", `/products/${product.id}`, { method: "PATCH", body: { price_cents: priceCents } });
    await refresh();
    toast("Preço alterado no catálogo. Confira se o carrinho recebeu o novo preço.");
  } catch (error) { toast(error.message); }
}

async function changeStock(product) {
  const answer = prompt(`Novo estoque de ${product.name}`, product.stock);
  if (answer === null) return;
  const stock = parseQuantity(answer);
  if (Number.isNaN(stock)) return toast("Estoque inválido. Use um número inteiro.");
  try {
    await api("catalog", `/products/${product.id}`, { method: "PATCH", body: { stock } });
    await loadProducts();
  } catch (error) { toast(error.message); }
}

async function refresh() {
  await Promise.all([loadProducts(), loadCart(), loadOrders()]).catch(error => toast(error.message));
}

$("product-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = new FormData(event.target);
  const priceCents = parseMoneyToCents(form.get("price"));
  const stock = parseQuantity(form.get("stock"));
  if (Number.isNaN(priceCents) || Number.isNaN(stock)) return toast("Informe preço (ex.: 149,90) e estoque inteiro.");
  try {
    await api("catalog", "/products", {
      method: "POST",
      body: { name: form.get("name"), price_cents: priceCents, stock },
    });
    event.target.reset();
    await loadProducts();
  } catch (error) { toast(`Cadastro inválido: ${error.message}`); }
});

$("checkout").addEventListener("click", async () => {
  const id = storedCart();
  if (!id) return toast("Adicione itens ao carrinho primeiro.");
  try {
    await api("cart", `/carts/${id}/checkout`, { method: "POST" });
    storeCart(null);
    await refresh();
    toast("Compra finalizada. Acompanhe o pedido.");
  } catch (error) { toast(`Checkout recusado: ${error.message}`); }
});

$("new-cart").addEventListener("click", () => { storeCart(null); loadCart(); });
$("refresh").addEventListener("click", refresh);
$("customer").addEventListener("change", () => { storeCart(null); refresh(); });

refresh();
setInterval(() => Promise.all([loadOrders(), loadProducts()]).catch(() => {}), 3000);
