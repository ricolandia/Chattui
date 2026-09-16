"""Plugin de busca/leitura no Trilium pro chattui (ETAPI).

Complementa o trilium_note.py (que cria): este BATE-PRONTO busca notas por
texto e lê o conteúdo de uma nota específica. O modelo pode encadear:
primeiro `buscar_trilium query=...` (recebe IDs), depois
`buscar_trilium note_id=...` pra ler o conteúdo.

Fica em plugins/ (pasta do projeto); pra desativar, renomeie começando
com "_". Requer: requests + envs TRILIUM_URL e TRILIUM_TOKEN (mesmas do
trilium_note.py; veja env.example).
"""

from __future__ import annotations

import html as html_mod
import os
import re
from html.parser import HTMLParser

MAX_CONTENT_CHARS = 6000


def _strip_html(raw: str) -> str:
    """HTML → texto puro usando só stdlib (notas tipo 'text' do Trilium
    guardam HTML). Tenta bs4 se estiver disponível, senão HTMLParser."""

    class _TextExtractor(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.parts: list[str] = []
            self._skip = 0

        def handle_starttag(self, tag, attrs) -> None:
            if tag in ("script", "style"):
                self._skip += 1
            if tag in ("p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"):
                self.parts.append("\n")

        def handle_endtag(self, tag) -> None:
            if tag in ("script", "style") and self._skip:
                self._skip -= 1

        def handle_data(self, data) -> None:
            if not self._skip:
                self.parts.append(data)

    try:
        from bs4 import BeautifulSoup  # type: ignore[import-not-found]
        text = BeautifulSoup(raw, "lxml").get_text("\n")
    except Exception:  # noqa: BLE001 — sem bs4/lxml, cai no HTMLParser
        parser = _TextExtractor()
        try:
            parser.feed(raw)
        except Exception:  # noqa: BLE001
            return re.sub(r"<[^>]+>", " ", raw)
        text = "".join(parser.parts)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    text = html_mod.unescape("\n".join(lines))
    return re.sub(r"\n{3,}", "\n\n", text)


def _get(path: str, params: dict | None = None, timeout: int = 20) -> str:
    import requests

    url = os.getenv("TRILIUM_URL", "")
    token = os.getenv("TRILIUM_TOKEN", "")
    if not url or not token:
        return "[erro] TRILIUM_URL e/ou TRILIUM_TOKEN não configurados (variáveis de ambiente)."
    headers = {"Authorization": token}
    resp = requests.get(url.rstrip("/") + path, params=params, headers=headers, timeout=timeout)
    if resp.status_code != 200:
        return f"[erro {resp.status_code}] {resp.text[:300]}"
    return resp.text


TOOL_SCHEMA = {
    "name": "buscar_trilium",
    "description": (
        "Busca notas no Trilium (a base de anotações do usuário) por texto E/OU lê o "
        "conteúdo de uma nota por ID. Use quando ele perguntar 'o que eu anotei sobre X', "
        "'tem algo no Trilium sobre Y', ou quiser recuperar uma nota. Primeiro busque "
        "(query) pra descobrir os IDs, depois leia com note_id."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "termos de busca no título/conteúdo das notas"},
            "note_id": {"type": "string", "description": "ID de uma nota pra ler o conteúdo dela direto"},
            "top": {"type": "integer", "description": "quantos resultados na busca (padrão 5)"},
        },
        "required": [],
    },
}


def run(query: str = "", note_id: str = "", top: int = 5) -> str:
    import json

    if not (query.strip() or note_id.strip()):
        return "[erro] informe query (buscar) ou note_id (ler nota)."

    if note_id.strip():
        body = _get(f"/etapi/notes/{note_id.strip()}/content")
        if body.startswith("[erro"):
            return body
        text = _strip_html(body).strip()
        if not text:
            return f"[nota {note_id}] está vazia ou sem texto extraível."
        if len(text) > MAX_CONTENT_CHARS:
            text = text[:MAX_CONTENT_CHARS] + f"\n\n[...conteúdo truncado em {MAX_CONTENT_CHARS} caracteres...]"
        return f"[nota {note_id}]\n{text}"

    raw = _get("/etapi/notes", params={"search": query.strip(), "limit": max(1, int(top or 5))})
    if raw.startswith("[erro"):
        return raw
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return f"[erro] resposta inesperada da busca:\n{raw[:300]}"
    items = data.get("results") or []
    if not items:
        return "Nenhuma nota encontrada no Trilium para essa busca."
    lines = [f"{len(items)} nota(s) encontrada(s) — use 'buscar_trilium' com o note_id pra ler o conteúdo:\n"]
    for it in items[: max(1, int(top or 5))]:
        nid = it.get("noteId") or it.get("id") or "?"
        title = (it.get("title") or "(sem título)").strip()
        lines.append(f"- {title}  →  note_id: {nid}")
    return "\n".join(lines)
