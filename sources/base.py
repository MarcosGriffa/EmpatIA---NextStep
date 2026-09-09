"""
sources/base.py — Interfaz común para todas las fuentes de empleo.

Cada fuente (Computrabajo, RemoteOK, etc.) implementa la clase JobSource
y su método search(). Así el pipeline principal no necesita saber nada
sobre cómo scrapea o consulta cada portal — solo le pide una lista de
ofertas ya normalizadas.

Esquema normalizado de una oferta (dict):
{
    "source":      "computrabajo" | "remoteok" | ...,
    "title":       str,
    "company":     str,
    "location":    str,   # ciudad/país o "Remoto"
    "modality":    str,   # "remoto" | "hibrido" | "presencial" | ""
    "description": str,   # texto completo si está disponible, sino snippet
    "url":         str,
    "posted_at":   str,   # fecha como texto, formato variable según fuente
    "scraped_at":  str,   # ISO timestamp de cuándo se obtuvo
}
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import datetime


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# Detección de modalidad por reglas — barata (regex sobre texto que ya
# tenemos), sin llamar a ninguna IA. Ver la conversación de diseño: la
# etapa 2 (LLM grande) ya cuesta y sólo cubre ~10 finalistas, así que la
# modalidad se saca de acá y del scrape, no del modelo.
#
# EL ORDEN IMPORTA y es contraintuitivo:
#   1. HÍBRIDO primero. Computrabajo etiqueta los avisos mixtos con el chip
#      literal "Presencial y remoto" (verificado en vivo, 09/09/2026) — eso
#      es híbrido, no remoto. Si "remoto" se chequeara antes, todos esos
#      avisos (la mayoría de los que traen modalidad) saldrían mal como
#      "remoto" y no se les aplicaría la penalización de cercanía que
#      corresponde. También cubre el título que dice "... / Híbrido".
#   2. REMOTO después: sólo cuando es remoto "puro" (sin "presencial" al lado).
#   3. PRESENCIAL al final: la palabra más ambigua.
_MODALITY_PATTERNS = [
    ("hibrido", re.compile(
        r"\b(h[ií]brid[oa]|hybrid|esquema h[ií]brido|modalidad h[ií]brida|"
        r"presencial\s*(?:y|/|o|\+|&)\s*remot[oa]|"
        r"remot[oa]\s*(?:y|/|o|\+|&)\s*presencial|"
        r"remoto parcial|parcialmente remoto)\b", re.IGNORECASE)),
    ("remoto", re.compile(
        r"\b(100\s?%?\s?remoto|full\s?remote|totalmente remoto|"
        r"remoto|remota|remote|teletrabajo|home\s?office|"
        r"trabajo desde casa|desde tu casa)\b", re.IGNORECASE)),
    ("presencial", re.compile(
        r"\b(100\s?%?\s?presencial|presencial|on\s?site|on-site|"
        r"en (?:la )?oficina|en planta|modalidad presencial)\b", re.IGNORECASE)),
]


def detect_modality(*texts: str) -> str:
    """Devuelve 'remoto' | 'hibrido' | 'presencial' | '' a partir de uno o
    más textos (título, tag de la tarjeta, snippet). '' = no se pudo
    determinar (no se penaliza cercanía en ese caso — ver geo.py)."""
    blob = " ".join(t for t in texts if t)
    if not blob.strip():
        return ""
    for name, pat in _MODALITY_PATTERNS:
        if pat.search(blob):
            return name
    return ""


def normalize_job(
    source: str,
    title: str,
    company: str = "",
    location: str = "",
    modality: str = "",
    description: str = "",
    url: str = "",
    posted_at: str = "",
) -> dict:
    """Arma un dict de oferta con el esquema normalizado, rellenando lo que falte."""
    return {
        "source": source,
        "title": (title or "").strip(),
        "company": (company or "").strip(),
        "location": (location or "").strip(),
        "modality": (modality or "").strip().lower(),
        "description": (description or "").strip(),
        "url": (url or "").strip(),
        "posted_at": (posted_at or "").strip(),
        "scraped_at": now_iso(),
    }


class JobSource(ABC):
    """Clase base que toda fuente de empleo debe implementar."""

    #: nombre corto de la fuente, usado en logs y en el campo "source"
    name: str = "base"

    #: True si esta fuente es específica de tecnología/IT (se activa solo
    #: cuando el clasificador de CV detecta que el área es tech).
    is_tech_vertical: bool = False

    @abstractmethod
    def search(self, query: str, max_results: int = 25) -> list[dict]:
        """
        Busca ofertas para un término de búsqueda dado.
        Devuelve una lista de dicts con el esquema normalizado (ver normalize_job).
        Nunca debería levantar una excepción hacia afuera: si algo falla,
        loguea el error y devuelve [] para no tumbar el resto del pipeline.
        """
        raise NotImplementedError
