"""Verificação de homologação: saúde de cada serviço e uma saga completa de pedido."""
import json
import sys
import time
import urllib.error
import urllib.request

CATALOG, CART, ORDERS = (f"http://localhost:{port}" for port in (8001, 8002, 8003))
WEB = "http://localhost:8080"
TIMEOUT_S = 30


def call(method: str, url: str, body: dict | None = None) -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data, {"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, None


def wait_until(check, description: str):
    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            result = check()
        except (urllib.error.URLError, ConnectionError):
            result = None
        if result:
            return result
        time.sleep(1)
    raise TimeoutError(description)


def main() -> int:
    try:
        for base in (CATALOG, CART, ORDERS):
            wait_until(lambda: call("GET", f"{base}/health")[0] == 200, f"{base} indisponível")
            print(f"OK saúde {base}")

        for asset in ("app.js", "lib.js", "styles.css"):
            request = urllib.request.Request(f"{WEB}/{asset}")
            with urllib.request.urlopen(request, timeout=5) as response:
                if response.status != 200:
                    raise RuntimeError(f"front sem {asset}")
        wait_until(lambda: call("GET", f"{WEB}/api/catalog/health")[0] == 200, "front indisponível")
        print(f"OK front {WEB}")

        _, product = call("POST", f"{CATALOG}/products", {"name": "Sonda", "price_cents": 1000, "stock": 3})
        _, cart = call("POST", f"{CART}/carts", {"customer_id": "homolog"})
        item = {"product_id": product["id"], "quantity": 1}
        wait_until(
            lambda: call("PUT", f"{CART}/carts/{cart['id']}/items", item)[0] == 200,
            "carrinho não recebeu product.created",
        )
        print("OK evento product.created")
        status, _ = call("POST", f"{CART}/carts/{cart['id']}/checkout")
        if status != 200:
            raise RuntimeError(f"checkout retornou {status}")

        def confirmed():
            orders = call("GET", f"{ORDERS}/orders?customer_id=homolog")[1]
            return [order for order in orders if order["cart_id"] == cart["id"] and order["status"] == "CONFIRMED"]

        wait_until(confirmed, "pedido não foi confirmado")
        print("OK saga de pedido confirmada")
        return 0
    except (TimeoutError, RuntimeError, TypeError, urllib.error.URLError) as error:
        print(f"FALHA {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
