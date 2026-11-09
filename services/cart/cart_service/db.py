import sqlite3
from uuid import uuid4

SCHEMA = """
CREATE TABLE IF NOT EXISTS product_snapshots (
    product_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    price_cents INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS carts (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN'
);
CREATE TABLE IF NOT EXISTS cart_items (
    cart_id TEXT NOT NULL REFERENCES carts (id),
    product_id TEXT NOT NULL REFERENCES product_snapshots (product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (cart_id, product_id)
);
CREATE TABLE IF NOT EXISTS processed_events (event_id TEXT PRIMARY KEY);
"""


class CartDb:
    def __init__(self, path: str) -> None:
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def upsert_snapshot(self, product_id: str, name: str, price_cents: int) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO product_snapshots (product_id, name, price_cents) VALUES (?, ?, ?)
                ON CONFLICT (product_id) DO UPDATE
                SET name = excluded.name, price_cents = excluded.price_cents
                """,
                (product_id, name, price_cents),
            )

    def update_snapshot_price(self, product_id: str, price_cents: int) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE product_snapshots SET price_cents = ? WHERE product_id = ?",
                (price_cents, product_id),
            )

    def has_snapshot(self, product_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM product_snapshots WHERE product_id = ?", (product_id,)
        ).fetchone()
        return row is not None

    def create_cart(self, customer_id: str) -> str:
        cart_id = str(uuid4())
        with self.conn:
            self.conn.execute(
                "INSERT INTO carts (id, customer_id) VALUES (?, ?)", (cart_id, customer_id)
            )
        return cart_id

    def get_cart(self, cart_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM carts WHERE id = ?", (cart_id,)).fetchone()

    def get_items(self, cart_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT i.product_id, s.name, i.quantity, s.price_cents AS unit_price_cents
            FROM cart_items i JOIN product_snapshots s USING (product_id)
            WHERE i.cart_id = ?
            ORDER BY s.name
            """,
            (cart_id,),
        ).fetchall()

    def set_item(self, cart_id: str, product_id: str, quantity: int) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO cart_items (cart_id, product_id, quantity) VALUES (?, ?, ?)
                ON CONFLICT (cart_id, product_id) DO UPDATE SET quantity = excluded.quantity
                """,
                (cart_id, product_id, quantity),
            )

    def remove_item(self, cart_id: str, product_id: str) -> None:
        with self.conn:
            self.conn.execute(
                "DELETE FROM cart_items WHERE cart_id = ? AND product_id = ?",
                (cart_id, product_id),
            )

    def close_cart(self, cart_id: str) -> None:
        with self.conn:
            self.conn.execute("UPDATE carts SET status = 'CHECKED_OUT' WHERE id = ?", (cart_id,))

    def mark_processed(self, event_id: str) -> bool:
        """Retorna False se o evento já foi processado."""
        with self.conn:
            inserted = self.conn.execute(
                "INSERT OR IGNORE INTO processed_events (event_id) VALUES (?)", (event_id,)
            )
        return inserted.rowcount == 1
