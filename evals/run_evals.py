"""
run_evals.py — Corre el motor de matching REAL de NextStep sobre el
dataset sintético y guarda cada resultado crudo.

Qué se usa del proyecto (sin modificarlo):
  - semantic_match.prefilter_by_embeddings  → etapa 1 (Cohere)
  - semantic_match.explain_match            → etapa 2 (Groq)
  - EMBEDDING_TOP_K / EXPLAIN_TOP_N de pipeline.py (se leen del archivo,
    sin importarlo, para no arrastrar los scrapers)

Lo único que se agrega es instrumentación: se "envuelven" los clientes de
Cohere y Groq para medir latencia y tokens de cada llamada. La lógica de
matching es exactamente la de producción.

Qué llamadas al LLM se hacen, por CV:
  produccion   las EXPLAIN_TOP_N finalistas, igual que en la web.
  what_if      hasta --extra ofertas de los puestos 11-30 de la etapa 1
               (relevantes + una no relevante). Producción NUNCA las manda
               al LLM; acá se miden para estimar qué se pierde.
  repeticion   --consistencia pares de producción se repiten una vez, para
               medir si el LLM da el mismo score dos veces.

Todo se guarda en evals/salida/*.jsonl a medida que avanza: si se corta
(límite diario de Groq, se cae internet, Ctrl+C), volver a correr el
script retoma desde donde quedó.

Uso:
    python evals/run_evals.py                 # corrida real (necesita .env)
    python evals/run_evals.py --mock          # simulada, sin APIs (para probar)
    python evals/run_evals.py --cvs 10        # sólo los primeros 10 CVs
"""

from __future__ import annotations

import sys as _sys

# En la consola de Windows, sin esto los acentos y flechas rompen el print.
if hasattr(_sys.stdout, "reconfigure"):
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

DATA = HERE / "datos"


def leer_constantes_pipeline(motor: Path = ROOT) -> tuple[int, int, int]:
    """(EMBEDDING_TOP_K, EXPLAIN_TOP_N = cuántas lee el LLM, SHOW_TOP_N =
    cuántas se muestran). Versiones viejas no tienen SHOW_TOP_N: ahí el LLM
    leía exactamente las que se mostraban."""
    txt = (motor / "pipeline.py").read_text(encoding="utf-8")
    k = int(re.search(r"^EMBEDDING_TOP_K\s*=\s*(\d+)", txt, re.M).group(1))
    m_n = re.search(r'^EXPLAIN_TOP_N\s*=\s*(?:int\(os\.getenv\("EXPLAIN_TOP_N",\s*"(\d+)"\)\)|(\d+))', txt, re.M)
    configurable = m_n.group(1) is not None
    n = int(m_n.group(1) or m_n.group(2))
    if configurable and os.getenv("EXPLAIN_TOP_N"):
        n = int(os.environ["EXPLAIN_TOP_N"])
    m = re.search(r"^SHOW_TOP_N\s*=\s*(\d+)", txt, re.M)
    return k, n, int(m.group(1)) if m else n


def leer_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def append_jsonl(path: Path, row: dict):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ── Instrumentación ─────────────────────────────────────────────
class Medidor:
    """Guarda la última medición de cada proveedor, para que el runner la
    asocie a la llamada que acaba de hacer."""

    def __init__(self, cache_path: Path | None = None):
        import threading

        self.embed_calls: list[dict] = []
        self.local = threading.local()  # cada hilo guarda su última llamada al LLM
        self.cache_path = cache_path
        self.cache_emb: dict[str, list[float]] = {}
        if cache_path and cache_path.exists():
            self.cache_emb = json.loads(cache_path.read_text(encoding="utf-8"))

    def guardar_cache(self):
        if self.cache_path:
            self.cache_path.write_text(json.dumps(self.cache_emb), encoding="utf-8")


