"""Plugin de busca web pro chattui.

Fica em plugins/ (pasta do projeto); pra desativar, renomeie começando
com "_". Usa a mesma lib (ddgs) que você já usa no orquestrador — não
precisa de chave de API.
"""

TOOL_SCHEMA = {
    "name": "web_search",
    "description": "Busca na web e retorna títulos, resumos e links dos resultados mais relevantes.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "termo de busca"},
            "max_results": {"type": "integer", "description": "quantidade de resultados (padrão 5)"},
        },
        "required": ["query"],
    },
}


def run(query: str, max_results: int = 5) -> str:
    from ddgs import DDGS

    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results))

    if not results:
        return "Nenhum resultado encontrado."

    lines = []
    for r in results:
        lines.append(f"- {r.get('title')}: {r.get('body')} ({r.get('href')})")
    return "\n".join(lines)
