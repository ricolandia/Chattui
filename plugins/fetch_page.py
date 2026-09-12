"""Plugin de leitura de página web pro chattui.

Diferente do web_search (que busca por TERMO), este baixa uma URL
específica e retorna o texto — é a ferramenta certa quando o usuário
pergunta "o que é <site>" ou manda um link direto.

Segurança (anti-SSRF): por padrão bloqueia loopback/rede privada/
link-local (IPv4 e IPv6) — inclusive em redirects. Pra liberar acesso à
sua própria rede, defina `permitir_rede_local = true` em [seguranca] no
config.toml (o chattui exporta CHATTUI_PERMITIR_REDE_LOCAL pro plugin).

Fica em plugins/ (pasta do projeto); pra desativar, renomeie começando
com "_".
Requer: pip install requests beautifulsoup4 lxml --break-system-packages
"""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urljoin, urlsplit

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
MAX_REDIRECTS = 5


def _permitir_rede_local() -> bool:
    return os.environ.get("CHATTUI_PERMITIR_REDE_LOCAL", "0").strip().lower() in ("1", "true", "yes", "on")


def _host_bloqueado(host: str) -> str | None:
    """Retorna o motivo do bloqueio, ou None se o host pode ser acessado.

    Resolve o hostname e rejeita se QUALQUER endereço resolvido for
    loopback/privado/link-local/reservado (cobre DNS rebinding simples)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return None  # deixa o requests reportar o erro de DNS
    for info in infos:
        raw = info[4][0]
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            continue
        mapped = getattr(ip, "ipv4_mapped", None)
        if mapped is not None:
            ip = mapped
        if not ip.is_global:
            return f"{host} → {raw}"
    return None


def _validar_url(url: str) -> str | None:
    """Retorna mensagem de erro se a URL for inválida/bloqueada, senão None."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return "[erro] só http/https são aceitos."
    if not parts.hostname:
        return "[erro] URL sem host."
    if _permitir_rede_local():
        return None
    motivo = _host_bloqueado(parts.hostname)
    if motivo:
        return (
            f"[erro] acesso a rede local/host privado bloqueado ({motivo}). "
            "Pra liberar, use `permitir_rede_local = true` em [seguranca] no config.toml."
        )
    return None


def run(url: str) -> str:
    import requests
    from bs4 import BeautifulSoup

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 (chattui)"}
    current = url
    resp = None
    for _ in range(MAX_REDIRECTS + 1):
        erro = _validar_url(current)
        if erro:
            return erro
        resp = session.get(current, timeout=15, headers=headers, allow_redirects=False)
        if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("location"):
            current = urljoin(current, resp.headers["location"])
            continue
        break
    else:
        return "[erro] muitos redirects."
    if resp is None:
        return "[erro] não consegui baixar a página."
    try:
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        return f"[erro ao baixar] {exc}"

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
