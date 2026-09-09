"""
matching.py — Orquesta el pipeline existente para la API web.

OJO: esto NO reemplaza ni modifica pipeline.py/cv_profile.py/semantic_match.py
— los importa y los usa tal cual, igual que lo haría alguien corriendo
`python pipeline.py` por consola. Lo único que agrega:

  1. Recibe el CV ya guardado en disco (subido por el usuario vía la web)
     en vez de leerlo de sys.argv.
  2. Le pone un job_id estable a cada oferta encontrada.
  3. Excluye las ofertas que el usuario ya marcó como "aplicado" en una
     corrida anterior, ANTES de gastar la etapa 2 (la que usa el modelo
     grande de Groq) — no tiene sentido volver a explicar un match que la
     persona ya aplicó.
  4. Guarda el resultado con storage.save_match_results en vez del
     json/csv que usa pipeline.py por consola.
  5. Marca las ofertas mostradas como "vistas" (seen_jobs) — así, si esta
     persona más adelante prende los avisos por mail, el chequeo semanal
     no le manda por mail algo que ya vio acá. Ver notificaciones_semanales.py.
"""

from __future__ import annotations

import geo
from cv_profile import extract_cv_text, classify_cv
from pipeline import collect_jobs, EMBEDDING_TOP_K, EXPLAIN_TOP_N
from semantic_match import rank_and_explain

from . import storage
from .job_utils import make_job_id


def run_full_pipeline(user_id: str, cv_path: str, filename: str, zona: str = "") -> dict:
    """Corre CV → clasificación → búsqueda → matching, de punta a punta,
    y devuelve todo lo que necesita el frontend.

    zona: lo que la persona eligió (opcional) en el <select> del formulario
    de subida. Se usa como ubicación del candidato SOLO si el CV no la trae."""

    cv_text = extract_cv_text(cv_path)
    profile = classify_cv(cv_text)

    # Ubicación del candidato: primero la que sacó la IA del CV (ya
    # normalizada a nivel ciudad en cv_profile.classify_cv), y si no hay, la
    # que eligió a mano en el formulario. Puede quedar None → no se penaliza
    # nada por cercanía (ver geo.proximity_score).
    ubicacion_cand = profile.get("ubicacion") or geo.normalize_candidate_location(zona)
    profile["ubicacion"] = ubicacion_cand
    cand_location = geo.parse_location(ubicacion_cand) if ubicacion_cand else None

    # PRIVACIDAD: la dirección exacta (calle + altura + piso) es dato
    # personal de un tercero. Se borra del texto ANTES de persistirlo — el
    # matching ya corrió sobre el texto completo en memoria, a la base va la
    # versión redactada. Ver geo.redact_address y web/.../privacidad.
    cv_text_guardado = geo.redact_address(cv_text)
    cv_id = storage.save_cv_profile(user_id, filename, cv_text_guardado, profile)

    jobs = collect_jobs(
        profile["search_queries"], profile.get("search_queries_en", []), profile["is_tech"]
    )

    for job in jobs:
        job["job_id"] = make_job_id(job)

    applied_ids = storage.get_applied_job_ids(user_id)
    jobs = [job for job in jobs if job["job_id"] not in applied_ids]

    if jobs:
        results = rank_and_explain(
            cv_text, jobs,
            embedding_top_k=EMBEDDING_TOP_K, explain_top_n=EXPLAIN_TOP_N,
            cand_location=cand_location,
        )
    else:
        results = []

    for r in results:
        r["applied"] = False  # recién generados, ninguno puede estar aplicado todavía

    match_id = storage.save_match_results(user_id, cv_id, results, profile=profile)

    try:
        storage.mark_jobs_seen(user_id, [r["job_id"] for r in results])
    except Exception as e:
        # Nunca dejar que esto tumbe la búsqueda: es soporte para los avisos
        # por mail (feature aparte), no el resultado que la persona está
        # esperando ver. Importa especialmente en la ventana de tiempo antes
        # de correr la migración de supabase/schema.sql (tabla seen_jobs
        # inexistente todavía) — sin este try/except, ESO rompería la
        # búsqueda para todo el mundo, no solo para los avisos.
        print(f"[matching] no se pudo marcar seen_jobs (no crítico): {e}")

    return {
        "cv_id": cv_id,
        "match_id": match_id,
        "profile": profile,
        "results": results,
    }
