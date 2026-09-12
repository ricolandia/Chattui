"""Plugin de criação de nota no Trilium pro chattui.
Fica em plugins/ (pasta do projeto); pra desativar, renomeie começando
com "_". Requer: pip install requests
"""

import os

# Ferramenta que GRAVA no Trilium — o chattui pede confirmação antes.
DESTRUCTIVE = True

# mesma nota mãe fixa do trilium_post.py; sobrescreva via TRILIUM_PARENT_ID
PARENT_NOTE_ID = os.environ.get("TRILIUM_PARENT_ID", "Your_note_ID")

TOOL_SCHEMA = {
    "name": "criar_nota_trilium",
    "description": "Cria uma nota de texto no Trilium, dentro da nota mãe padrão do usuário.",
    "parameters": {
        "type": "object",
        "properties": {
            "titulo": {"type": "string", "description": "título da nota"},
            "conteudo": {"type": "string", "description": "corpo da nota (texto simples)"},
            "parent_id": {
                "type": "string",
                "description": "id da nota mãe no Trilium (opcional — usa a padrão do usuário se omitido)",
            },
        },
        "required": ["titulo", "conteudo"],
    },
}


def run(titulo: str, conteudo: str, parent_id: str = "") -> str:
    import requests

    url = os.getenv("TRILIUM_URL", "")
    token = os.getenv("TRILIUM_TOKEN", "")
    if not token:
        return "[erro] TRILIUM_TOKEN não configurado (variável de ambiente)."
    if not url:
        return "[erro] TRILIUM_URL não configurado (variável de ambiente)."

    endpoint = f"{url.rstrip('/')}/etapi/create-note"
    headers = {"Authorization": token, "Content-Type": "application/json"}
    payload = {
        "parentNoteId": parent_id or PARENT_NOTE_ID,
        "title": titulo,
        "type": "text",
        "content": conteudo,
    }
    resp = requests.post(endpoint, json=payload, headers=headers, timeout=15)
    if resp.status_code == 201:
        note_id = resp.json().get("note", {}).get("noteId")
        return f"Nota '{titulo}' criada no Trilium. ID: {note_id}"
    return f"[erro {resp.status_code}] {resp.text[:300]}"
