"""SQLAlchemy database operations for uploaded datasets."""
from __future__ import annotations
import re
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

def get_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite:///") and not database_url.endswith(":memory:"):
        Path(database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(database_url, future=True)

def clean_column_names(frame: pd.DataFrame) -> pd.DataFrame:
    cleaned, seen = [], {}
    for original in frame.columns:
        name = re.sub(r"\s+", "_", str(original).strip().lower())
        name = re.sub(r"[^a-z0-9_]", "", name)
        name = re.sub(r"_+", "_", name).strip("_") or "column"
        if name[0].isdigit(): name = f"column_{name}"
        seen[name] = seen.get(name, 0) + 1
        cleaned.append(name if seen[name] == 1 else f"{name}_{seen[name]}")
    result = frame.copy(); result.columns = cleaned
    return result

def table_name_from_file(file_path: str) -> str:
    return clean_column_names(pd.DataFrame(columns=[Path(file_path).stem])).columns[0]

def load_dataframe(frame: pd.DataFrame, table_name: str, engine: Engine) -> pd.DataFrame:
    normalized = clean_column_names(frame)
    normalized.to_sql(table_name, engine, if_exists="replace", index=False)
    return normalized

def get_tables(engine: Engine) -> list[str]:
    return inspect(engine).get_table_names()

def get_table_details(engine: Engine, table_name: str) -> tuple[int, int]:
    """Return row and column counts for an existing inspected table."""
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        raise ValueError(f"Database table not found: {table_name}")
    safe_name = table_name.replace('"', '""')
    with engine.connect() as connection:
        rows = connection.execute(text(f'SELECT COUNT(*) FROM "{safe_name}"')).scalar_one()
    return rows, len(inspector.get_columns(table_name))

def get_schema(engine: Engine, table_names: list[str] | None = None) -> str:
    """Return the actual schema, optionally scoped to active uploaded tables."""
    inspector = inspect(engine); tables = table_names or inspector.get_table_names()
    if not tables: raise ValueError("No tables are loaded in the database.")
    available = set(inspector.get_table_names())
    missing = set(tables) - available
    if missing: raise ValueError(f"Database table not found: {', '.join(sorted(missing))}")
    sections = []
    for table in tables:
        columns = "\n".join(f"- {c['name']}: {c['type']}" for c in inspector.get_columns(table))
        sections.append(f"Table: {table}\n\nColumns:\n{columns}")
    return "Database Schema:\n\n" + "\n\n".join(sections)

def execute_query(sql: str, engine: Engine) -> pd.DataFrame:
    with engine.connect() as connection:
        return pd.read_sql_query(text(sql), connection)
