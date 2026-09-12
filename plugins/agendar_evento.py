"""Plugin de agenda pro chattui (Radicale/CalDAV) — embrulha um agendar.py
existente via subprocess, sem duplicar a lógica CalDAV.

Fica em plugins/ (pasta do projeto); pra desativar, renomeie começando
com "_". Requer: requests instalado no ambiente (mesmo do script).

Envs: CHATTUI_SCRIPTS_PY (obrigatória — pasta onde está o agendar.py) e,
opcionalmente, RADICALE_URL / RADICALE_USER / RADICALE_PASS (defaults do
próprio agendar.py).
"""

from __future__ import annotations

# Ferramenta que GRAVA na agenda (CalDAV) — o chattui pede confirmação antes.
DESTRUCTIVE = True

import datetime
import os
import subprocess
import sys
from pathlib import Path

TOOL_SCHEMA = {
    "name": "agendar_evento",
    "description": (
        "Cria um evento na agenda do usuário (CalDAV/Radicale — sincronizada com o "
        "calendário dele) ou lista os próximos 90 dias. Use quando ele pedir pra "
        "agendar/lembrar de algo com data e hora. Datas SEMPRE no formato "
        "YYYY-MM-DD e hora HH:MM (24h, hora local). O lembrete do Telegram avisa "
        "automaticamente no dia."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "acao": {
                "type": "string",
                "enum": ["criar", "listar"],
                "description": "'criar' (padrão) adiciona evento; 'listar' mostra os próximos 90 dias.",
            },
            "titulo": {"type": "string", "description": "título curto do evento, ex: 'Post SEO - motion comics'"},
            "data": {"type": "string", "description": "data no formato YYYY-MM-DD (ex: 2026-09-15)"},
            "hora": {"type": "string", "description": "hora de início no formato HH:MM (ex: 10:00)"},
            "duracao_min": {"type": "integer", "description": "duração em minutos (padrão 60)"},
            "desc": {"type": "string", "description": "descrição/detalhe do evento (opcional)"},
        },
        "required": [],
    },
}

_TIMEOUT_S = 60


def _script_path() -> Path | None:
    base = os.environ.get("CHATTUI_SCRIPTS_PY", "").strip()
    if not base:
        return None
    return Path(base).expanduser() / "agendar.py"


def run(
    acao: str = "criar",
    titulo: str = "",
    data: str = "",
    hora: str = "",
    duracao_min: int = 60,
    desc: str = "",
) -> str:
    script = _script_path()
    if script is None:
        return "[erro] env CHATTUI_SCRIPTS_PY não definida — aponte no .env pra pasta que contém o agendar.py."
    if not script.exists():
        return f"[erro] agendar.py não encontrado em {script} — ajuste CHATTUI_SCRIPTS_PY."
    acao = (acao or "criar").lower()
    try:
        if acao == "listar":
            cmd = [sys.executable, str(script), "--list"]
        else:
            if not (titulo and data and hora):
                return "[erro] Para 'criar' informe titulo, data (YYYY-MM-DD) e hora (HH:MM)."
            try:
                inicio = datetime.datetime.strptime(f"{data} {hora}", "%Y-%m-%d %H:%M")
            except ValueError:
                return "[erro] Data ou hora inválida — use data YYYY-MM-DD e hora HH:MM."
            fim = inicio + datetime.timedelta(minutes=max(1, int(duracao_min or 60)))
            cmd = [
                sys.executable, str(script), titulo, data, hora,
                "--fim", fim.strftime("%H:%M"),
            ]
            if desc:
                cmd += ["--desc", desc]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return "[erro] tempo esgotado ao falar com a agenda Radicale."
    except Exception as exc:  # noqa: BLE001
        return f"[erro ao rodar agendar.py] {exc}"
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        return f"[erro {proc.returncode}] {err or out or 'falha desconhecida'}"
    return out or err or "ok (sem saída do agendar.py)"
