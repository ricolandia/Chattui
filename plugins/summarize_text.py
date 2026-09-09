"""Plugin de resumo de texto pro chattui (sumarização extrativa, sem LLM).

Fica em plugins/ (pasta do projeto); pra desativar, renomeie começando
com "_".
Requer:
    pip install sumy --break-system-packages
    python3 -c "import nltk; nltk.download('punkt_tab')"   # uma vez só
"""

TOOL_SCHEMA = {
    "name": "summarize_text",
    "description": "Resume um texto longo em N frases usando sumarização extrativa (LSA) — não usa LLM, é determinístico e rápido.",
    "parameters": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "texto a ser resumido"},
            "sentences": {"type": "integer", "description": "quantidade de frases no resumo (padrão 5)"},
            "language": {"type": "string", "description": "idioma do texto para o tokenizador (padrão 'portuguese')"},
        },
        "required": ["text"],
    },
}


def run(text: str, sentences: int = 5, language: str = "portuguese") -> str:
    from sumy.nlp.tokenizers import Tokenizer
    from sumy.parsers.plaintext import PlaintextParser
    from sumy.summarizers.lsa import LsaSummarizer

    parser = PlaintextParser.from_string(text, Tokenizer(language))
    summarizer = LsaSummarizer()
    summary_sentences = summarizer(parser.document, sentences)
    result = " ".join(str(s) for s in summary_sentences)
    return result or "Não foi possível gerar um resumo (texto muito curto?)."
