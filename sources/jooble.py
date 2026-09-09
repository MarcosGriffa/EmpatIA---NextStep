"""
sources/jooble.py — Jooble (metabuscador de empleo, API REST oficial).

Fuente GENERAL (no vertical tech): como es un metabuscador que agrega
avisos de muchos portales, cubre cualquier rubro. Cubre Argentina y 60+
países.

API (doc oficial: help.jooble.org, "REST API documentation"):
  - POST https://jooble.org/api/{key}  (la key va en la URL, no en headers)
  - Body JSON: {"keywords": ..., "location": ..., "page": ..., "ResultOnPage": ...}
  - "location" acepta ciudad, región o país — pasamos "Argentina" para
    filtrar al país correcto.
  - Respuesta: {"totalCount": int, "jobs": [{id, title, location, snippet,
    salary, source, type, link, company, updated}]}

⚠️ Límite del plan gratuito: 500 requests EN TOTAL por key (de por vida,
no por mes). Cada búsqueda del pipeline = 1 request, o sea ~5 requests por
CV subido (una por query del clasificador). La key vive en el .env como
JOOBLE_API_KEY; si falta, la fuente avisa una vez y devuelve [] sin romper
el pipeline.

✅ ESTADO (13/08/2026): ACTIVA y funcionando contra ar.jooble.org, con
avisos argentinos reales (San Nicolás, Rosario, San Isidro, Córdoba...).
Probada con búsquedas de rubros distintos ("analista de datos" y
"enfermero") para confirmar que sirve como fuente general y no solo tech.

Lección aprendida en el camino, por si aparece de nuevo: la API es
POR PAÍS. La primera key que se consiguió estaba registrada en el dominio
de EE.UU. (jooble.org) y, aunque respondía 200, devolvía solo avisos de
allá y CERO al filtrar por Argentina; contra ar.jooble.org daba 403. Ese
403 es cómo Jooble dice "esta key no vale para este dominio" (se confirmó
comparando con una key inventada, que da el mismo error). La key hay que
sacarla entrando desde ar.jooble.org, no desde jooble.org.

Dato útil: aunque un GET normal a la home de ar.jooble.org devuelve 403
desde Python (parece protección anti-bot, como la que nos frenó con
Multitrabajos/Konzerta), el endpoint /api NO tiene ese problema — anda
bien server-to-server.
"""

from __future__ import annotations

import os

import requests
from dotenv import load_dotenv

from .base import JobSource, normalize_job, detect_modality

load_dotenv()

# Dominio del país al que pertenece la key. Para la key argentina que se va
# a pedir, es ar.jooble.org (el dominio ya filtra el país, no hace falta
# location). Se puede pisar con JOOBLE_API_HOST en el .env — útil para
# probar con una key de otro país.
API_HOST = os.getenv("JOOBLE_API_HOST", "ar.jooble.org")
API_URL = "https://{host}/api/{key}"
# Con dominio de país, location queda para afinar por ciudad si algún día
# se quiere. Vacío = todo el país.
LOCATION = ""


class JoobleSource(JobSource):
    name = "jooble"
    is_tech_vertical = False

    def __init__(self):
        self._warned_no_key = False

    def search(self, query: str, max_results: int = 25) -> list[dict]:
        api_key = os.getenv("JOOBLE_API_KEY")
        if not api_key:
            if not self._warned_no_key:
                print("    [jooble] Sin JOOBLE_API_KEY en el .env — fuente salteada.")
                self._warned_no_key = True
            return []

        try:
            resp = requests.post(
                API_URL.format(host=API_HOST, key=api_key),
                json={
                    "keywords": query,
                    "location": LOCATION,
                    "page": 1,
                    "ResultOnPage": max_results,
                },
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"    [jooble] ERROR: {e}")
            return []

        raw_jobs = data.get("jobs", []) if isinstance(data, dict) else []
        jobs = []
        for item in raw_jobs:
            # El snippet viene con HTML de resaltado (<b>...</b>) — lo limpiamos.
            snippet = (item.get("snippet") or "").replace("<b>", "").replace("</b>", "").replace("&nbsp;", " ")
            # Jooble a veces trae salario — no está en nuestro esquema, así
            # que lo sumamos al texto para que la IA del matching lo vea.
            salary = (item.get("salary") or "").strip()
            if salary:
                snippet = f"Salario: {salary}. {snippet}"

            # Modalidad: primero por reglas sobre título + snippet + el campo
            # "type" que a veces trae Jooble; si nada, el fallback histórico
            # (location contiene "remot", ej. "Remoto (Argentina)").
            title_txt = item.get("title", "")
            job_type = (item.get("type") or "").lower()
            modality = detect_modality(title_txt, snippet, job_type)
            if not modality and "remot" in (item.get("location") or "").lower():
                modality = "remoto"

            jobs.append(
                normalize_job(
                    source=self.name,
                    title=item.get("title", ""),
                    company=item.get("company", ""),
                    location=item.get("location", ""),
                    modality=modality,
                    description=snippet,
                    url=item.get("link", ""),
                    posted_at=item.get("updated", ""),
                )
            )
            if len(jobs) >= max_results:
                break

        print(f"    [jooble] '{query}' → {len(jobs)} ofertas")
        return jobs
