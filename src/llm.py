"""Dependency-free client for a local Ollama server."""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

class OllamaError(RuntimeError): pass

class OllamaClient:
    def __init__(self, host: str, model: str): self.host, self.model = host.rstrip("/"), model
    def _request(self, endpoint: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(f"{self.host}{endpoint}", data=data, headers={"Content-Type": "application/json"}, method="POST" if data else "GET")
        try:
            with urlopen(request, timeout=120) as response: return json.loads(response.read().decode())
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise OllamaError("Ollama is not available. Please make sure Ollama is running.") from exc

    def _find_executable(self) -> str | None:
        """Find Ollama without depending on the PowerShell PATH setting."""
        candidates = [os.getenv("OLLAMA_EXECUTABLE")]
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            candidates.append(str(Path(local_app_data) / "Programs" / "Ollama" / "ollama.exe"))
        candidates.append(shutil.which("ollama"))
        return next((item for item in candidates if item and Path(item).is_file()), None)

    def ensure_running(self) -> None:
        """Launch the local server if it is not already reachable."""
        try:
            self._request("/api/tags")
            return
        except OllamaError:
            pass
        executable = self._find_executable()
        if not executable:
            raise OllamaError("Ollama is not available and its executable was not found. Install Ollama or set OLLAMA_EXECUTABLE.")
        try:
            subprocess.Popen(
                [executable, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            raise OllamaError("Ollama could not be started automatically. Run: ollama serve") from exc
        for _ in range(10):
            time.sleep(1)
            try:
                self._request("/api/tags")
                return
            except OllamaError:
                continue
        raise OllamaError("Ollama did not start within 10 seconds. Run: ollama serve")

    def verify(self) -> None:
        self.ensure_running()
        names = {model.get("name", "") for model in self._request("/api/tags").get("models", [])}
        if self.model not in names: raise OllamaError(f"Model {self.model} is not installed. Run: ollama pull {self.model}")
    def generate(self, prompt: str) -> str:
        result = self._request("/api/generate", {"model": self.model, "prompt": prompt, "stream": False}).get("response", "").strip()
        if not result: raise OllamaError("Ollama returned an empty response.")
        return result

def generate_sql(question: str, schema: str, history: list[dict[str, str]], client: OllamaClient) -> str:
    conversation = "\n".join(f"User: {item['question']}\nSQL: {item['sql']}" for item in history[-5:]) or "No previous conversation."
    prompt = f"""You are an expert Text-to-SQL system. Convert the user's question into SQL.
Database dialect: SQLite

{schema}

Conversation history:
{conversation}

User question: {question}

Rules:
1. Use ONLY tables and columns in the schema.
2. Generate SQLite-compatible SQL.
3. Only SELECT or WITH ... SELECT is allowed.
4. INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, ATTACH, DETACH, and PRAGMA are forbidden.
5. Generate exactly one statement.
6. Do not include Markdown, explanations, or code fences.
7. Return ONLY the SQL query.
"""
    return client.generate(prompt)

def generate_answer(question: str, sql: str, result_csv: str, client: OllamaClient) -> str:
    return client.generate(f"""Answer the user's question accurately using only this SQL result. Be concise. If no rows were returned, say so. Do not invent facts.
Question: {question}
SQL used: {sql}
Result (CSV):
{result_csv}""")
