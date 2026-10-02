"""Хранение лекарств пользователей в SQLite."""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

DB_PATH = "pharmacy.db"


@dataclass
class Medicine:
    id: int
    name: str
    description: str
    expiry_date: date
    quantity: int

    def days_left(self, today: date) -> int:
        return (self.expiry_date - today).days


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS medicines (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                name        TEXT    NOT NULL,
                description TEXT,
                expiry_date DATE,
                quantity    INTEGER,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_medicines_user ON medicines (user_id)"
        )


def _to_medicine(row) -> Medicine:
    medicine_id, name, description, expiry_date, quantity = row
    return Medicine(
        id=medicine_id,
        name=name,
        description=description or "",
        expiry_date=date.fromisoformat(expiry_date),
        quantity=quantity,
    )


def add_medicine(user_id: int, name: str, description: str,
                 expiry_date: date, quantity: int) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO medicines (user_id, name, description, expiry_date, quantity)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, name, description, expiry_date.isoformat(), quantity),
        )


def get_medicines(user_id: int) -> List[Medicine]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, name, description, expiry_date, quantity
            FROM medicines
            WHERE user_id = ?
            ORDER BY expiry_date
            """,
            (user_id,),
        ).fetchall()
    return [_to_medicine(row) for row in rows]


def get_medicine(user_id: int, medicine_id: int) -> Optional[Medicine]:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT id, name, description, expiry_date, quantity
            FROM medicines
            WHERE id = ? AND user_id = ?
            """,
            (medicine_id, user_id),
        ).fetchone()
    return _to_medicine(row) if row else None


def delete_medicine(user_id: int, medicine_id: int) -> bool:
    with connect() as conn:
        cursor = conn.execute(
            "DELETE FROM medicines WHERE id = ? AND user_id = ?",
            (medicine_id, user_id),
        )
    return cursor.rowcount > 0


def delete_expired(user_id: int, today: date) -> int:
    with connect() as conn:
        cursor = conn.execute(
            "DELETE FROM medicines WHERE user_id = ? AND expiry_date < ?",
            (user_id, today.isoformat()),
        )
    return cursor.rowcount
