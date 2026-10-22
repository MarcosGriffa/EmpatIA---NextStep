"""
sources/computrabajo.py — Computrabajo Argentina, adaptado a la interfaz común.

Reusa la lógica de scraping que ya tenías funcionando en computrabajo.py
(selector article.box_offer, verificado en producción), pero ahora la
búsqueda es dinámica: recibe un término de búsqueda en vez de una lista
fija de rutas "IT junior". Así sirve para cualquier rubro que detecte
el clasificador de CV (data, ventas, biología, lo que sea).
"""

from __future__ import annotations

import re
import time
import random

import requests
from bs4 import BeautifulSoup

from .base import JobSource, normalize_job, detect_modality

BASE_URL = "https://ar.computrabajo.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
}
MAX_PAGES = 2  # por query — mantenemos bajo para no pegarle demasiado a un solo portal


def _txt(el) -> str:
    return el.get_text(strip=True) if el else ""


def _slugify(query: str) -> str:
    """'analista de datos junior' → 'analista-de-datos-junior'"""
    slug = query.strip().lower()
    slug = re.sub(r"[^a-z0-9áéíóúñ\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    return slug


def _parse_card(card, query: str) -> dict | None:
    title_el = (
        card.select_one("h2 a")
        or card.select_one("a.js-o-link")
        or card.select_one("a[href*='oferta']")
    )
    if not title_el:
        return None

    title = _txt(title_el)
    href = title_el.get("href", "")
    url = BASE_URL + href if href.startswith("/") else href

    # Filtramos textos que son botones/CTA, no nombres de empresa reales
    # (bug detectado en la primera corrida real: a veces el selector
    # agarraba el botón "Postular" en vez del nombre de la empresa).
    _NOT_COMPANY = {"postular", "aplicar", "ver más", "ver mas", "ver oferta", "apply"}

    def _first_valid_company(*elements) -> str:
        for el in elements:
            text = _txt(el)
            if text and text.strip().lower() not in _NOT_COMPANY:
                return text
        return ""

    # Cuando la empresa está identificada, su nombre viene como link dentro
    # de "p.dFlex.vm_fx.fs16.fc_base.mt5" (selectores de abajo). Pero cuando
    # el aviso es anónimo (texto "Importante empresa del sector") o lo
    # publica una consultora de selección sin linkear su perfil, ese mismo
    # párrafo trae el nombre como texto plano, sin ningún <a> — por eso
    # antes quedaba vacío. Como último recurso usamos el texto completo de
    # ese párrafo (bug detectado en la corrida real del 10/08/2026).
    company_p = card.select_one("p.dFlex.vm_fx.fs16.fc_base.mt5")
    company = _first_valid_company(
        card.select_one("a.fc_base.t_ellipsis"),
        card.select_one("p.fc_base a"),
        card.select_one("span.fc_base"),
        company_p,
    )

    location = ""
    for p in card.select("p.fs16.fc_base.mt5"):
        if "dFlex" not in p.get("class", []):
            span = p.select_one("span.mr10")
            location = _txt(span) if span else _txt(p)
            break

    # Modalidad: Computrabajo la muestra como un tag suelto en la tarjeta
    # ("Presencial" / "Híbrido" / "Remoto" / "Teletrabajo"). El selector
    # viejo hacía match EXACTO de texto y casi nunca acertaba (en 3 corridas
    # reales guardadas, todas las ofertas de Computrabajo salían con
    # modality=""). Ahora pasamos el texto completo de la tarjeta + el
    # título por detect_modality() (regex), que además tolera "Teletrabajo",
    # "100% remoto", etc. Ver sources/base.py.
    modality = detect_modality(title, card.get_text(" ", strip=True))

    date_el = card.select_one("p.fs13.fc_aux.mt15")

    return normalize_job(
        source="computrabajo",
        title=title,
        company=company,
        location=location,
        modality=modality,
        description="",  # descripción completa requeriría entrar a cada aviso
        url=url,
        posted_at=_txt(date_el),
    )


def fetch_full_description(url: str) -> str:
    """Entra al aviso individual y trae la descripción completa.

    El listado de búsqueda no la trae (para no pegarle una request extra por
    cada tarjeta), pero cv_tailor.py sí la necesita para adaptar el CV en
    base a los requisitos reales del puesto — y ahí solo se llama esto para
    un puñado de avisos (el top N finalista), no para todo el listado.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"    [computrabajo] ERROR trayendo descripción de {url}: {e}")
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")
    p = soup.select_one("div.mb40.pb40.bb1 p.mbB")
    texto = _txt(p)
    if not texto:
        # Respaldo por si Computrabajo cambia las clases del HTML: el
        # resumen que el propio aviso publica para buscadores.
        meta = soup.select_one('meta[name="description"]') or soup.select_one('meta[property="og:description"]')
        texto = (meta.get("content") or "").strip() if meta else ""
    return texto


class ComputrabajoSource(JobSource):
    name = "computrabajo"
    is_tech_vertical = False

    def search(self, query: str, max_results: int = 25) -> list[dict]:
        path = f"/trabajo-de-{_slugify(query)}"
        jobs = []

        for page in range(1, MAX_PAGES + 1):
            url = BASE_URL + path if page == 1 else f"{BASE_URL}{path}?p={page}"
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                resp.raise_for_status()
            except Exception as e:
                print(f"    [computrabajo] ERROR p{page}: {e}")
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("article.box_offer")
            if not cards:
                break

            for card in cards:
                job = _parse_card(card, query)
                if job:
                    jobs.append(job)
                if len(jobs) >= max_results:
                    break

            if len(jobs) >= max_results:
                break

            time.sleep(random.uniform(2.0, 3.5))

        print(f"    [computrabajo] '{query}' → {len(jobs)} ofertas")
        return jobs[:max_results]
