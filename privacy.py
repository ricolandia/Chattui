"""Anonimização de PII no envio (outbound) — email, CPF, CNPJ e telefone.

Uso principal: quando o modelo é um endpoint **remoto** (nuvem), o payload
enviado passa por aqui antes de sair da máquina. Placeholders estáveis
(`[EMAIL_1]`, `[CPF_2]`...) substituem os valores; o mesmo valor sempre
recebe o mesmo token dentro de um turno, e `restaurar()` devolve o texto
original na exibição/persistência.

Sem dependências externas (stdlib). Nomes próprios não são detectáveis por
regex — o escopo aqui é dado estruturado.
"""

from __future__ import annotations

import re

# Ordem importa: CNPJ antes de CPF (o CPF com separadores opcionais pode
# casar parte de um CNPJ); telefone exige DDD pra não pegar data/ID curto.
PADROES: list[tuple[str, str]] = [
    ("email", r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),
    ("cnpj", r"\b\d{2}\.?\d{3}\.?\d{3}/\d{4}-?\d{2}\b"),
    ("cpf", r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),
    ("telefone", r"(?<![\d-])(?:\+?55[ -]?)?\(?\d{2}\)?[ -]?9?\d{4}[ -]?\d{4}(?![\d-])"),
]

RE_COMPILADOS = [(nome, re.compile(padrao)) for nome, padrao in PADROES]


class Anonimizador:
    """Estado de anonimização de um turno (mapa + contadores estáveis)."""

    def __init__(self, mapeamento: dict[str, str] | None = None):
        self.mapeamento: dict[str, str] = dict(mapeamento or {})
        self._contadores: dict[str, int] = {}
        for placeholder in self.mapeamento:
            nome = placeholder.strip("[]_").rsplit("_", 1)[0].lower()
            self._contadores[nome] = self._contadores.get(nome, 0) + 1

    def processar(self, texto: str) -> str:
        if not texto:
            return texto
        resultado = texto
        for nome, regex in RE_COMPILADOS:
            def _substituir(match, nome=nome):
                valor = match.group(0)
                if valor in self.mapeamento.values():
                    for token, original in self.mapeamento.items():
                        if original == valor:
                            return token
                self._contadores[nome] = self._contadores.get(nome, 0) + 1
                placeholder = f"[_{nome.upper()}_{self._contadores[nome]}_]"
                self.mapeamento[placeholder] = valor
                return placeholder

            resultado = regex.sub(_substituir, resultado)
        return resultado

    @property
    def total(self) -> int:
        return len(self.mapeamento)


def anonimizar(texto: str) -> tuple[str, dict[str, str]]:
    """Substitui PII por placeholders. Retorna (texto_anonimo, mapeamento)."""
    anon = Anonimizador()
    return anon.processar(texto), anon.mapeamento


def restaurar(texto: str, mapeamento: dict[str, str]) -> str:
    """Devolve os placeholders aos valores originais."""
    resultado = texto
    for placeholder, valor in mapeamento.items():
        resultado = resultado.replace(placeholder, valor)
    return resultado
