# Local Ollama Text-to-SQL Chatbot

Terminal-only Natural Language → SQL → database → result → answer chatbot. It uses local Ollama (`qwen2.5:7b` by default), SQLAlchemy, and SQLite—no cloud service or web UI.

1. Run `ollama pull qwen2.5:7b`. The app starts the local Ollama server automatically when needed.
2. Run `pip install -r requirements.txt`.
3. Optionally copy `.env.example` to `.env` to change the model, host, or database URL.
4. Start with `python main.py`, then choose to load a dataset file or open an existing table. You can also use `python main.py --file data/orders.csv` as a shortcut.

CSV, XLSX, and Parquet are supported. Safe lower-case column names are generated when the table is created. Each question visibly follows: generated SQL → validation → SQLAlchemy execution → result → Ollama explanation.
