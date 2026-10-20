"""
sources/getonboard.py — Get on Board (getonbrd.com), API pública oficial.

Bolsa de empleo de Latinoamérica con fuerte presencia en Argentina. Su
fuerte es tecnología, pero también publica marketing, diseño, ventas,
producto y administración en empresas tech, así que se usa como fuente
GENERAL, con las queries en español.

API pública (sin key, documentada en getonbrd.com/api-doc.html):
  GET https://www.getonbrd.com/api/v0/search/jobs?query=...&per_page=..&page=1
  Respuesta JSON:API: {"data": [{"id", "type": "job", "attributes": {...},
  "links": {"public_url"}}]}

Sólo se quedan las ofertas abiertas a Argentina: las que listan Argentina
entre sus países o son 100% remotas para LATAM.

⚠️ Escrita el 20/10/2026 sin poder probarla en vivo (el entorno donde se
programó no tenía salida a getonbrd.com). Probarla con:
    python tools/probar_fuentes.py getonboard
"""

from __future__ import annotations

import os
import re

import requests

from .base import JobSource, normalize_job

API_URL = "https://www.getonbrd.com/api/v0/search/jobs"
MAX_PAGINAS = 4
HEADERS = {"Accept": "application/json", "User-Agent": "EmpatIA-NextStep/1.0 (+https://www.empatianextstep.com)"}

_MODALIDAD = {"fully_remote": "remoto", "remote_local": "remoto", "hybrid": "hibrido", "no_remote": "presencial"}


def _limpiar_html(texto: str) -> str:
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    return re.sub(r"\s+", " ", texto).strip()


def _abierta_a_argentina(attrs: dict) -> bool:
    paises = attrs.get("countries") or []
    texto = " ".join(str(p) for p in paises).lower() + " " + str(attrs.get("location") or "").lower()
    if "argentin" in texto:
        return True
    if attrs.get("remote_modality") == "fully_remote":
        return True
    # remoto sin países listados = abierto a cualquier lugar
    return bool(attrs.get("remote")) and not paises


class GetOnBoardSource(JobSource):
    name = "getonboard"
    is_tech_vertical = False

    def search(self, query: str, max_results: int = 25) -> list[dict]:
        # La API no filtra por país y la mayoría de lo que devuelve es de
        # Chile y Colombia (en una prueba: 19 de 20). Se piden hasta
        # MAX_PAGINAS páginas y se corta apenas haya suficientes para Argentina.
        crudos: list = []
        for pagina in range(1, MAX_PAGINAS + 1):
            try:
                resp = requests.get(
                    API_URL,
                    params={"query": query, "per_page": 50, "page": pagina, "expand": '["company"]'},
                    headers=HEADERS,
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(f"    [getonboard] ERROR p{pagina}: {e}")
                break
            lote = (data.get("data") or []) if isinstance(data, dict) else []
            crudos.extend(lote)
            if len(lote) < 50 or sum(_abierta_a_argentina(i.get("attributes") or {}) for i in crudos) >= max_results:
                break

        jobs = []
        descartadas: list[str] = []
        for item in crudos:
            attrs = item.get("attributes") or {}
            if not _abierta_a_argentina(attrs):
                descartadas.append(f"{attrs.get('countries')}/{attrs.get('remote_modality')}")
                continue
            empresa = ""
            comp = attrs.get("company")
            if isinstance(comp, dict):
                empresa = ((comp.get("data") or {}).get("attributes") or {}).get("name", "") or comp.get("name", "")
            descripcion = " ".join(
                _limpiar_html(attrs.get(k, "")) for k in ("description", "functions", "desirable") if attrs.get(k)
            )
            url = (item.get("links") or {}).get("public_url") or f"https://www.getonbrd.com/jobs/{item.get('id', '')}"
            jobs.append(
                normalize_job(
                    source=self.name,
                    title=attrs.get("title", ""),
                    company=empresa,
                    location="Argentina" if "argentin" in str(attrs.get("countries", "")).lower() else "Remoto (LATAM)",
                    modality=_MODALIDAD.get(attrs.get("remote_modality") or "", ""),
                    description=descripcion[:3000],
                    url=url,
                    posted_at=str(attrs.get("published_at") or ""),
                )
            )
            if len(jobs) >= max_results:
                break

        print(f"    [getonboard] '{query}' → {len(jobs)} ofertas (de {len(crudos)} que devolvió la API)")
        if descartadas and os.getenv("DEBUG_FUENTES"):
            print(f"    [getonboard] descartadas por país/modalidad: {descartadas[:10]}")
        return jobs
