"""
semantic_match.py — Matching semántico CV vs. ofertas, en dos etapas.

Etapa 1 (barata, corre sobre TODAS las ofertas): embeddings + similitud
coseno. Convierte el CV y cada oferta en un vector de significado y
rankea por cercanía — así "Analista de Datos" matchea con "Data Analyst Jr"
aunque no compartan palabras. Usa la API de Cohere (modelo multilingüe);
cuesta centavos por búsqueda. Ver el comentario en EMBEDDING_MODEL para
por qué dejó de correr local.

Etapa 2 (más cara, corre SOLO sobre el top N finalistas): un LLM (Groq,
modelo grande) lee el CV completo + la descripción completa de cada oferta
finalista y genera una explicación real de por qué matchea o no — esto es
lo que da "entendimiento", no solo cercanía de tema.

Ver conversación de costos: la etapa 1 es prácticamente gratis y filtra
las ofertas irrelevantes; la etapa 2 solo se aplica a un puñado de avisos
por usuario, así que el costo total sigue siendo de centavos.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

# Filtro semántico (etapa 1). Migrado a la API de Cohere el 17/08/2026.
#
# Antes corría un modelo local (sentence-transformers + torch). Funcionaba,
# pero arrastraba 800 MB de librerías, bajaba 400 MB de modelo en cada
# arranque, y el motor llegaba a 768 MB de RAM en una búsqueda — no entraba
# en los 512 MB de un servidor gratuito, que es donde queremos publicarlo.
#
# Cohere se eligió sobre OpenAI por tres razones: tiene clave gratuita sin
# tarjeta, su modelo multilingüe está entrenado explícitamente para español,
# y distingue "consulta" de "documento" (acá el CV es la consulta y los
# avisos los documentos), lo que se ajusta mejor a este tipo de búsqueda que
# tratar a los dos textos igual.
#
# Toda la dependencia de Cohere vive en este archivo: cambiar de proveedor
# es reescribir _embed() y nada más.
EMBEDDING_MODEL = "embed-multilingual-v3.0"
EMBED_BATCH = 90  # la API acepta hasta 96 textos por llamada
# Modelo grande, para el análisis fino del match. Cambiado el 17/08/2026:
# Groq dio de baja `llama-3.3-70b-versatile` junto con toda la línea Llama.
EXPLAIN_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
# Temperatura 0 desde el 13/10/2026: con 0.3, el mismo CV + la misma oferta
# daban scores distintos al repetir (±4,6 puntos en promedio, hasta 35 en un
# caso — ver evals/). Para un ranking queremos el mismo veredicto siempre.
EXPLAIN_TEMPERATURE = 0
# Cuántas llamadas al LLM en paralelo por búsqueda. Antes iban en serie
# (10 × ~2,5 s = 25 s de espera). Configurable porque el límite de pedidos
# por minuto de Groq depende del plan: si aparecen 429, bajar este número.
LLM_MAX_PARALLEL = int(os.getenv("LLM_MAX_PARALLEL", "6"))
# gpt-oss "piensa" antes de responder y esos tokens de razonamiento se
# cobran y cuentan para el cupo de Groq: eran ~60% de cada llamada (~345 de
# salida contra ~550 de entrada). Para puntuar un match alcanza con
# razonamiento corto. Medido con evals/ antes de dejarlo fijo.
EXPLAIN_REASONING_EFFORT = os.getenv("EXPLAIN_REASONING_EFFORT", "low")

_cohere_client = None


def _get_cohere():
    global _cohere_client
    if _cohere_client is None:
        import cohere

        api_key = os.getenv("COHERE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Falta COHERE_API_KEY en el .env. Sacá una gratis (sin tarjeta) "
                "en dashboard.cohere.com — ver .env.example."
            )
        _cohere_client = cohere.ClientV2(api_key)
    return _cohere_client


def _embed(textos: list[str], tipo: str) -> np.ndarray:
    """Convierte textos en vectores. `tipo` es "search_query" (lo que se
    busca: el CV) o "search_document" (lo que se tiene: los avisos)."""
    co = _get_cohere()
    vectores: list[list[float]] = []
    for i in range(0, len(textos), EMBED_BATCH):
        lote = textos[i : i + EMBED_BATCH]
        resp = co.embed(
            texts=lote,
            model=EMBEDDING_MODEL,
            input_type=tipo,
            embedding_types=["float"],
        )
        vectores.extend(resp.embeddings.float_)
    return np.array(vectores, dtype=np.float32)


def prefilter_by_embeddings(cv_text: str, jobs: list[dict], top_k: int = 30) -> list[dict]:
    """
    Etapa 1: rankea todas las ofertas por similitud semántica con el CV
    y devuelve las top_k más cercanas. Le agrega el campo "similarity" a cada oferta.

    Si la API de Cohere falla, no se corta la búsqueda: se dejan pasar las
    primeras `top_k` ofertas tal como vinieron para que la etapa 2 (la IA)
    haga su trabajo igual. Se pierde calidad de preselección, no el servicio.
    """
    if not jobs:
        return []

    job_texts = [f"{j['title']} — {j.get('description', '')}"[:1000] for j in jobs]

    try:
        cv_vec = _embed([cv_text[:3000]], "search_query")[0]
        job_vecs = _embed(job_texts, "search_document")
    except Exception as e:
        print(f"    [embeddings] ERROR ({e}) — se sigue sin preselección semántica.")
        for job in jobs:
            job["similarity"] = 0.0
        return jobs[:top_k]

    # Similitud del coseno: como los vectores de Cohere vienen normalizados,
    # alcanza con el producto punto, pero normalizamos igual por las dudas.
    cv_norm = cv_vec / (np.linalg.norm(cv_vec) + 1e-9)
    job_norms = job_vecs / (np.linalg.norm(job_vecs, axis=1, keepdims=True) + 1e-9)
    similarities = job_norms @ cv_norm

    for job, sim in zip(jobs, similarities):
        job["similarity"] = round(float(sim), 4)

    ranked = sorted(jobs, key=lambda j: j["similarity"], reverse=True)
    return ranked[:top_k]


def _get_client():
    """Cliente del LLM de la etapa 2. Por defecto Groq. Si en el .env está
    LLM_BASE_URL, usa cualquier proveedor compatible con la API de OpenAI
    (OpenRouter, DeepInfra, Together...) con LLM_API_KEY — el mismo modelo
    open-source gpt-oss-120b se sirve en muchos lados. Se agregó el
    16/10/2026 porque el plan pago de Groq no estaba disponible."""
    base_url = os.getenv("LLM_BASE_URL")
    if base_url:
        from openai import OpenAI

        api_key = os.getenv("LLM_API_KEY")
        if not api_key:
            raise RuntimeError("Falta LLM_API_KEY en el .env (está LLM_BASE_URL).")
        return OpenAI(base_url=base_url, api_key=api_key, max_retries=3)
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("Falta GROQ_API_KEY en el .env.")
    return Groq(api_key=api_key)


EXPLAIN_SYSTEM_PROMPT = """\
Sos un reclutador experto. Vas a recibir un CV y la descripción de una
oferta de trabajo. Tu tarea es evaluar si la persona del CV es un buen
candidato para esa oferta, leyendo y entendiendo ambos textos (no solo
comparando palabras sueltas).