def instrumentar(sm, medidor: Medidor):
    orig_cohere, orig_groq = sm._get_cohere, sm._get_client

    class CohereProxy:
        """Además de medir, cachea los vectores de las OFERTAS. Las 200
        ofertas son las mismas para los 40 CVs y el modelo es determinístico,
        así que reusar el vector da exactamente el mismo resultado que volver
        a pedirlo — pero evita mandar 200 textos por CV y chocar con el límite
        de la clave trial de Cohere (100.000 tokens/minuto, 40 llamadas/min).
        El cache se guarda en disco: una corrida retomada no vuelve a gastar."""

        def __init__(self, real):
            self._real = real

        def _llamar(self, **kw):
            espera = 30
            for intento in range(5):
                try:
                    return self._real.embed(**kw)
                except Exception as e:
                    if ("429" in str(e) or "rate limit" in str(e).lower()) and intento < 4:
                        print(f"      Cohere: límite por minuto, espero {espera}s...")
                        time.sleep(espera)
                        espera = min(espera * 2, 120)
                        continue
                    raise

        def embed(self, **kw):
            from types import SimpleNamespace

            t0 = time.perf_counter()
            textos = kw.get("texts", [])
            tipo = kw.get("input_type")
            tokens = 0
            if tipo == "search_document":
                faltan = [t for t in dict.fromkeys(textos) if t not in medidor.cache_emb]
                if faltan:
                    resp = self._llamar(**{**kw, "texts": faltan})
                    for t, v in zip(faltan, resp.embeddings.float_):
                        medidor.cache_emb[t] = v
                    medidor.guardar_cache()
                    try:
                        tokens = int(resp.meta.billed_units.input_tokens)
                    except Exception:
                        tokens = None
                resp = SimpleNamespace(embeddings=SimpleNamespace(float_=[medidor.cache_emb[t] for t in textos]))
                n_api = len(faltan)
            else:
                resp = self._llamar(**kw)
                try:
                    tokens = int(resp.meta.billed_units.input_tokens)
                except Exception:
                    tokens = None
                n_api = len(textos)
            medidor.embed_calls.append({
                "n_textos": len(textos), "n_textos_api": n_api, "tipo": tipo,
                "latencia_ms": round((time.perf_counter() - t0) * 1000), "tokens": tokens,
            })
            return resp

    class GroqProxy:
        def __init__(self, real):
            self._real = real
            self.chat = self
            self.completions = self

        def create(self, **kw):
            t0 = time.perf_counter()
            resp = self._real.chat.completions.create(**kw)
            u = getattr(resp, "usage", None)
            medidor.local.ultima = {
                "latencia_ms": round((time.perf_counter() - t0) * 1000),
                "tokens_in": getattr(u, "prompt_tokens", None),
                "tokens_out": getattr(u, "completion_tokens", None),
                "modelo": kw.get("model"),
            }
            return resp

    sm._get_cohere = lambda: CohereProxy(orig_cohere())
    sm._get_client = lambda: GroqProxy(orig_groq())


# ── Corrida ─────────────────────────────────────────────────────
def job_desde_oferta(of: dict) -> dict:
    """Misma forma que una oferta normalizada de sources/base.py."""
    return {
        "oferta_id": of["oferta_id"],
        "source": of["source"],
        "title": of["titulo"],
        "company": of["empresa"],
        "location": of["zona"],
        "modality": "",
        "description": of["descripcion"],
        "url": "",
    }


def es_error_de_cuota(e: Exception) -> bool:
    s = str(e).lower()
    return "rate limit" in s or "429" in s or "quota" in s or "tokens per day" in s


