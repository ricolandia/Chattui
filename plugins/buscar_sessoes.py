"""Plugin de recall das sessões do opencode pro chattui.

Embrulha um buscar-memoria.py local via subprocess (--json): busca
lexical FTS5/BM25 no índice das conversas passadas do opencode e devolve
trechos com título/data/ID da sessão de origem.

Fica em plugins/ (pasta do projeto); pra desativar, renomeie começando
com "_". Requer só stdlib + o índice local gerado por indice-memoria.py.
Env obrigatória: CHATTUI_SCRIPTS_PY (pasta onde está o buscar-memoria.py).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

TOOL_SCHEMA = {
    "name": "buscar_sessoes",
    "description": (
        "Busca o que foi conversado/falado em sessões passadas do opencode do usuário "
        "(memória lexical das conversas). Use quando ele perguntar o que foi combinado "
        "sobre X, como algo foi feito antes, ou quiser retomar um assunto de outra sessão. "
        "Retorna trechos com título, data e ID da sessão de origem."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "termos da busca (ex: 'propostas workana', 'config trilium')"},
            "limite": {"type": "integer", "description": "quantidade de sessões retornadas (padrão 5)"},
        },
        "required": ["query"],
    },
}

_TIMEOUT_S = 60


def _script_path() -> Path | None:
    base = os.environ.get("CHATTUI_SCRIPTS_PY", "").strip()
    if not base:
        return None
    return Path(base).expanduser() / "buscar-memoria.py"


def run(query: str, limite: int = 5) -> str:
    script = _script_path()
    if script is None:
        return "[erro] env CHATTUI_SCRIPTS_PY não definida — aponte no .env pra pasta que contém o buscar-memoria.py."
    if not script.exists():
        return f"[erro] buscar-memoria.py não encontrado em {script} — ajuste CHATTUI_SCRIPTS_PY."
    query = (query or "").strip()
    if not query:
        return "[erro] informe os termos da busca."
    try:
        proc = subprocess.run(
            [sys.executable, str(script), query, "--limite", str(max(1, int(limite or 5))), "--json"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return "[erro] tempo esgotado na busca de sessões."
    except Exception as exc:  # noqa: BLE001
        return f"[erro ao rodar buscar-memoria.py] {exc}"
    if proc.returncode != 0:
        return f"[erro {proc.returncode}] {(proc.stderr or proc.stdout or '').strip()[:300]}"
    try:
        hits = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return f"[erro] saída inesperada:\n{(proc.stdout or '')[:300]}"
    if not hits:
        return "Nenhuma sessão encontrada para esses termos na memória do opencode."
    lines = [f"{len(hits)} sessão(ões) relacionada(s):\n"]
    for h in hits:
        title = (h.get("title") or "(sem título)").strip()
        data = h.get("data") or "-"
        sid = h.get("session_id") or "?"
        snippet = (h.get("snippet") or "").strip()
        lines.append(f"## {title}  [{data}]  (sessão {sid})")
        lines.append(snippet)
        lines.append("")
    return "\n".join(lines)
