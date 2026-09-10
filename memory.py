"""Memória de longo prazo — fatos que persistem entre conversas.

Separado do histórico de conversas de propósito: histórico é "o que foi dito",
memória é "o que deve ser lembrado sempre". É reinjetada como system message
em toda chamada à API, então o orçamento de caracteres existe pra não recriar
o mesmo problema de consumo de tokens que motivou este projeto.

Com um `Embedder` configurado, o `add_semantic` faz **upsert**: um fato
parecido com um já salvo (cosseno ≥ limiar) substitui o antigo em vez de
empilhar uma duplicata semântica. Sem embedder, cai no `add` simples.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from embeddings import Embedder, cosine, from_blob, to_blob

MAX_MEMORY_CHARS = 2000  # orçamento de contexto por chamada


class MemoryStore:
    def __init__(self, db_path: Path, embedder: Embedder | None = None, limiar: float = 0.90):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                created_at REAL NOT NULL
            )"""
        )
        try:
            self.conn.execute("ALTER TABLE memory ADD COLUMN embedding BLOB")
        except sqlite3.OperationalError:
            pass  # coluna já existe
        self.conn.commit()
        self.embedder = embedder
        self.limiar = float(limiar)

    def add(self, content: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO memory (content, created_at) VALUES (?, ?)",
            (content.strip(), time.time()),
        )
        self.conn.commit()
        return cur.lastrowid

    async def add_semantic(self, content: str) -> tuple[int, str, str | None]:
        """Insere ou atualiza (upsert) usando embeddings.

        Retorna (id, ação, texto_antigo) com ação em {"inserted", "updated"}.
        """
        if self.embedder is None:
            return self.add(content), "inserted", None
        content = content.strip()
        vec = (await self.embedder.embed([content]))[0]
        rows = list(self.conn.execute("SELECT id, content, embedding FROM memory ORDER BY id ASC"))
        # backfill preguiçoso: fatos antigos sem embedding ganham um agora
        missing = [(rid, text) for rid, text, blob in rows if not blob]
        if missing:
            vecs = await self.embedder.embed([text for _, text in missing])
            for (rid, _text), emb in zip(missing, vecs):
                self.conn.execute("UPDATE memory SET embedding = ? WHERE id = ?", (to_blob(emb), rid))
            self.conn.commit()
            rows = list(self.conn.execute("SELECT id, content, embedding FROM memory ORDER BY id ASC"))
        best_id: int | None = None
        best_sim = -1.0
        best_text = ""
        for rid, text, blob in rows:
            sim = cosine(vec, from_blob(blob))
            if sim > best_sim:
                best_sim, best_id, best_text = sim, rid, text
        if best_id is not None and best_sim >= self.limiar:
            self.conn.execute(
                "UPDATE memory SET content = ?, embedding = ? WHERE id = ?",
                (content, to_blob(vec), best_id),
            )
            self.conn.commit()
            return best_id, "updated", best_text
        cur = self.conn.execute(
            "INSERT INTO memory (content, embedding, created_at) VALUES (?, ?, ?)",
            (content, to_blob(vec), time.time()),
        )
        self.conn.commit()
        return cur.lastrowid, "inserted", None

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
