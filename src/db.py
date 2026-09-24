"""DuckDB connection helper."""

from __future__ import annotations

import duckdb

from src.config import DB_PATH


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DB_PATH), read_only=read_only)


def scalar(con: duckdb.DuckDBPyConnection, sql: str, params: list | None = None):
    """First column of the first row, or None when the query returns nothing.

    `fetchone()` is Optional-typed, and unpacking it directly is what makes
    type checkers complain at every call site.
    """
    row = con.execute(sql, params or []).fetchone()
    return row[0] if row else None
