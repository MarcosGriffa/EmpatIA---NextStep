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
EXPLAIN_MODEL = "openai/gpt-oss-120b"

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


def _get_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("Falta GROQ_API_KEY en el .env.")
    return Groq(api_key=api_key)


EXPLAIN_SYSTEM_PROMPT = """\
Sos un reclutador experto. Vas a recibir un CV y la descripción de una
oferta de trabajo. Tu tarea es evaluar si la persona del CV es un buen
candidato para esa oferta, leyendo y entendiendo ambos textos (no solo
comparando palabras sueltas).

Devolvé ÚNICAMENTE un JSON con este esquema:
{
  "score": número entero 0-100 — qué tan buen match es,
  "matches": ["2 a 4 razones concretas", "por las que sí matchea"],
  "gaps": ["0 a 3 cosas", "que pide la oferta", "y no se ven en el CV"],
  "explicacion": "1-2 frases en español, tono directo, explicando el veredicto"
}
Devolvé SOLO el JSON.
"""


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
        temperature=0.3,
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


def rank_and_explain(
    cv_text: str,
    jobs: list[dict],
    embedding_top_k: int = 30,
    explain_top_n: int = 15,
    cand_location=None,
) -> list[dict]:
    """
    Pipeline completo de matching: prefiltro por embeddings + explicación LLM
    sobre los finalistas. Devuelve la lista final ordenada, con "similarity"
    (etapa 1) y "score"/"matches"/"gaps"/"explicacion" (etapa 2).

    cand_location: un geo.Location (o None). Si viene, cada oferta se anota
    con la cercanía candidato↔oferta y el orden final usa el score YA
    ajustado por cercanía (score_final = score * factor_geo). El "score" del
    LLM queda intacto para mostrarlo y para BI; la penalización sólo aplica
    a ofertas presenciales/híbridas con ubicación conocida de ambos lados
    (nunca a remotas, ni a modalidad/ubicación desconocida). Ver geo.py.
    """
    finalists = prefilter_by_embeddings(cv_text, jobs, top_k=embedding_top_k)
    print(f"Prefiltro por embeddings: {len(jobs)} → {len(finalists)} finalistas")

    to_explain = finalists[:explain_top_n]
    print(f"Generando explicaciones con IA para {len(to_explain)} ofertas finalistas...")

    results = []
    for i, job in enumerate(to_explain, 1):
        print(f"  [{i}/{len(to_explain)}] {job['title'][:50]}...")
        verdict = explain_match(cv_text, job)
        job.update(verdict)
        results.append(job)

    if cand_location is not None:
        import geo

        for job in results:
            geo.annotate_job(job, cand_location)
        results.sort(key=geo.sort_key_score_final, reverse=True)
    else:
        results.sort(key=lambda j: j.get("score", 0), reverse=True)
    return results
