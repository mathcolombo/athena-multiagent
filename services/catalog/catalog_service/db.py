import sqlite3
from uuid import uuid4

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
    stock INTEGER NOT NULL CHECK (stock >= 0),
    low_stock_threshold INTEGER CHECK (low_stock_threshold >= 0)
);
CREATE TABLE IF NOT EXISTS processed_events (event_id TEXT PRIMARY KEY);
"""


class CatalogDb:
    def __init__(self, path: str) -> None:
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(products)")}
        if "low_stock_threshold" not in columns:
            with self.conn:
                self.conn.execute(
                    "ALTER TABLE products ADD COLUMN low_stock_threshold INTEGER "
                    "CHECK (low_stock_threshold >= 0)"
                )

    def create_product(
        self,
        name: str,
        price_cents: int,
        stock: int,
        low_stock_threshold: int | None = None,
    ) -> sqlite3.Row:
        product_id = str(uuid4())
        with self.conn:
            self.conn.execute(
                "INSERT INTO products (id, name, price_cents, stock, low_stock_threshold) "
                "VALUES (?, ?, ?, ?, ?)",
                (product_id, name, price_cents, stock, low_stock_threshold),
            )
        return self.get_product(product_id)

    def get_product(self, product_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()

    def list_products(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM products ORDER BY name").fetchall()

    def update_product(
        self,
        product_id: str,
        name: str | None = None,
        price_cents: int | None = None,
        stock: int | None = None,
        low_stock_threshold: int | None = None,
        set_threshold: bool = False,
    ) -> sqlite3.Row | None:
        """`set_threshold` indica que o limite foi informado (inclusive como nulo)."""
        with self.conn:
            self.conn.execute(
                """
                UPDATE products
                SET name = COALESCE(?, name),
                    price_cents = COALESCE(?, price_cents),
                    stock = COALESCE(?, stock),
                    low_stock_threshold = CASE WHEN ? THEN ? ELSE low_stock_threshold END
                WHERE id = ?
                """,
                (name, price_cents, stock, int(set_threshold), low_stock_threshold, product_id),
            )
        return self.get_product(product_id)

    def reserve_stock(self, items: list[tuple[str, int]]) -> bool:
        """Reserva todos os itens ou nenhum."""
        with self.conn:
            for product_id, quantity in items:
                updated = self.conn.execute(
                    "UPDATE products SET stock = stock - ? WHERE id = ? AND stock >= ?",
                    (quantity, product_id, quantity),
                )
                if updated.rowcount == 0:
                    self.conn.rollback()
                    return False
        return True

    def mark_processed(self, event_id: str) -> bool:
        """Retorna False se o evento já foi processado."""
        with self.conn:
            inserted = self.conn.execute(
                "INSERT OR IGNORE INTO processed_events (event_id) VALUES (?)", (event_id,)
            )
        return inserted.rowcount == 1
