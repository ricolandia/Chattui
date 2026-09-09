"""Memória de longo prazo — fatos que persistem entre conversas.

Separado do histórico de conversas de propósito: histórico é "o que foi dito",
memória é "o que deve ser lembrado sempre". É reinjetada como system message
em toda chamada à API, então o orçamento de caracteres existe pra não recriar
o mesmo problema de consumo de tokens que motivou este projeto.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

MAX_MEMORY_CHARS = 2000  # orçamento de contexto por chamada


class MemoryStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                created_at REAL NOT NULL
            )"""
        )
        self.conn.commit()

    def add(self, content: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO memory (content, created_at) VALUES (?, ?)",
            (content.strip(), time.time()),
        )
        self.conn.commit()
        return cur.lastrowid

    def list(self) -> list[sqlite3.Row]:
        self.conn.row_factory = sqlite3.Row
        return list(self.conn.execute("SELECT * FROM memory ORDER BY id ASC"))

    def delete(self, mem_id: int) -> None:
        self.conn.execute("DELETE FROM memory WHERE id = ?", (mem_id,))
        self.conn.commit()

    def as_system_prompt(self) -> str | None:
        """Monta o system message com as memórias, das mais recentes até
        estourar MAX_MEMORY_CHARS (corta as mais antigas primeiro)."""
        rows = self.list()
        if not rows:
            return None
        lines: list[str] = []
        total = 0
        for row in reversed(rows):
            line = f"- {row['content']}"
            if total + len(line) > MAX_MEMORY_CHARS:
                break
            lines.append(line)
            total += len(line)
        lines.reverse()
        if not lines:
            return None
        return "Fatos que você deve lembrar sobre o usuário e o contexto:\n" + "\n".join(lines)
