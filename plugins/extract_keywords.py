"""Plugin de extração de palavras-chave pro chattui (YAKE — não-supervisionado, sem treino).

Fica em plugins/ (pasta do projeto); pra desativar, renomeie começando
com "_".
Requer: pip install yake --break-system-packages
"""

TOOL_SCHEMA = {
    "name": "extract_keywords",
    "description": "Extrai as palavras/expressões-chave mais relevantes de um texto usando YAKE.",
    "parameters": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "texto de onde extrair palavras-chave"},
            "max_keywords": {"type": "integer", "description": "quantidade máxima de palavras-chave (padrão 10)"},
            "language": {"type": "string", "description": "código do idioma, ex: 'pt', 'en' (padrão 'pt')"},
        },
        "required": ["text"],
    },
}


def run(text: str, max_keywords: int = 10, language: str = "pt") -> str:
    import yake

    kw_extractor = yake.KeywordExtractor(lan=language, n=2, top=max_keywords)
    keywords = kw_extractor.extract_keywords(text)
    keywords.sort(key=lambda pair: pair[1])  # score menor = mais relevante no YAKE
    if not keywords:
        return "Nenhuma palavra-chave encontrada."
    return "\n".join(f"- {kw}" for kw, _score in keywords)
