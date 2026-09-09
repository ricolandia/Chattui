"""Salva o resultado de cada chamada de ferramenta como uma nota .md.

Isso cria um arquivo por busca/consulta em NOTES_DIR — serve tanto de
histórico legível quanto de fonte pronta pra indexar no RAG (rag.py).
"""

from __future__ import annotations

import re
import time
from pathlib import Path


def _slugify(text: str, max_len: int = 40) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:max_len].strip("-") or "nota"


def save_tool_result(notes_dir: Path, tool_name: str, arguments: dict, result: str) -> Path:
    notes_dir.mkdir(parents=True, exist_ok=True)
    # microssegundos no timestamp: o laço de tool calling roda em segundos e
    # duas chamadas iguais no mesmo segundo não podem sobrescrever uma à outra
    ts = time.strftime("%Y%m%d-%H%M%S")
    micro = time.time_ns() % 1_000_000
    main_arg = next(iter(arguments.values()), "") if arguments else ""
    slug = _slugify(str(main_arg)) if main_arg else tool_name
    path = notes_dir / f"{ts}_{micro:06d}_{tool_name}_{slug}.md"

    args_line = ", ".join(f"{k}={v!r}" for k, v in arguments.items())
    front_matter = (
        f"---\n"
        f"tool: {tool_name}\n"
        f"arguments: {args_line}\n"
        f"created_at: {ts}\n"
        f"---\n\n"
    )
    path.write_text(front_matter + result, encoding="utf-8")
    return path


_BAD_PREFIXES = ("[erro", "nenhum resultado encontrado", "comando desconhecido", "página carregada, mas sem texto")


def is_indexable(result: str, min_chars: int = 40) -> bool:
    """Filtra resultados vazios/de erro pra não sujar o índice do RAG."""
    if not result or len(result.strip()) < min_chars:
        return False
    return not result.strip().lower().startswith(_BAD_PREFIXES)
