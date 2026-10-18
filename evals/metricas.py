"""
metricas.py — Calcula las métricas de la evaluación y exporta las tablas
para Power BI y el resumen para el reporte HTML.

Entrada:  evals/datos/*  +  evals/salida/etapa1.jsonl, etapa2.jsonl
Salida:   evals/salida/resumen.json        (lo lee reporte_html.py)
          evals/salida/bi/*.csv            (modelo estrella para Power BI)

Métricas (todas sobre la etiqueta por reglas, "relevante" = relevancia ≥ 2):

  Etapa 1 — embeddings (Cohere)
    recall@10   de todas las ofertas relevantes, cuántas quedan entre las
                10 que pasan al LLM. Es el techo del sistema: lo que no
                entra acá, el usuario nunca lo ve.
    recall@30   ídem con las 30 "finalistas" de EMBEDDING_TOP_K.
    nDCG@10     calidad del orden de los embeddings solos (ganancia 2^rel-1).

  Etapa 2 — LLM (Groq)
    nDCG@10 final    el top 10 que ve el usuario, ordenado por score del LLM.
    nDCG@10 interno  qué tan bien ordena el LLM las 10 que recibió,
                     comparado con el mejor orden posible de esas mismas 10.
                     Aísla al LLM de los errores de la etapa 1.
    precision@5/@10, MRR (posición de la primera relevante).
    calibración      score promedio del LLM por nivel de relevancia,
                     correlación de Spearman, y precisión/recall por umbral.
    consistencia     diferencia de score al repetir el mismo par.

  Costo y latencia (tokens reales informados por las APIs)
    costo por búsqueda y estimación de "mandar todo al LLM" (sin etapa 1).

Uso:
    python evals/metricas.py          (o --mock para la salida simulada)
"""

from __future__ import annotations

import sys as _sys

# En la consola de Windows, sin esto los acentos y flechas rompen el print.
if hasattr(_sys.stdout, "reconfigure"):
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

HERE = Path(__file__).resolve().parent
DATA = HERE / "datos"

# Precios de referencia en USD por millón de tokens. EDITABLES: revisar la
# página de precios de cada proveedor antes de publicar números de costo.
PRECIO_LLM_IN = 0.15     # Groq — openai/gpt-oss-120b, input
PRECIO_LLM_OUT = 0.60    # Groq — openai/gpt-oss-120b, output
PRECIO_EMBED = 0.10      # Cohere — embed-multilingual-v3.0

from catalogo import ROLES, RUBRO_LABEL, SENIORITIES  # noqa: E402

REL_LABEL = {3: "Match fuerte", 2: "Match parcial", 1: "Relacionado", 0: "No relevante"}


def leer_jsonl(p: Path) -> list[dict]:
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def dcg(rels: list[int]) -> float:
    return sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rels))


def ndcg(rels: list[int], ideal: list[int], k: int) -> float:
    idcg = dcg(sorted(ideal, reverse=True)[:k])
    return dcg(rels[:k]) / idcg if idcg else 0.0


def spearman(x: list[float], y: list[float]) -> float:
    def rank(v):
        orden = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(orden):
            j = i
            while j + 1 < len(orden) and v[orden[j + 1]] == v[orden[i]]:
                j += 1
            for t in range(i, j + 1):
                r[orden[t]] = (i + j) / 2 + 1
            i = j + 1
        return r
    rx, ry = rank(x), rank(y)
    mx, my = mean(rx), mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else 0.0


def pct(x: float) -> float:
    return round(100 * x, 1)


