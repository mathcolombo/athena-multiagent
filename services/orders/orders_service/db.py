import json
import sqlite3
from uuid import uuid4

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    cart_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    items TEXT NOT NULL,
    total_cents INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    rejection_reason TEXT
);
CREATE TABLE IF NOT EXISTS processed_events (event_id TEXT PRIMARY KEY);
"""


class OrdersDb:
    def __init__(self, path: str) -> None:
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def create_order(
        self, cart_id: str, customer_id: str, items: list[dict], total_cents: int
    ) -> str:
        order_id = str(uuid4())
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO orders (id, cart_id, customer_id, items, total_cents)
                VALUES (?, ?, ?, ?, ?)
                """,
                (order_id, cart_id, customer_id, json.dumps(items), total_cents),
            )
        return order_id

    def get_order(self, order_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        return self._to_dict(row) if row is not None else None

    def list_orders(self, customer_id: str | None = None) -> list[dict]:
        if customer_id is None:
            rows = self.conn.execute("SELECT * FROM orders").fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM orders WHERE customer_id = ?", (customer_id,)
            ).fetchall()
        return [self._to_dict(row) for row in rows]

    def resolve_pending(
        self, order_id: str, status: str, rejection_reason: str | None = None
    ) -> bool:
        with self.conn:
            updated = self.conn.execute(
                """
                UPDATE orders SET status = ?, rejection_reason = ?
                WHERE id = ? AND status = 'PENDING'
                """,
                (status, rejection_reason, order_id),
            )
        return updated.rowcount == 1

    def mark_processed(self, event_id: str) -> bool:
        """Retorna False se o evento já foi processado."""
        with self.conn:
            inserted = self.conn.execute(
                "INSERT OR IGNORE INTO processed_events (event_id) VALUES (?)", (event_id,)
            )
        return inserted.rowcount == 1

    @staticmethod
    def _to_dict(row: sqlite3.Row) -> dict:
        return {**dict(row), "items": json.loads(row["items"])}
