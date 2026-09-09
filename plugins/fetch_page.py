"""Plugin de leitura de página web pro chattui.

Diferente do web_search (que busca por TERMO), este baixa uma URL
específica e retorna o texto — é a ferramenta certa quando o usuário
pergunta "o que é <site>" ou manda um link direto.

Fica em plugins/ (pasta do projeto); pra desativar, renomeie começando
com "_".
Requer: pip install requests beautifulsoup4 lxml --break-system-packages
"""

TOOL_SCHEMA = {
    "name": "fetch_page",
    "description": (
        "Baixa uma página web a partir de uma URL específica e retorna o texto principal, "
        "sem HTML. Use esta ferramenta (e não web_search) quando o usuário perguntar sobre "
        "um site específico ou mandar um link direto."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL da página (com ou sem http(s)://)"},
        },
        "required": ["url"],
    },
}

MAX_CHARS = 6000


def run(url: str) -> str:
    import requests
    from bs4 import BeautifulSoup

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 (chattui)"})
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = "\n".join(lines)

    if not text:
        return "Página carregada, mas sem texto extraível (pode depender de JavaScript pra renderizar o conteúdo)."
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n\n[...conteúdo truncado...]"
    return text