def p95(v: list[float]) -> float:
    s = sorted(v)
    return s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))] if s else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--salida", default="")
    ap.add_argument("--por-rubro", type=int, default=0, help="calcular sólo sobre los primeros K CVs de cada rubro")
    args = ap.parse_args()
    out = Path(args.salida) if args.salida else HERE / ("salida_mock" if args.mock else "salida")
    bi = out / "bi"
    bi.mkdir(parents=True, exist_ok=True)

    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    # top_n = cuántas LEE el LLM; show_n = cuántas se muestran. En la versión
    # original del motor eran el mismo número (10).
    top_k, top_n = meta["embedding_top_k"], meta["explain_top_n"]
    show_n = meta.get("show_top_n", top_n)
    tiempos = {}
    if (out / "etapa2_tiempos.jsonl").exists():
        tiempos = {r["cv_id"]: r["wall_ms"] for r in leer_jsonl(out / "etapa2_tiempos.jsonl")}
    cvs = {c["cv_id"]: c for c in leer_jsonl(DATA / "cvs.jsonl")}
    ofertas = {o["oferta_id"]: o for o in leer_jsonl(DATA / "ofertas.jsonl")}
    etq, motivo = {}, {}
    with open(DATA / "etiquetas.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            etq[(r["cv_id"], r["oferta_id"])] = int(r["relevancia"])
            motivo[(r["cv_id"], r["oferta_id"])] = r["motivo"]

    etapa1 = {r["cv_id"]: r for r in leer_jsonl(out / "etapa1.jsonl")}
    llamadas = leer_jsonl(out / "etapa2.jsonl")
    llm = {(r["cv_id"], r["oferta_id"]): r for r in llamadas if r["rep"] == 0}
    if args.por_rubro:
        from muestra import seleccionar
        elegidos = {c["cv_id"] for c in seleccionar(list(cvs.values()), args.por_rubro)}
        etapa1 = {k: v for k, v in etapa1.items() if k in elegidos}
        llamadas = [r for r in llamadas if r["cv_id"] in elegidos]
        llm = {k: v for k, v in llm.items() if k[0] in elegidos}
    cv_ids = [c for c in cvs if c in etapa1]

    # Costo y latencia de embeber TODAS las ofertas una vez (la búsqueda
    # que no tuvo cache). max() porque una sola corrida las tiene completas.
    def _docs(r, campo):
        return sum((c.get(campo) or 0) for c in r["embed_calls"] if c.get("tipo") == "search_document")
    doc_tokens = max((_docs(r, "tokens") for r in etapa1.values()), default=0)
    doc_lat = max((_docs(r, "latencia_ms") for r in etapa1.values()), default=0)

    # ── Por CV ──
    filas_cv, pares = [], []
    for cv_id in cv_ids:
        cv = cvs[cv_id]
        ranking = etapa1[cv_id]["ranking"]
        orden_emb = [oid for oid, _ in ranking]
        sim = dict(ranking)
        rels_emb = [etq[(cv_id, o)] for o in orden_emb]
        todas = [etq[(cv_id, o)] for o in ofertas]
        n_rel = sum(r >= 2 for r in todas)

        leidas = orden_emb[:top_n]
        completo = all((cv_id, o) in llm for o in leidas)
        # mismo orden que rank_and_explain: score desc, empates en orden de etapa 1
        final_todas = sorted(leidas, key=lambda o: llm.get((cv_id, o), {}).get("score") or 0, reverse=True) if completo else []
        final = final_todas[:show_n]
        rels_final_todas = [etq[(cv_id, o)] for o in final_todas]
        rels_final = [etq[(cv_id, o)] for o in final]
        rank_final = {o: i + 1 for i, o in enumerate(final)}
        rank_emb = {o: i + 1 for i, o in enumerate(orden_emb)}

        primera = next((i + 1 for i, r in enumerate(rels_final) if r >= 2), None)
        e1 = etapa1[cv_id]
        # Las ofertas se embeben una sola vez y se cachean (ver run_evals.py),
        # pero en producción cada búsqueda las embebe todas: para costo y
        # latencia se suma el embedding completo de las ofertas a cada CV.
        q_calls = [c for c in e1["embed_calls"] if c.get("tipo") == "search_query"]
        emb_tokens = sum((c.get("tokens") or 0) for c in q_calls) + doc_tokens
        lat_e1 = sum(c.get("latencia_ms") or 0 for c in q_calls) + doc_lat
        llm_cv = [r for r in llamadas if r["cv_id"] == cv_id and r["proposito"] == "produccion"]
        tin = sum(r.get("tokens_in") or 0 for r in llm_cv)
        tout = sum(r.get("tokens_out") or 0 for r in llm_cv)
        costo = emb_tokens * PRECIO_EMBED / 1e6 + tin * PRECIO_LLM_IN / 1e6 + tout * PRECIO_LLM_OUT / 1e6

        filas_cv.append({
            "cv_id": cv_id,
            "n_relevantes": n_rel,
            "recall10_emb": round(sum(r >= 2 for r in rels_emb[:show_n]) / n_rel, 4) if n_rel else None,
            "recall_leidas": round(sum(r >= 2 for r in rels_emb[:top_n]) / n_rel, 4) if n_rel else None,
            "recall10_final": round(sum(r >= 2 for r in rels_final) / n_rel, 4) if n_rel and completo else None,
            "recall30_emb": round(sum(r >= 2 for r in rels_emb[:top_k]) / n_rel, 4) if n_rel else None,
            "ndcg10_emb": round(ndcg(rels_emb, todas, 10), 4),
            "ndcg10_final": round(ndcg(rels_final, todas, 10), 4) if completo else None,
            "ndcg10_interno": round(ndcg(rels_final_todas, rels_emb[:top_n], 10), 4) if completo and any(rels_emb[:top_n]) else None,
            "ndcg10_interno_emb": round(ndcg(rels_emb[:top_n], rels_emb[:top_n], 10), 4) if any(rels_emb[:top_n]) else None,
            "p5_final": round(sum(r >= 2 for r in rels_final[:5]) / 5, 4) if completo else None,
            "p10_final": round(sum(r >= 2 for r in rels_final[:10]) / 10, 4) if completo else None,
            "mrr_final": round(1 / primera, 4) if primera else 0.0,
            "relevantes_no_leidas": sum(r >= 2 for r in rels_emb[top_n:]),
            "relevantes_en_final": sum(r >= 2 for r in rels_final),
            "relevantes_fuera_30": sum(r >= 2 for r in rels_emb[top_k:]),
            "trampas_en_top10": sum(1 for o in (final or orden_emb[:show_n]) if ofertas[o]["es_trampa"] and ofertas[o]["trampa_rubro"] == cv["rubro"]),
            "latencia_etapa1_ms": lat_e1,
            "latencia_etapa2_ms": tiempos.get(cv_id, sum(r.get("latencia_ms") or 0 for r in llm_cv)),
            "tokens_embed": emb_tokens, "tokens_llm_in": tin, "tokens_llm_out": tout,
            "costo_usd": round(costo, 6),
        })

        for oid, of in ofertas.items():
            r_llm = llm.get((cv_id, oid))
            rel = etq[(cv_id, oid)]
            if cv["rol"] == of["rol"]:
                tipo = "Mismo rol"
            elif cv["rubro"] == of["rubro"]:
                tipo = "Mismo rubro, otro rol"
            elif of["es_trampa"] and of["trampa_rubro"] == cv["rubro"]:
                tipo = "Trampa de vocabulario"
            elif rel == 1:
                tipo = "Rol afín"
            else:
                tipo = "Otro rubro"
            pares.append({
                "par_id": f"{cv_id}-{oid}", "cv_id": cv_id, "oferta_id": oid,
                "relevancia": rel, "motivo": motivo[(cv_id, oid)], "tipo_par": tipo,
                "gap_seniority": abs(SENIORITIES.index(cv["seniority"]) - SENIORITIES.index(of["seniority"])) if tipo == "Mismo rol" else None,
                "similarity": round(sim[oid] * 100, 2), "rank_emb": rank_emb[oid],
                "en_top10_emb": int(rank_emb[oid] <= show_n), "leida_por_llm": int(rank_emb[oid] <= top_n), "en_top30_emb": int(rank_emb[oid] <= top_k),
                "evaluado_llm": int(r_llm is not None), "proposito_llm": r_llm["proposito"] if r_llm else "",
                "score_llm": r_llm["score"] if r_llm else None,
                "rank_final": rank_final.get(oid), "en_resultado_final": int(oid in rank_final),
            })

    def prom(campo):
        v = [f[campo] for f in filas_cv if f[campo] is not None]
        return round(mean(v), 4) if v else None

    # ── Calibración ──
    puntuados = [(etq[(r["cv_id"], r["oferta_id"])], r["score"]) for r in llamadas
                 if r["rep"] == 0 and isinstance(r.get("score"), (int, float))]
    por_rel = {}
    for rel in (0, 1, 2, 3):
        v = [s for rr, s in puntuados if rr == rel]
        por_rel[rel] = {"n": len(v), "promedio": round(mean(v), 1) if v else None,
                        "mediana": median(v) if v else None,
                        "min": min(v) if v else None, "max": max(v) if v else None}
    umbrales = []
    for t in range(40, 95, 5):
        tp = sum(1 for r, s in puntuados if s >= t and r >= 2)
        fp = sum(1 for r, s in puntuados if s >= t and r < 2)
        fn = sum(1 for r, s in puntuados if s < t and r >= 2)
        umbrales.append({"umbral": t, "precision": pct(tp / (tp + fp)) if tp + fp else None,
                         "recall": pct(tp / (tp + fn)) if tp + fn else None, "n_sobre_umbral": tp + fp})

    # ── Consistencia ──
    base = {(r["cv_id"], r["oferta_id"]): r["score"] for r in llamadas if r["rep"] == 0}
    deltas = [abs(r["score"] - base[(r["cv_id"], r["oferta_id"])]) for r in llamadas
              if r["rep"] == 1 and (r["cv_id"], r["oferta_id"]) in base
              and isinstance(r.get("score"), (int, float)) and isinstance(base[(r["cv_id"], r["oferta_id"])], (int, float))]

    # ── What-if: relevantes en puestos 11-30 que el LLM nunca ve ──
    wi = [r for r in llamadas if r["proposito"] == "what_if"]
    rescatables = 0
    wi_rel = [r for r in wi if etq[(r["cv_id"], r["oferta_id"])] >= 2]
    for r in wi_rel:
        # ¿habría entrado al top que se muestra? (supera al peor score mostrado)
        orden_cv = [o for o, _ in etapa1[r["cv_id"]]["ranking"]][:top_n]
        prod_scores = sorted([llm[(r["cv_id"], o)]["score"] or 0 for o in orden_cv if (r["cv_id"], o) in llm],
                             reverse=True)[:show_n]
        if prod_scores and r["score"] is not None and r["score"] > min(prod_scores):
            rescatables += 1

    # ── Por segmento ──
    def seg_metricas(filtro_cv):
        fs = [f for f in filas_cv if filtro_cv(cvs[f["cv_id"]])]
        def m(c):
            v = [f[c] for f in fs if f[c] is not None]
            return pct(mean(v)) if v else None
        return {"n_cvs": len(fs), "recall10_emb": m("recall10_emb"), "recall30_emb": m("recall30_emb"),
                "ndcg10_final": m("ndcg10_final"), "p5_final": m("p5_final"), "ndcg10_emb": m("ndcg10_emb")}

    por_rubro = {r: {"label": RUBRO_LABEL[r], **seg_metricas(lambda c, r=r: c["rubro"] == r)} for r in RUBRO_LABEL}
    por_seniority = {s: seg_metricas(lambda c, s=s: c["seniority"] == s) for s in SENIORITIES}
    por_seccion = {
        "con_seccion_skills": seg_metricas(lambda c: c["seccion_skills"]),
        "sin_seccion_skills": seg_metricas(lambda c: not c["seccion_skills"]),
    }

    # Trampas e idioma
    trampa_pares = [p for p in pares if p["tipo_par"] == "Trampa de vocabulario"]
    trampas = {
        "n_pares": len(trampa_pares),
        "en_top30": sum(p["en_top30_emb"] for p in trampa_pares),
        "en_top10": sum(p["en_top10_emb"] for p in trampa_pares),
        "score_llm_promedio": round(mean([p["score_llm"] for p in trampa_pares if p["score_llm"] is not None]), 1)
        if any(p["score_llm"] is not None for p in trampa_pares) else None,
        "rank_emb_promedio": round(mean([p["rank_emb"] for p in trampa_pares]), 1) if trampa_pares else None,
    }
    rel_pairs = [p for p in pares if p["relevancia"] >= 2]
    idioma = {}
    for lang in ("es", "en"):
        v = [p for p in rel_pairs if ofertas[p["oferta_id"]]["idioma"] == lang]
        idioma[lang] = {"n_pares_relevantes": len(v),
                        "recall10_emb": pct(mean([p["en_top10_emb"] for p in v])) if v else None,
                        "rank_emb_promedio": round(mean([p["rank_emb"] for p in v]), 1) if v else None,
                        "similarity_promedio": round(mean([p["similarity"] for p in v]), 1) if v else None}
    seniority_llm = {}
    for g in (0, 1, 2):
        v = [p["score_llm"] for p in pares if p["tipo_par"] == "Mismo rol" and p["gap_seniority"] == g and p["score_llm"] is not None]
        seniority_llm[str(g)] = {"n": len(v), "score_promedio": round(mean(v), 1) if v else None}

    # ── Costo ──
    prod_calls = [r for r in llamadas if r["proposito"] == "produccion"]
    tin = mean([r.get("tokens_in") or 0 for r in prod_calls]) if prod_calls else 0
    tout = mean([r.get("tokens_out") or 0 for r in prod_calls]) if prod_calls else 0
    costo_llamada = tin * PRECIO_LLM_IN / 1e6 + tout * PRECIO_LLM_OUT / 1e6
    costo_busqueda = mean([f["costo_usd"] for f in filas_cv]) if filas_cv else 0
    n_of = len(ofertas)
    emb_por_busqueda = mean([f["tokens_embed"] for f in filas_cv]) * PRECIO_EMBED / 1e6 if filas_cv else 0
    costo_todo_llm = costo_llamada * n_of
    lat_llm = [r["latencia_ms"] for r in prod_calls if r.get("latencia_ms")]

    resumen = {
        "meta": meta,
        "dataset": {
            "n_cvs": len(cv_ids), "n_ofertas": n_of, "n_pares": len(pares),
            "n_trampas": sum(o["es_trampa"] for o in ofertas.values()),
            "n_ingles": sum(o["idioma"] == "en" for o in ofertas.values()),
            "distribucion_relevancia": {REL_LABEL[r]: sum(1 for p in pares if p["relevancia"] == r) for r in (3, 2, 1, 0)},
            "llamadas_llm": len(llamadas),
        },
        "global": {
            "recall10_emb": pct(prom("recall10_emb")), "recall30_emb": pct(prom("recall30_emb")),
            "ndcg10_emb": pct(prom("ndcg10_emb")), "ndcg10_final": pct(prom("ndcg10_final") or 0),
            "ndcg10_interno": pct(prom("ndcg10_interno") or 0), "ndcg10_interno_emb": pct(prom("ndcg10_interno_emb") or 0),
            "p5_final": pct(prom("p5_final") or 0), "p10_final": pct(prom("p10_final") or 0),
            "mrr_final": round(prom("mrr_final") or 0, 3),
            "relevantes_total": sum(f["n_relevantes"] for f in filas_cv),
            "relevantes_no_leidas": sum(f["relevantes_no_leidas"] for f in filas_cv),
            "relevantes_en_final": sum(f["relevantes_en_final"] for f in filas_cv),
            "recall_leidas": pct(prom("recall_leidas")), "recall10_final": pct(prom("recall10_final") or 0),
            "relevantes_fuera_30": sum(f["relevantes_fuera_30"] for f in filas_cv),
            "cvs_con_top1_relevante": sum(1 for f in filas_cv if f["mrr_final"] == 1),
        },
        "calibracion": {"por_relevancia": por_rel, "spearman": round(spearman([r for r, _ in puntuados], [s for _, s in puntuados]), 3) if puntuados else None,
                        "umbrales": umbrales},
        "consistencia": {"n": len(deltas), "delta_promedio": round(mean(deltas), 1) if deltas else None,
                         "delta_max": max(deltas) if deltas else None,
                         "pct_delta_10_o_mas": pct(sum(d >= 10 for d in deltas) / len(deltas)) if deltas else None},
        "json_errores": {"n": sum(1 for r in llamadas if not r.get("json_ok", True)), "de": len(llamadas)},
        "what_if": {"llamadas": len(wi), "relevantes_evaluadas": len(wi_rel), "rescatables": rescatables},
        "trampas": trampas, "idioma": idioma, "seniority_llm": seniority_llm,
        "por_rubro": por_rubro, "por_seniority": por_seniority, "por_seccion_skills": por_seccion,
        "costo": {
            "precios_usd_por_millon": {"llm_in": PRECIO_LLM_IN, "llm_out": PRECIO_LLM_OUT, "embed": PRECIO_EMBED},
            "tokens_llm_in_promedio": round(tin), "tokens_llm_out_promedio": round(tout),
            "costo_por_busqueda_usd": round(costo_busqueda, 5),
            "costo_si_todo_al_llm_usd": round(costo_todo_llm, 5),
            "ahorro_pct": pct(1 - costo_busqueda / costo_todo_llm) if costo_todo_llm else None,
            "latencia_etapa1_ms_promedio": round(mean([f["latencia_etapa1_ms"] for f in filas_cv])) if filas_cv else None,
            "latencia_llm_ms_promedio": round(mean(lat_llm)) if lat_llm else None,
            "latencia_llm_ms_p95": p95(lat_llm),
            "latencia_busqueda_ms_promedio": round(mean([f["latencia_etapa1_ms"] + f["latencia_etapa2_ms"] for f in filas_cv])) if filas_cv else None,
        },
        "por_cv": filas_cv,
    }

    # Ejemplos para el reporte: los errores más llamativos del LLM
    ejemplos = []
    for r in llamadas:
        if r["rep"] != 0 or r.get("score") is None:
            continue
        rel = etq[(r["cv_id"], r["oferta_id"])]
        if (rel >= 3 and r["score"] < 50) or (rel == 0 and r["score"] >= 60):
            cv, of = cvs[r["cv_id"]], ofertas[r["oferta_id"]]
            ejemplos.append({
                "tipo": "Subestimó un match fuerte" if rel >= 3 else "Sobrestimó una no relevante",
                "cv": f"{ROLES[cv['rol']]['nombre']} ({cv['seniority']})", "oferta": of["titulo"],
                "relevancia": rel, "motivo": motivo[(r["cv_id"], r["oferta_id"])],
                "score": r["score"], "explicacion": r.get("explicacion", "")[:300],
            })
    resumen["ejemplos_error"] = sorted(ejemplos, key=lambda e: -abs(e["score"] - (85 if e["relevancia"] >= 3 else 10)))[:6]

    (out / "resumen.json").write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── Export estrella para Power BI ──
    def write(nombre, filas, campos=None):
        campos = campos or list(filas[0].keys())
        with open(bi / nombre, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=campos)
            w.writeheader()
            w.writerows(filas)

    write("dim_cv.csv", [{
        "cv_id": c["cv_id"], "rubro": RUBRO_LABEL[c["rubro"]], "rol": ROLES[c["rol"]]["nombre"],
        "seniority": c["seniority"], "orden_seniority": SENIORITIES.index(c["seniority"]),
        "anios_experiencia": c["anios"], "n_skills": len(c["skills"]),
        "seccion_skills": "Con sección de skills" if c["seccion_skills"] else "Sin sección de skills",
    } for c in cvs.values() if c["cv_id"] in etapa1])
    write("dim_oferta.csv", [{
        "oferta_id": o["oferta_id"], "titulo": o["titulo"], "empresa": o["empresa"],
        "rubro": RUBRO_LABEL[o["rubro"]], "rol": ROLES[o["rol"]]["nombre"], "seniority": o["seniority"],
        "idioma": "Inglés" if o["idioma"] == "en" else "Español", "es_trampa": int(o["es_trampa"]),
        "trampa_apunta_a": RUBRO_LABEL.get(o["trampa_rubro"], ""),
    } for o in ofertas.values()])
    write("dim_relevancia.csv", [{"relevancia": r, "etiqueta": REL_LABEL[r], "es_relevante": int(r >= 2)} for r in (3, 2, 1, 0)])
    write("fact_pares.csv", pares)
    write("fact_llm_llamadas.csv", [{
        "llamada_id": i + 1, "par_id": f"{r['cv_id']}-{r['oferta_id']}", "cv_id": r["cv_id"], "oferta_id": r["oferta_id"],
        "proposito": r["proposito"], "repeticion": r["rep"], "score": r["score"],
        "relevancia": etq[(r["cv_id"], r["oferta_id"])], "json_ok": int(r.get("json_ok", True)),
        "latencia_ms": r.get("latencia_ms"), "tokens_in": r.get("tokens_in"), "tokens_out": r.get("tokens_out"),
        "costo_usd": round((r.get("tokens_in") or 0) * PRECIO_LLM_IN / 1e6 + (r.get("tokens_out") or 0) * PRECIO_LLM_OUT / 1e6, 7),
    } for i, r in enumerate(llamadas)])
    write("fact_metricas_cv.csv", filas_cv)

    g = resumen["global"]
    print(f"Modo {meta['modo'].upper()} — {len(cv_ids)} CVs")
    print(f"  Etapa 1  recall@10 {g['recall10_emb']}% | recall@30 {g['recall30_emb']}% | nDCG@10 {g['ndcg10_emb']}%")
    print(f"  Final    nDCG@10 {g['ndcg10_final']}% | P@5 {g['p5_final']}% | MRR {g['mrr_final']}")
    print(f"  LLM ordena las 10: nDCG interno {g['ndcg10_interno']}% (embeddings solos: {g['ndcg10_interno_emb']}%)")
    print(f"  Spearman score↔relevancia: {resumen['calibracion']['spearman']} | consistencia Δ prom {resumen['consistencia']['delta_promedio']}")
    print(f"  Costo por búsqueda ${resumen['costo']['costo_por_busqueda_usd']} vs todo al LLM ${resumen['costo']['costo_si_todo_al_llm_usd']}")
    print(f"\nGuardado: {out / 'resumen.json'} y {bi}/*.csv")


if __name__ == "__main__":
    main()
