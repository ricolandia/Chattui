"""Exemplo de como plugar um script que você já tem — não use direto,
é um molde. Copie, renomeie e ajuste o import pro seu script real.
"""

TOOL_SCHEMA = {
    "name": "criar_nota_trilium",
    "description": "Cria uma nota no Trilium com o título e conteúdo dados.",
    "parameters": {
        "type": "object",
        "properties": {
            "titulo": {"type": "string", "description": "título da nota"},
            "conteudo": {"type": "string", "description": "corpo da nota em texto/markdown"},
        },
        "required": ["titulo", "conteudo"],
    },
}


def run(titulo: str, conteudo: str) -> str:
    # Import tardio de propósito: só carrega o módulo pesado se a
    # ferramenta for de fato chamada.
    import sys

    sys.path.insert(0, "/caminho/para/_agent-mini")  # ajuste pro seu path real
    import trilium_post  # seu script já existente

    trilium_post.criar_nota(titulo, conteudo)  # ajuste pro nome real da função
    return f"Nota '{titulo}' criada no Trilium."