Criterios:
- Lo central es si el PUESTO es el mismo o equivalente, aunque el título
  esté escrito distinto ("Mozo" y "Personal de Salón", "Encargado de local"
  y "Gerente de local"). Palabras técnicas sueltas en la descripción de la
  empresa no convierten un puesto en otro.
- Tené en cuenta el seniority: si la oferta pide bastante más experiencia
  de la que muestra el CV, o la persona está claramente sobrecalificada,
  bajá el score aunque las habilidades coincidan.
- Usá toda la escala: 85-100 mismo puesto y nivel, cumple casi todo;
  60-84 mismo puesto con faltantes o un nivel de diferencia; 30-59 puesto
  relacionado o desajuste fuerte de nivel; 0-29 otro rubro.

Devolvé ÚNICAMENTE un JSON con este esquema:
{
  "score": número entero 0-100 — qué tan buen match es,
  "matches": ["2 a 4 razones concretas", "por las que sí matchea"],
  "gaps": ["0 a 3 cosas", "que pide la oferta", "y no se ven en el CV"],
  "explicacion": "1-2 frases en español, tono directo, explicando el veredicto"
}
Devolvé SOLO el JSON.
"""


def _extra_proveedor() -> dict:
    """OpenRouter reparte los pedidos entre varios servidores del mismo
    modelo, y cada uno da scores un poco distintos (en las evals, la
    variación al repetir subió de ±2,6 a ±4,8). LLM_PROVIDER fija uno solo
    (ej. "deepinfra" o "groq") para que el ranking sea estable."""
    prov = os.getenv("LLM_PROVIDER")
    if not prov or not os.getenv("LLM_BASE_URL"):
        return {}
    return {"extra_body": {"provider": {"order": [prov], "allow_fallbacks": True}}}


def explain_match(cv_text: str, job: dict) -> dict:
    """
    Etapa 2: el LLM lee CV + oferta y devuelve score + explicación real.
    Se llama solo sobre las ofertas finalistas (después del prefiltro de embeddings).
    """
    client = _get_client()

    job_desc = job.get("description") or job.get("title", "")
    user_content = (
        f"CV:\n{cv_text[:3000]}\n\n"
        f"OFERTA:\nTítulo: {job.get('title', '')}\n"
        f"Empresa: {job.get('company', '')}\n"
        f"Descripción: {job_desc[:1500]}"
    )

    resp = client.chat.completions.create(
        model=EXPLAIN_MODEL,
        messages=[
            {"role": "system", "content": EXPLAIN_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=EXPLAIN_TEMPERATURE,
        reasoning_effort=EXPLAIN_REASONING_EFFORT,
        **_extra_proveedor(),
        response_format={"type": "json_object"},
    )

    raw = resp.choices[0].message.content.strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {
            "score": int(job.get("similarity", 0) * 100),
            "matches": [],
            "gaps": [],
            "explicacion": "No se pudo generar explicación detallada (error del modelo).",
        }
    return result


def _veredicto_de_respaldo(job: dict, motivo: str) -> dict:
    """Si el LLM falla para UNA oferta (límite de Groq, timeout), la búsqueda
    sigue: esa oferta queda con el score de la etapa 1 y una aclaración."""
    return {
        "score": int(job.get("similarity", 0) * 100),
        "matches": [],
        "gaps": [],
        "explicacion": f"No se pudo generar la explicación ({motivo}).",
        "llm_error": True,
    }


# Fuentes cuyo listado no trae descripción y de las que se puede traer el
# aviso completo. Hoy sólo Computrabajo (ver sources/computrabajo.py).
DESCRIPCION_MAX_PARALLEL = 3


def completar_descripciones(jobs: list[dict]) -> int:
    """Trae la descripción completa de las finalistas que llegaron sin ella,
    ANTES de que las lea el LLM. Agregado el 22/10/2026: en producción, 9 de
    las 10 ofertas mostradas eran de Computrabajo sin descripción, o sea que
    el LLM las puntuaba sólo por el título. Se hace sólo con las finalistas
    (no con las ~250 ofertas del listado) para no sumar demasiado tiempo ni
    pegarle de más al sitio. Devuelve cuántas se completaron."""
    faltan = [j for j in jobs if not (j.get("description") or "").strip()
              and j.get("source") == "computrabajo" and j.get("url")]
    if not faltan:
        return 0
    from sources.computrabajo import fetch_full_description

    def _traer(job):
        try:
            return fetch_full_description(job["url"])
        except Exception as e:  # noqa: BLE001
            print(f"    [descripciones] error en {job.get('url')}: {e}")
            return ""

    with ThreadPoolExecutor(max_workers=DESCRIPCION_MAX_PARALLEL) as pool:
        textos = list(pool.map(_traer, faltan))
    completadas = 0
    for job, texto in zip(faltan, textos):
        if texto:
            job["description"] = texto
            completadas += 1
    return completadas


def explain_many(cv_text: str, jobs: list[dict], max_workers: int | None = None) -> list[dict]:
    """explain_match sobre varias ofertas EN PARALELO. Devuelve los veredictos
    en el mismo orden que `jobs`. Un error en una oferta no tumba al resto."""
    if not jobs:
        return []
    workers = max(1, min(max_workers or LLM_MAX_PARALLEL, len(jobs)))

    def _uno(job):
        try:
            return explain_match(cv_text, job)
        except Exception as e:  # noqa: BLE001 — cualquier falla de la API
            print(f"    [LLM] error en '{job.get('title', '')[:40]}': {e}")
            return _veredicto_de_respaldo(job, type(e).__name__)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_uno, jobs))


def rank_and_explain(
    cv_text: str,
    jobs: list[dict],
    embedding_top_k: int = 30,
    explain_top_n: int = 30,
    show_top_n: int | None = None,
    cand_location=None,
) -> list[dict]:
    """
    Pipeline completo de matching: prefiltro por embeddings + análisis LLM
    sobre los finalistas. Devuelve la lista final ordenada, con "similarity"
    (etapa 1) y "score"/"matches"/"gaps"/"explicacion" (etapa 2).

    explain_top_n: cuántas finalistas LEE el LLM.
    show_top_n:    cuántas se DEVUELVEN, las mejores según el LLM (None = todas).

    Separar las dos cosas es el cambio del 13/10/2026: antes el LLM leía sólo
    las 10 que se mostraban, así que una oferta buena que los embeddings
    dejaban en el puesto 15 nunca llegaba al usuario. Las evals mostraron que
    eso pasaba con ~13% de las ofertas relevantes (ver evals/).

    cand_location: un geo.Location (o None). Si viene, cada oferta se anota
    con la cercanía candidato↔oferta y el orden final usa el score YA
    ajustado por cercanía (score_final = score * factor_geo). El "score" del
    LLM queda intacto para mostrarlo y para BI; la penalización sólo aplica
    a ofertas presenciales/híbridas con ubicación conocida de ambos lados
    (nunca a remotas, ni a modalidad/ubicación desconocida). Ver geo.py.
    """
    import time as _time
    from collections import Counter

    t0 = _time.perf_counter()
    finalists = prefilter_by_embeddings(cv_text, jobs, top_k=embedding_top_k)
    t_emb = _time.perf_counter() - t0
    print(f"Prefiltro por embeddings: {len(jobs)} → {len(finalists)} finalistas ({t_emb:.1f}s)")

    to_explain = finalists[:explain_top_n]
    print(f"Analizando con IA {len(to_explain)} ofertas finalistas "
          f"({min(LLM_MAX_PARALLEL, max(1, len(to_explain)))} en paralelo)...")

    t0 = _time.perf_counter()
    n_completadas = completar_descripciones(to_explain)
    sin_desc = sum(1 for j in to_explain if not (j.get("description") or "").strip())
    print(f"[descripciones] {n_completadas} completadas en {_time.perf_counter() - t0:.1f}s | siguen sin descripción: {sin_desc}")

    t0 = _time.perf_counter()
    veredictos = explain_many(cv_text, to_explain)
    print(f"[LLM] {len(to_explain)} ofertas en {_time.perf_counter() - t0:.1f}s")
    results = []
    for job, verdict in zip(to_explain, veredictos):
        job.update(verdict)
        results.append(job)

    if cand_location is not None:
        import geo

        for job in results:
            geo.annotate_job(job, cand_location)
        results.sort(key=geo.sort_key_score_final, reverse=True)
    else:
        results.sort(key=lambda j: j.get("score", 0), reverse=True)
    final = results[:show_top_n] if show_top_n else results
    # De qué portales salen las ofertas que se muestran (diagnóstico en logs)
    print("[fuentes del resultado] " + ", ".join(f"{k} {v}" for k, v in Counter(j.get("source", "?") for j in final).most_common())
          + f" | sin descripción: {sum(1 for j in final if not j.get('description'))}")
    return final
