"""Plugins = scripts Python simples, sem framework.

Cada arquivo .py em plugins/ (pasta do projeto; ou CHATTUI_PLUGINS_DIR)
deve expor:

    TOOL_SCHEMA = {
        "name": "nome_da_ferramenta",
        "description": "o que ela faz, em uma frase",
        "parameters": {  # JSON Schema dos argumentos
            "type": "object",
            "properties": {...},
            "required": [...],
        },
    }

    def run(**kwargs) -> str:
        ...
        return "resultado em texto pro modelo ler"

`run` pode ser síncrona ou `async def`; funções síncronas rodam em thread
própria (não bloqueiam a interface). Isso é o suficiente pra plugar
scripts que já existem (ex: chamar trilium_post.py, o agendador do
Radicale, etc.) só envolvendo a lógica existente numa função `run`.
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
from pathlib import Path
from typing import Any, Callable


class PluginManager:
    def __init__(self, plugins_dir: Path):
        self.plugins_dir = plugins_dir
        self.plugins: dict[str, dict[str, Any]] = {}
        self.load_errors: list[str] = []
        self._load()

    def _load(self) -> None:
        if not self.plugins_dir.exists():
            return
        for py_file in sorted(self.plugins_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
                module = importlib.util.module_from_spec(spec)
                assert spec.loader is not None
                spec.loader.exec_module(module)
                schema = getattr(module, "TOOL_SCHEMA", None)
                run_fn: Callable | None = getattr(module, "run", None)
                if schema is None or run_fn is None:
                    self.load_errors.append(f"{py_file.name}: falta TOOL_SCHEMA ou run()")
                    continue
                self.plugins[schema["name"]] = {
                    "schema": schema,
                    "run": run_fn,
                    "file": py_file.name,
                    "destructive": bool(getattr(module, "DESTRUCTIVE", False)),
                }
            except Exception as exc:  # noqa: BLE001 — plugin de terceiro, qualquer erro vira aviso
                self.load_errors.append(f"{py_file.name}: {exc}")

    def is_destructive(self, name: str) -> bool:
        plugin = self.plugins.get(name)
        return bool(plugin and plugin.get("destructive"))

    def get_tool_schemas(self) -> list[dict]:
        return [{"type": "function", "function": p["schema"]} for p in self.plugins.values()]

    async def run_tool(self, name: str, arguments: dict) -> str:
        plugin = self.plugins.get(name)
        if plugin is None:
            return f"[erro] plugin '{name}' não encontrado"
        fn = plugin["run"]
        try:
            if inspect.iscoroutinefunction(fn):
                result = await fn(**arguments)
            else:
                # plugin síncrono roda em thread própria — não bloqueia a UI
                result = await asyncio.to_thread(fn, **arguments)
            return str(result)
        except Exception as exc:  # noqa: BLE001
            return f"[erro ao rodar '{name}'] {exc}"
