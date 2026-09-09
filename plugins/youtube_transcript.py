"""Plugin de transcrição de YouTube pro chattui.

Fica em plugins/ (pasta do projeto); pra desativar, renomeie começando
com "_".
Requer: pip install youtube-transcript-api --break-system-packages
"""

TOOL_SCHEMA = {
    "name": "youtube_transcript",
    "description": "Busca a transcrição de um vídeo do YouTube (por URL ou ID) e retorna o texto completo.",
    "parameters": {
        "type": "object",
        "properties": {
            "video_url": {"type": "string", "description": "URL completa do vídeo ou apenas o ID de 11 caracteres"},
            "language": {
                "type": "string",
                "description": "código do idioma preferido (ex: 'pt', 'en'). Se omitido, tenta pt, pt-BR, en, nessa ordem.",
            },
        },
        "required": ["video_url"],
    },
}

MAX_CHARS = 8000  # corta transcrições muito longas pra não estourar o contexto


def _extract_video_id(video_url: str) -> str:
    import re

    match = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})", video_url)
    return match.group(1) if match else video_url.strip()


def run(video_url: str, language: str = "") -> str:
    from youtube_transcript_api import YouTubeTranscriptApi

    video_id = _extract_video_id(video_url)
    languages_to_try = [language] if language else []
    languages_to_try += ["pt", "pt-BR", "en"]

    api = YouTubeTranscriptApi()
    try:
        fetched = api.fetch(video_id, languages=languages_to_try)
    except Exception:
        # nenhum dos idiomas preferidos existe — pega o primeiro disponível
        transcript_list = api.list(video_id)
        fetched = next(iter(transcript_list)).fetch()

    text = " ".join(snippet.text for snippet in fetched)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + f"\n\n[...transcrição truncada em {MAX_CHARS} caracteres...]"
    return text
