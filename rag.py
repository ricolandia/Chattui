"""RAG minimalista, sem chromadb/langchain e sem segurar a base na RAM.

Embeddings vêm de qualquer endpoint OpenAI-compatível (na prática, o
endpoint /embeddings do Ollama servindo nomic-embed-text ou similar).
Os vetores ficam guardados como BLOB no SQLite (fonte da verdade) e a
matriz normalizada mora num arquivo .npy lido via np.memmap: o SO faz
page-in sob demanda durante a busca e descarta sob pressão de memória —
idle fica com RAM ~0 extra, mesmo com dezenas de milhares de chunks.

Arquivos (ao lado do .db):
  rag.db.matrix.npy  — matriz float32 normalizada (linha i ↔ ids[i])
  rag.db.ids.npy     — ids (int64) alinhados às linhas
  rag.db.meta.json   — {count, max_id, dims} pra saber se está atualizado
Apague os três (ou só o .meta/.npy) pra forçar rebuild do zero.

Dedupe: chunks repetidos da MESMA fonte na MESMA biblioteca não são
re-indexados (hash SHA-1 por chunk em text_hash). Bibliotecas (lib) são
coleções organizadas por tema/projeto: cada chunk pertence a uma lib
(default 'geral'); a busca pode filtrar por lib ou varrer todas.
numpy é importado só dentro dos métodos.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path

import httpx

_MAX_PLACEHOLDERS = 900  # limite conservador de variáveis SQLite numa query


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()


def _chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= n:
            break
        start = end - overlap
    return chunks


class RagStore:
    def __init__(self, db_path: Path, api_base: str, embedding_model: str, api_key: str | None = None):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS rag_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                chunk TEXT NOT NULL,
                embedding BLOB NOT NULL,
                lib TEXT NOT NULL DEFAULT 'geral',
                text_hash TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL
            )"""
        )
        for column in (
            "ALTER TABLE rag_chunks ADD COLUMN lib TEXT NOT NULL DEFAULT 'geral'",
            "ALTER TABLE rag_chunks ADD COLUMN text_hash TEXT NOT NULL DEFAULT ''",
        ):
            try:
                self.conn.execute(column)
            except sqlite3.OperationalError:
                pass  # coluna já existe (banco novo ou migrado)
        self.conn.execute("DROP INDEX IF EXISTS idx_rag_source_hash")
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_rag_lib_source_hash ON rag_chunks (lib, source, text_hash)"
        )
        self.conn.commit()
        self.api_base = api_base.rstrip("/")
        self.embedding_model = embedding_model
        self.api_key = api_key
        self._lock = asyncio.Lock()
        stem = db_path.name  # ex.: "rag.db"
        self._matrix_file = db_path.with_name(stem + ".matrix.npy")
        self._ids_file = db_path.with_name(stem + ".ids.npy")
        self._meta_file = db_path.with_name(stem + ".meta.json")
        self._ids_cache: list[int] | None = None
        self._dims_cache: int | None = None

    # ------------------------------------------------------ arquivos

    def _clean_files(self) -> None:
        for path in (self._matrix_file, self._ids_file, self._meta_file):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        self._ids_cache = None
        self._dims_cache = None

    def _read_meta(self) -> dict | None:
        try:
            return json.loads(self._meta_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _write_meta(self, count: int, max_id: int, dims: int) -> None:
        tmp = self._meta_file.with_name(self._meta_file.name + ".tmp")
        tmp.write_text(
            json.dumps({"count": count, "max_id": max_id, "dims": dims}), encoding="utf-8"
        )
        os.replace(tmp, self._meta_file)

    def _valid_stats(self) -> tuple[int, int]:
        """(count, max_id) das linhas com BLOB de tamanho plausível (múltiplo de 4)."""
        row = self.conn.execute(
            "SELECT COUNT(*), COALESCE(MAX(id), 0) FROM rag_chunks "
            "WHERE embedding IS NOT NULL AND length(embedding) > 0 AND length(embedding) % 4 = 0"
        ).fetchone()
        return (int(row[0]), int(row[1]))

    def _rebuild_files(self) -> int:
        """Reconstrói .npy/.ids/.meta varrendo o SQLite linha a linha
        (streaming — não monta a matriz inteira em RAM). Retorna nº de linhas."""
        import numpy as np

        self.conn.row_factory = None
        rows = self.conn.execute(
            "SELECT id, embedding FROM rag_chunks "
            "WHERE embedding IS NOT NULL AND length(embedding) > 0 AND length(embedding) % 4 = 0 "
            "ORDER BY id"
        ).fetchall()
        if not rows:
            self._clean_files()
            return 0
        dims = int(len(rows[0][1]) / 4)
        ids: list[int] = []
        vectors: list[object] = []
        for rid, blob in rows:
            vec = np.frombuffer(blob, dtype=np.float32)
            if vec.size != dims:
                continue  # dims diferentes (modelo mudou no meio) — descarta a linha
            ids.append(int(rid))
            vectors.append(vec)
        if not ids:
            self._clean_files()
            return 0
        tmp = self._matrix_file.with_name(self._matrix_file.name + ".tmp")
        with open(tmp, "wb") as fh:
            matrix = np.empty((len(ids), dims), dtype=np.float32)
            for i, vec in enumerate(vectors):
                norm = np.linalg.norm(vec)
                matrix[i] = vec / (norm + 1e-8)
            np.save(fh, matrix)
        os.replace(tmp, self._matrix_file)
        self._save_ids(ids)
        self._write_meta(len(ids), ids[-1], dims)
        self._ids_cache = ids
        self._dims_cache = dims
        return len(ids)

    def _save_ids(self, ids: list[int]) -> None:
        import numpy as np

        tmp = self._ids_file.with_name(self._ids_file.name + ".tmp")
        with open(tmp, "wb") as fh:
            np.save(fh, np.array(ids, dtype=np.int64))
        os.replace(tmp, self._ids_file)

    def _append_files(self, new_ids: list[int], norms: list[object], dims: int) -> None:
        """Anexa linhas novas à matriz existente (sem rebuild total)."""
        import numpy as np

        if not self._matrix_file.exists() or not self._ids_file.exists():
            return  # base nova/sem arquivo — o próximo acesso reconstrói tudo
        meta = self._read_meta()
        if meta is None:
            self._matrix_file.unlink(missing_ok=True)
            return
        if meta["dims"] != dims:
            raise RuntimeError(
                f"Modelo de embedding mudou ({meta['dims']} → {dims} dims). "
                f"Apague {self._matrix_file.name} (e o .meta) pra reconstruir do zero."
            )
        old_count = int(meta["count"])
        new_count = old_count + len(new_ids)
        with open(self._matrix_file, "r+b") as fh:
            fh.seek(0, os.SEEK_END)
            fh.truncate(new_count * dims * 4)
        mm = np.memmap(self._matrix_file, dtype=np.float32, mode="r+", shape=(new_count, dims))
        try:
            for j, vec in enumerate(norms):
                mm[old_count + j] = vec
            mm.flush()
        finally:
            del mm
        ids_old = [int(i) for i in np.load(self._ids_file)] if self._ids_file.exists() else []
        self._save_ids(ids_old + [int(i) for i in new_ids])
        self._write_meta(new_count, new_ids[-1], dims)
        self._ids_cache = None  # recarregado no próximo uso

    def _ensure_matrix(self) -> tuple[int, int]:
        """Garante .npy/.ids atuais vs banco. Retorna (count, dims)."""
        import numpy as np

        count, max_id = self._valid_stats()
        if count == 0:
            self._clean_files()
            return (0, 0)
        meta = self._read_meta()
        if (
            meta is not None
            and meta["count"] == count
            and meta["max_id"] == max_id
            and self._matrix_file.exists()
            and self._ids_file.exists()
        ):
            self._ids_cache = [int(i) for i in np.load(self._ids_file)]
            self._dims_cache = int(meta["dims"])
            return (count, int(meta["dims"]))
        rebuilt = self._rebuild_files()
        if not rebuilt:
            return (0, 0)
        meta = self._read_meta()
        return (count, int(meta["dims"]) if meta else 0)

    def matrix_info(self) -> dict | None:
        """Info pra exibir em /rag_stats: tamanho em disco + dims (ou None)."""
        try:
            size = self._matrix_file.stat().st_size if self._matrix_file.exists() else 0
        except OSError:
            size = 0
        if not size:
            return None
        meta = self._read_meta()
        return {"mb": size / 1_000_000, "dims": meta["dims"] if meta else 0}

    # ----------------------------------------------------- embeddings

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.api_base}/embeddings",
                json={"model": self.embedding_model, "input": texts},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            return [d["embedding"] for d in data["data"]]

    # --------------------------------------------------------- adição

    async def add_file(self, path: Path, lib: str = "geral") -> int:
        async with self._lock:
            return await self._add_file_locked(path, lib)

    async def _add_file_locked(self, path: Path, lib: str) -> int:
        import numpy as np

        lib = (lib or "geral").strip() or "geral"
        text = path.read_text(errors="ignore")
        chunks = _chunk_text(text)
        if not chunks:
            return 0
        hashes = [_sha1(c) for c in chunks]
        # dedupe por lib+fonte: só embeda/insere o que ainda não existe AQUI
        existing: set[str] = set()
        for start in range(0, len(hashes), _MAX_PLACEHOLDERS):
            batch_h = hashes[start:start + _MAX_PLACEHOLDERS]
            ph = ",".join("?" * len(batch_h))
            rows = self.conn.execute(
                f"SELECT text_hash FROM rag_chunks WHERE lib = ? AND source = ? AND text_hash IN ({ph})",
                [lib, str(path), *batch_h],
            ).fetchall()
            existing.update(r[0] for r in rows)
        fresh = [(c, h) for c, h in zip(chunks, hashes) if h not in existing]
        if not fresh:
            return 0
        embeddings = await self._embed([c for c, _ in fresh])
        vectors = [np.array(emb, dtype=np.float32) for emb in embeddings]
        dims = vectors[0].size
        if self._matrix_file.exists():
            meta = self._read_meta()
            if meta is not None and meta["dims"] != dims:
                raise RuntimeError(
                    f"Modelo de embedding mudou ({meta['dims']} → {dims} dims). "
                    f"Apague {self._matrix_file.name} (e o .meta) pra reconstruir do zero."
                )
        norms = []
        for vec in vectors:
            norm = np.linalg.norm(vec)
            norms.append(vec / (norm + 1e-8))
        now = time.time()
        new_ids: list[int] = []
        for (chunk, chunk_hash), vec in zip(fresh, vectors):
            cur = self.conn.execute(
                "INSERT INTO rag_chunks (source, chunk, embedding, lib, text_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (str(path), chunk, vec.tobytes(), lib, chunk_hash, now),
            )
            new_ids.append(int(cur.lastrowid))
        self.conn.commit()
        if new_ids:
            count, max_id = self._valid_stats()
            meta = self._read_meta()
            up_to_date = (
                meta is not None
                and meta["count"] == count
                and meta["max_id"] == max_id
                and self._matrix_file.exists()
                and self._ids_file.exists()
            )
            if up_to_date:
                try:
                    self._append_files(new_ids, norms, dims)
                except RuntimeError:
                    raise
                except Exception:  # noqa: BLE001 — arquivo em estado estranho: rebuild depois
                    self._clean_files()
            else:
                # primeira base (ou arquivos apagados/atrasados): reconstrói tudo
                self._ensure_matrix()
        self._ids_cache = None
        return len(new_ids)

    # --------------------------------------------------------- busca

    async def search(self, query: str, top_k: int = 4, lib: str | None = None) -> list[tuple[str, str, float]]:
        """Busca semântica. lib=None busca em todas as bibliotecas."""
        async with self._lock:
            import numpy as np

            count, dims = self._ensure_matrix()
            if not count:
                return []
            if lib is not None and lib.strip():
                lib_rows = self.conn.execute(
                    "SELECT id FROM rag_chunks WHERE lib = ?", (lib.strip(),)
                ).fetchall()
                if not lib_rows:
                    return []
                lib_ids = {int(r[0]) for r in lib_rows}
            else:
                lib_ids = None
            query_emb = (await self._embed([query]))[0]
            q = np.array(query_emb, dtype=np.float32)
            q = q / (np.linalg.norm(q) + 1e-8)
            mm = np.load(self._matrix_file, mmap_mode="r")
            try:
                sims = np.asarray(mm @ q)
            finally:
                del mm
            if lib_ids is not None:
                # filtra os que não pertencem à lib ativa antes de ranquear
                mask = np.array([int(i) in lib_ids for i in self._ids_cache], dtype=bool)
                if not mask.any():
                    return []
                sims = np.where(mask, sims, -np.inf)
            top_idx = np.argsort(-sims)[:top_k]
            top_idx = [int(i) for i in top_idx]
            scores = [float(sims[i]) for i in top_idx]
            # remove os mascarados (-inf) que podem ter entrado na janela
            pairs = [(i, sc) for i, sc in zip(top_idx, scores) if np.isfinite(sc)]
            if not pairs:
                return []
            ids = [self._ids_cache[i] for i, _ in pairs]
            scores = [sc for _, sc in pairs]
            rows = self.conn.execute(
                f"SELECT id, source, chunk FROM rag_chunks WHERE id IN ({','.join('?' * len(ids))})",
                ids,
            ).fetchall()
            by_id = {int(r[0]): (r[1], r[2]) for r in rows}
            out: list[tuple[str, str, float]] = []
            for note_id, score in zip(ids, scores):
                pair = by_id.get(note_id)
                if pair:
                    out.append((pair[0], pair[1], score))
            return out

    def list_libs(self) -> list[tuple[str, int]]:
        """Bibliotecas com contagem de trechos (ordem: mais cheia primeiro)."""
        rows = self.conn.execute(
            "SELECT lib, COUNT(*) AS c FROM rag_chunks GROUP BY lib ORDER BY c DESC, lib ASC"
        ).fetchall()
        return [(str(r[0]), int(r[1])) for r in rows]

    def list_sources(self, lib: str) -> list[str]:
        """Fontes (arquivos) indexadas numa biblioteca."""
        rows = self.conn.execute(
            "SELECT DISTINCT source FROM rag_chunks WHERE lib = ? ORDER BY source", (lib,)
        ).fetchall()
        return [str(r[0]) for r in rows]

    def stats(self) -> tuple[int, set[str]]:
        self.conn.row_factory = sqlite3.Row
        count_row = self.conn.execute("SELECT COUNT(*) AS c FROM rag_chunks").fetchone()
        sources = {r["source"] for r in self.conn.execute("SELECT DISTINCT source FROM rag_chunks")}
        return (count_row["c"] if count_row else 0), sources
