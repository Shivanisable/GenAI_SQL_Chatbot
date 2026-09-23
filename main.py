"""Terminal entry point for the local Ollama Text-to-SQL chatbot."""
from __future__ import annotations
import argparse, os, sys
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
from src.database import execute_query, get_engine, get_schema, get_table_details, get_tables, load_dataframe, table_name_from_file
from src.llm import OllamaClient, OllamaError, generate_answer, generate_sql
from src.sql_validator import SQLValidationError, normalize_sql, validate_sql

def read_dataset(file_path: Path) -> pd.DataFrame:
    if file_path.suffix.lower() == ".csv": return pd.read_csv(file_path)
    if file_path.suffix.lower() == ".xlsx": return pd.read_excel(file_path)
    if file_path.suffix.lower() == ".parquet": return pd.read_parquet(file_path)
    raise ValueError("Unsupported file type. Use CSV, XLSX, or Parquet.")

def choose_dataset(engine) -> tuple[str, str, int, int]:
    """Let a terminal user load a file or open an existing database table."""
    while True:
        print("\nChoose a dataset:")
        print("  1. Load a CSV, Excel, or Parquet file")
        print("  2. Open an existing database table")
        print("  3. Exit")
        choice = input("Select an option [1-3]: ").strip()
        if choice == "1":
            raw_path = input("Dataset file path: ").strip().strip('"')
            path = Path(raw_path)
            if not path.is_file():
                print(f"[ERROR] Dataset not found: {path}")
                continue
            try:
                frame = read_dataset(path)
                table = table_name_from_file(str(path))
                loaded = load_dataframe(frame, table, engine)
                return path.name, table, len(loaded), len(loaded.columns)
            except (ValueError, OSError, pd.errors.ParserError) as exc:
                print(f"[ERROR] Could not load dataset: {exc}")
        elif choice == "2":
            tables = get_tables(engine)
            if not tables:
                print("[ERROR] No existing tables. Load a dataset first.")
                continue
            print("\nExisting tables:")
            for number, table in enumerate(tables, start=1): print(f"  {number}. {table}")
            selection = input("Select a table number: ").strip()
            try:
                table_index = int(selection) - 1
                if table_index < 0 or table_index >= len(tables):
                    raise ValueError
                table = tables[table_index]
                rows, columns = get_table_details(engine, table)
                return f"Existing table: {table}", table, rows, columns
            except (ValueError, IndexError):
                print("[ERROR] Please enter a valid table number.")
        elif choice == "3":
            raise KeyboardInterrupt
        else:
            print("[ERROR] Please choose 1, 2, or 3.")

def ask_question(question: str, engine, active_table: str, client: OllamaClient, history: list[dict[str, str]]) -> dict:
    """Generate, display, validate, execute, and explain SQL in that order."""
    print("\nGenerating SQL...")
    # Scope every question to the dataset table supplied for this chat session.
    active_schema = get_schema(engine, [active_table])
    generated_sql = normalize_sql(generate_sql(question, active_schema, history, client))
    print("\nGenerated SQL:\n" + "-" * 60); print(generated_sql); print("-" * 60)
    print("Validating SQL...")
    sql = validate_sql(generated_sql)
    print("[OK] SQL validation passed\nExecuting query...")
    result = execute_query(sql, engine)
    print("\nQuery Result:\n" + "-" * 60); print("No rows returned." if result.empty else result.to_string(index=False)); print("-" * 60)
    print("Generating answer...")
    answer = generate_answer(question, sql, result.head(100).to_csv(index=False), client)
    print("\nAnswer:\n" + answer)
    return {"question": question, "sql": sql, "result": result, "answer": answer}

def main() -> int:
    # Some Windows terminals use cp1252. Replace unsupported LLM characters
    # rather than crashing while displaying an otherwise valid answer.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Local Ollama Text-to-SQL chatbot")
    parser.add_argument("--file", help="Optional shortcut: path to CSV, XLSX, or Parquet dataset")
    args = parser.parse_args(); load_dotenv()
    try:
        client = OllamaClient(os.getenv("OLLAMA_HOST", "http://localhost:11434"), os.getenv("OLLAMA_MODEL", "qwen2.5:7b")); client.verify()
        database_url = os.getenv("DATABASE_URL", "sqlite:///data/database.db"); engine = get_engine(database_url)
        if args.file:
            path = Path(args.file)
            if not path.is_file(): print(f"[ERROR] Dataset not found: {path}"); return 1
            frame = read_dataset(path); table = table_name_from_file(str(path)); loaded = load_dataframe(frame, table, engine)
            dataset_name, rows, columns = path.name, len(loaded), len(loaded.columns)
        else:
            dataset_name, table, rows, columns = choose_dataset(engine)
        schema = get_schema(engine, [table])
    except (OllamaError, ValueError, OSError, pd.errors.ParserError) as exc: print(f"[ERROR] {exc}"); return 1
    except KeyboardInterrupt: print("\nGoodbye!"); return 0
    print("=" * 60 + "\n             LOCAL TEXT-TO-SQL CHATBOT\n                  Powered by Ollama\n" + "=" * 60)
    print(f"\n[OK] Ollama connected\n[OK] Model: {client.model}\n[OK] Dataset loaded\n[OK] Database connected\n[OK] Schema extracted\n\nDataset : {dataset_name}\nTable   : {table}\nRows    : {rows:,}\nColumns : {columns}\nDatabase: {database_url}\n\n{schema}\n\nType 'exit' or 'quit' to close.")
    history: list[dict[str, str]] = []
    while True:
        try: question = input("\nAsk question: ").strip()
        except (EOFError, KeyboardInterrupt): print("\nGoodbye!"); break
        if question.lower() in {"exit", "quit"}: print("Goodbye!"); break
        if not question: continue
        try:
            answer = ask_question(question, engine, table, client, history); history.append({"question": answer["question"], "sql": answer["sql"]})
        except (OllamaError, SQLValidationError, ValueError) as exc: print(f"[ERROR] {exc}")
        except Exception: print("[ERROR] The query could not be completed. Check the question and try again.")
    return 0
if __name__ == "__main__": raise SystemExit(main())
