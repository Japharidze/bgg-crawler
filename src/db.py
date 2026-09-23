"""DuckDB connection helper."""

from __future__ import annotations

import duckdb

from src.config import DB_PATH


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DB_PATH), read_only=read_only)