def llamar_llm(sm, medidor, cv_text, job, pausa) -> dict:
    """explain_match con reintentos ante límites por minuto. Si es el límite
    DIARIO, se propaga para cortar la corrida prolijamente."""
    espera = 20
    for intento in range(6):
        try:
            medidor.local.ultima = {}
            t0 = time.perf_counter()
            res = sm.explain_match(cv_text, dict(job))
            lat = round((time.perf_counter() - t0) * 1000)
            if pausa:
                time.sleep(pausa)
            return {**res, **{"latencia_ms": lat}, **medidor.local.ultima}
        except Exception as e:
            if "per day" in str(e).lower() or "tpd" in str(e).lower() or "rpd" in str(e).lower():
                raise
            if es_error_de_cuota(e) and intento < 5:
                print(f"      límite por minuto, espero {espera}s...")
                time.sleep(espera)
                espera = min(espera * 2, 120)
                continue
            raise
    raise RuntimeError("no se pudo llamar al LLM")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="sin APIs: embeddings y LLM simulados")
    ap.add_argument("--cvs", type=int, default=0, help="limitar a los primeros N CVs")
    ap.add_argument("--por-rubro", type=int, default=0,
                    help="usar sólo los primeros K CVs de cada rubro (muestra chica y balanceada)")
    ap.add_argument("--max-llamadas", type=int, default=0,
                    help="tope de llamadas al LLM en esta corrida (para no gastar todo el cupo diario de Groq)")
    ap.add_argument("--extra", type=int, default=4, help="llamadas what-if por CV (puestos 11-30)")
    ap.add_argument("--consistencia", type=int, default=30, help="pares de producción a repetir")
    ap.add_argument("--pausa", type=float, default=2.0, help="segundos entre llamadas a Groq")
    ap.add_argument("--paralelo", type=int, default=0,
                    help="llamadas al LLM en paralelo (default: LLM_MAX_PARALLEL de semantic_match, o 1)")
    ap.add_argument("--motor", default="",
                    help="carpeta con otra versión de semantic_match.py + pipeline.py (ej. evals/motor_v1)")
    ap.add_argument("--salida", default="", help="carpeta de salida (default evals/salida o evals/salida_mock)")
    args = ap.parse_args()

    out = Path(args.salida) if args.salida else HERE / ("salida_mock" if args.mock else "salida")
    out.mkdir(parents=True, exist_ok=True)
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")  # EXPLAIN_TOP_N, LLM_* y claves, igual que en producción
    except ImportError:
        pass

    if not (DATA / "cvs.jsonl").exists():
        print("No está el dataset. Corré primero: python evals/generar_dataset.py")
        sys.exit(1)

    cvs = leer_jsonl(DATA / "cvs.jsonl")
    ofertas = leer_jsonl(DATA / "ofertas.jsonl")
    if args.cvs:
        cvs = cvs[: args.cvs]
    if args.por_rubro:
        from muestra import seleccionar
        cvs = seleccionar(cvs, args.por_rubro)
    etiquetas = {}
    import csv
    with open(DATA / "etiquetas.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            etiquetas[(r["cv_id"], r["oferta_id"])] = int(r["relevancia"])

    motor = Path(args.motor).resolve() if args.motor else ROOT
    if args.motor:
        sys.path.insert(0, str(motor))
    top_k, top_n, show_n = leer_constantes_pipeline(motor)

    if args.mock:
        import mock_apis
        sm = mock_apis.semantic_match_simulado()
    else:
        import semantic_match as sm  # el módulo REAL del proyecto
    medidor = Medidor(out / "cache_embeddings.json")
    instrumentar(sm, medidor)

    meta = {
        "modo": "mock" if args.mock else "real",
        "motor": str(motor.relative_to(ROOT)) if motor != ROOT else "actual",
        "proveedor_llm": os.getenv("LLM_BASE_URL") or "groq",
        "embedding_model": sm.EMBEDDING_MODEL, "explain_model": sm.EXPLAIN_MODEL,
        "embedding_top_k": top_k, "explain_top_n": top_n, "show_top_n": show_n,
        "temperature": getattr(sm, "EXPLAIN_TEMPERATURE", 0.3),
        "reasoning_effort": getattr(sm, "EXPLAIN_REASONING_EFFORT", "medium (default)"),
        "llm_paralelo": args.paralelo or getattr(sm, "LLM_MAX_PARALLEL", 1),
        "n_cvs": len(cvs), "n_ofertas": len(ofertas),
        "fecha": time.strftime("%Y-%m-%d %H:%M"),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Modo {meta['modo'].upper()} | {len(cvs)} CVs × {len(ofertas)} ofertas | "
          f"etapa 1 top {top_k} → el LLM lee {top_n} → se muestran {show_n} ({sm.EXPLAIN_MODEL}, "
          f"{meta['llm_paralelo']} en paralelo)")

    # ── Etapa 1 ──
    f1 = out / "etapa1.jsonl"
    hechos1 = {r["cv_id"] for r in leer_jsonl(f1)}
    for i, cv in enumerate(cvs, 1):
        if cv["cv_id"] in hechos1:
            continue
        jobs = [job_desde_oferta(o) for o in ofertas]
        medidor.embed_calls = []
        t0 = time.perf_counter()
        finalistas = sm.prefilter_by_embeddings(cv["texto"], jobs, top_k=top_k)
        lat = round((time.perf_counter() - t0) * 1000)
        if all(j.get("similarity", 0) == 0 for j in jobs):
            print("[!] La etapa 1 devolvió similitud 0 para todo: falló Cohere (revisá COHERE_API_KEY). Corto acá.")
            sys.exit(2)
        orden = sorted(jobs, key=lambda j: j["similarity"], reverse=True)
        append_jsonl(f1, {
            "cv_id": cv["cv_id"],
            "ranking": [[j["oferta_id"], j["similarity"]] for j in orden],
            "finalistas": [j["oferta_id"] for j in finalistas],
            "latencia_ms": lat,
            "embed_calls": medidor.embed_calls,
        })
        print(f"[etapa 1] {i}/{len(cvs)} {cv['cv_id']} — {lat} ms")
    etapa1 = {r["cv_id"]: r for r in leer_jsonl(f1)}

    # ── Etapa 2: plan de llamadas ──
    rng = random.Random(7)
    plan = []
    for cv in cvs:
        orden = [o for o, _ in etapa1[cv["cv_id"]]["ranking"]]
        for oid in orden[:top_n]:
            plan.append((cv["cv_id"], oid, "produccion", 0))
        # what-if: las 20 siguientes a las que lee el LLM (producción no las ve)
        resto = orden[top_n:top_n + 20]
        rel = [o for o in resto if etiquetas[(cv["cv_id"], o)] >= 2]
        norel = [o for o in resto if etiquetas[(cv["cv_id"], o)] < 2]
        extra = rel[: max(0, args.extra - 1)]
        if norel and args.extra > 0:
            extra.append(rng.choice(norel))
        for oid in extra[: args.extra]:
            plan.append((cv["cv_id"], oid, "what_if", 0))
    prod = [p for p in plan if p[2] == "produccion"]
    for p in rng.sample(prod, min(args.consistencia, len(prod))):
        plan.append((p[0], p[1], "repeticion", 1))

    f2 = out / "etapa2.jsonl"
    hechos2 = {(r["cv_id"], r["oferta_id"], r["rep"]) for r in leer_jsonl(f2)}
    pendientes = [p for p in plan if (p[0], p[1], p[3]) not in hechos2]
    print(f"[etapa 2] {len(plan)} llamadas planificadas, {len(pendientes)} pendientes")

    cv_by_id = {c["cv_id"]: c for c in cvs}
    of_by_id = {o["oferta_id"]: o for o in ofertas}
    workers = 1 if args.mock else (args.paralelo or getattr(sm, "LLM_MAX_PARALLEL", 1))
    pausa = 0 if (args.mock or workers > 1) else args.pausa
    import threading
    from concurrent.futures import ThreadPoolExecutor

    lock = threading.Lock()
    hechas = [0]

    def ejecutar(item):
        cv_id, oid, proposito, rep = item
        res = llamar_llm(sm, medidor, cv_by_id[cv_id]["texto"], job_desde_oferta(of_by_id[oid]), pausa)
        json_ok = not str(res.get("explicacion", "")).startswith("No se pudo generar")
        with lock:
            append_jsonl(f2, {
                "cv_id": cv_id, "oferta_id": oid, "proposito": proposito, "rep": rep,
                "score": res.get("score"), "matches": res.get("matches", []), "gaps": res.get("gaps", []),
                "explicacion": res.get("explicacion", ""), "json_ok": json_ok,
                "latencia_ms": res.get("latencia_ms"), "tokens_in": res.get("tokens_in"),
                "tokens_out": res.get("tokens_out"), "modelo": res.get("modelo"),
            })
            hechas[0] += 1
            if hechas[0] % 10 == 0 or hechas[0] == len(pendientes):
                print(f"[etapa 2] {hechas[0]}/{len(pendientes)}")

    # Se agrupan por CV las llamadas de producción, como en una búsqueda real,
    # y se mide el tiempo de reloj de cada grupo (con N en paralelo, la
    # búsqueda tarda bastante menos que la suma de las llamadas).
    f_t = out / "etapa2_tiempos.jsonl"
    grupos: dict[tuple, list] = {}
    for p in pendientes:
        grupos.setdefault((p[0], p[2]), []).append(p)
    gastadas = 0
    for (cv_id, proposito), items in grupos.items():
        if args.max_llamadas and gastadas + len(items) > args.max_llamadas:
            print(f"\n[tope] Se llegó al máximo de {args.max_llamadas} llamadas para esta corrida.")
            print("    Lo hecho quedó guardado. Mañana corré el mismo comando y sigue desde acá.")
            sys.exit(0)
        gastadas += len(items)
        t0 = time.perf_counter()
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(ejecutar, items))
        except Exception as e:
            print(f"\n[!] Corte: {e}")
            print("    Lo hecho quedó guardado. Volvé a correr el script (mañana si es el límite diario).")
            sys.exit(2)
        if proposito == "produccion" and len(items) == top_n:
            append_jsonl(f_t, {"cv_id": cv_id, "n_llamadas": len(items), "paralelo": workers,
                               "wall_ms": round((time.perf_counter() - t0) * 1000)})

    print("\nCorrida completa. Calculando métricas y armando el reporte...\n")
    import subprocess
    extra = ["--mock"] if args.mock else []
    if args.por_rubro:
        extra += ["--por-rubro", str(args.por_rubro)]
    if args.salida:
        extra += ["--salida", str(out)]
    subprocess.run([sys.executable, str(HERE / "metricas.py"), *extra], check=True)
    subprocess.run([sys.executable, str(HERE / "reporte_html.py"), *extra], check=True)


if __name__ == "__main__":
    main()
