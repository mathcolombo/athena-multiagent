// Funções puras do front, sem acesso ao DOM, para serem testadas com `node --test`.

export const CART_OPEN = "OPEN";

export function formatMoney(cents) {
  return (cents / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

/** Aceita "150", "150,5", "1.234,56" e "150.50"; retorna NaN para texto inválido. */
export function parseMoneyToCents(text) {
  const raw = String(text).trim().replace(/^R\$\s*/, "");
  if (!/^\d{1,3}(\.\d{3})*(,\d{1,2})?$|^\d+([.,]\d{1,2})?$/.test(raw)) return NaN;
  const normalized = raw.includes(",") ? raw.replace(/\./g, "").replace(",", ".") : raw;
  return Math.round(Number(normalized) * 100);
}

export function parseQuantity(text) {
  const value = Number(String(text).trim());
  return Number.isInteger(value) && value >= 0 ? value : NaN;
}

export function shortId(id) {
  return String(id).slice(0, 8);
}

export function orderStatusClass(status) {
  return `status-${status}`;
}

export function nextQuantity(cart, productId) {
  const current = cart.items.find(item => item.product_id === productId)?.quantity ?? 0;
  return current + 1;
}

export function errorMessage(status, data) {
  if (data?.detail === undefined) return `HTTP ${status}`;
  return typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
}

export function requestInit(method = "GET", body) {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}
