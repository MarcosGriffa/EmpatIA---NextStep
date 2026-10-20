"""
sources/careerjet.py — Careerjet (metabuscador), API oficial para partners.

Fuente GENERAL: como Jooble, junta avisos de muchos portales y sitios de
empresas, de cualquier rubro. En Argentina opera como opcionempleo.com.ar.
Sirve para cubrir el hueco que deja Jooble cuando se le agota el cupo.

API v4 (la que usan los clientes oficiales de Careerjet):
  GET https://search.api.careerjet.net/v4/query
      ?locale_code=es_AR&keywords=...&location=Argentina
      &user_ip=...&user_agent=...&page_size=..
  Autenticación: HTTP Basic, con la API key como usuario y clave vacía.
  Respuesta: {"type": "JOBS", "hits", "pages", "jobs": [{title, company,
  locations, description, url, date, salary}]}

La key es gratis: se pide creando una cuenta de partner en careerjet.com
(sección "Partners" / "API"). Va en el .env como CAREERJET_API_KEY. Sin
key, la fuente avisa una vez y devuelve [] sin romper nada.

user_ip / user_agent: Careerjet los pide para su control de fraude. Como
la búsqueda la dispara nuestro servidor, se manda la IP pública del
servidor si está en CAREERJET_USER_IP (si no, una genérica).

⚠️ Escrita el 20/10/2026 sin poder probarla en vivo. Probarla con:
    python tools/probar_fuentes.py careerjet
"""

from __future__ import annotations

import os

import requests
from dotenv import load_dotenv

from .base import JobSource, detect_modality, normalize_job

load_dotenv()

API_URL = "https://search.api.careerjet.net/v4/query"
USER_AGENT = "Mozilla/5.0 (compatible; EmpatIA-NextStep/1.0; +https://www.empatianextstep.com)"


class CareerjetSource(JobSource):
    name = "careerjet"
    is_tech_vertical = False

    def __init__(self):
        self._warned_no_key = False

    def search(self, query: str, max_results: int = 25) -> list[dict]:
        api_key = os.getenv("CAREERJET_API_KEY")
        if not api_key:
            if not self._warned_no_key:
                print("    [careerjet] Sin CAREERJET_API_KEY en el .env — fuente salteada.")
                self._warned_no_key = True
            return []

        try:
            resp = requests.get(
                API_URL,
                params={
                    "locale_code": "es_AR",
                    "keywords": query,
                    "location": "Argentina",
                    "page_size": max_results,
                    "page": 1,
                    "user_ip": os.getenv("CAREERJET_USER_IP", "200.0.0.1"),
                    "user_agent": USER_AGENT,
                },
                auth=(api_key, ""),
                headers={"User-Agent": USER_AGENT, "Referer": "https://www.empatianextstep.com/"},
                timeout=15,
            )
            if resp.status_code != 200:
                # El cuerpo de la respuesta suele decir el motivo (clave sin
                # aprobar, IP no válida, sitio no verificado...).
                print(f"    [careerjet] ERROR {resp.status_code}: {resp.text[:400]}")
                return []
            data = resp.json()
        except Exception as e:
            print(f"    [careerjet] ERROR: {e}")
            return []

        if not isinstance(data, dict) or data.get("type") != "JOBS":
            print(f"    [careerjet] respuesta inesperada: {str(data)[:200]}")
            return []

        jobs = []
        for item in data.get("jobs") or []:
            title = item.get("title", "")
            desc = item.get("description", "")
            salario = (item.get("salary") or "").strip()
            if salario:
                desc = f"Salario: {salario}. {desc}"
            jobs.append(
                normalize_job(
                    source=self.name,
                    title=title,
                    company=item.get("company", ""),
                    location=item.get("locations", "") or item.get("site", ""),
                    modality=detect_modality(title, desc),
                    description=desc,
                    url=item.get("url", ""),
                    posted_at=item.get("date", ""),
                )
            )
            if len(jobs) >= max_results:
                break

        print(f"    [careerjet] '{query}' → {len(jobs)} ofertas")
        return jobs
