"""
pipeline.py — Motor completo, de punta a punta.

  CV → clasificación (área, seniority, queries ES/EN) → búsqueda en portales
     → prefiltro por embeddings → explicación con IA de los finalistas
     → resultado final ordenado

Uso:
    python pipeline.py test_cvs/cv_marcos.txt
    python pipeline.py test_cvs/cv_ventas.txt

Guarda el resultado en data/resultados_<nombre_cv>.json y .csv, y también
lo imprime lindo en la consola.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pandas as pd

import geo
from cv_profile import extract_cv_text, classify_cv
from semantic_match import rank_and_explain

from sources.computrabajo import ComputrabajoSource
from sources.jooble import JoobleSource
# from sources.multitrabajos import MultitrabajosSource  # DESACTIVADO: es de Ecuador, no Argentina
# from sources.konzerta import KonzertaSource             # DESACTIVADO: es de Panamá, no Argentina
from sources.remoteok import RemoteOKSource
from sources.jobicy import JobicySource
from sources.himalayas import HimalayasSource
from sources.weworkremotely import WeWorkRemotelySource

# Fuentes generales (español): se consultan siempre, sin importar el rubro.
#
# Multitrabajos y Konzerta quedaron afuera tras investigarlas (10/08/2026):
# no son sitios argentinos (Multitrabajos = Ecuador, Konzerta = Panamá; no
# existe versión .com.ar ni subdominio ar. de ninguna de las dos), así que
# aunque tienen una API JSON real detrás del loader de JavaScript, traerían
# ofertas del país equivocado. Además esa API está protegida por Cloudflare
# y devuelve 403 a pedidos que no vengan de un navegador real. Ver detalle
# en README_FASE1.md.
# Jooble sumado el 13/08/2026: metabuscador con API oficial, apuntando al
# dominio argentino (ar.jooble.org). Fuente general — trae de cualquier
# rubro, no solo tech. OJO con el cupo: el plan gratuito son 500 requests
# EN TOTAL de por vida (~1 por query, ~5 por CV) — ver sources/jooble.py.
GENERAL_SOURCES = [ComputrabajoSource(), JoobleSource()]

# Fuentes verticales tech (inglés): se activan solo si el CV es de área IT,
# y se consultan con las queries en inglés (search_queries_en).
TECH_SOURCES = [RemoteOKSource(), JobicySource(), HimalayasSource(), WeWorkRemotelySource()]

MAX_RESULTS_PER_QUERY = 25
EMBEDDING_TOP_K = 30
# Cuántas finalistas LEE el LLM. Hasta el 13/10/2026 era 10 y coincidía con
# lo que se muestra; las evals (evals/) mostraron que ~13% de las ofertas
# relevantes quedaban entre los puestos 11 y 30 de los embeddings — sobre
# todo títulos escritos distinto ("Personal de Salón" para un CV de mozo) —
# y que el LLM las reconocía (88-92 de score) cuando las leía. Ahora lee
# las 30 en paralelo (ver LLM_MAX_PARALLEL en semantic_match.py).
EXPLAIN_TOP_N = int(os.getenv("EXPLAIN_TOP_N", "30"))
# Cuántas se muestran al usuario: las mejores según el LLM.
SHOW_TOP_N = 10


def _normalize_key(title: str, company: str) -> str | None:
    """Clave para detectar ofertas duplicadas aunque la URL tenga un hash
    de tracking distinto: título + empresa, en minúscula y sin espacios extra.

    Devuelve None si la empresa viene vacía — encontrado el 20/08/2026
    investigando por qué Jooble aportaba 100 ofertas crudas y ninguna
    sobrevivía hasta el ranking final: Jooble (metabuscador) a menudo no
    trae el campo "company", y con título+empresa vacía, ofertas REALES y
    DISTINTAS con un título genérico ("Analista de Datos") colapsaban en
    la misma clave — la primera procesada ganaba (casi siempre Computrabajo,
    que corre primero en GENERAL_SOURCES) y el resto se descartaba como
    "duplicado" sin serlo. Con empresa vacía, título+empresa ya no alcanza
    para confirmar que es la misma oferta — se vuelve a la URL exacta nomás
    para esos casos (ver collect_jobs), que es más conservador: en el peor
    caso deja pasar algún duplicado real, nunca borra una oferta distinta."""
    company_norm = re.sub(r"\s+", " ", (company or "").strip().lower())
    if not company_norm:
        return None
    title_norm = re.sub(r"\s+", " ", (title or "").strip().lower())
    return f"{title_norm}::{company_norm}"


def collect_jobs(
    search_queries_es: list[str],
    search_queries_en: list[str],
    is_tech: bool,
    general_sources: list | None = None,
) -> list[dict]:
    """Corre las fuentes generales con las queries en español y, si el CV es
    tech, las fuentes verticales con las queries en inglés. Devuelve la lista
    combinada, deduplicada por URL exacta y por título+empresa (esto último
    solo si la empresa no viene vacía — ver _normalize_key).

    general_sources: por defecto usa GENERAL_SOURCES (Computrabajo + Jooble),
    igual que siempre — ningún llamador existente cambia de comportamiento.
    Los avisos automáticos por mail (notificaciones_semanales.py) pasan acá
    una lista sin Jooble, para no gastarle cupo a los chequeos en segundo
    plano: ese cupo se reserva para cuando alguien busca a mano y está
    esperando el resultado ahí mismo."""
    all_jobs = []
    fuentes_generales = general_sources if general_sources is not None else GENERAL_SOURCES

    for source in fuentes_generales:
        print(f"\n[{source.name}]")
        for query in search_queries_es:
            try:
                jobs = source.search(query, max_results=MAX_RESULTS_PER_QUERY)
            except Exception as e:
                print(f"    [{source.name}] EXCEPCIÓN no controlada: {e}")
                jobs = []
            all_jobs.extend(jobs)

    if is_tech:
        queries_en = search_queries_en or search_queries_es  # fallback si vino vacío
        for source in TECH_SOURCES:
            print(f"\n[{source.name}]")
            for query in queries_en:
                try:
                    jobs = source.search(query, max_results=MAX_RESULTS_PER_QUERY)
                except Exception as e:
                    print(f"    [{source.name}] EXCEPCIÓN no controlada: {e}")
                    jobs = []
                all_jobs.extend(jobs)

    seen_urls = set()
    seen_keys = set()
    unique_jobs = []
    for job in all_jobs:
        url = job.get("url", "")
        key = _normalize_key(job.get("title", ""), job.get("company", ""))
        if url and url in seen_urls:
            continue
        # key es None cuando la empresa vino vacía — no deduplicar por
        # título solo, dejar pasar (la URL exacta ya se chequeó arriba).
        if key is not None and key in seen_keys:
            continue
        seen_urls.add(url)
        if key is not None:
            seen_keys.add(key)
        unique_jobs.append(job)

    print(f"\nTotal ofertas encontradas: {len(all_jobs)} | Únicas: {len(unique_jobs)}")
    return unique_jobs


def run(cv_path: str):
    print("=" * 60)
    print("  MOTOR DE MATCHING CV ↔ EMPLEO — Fase 1")
    print("=" * 60)

    cv_text = extract_cv_text(cv_path)
    print(f"\nCV leído: {len(cv_text)} caracteres")

    print("\nClasificando CV con IA...")
    profile = classify_cv(cv_text)
    print(json.dumps(profile, indent=2, ensure_ascii=False))

    jobs = collect_jobs(profile["search_queries"], profile.get("search_queries_en", []), profile["is_tech"])

    if not jobs:
        print("\n[!] No se encontraron ofertas. Revisá los [WARN]/[ERROR] de arriba.")
        return

    cand_location = geo.parse_location(profile["ubicacion"]) if profile.get("ubicacion") else None
    if cand_location is not None:
        print(f"Ubicación del candidato detectada: {profile['ubicacion']}")

    results = rank_and_explain(
        cv_text, jobs, embedding_top_k=EMBEDDING_TOP_K, explain_top_n=EXPLAIN_TOP_N,
        show_top_n=SHOW_TOP_N, cand_location=cand_location,
    )

    # ── Guardar resultados ──
    cv_slug = Path(cv_path).stem
    out_dir = Path("data")
    out_dir.mkdir(exist_ok=True)

    json_path = out_dir / f"resultados_{cv_slug}.json"
    csv_path = out_dir / f"resultados_{cv_slug}.csv"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"profile": profile, "results": results}, f, indent=2, ensure_ascii=False)

    pd.DataFrame(results).to_csv(csv_path, index=False, encoding="utf-8")

    # ── Mostrar top resultados ──
    print(f"\n{'=' * 60}")
    print(f"  TOP MATCHES — área detectada: {profile['area']} ({profile['seniority']})")
    print(f"{'=' * 60}")

    for i, r in enumerate(results[:10], 1):
        score_txt = f"Score {r.get('score', '?')}/100"
        if r.get("score_final") is not None and r.get("score_final") != r.get("score"):
            score_txt += f" (ajustado por cercanía: {r['score_final']}/100)"
        print(f"\n  #{i} — {score_txt} — {r['title']}")
        cercania = f" | {r['proximity_label']}" if r.get("proximity_label") else ""
        print(f"  {r['company']} | {r['location']}{cercania} | fuente: {r['source']}")
        if r.get("matches"):
            print(f"  ✓ Matchea: {', '.join(r['matches'])}")
        if r.get("gaps"):
            print(f"  ✗ Le falta: {', '.join(r['gaps'])}")
        print(f"  → {r.get('explicacion', '')}")
        print(f"  {r['url']}")

    print(f"\n✓ Guardado en {json_path} y {csv_path}")


if __name__ == "__main__":
    cv_arg = sys.argv[1] if len(sys.argv) > 1 else "test_cvs/cv_marcos.txt"
    run(cv_arg)
