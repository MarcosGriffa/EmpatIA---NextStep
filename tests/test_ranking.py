"""
test_ranking.py — Tests de semantic_match.explain_many y rank_and_explain
(cambio del 13/10/2026: el LLM lee 30 finalistas en paralelo y se muestran 10).

No usa pytest ni llama a ninguna API: se reemplazan prefilter_by_embeddings
y explain_match por versiones falsas. Corré:  python tests/test_ranking.py
"""

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import semantic_match as sm  # noqa: E402

_fallos: list[str] = []


def eq(got, want, msg):
    ok = got == want
    print(f"  [{'ok  ' if ok else 'FALLA'}] {msg}  (esperado={want!r}, obtenido={got!r})")
    if not ok:
        _fallos.append(msg)


jobs = [{"title": f"Oferta {i}", "similarity": 0.9 - i * 0.01, "score_falso": (i * 37) % 100} for i in range(30)]
hilos = set()


def explain_falso(cv_text, job):
    hilos.add(threading.get_ident())
    time.sleep(0.05)
    if job["title"] == "Oferta 7":
        raise RuntimeError("429 rate limit (simulado)")
    return {"score": job["score_falso"], "matches": [], "gaps": [], "explicacion": "ok"}


sm.explain_match = explain_falso
sm.prefilter_by_embeddings = lambda cv, js, top_k=30: js[:top_k]

print("\n== explain_many ==")
t0 = time.perf_counter()
v = sm.explain_many("cv", jobs[:12], max_workers=6)
dur = time.perf_counter() - t0
eq([x["score"] for i, x in enumerate(v) if i != 7], [jobs[i]["score_falso"] for i in range(12) if i != 7],
   "devuelve los veredictos en el mismo orden que las ofertas")
eq(v[7].get("llm_error"), True, "si una llamada falla, esa oferta queda marcada y el resto sigue")
eq(v[7]["score"], int(jobs[7]["similarity"] * 100), "la oferta que falló usa la similitud como score de respaldo")
eq(len(hilos) > 1, True, "corre en más de un hilo")
eq(dur < 0.05 * 12 * 0.6, True, "en paralelo tarda bastante menos que en serie")

print("\n== rank_and_explain ==")
r = sm.rank_and_explain("cv", [dict(j) for j in jobs], embedding_top_k=30, explain_top_n=30, show_top_n=10)
eq(len(r), 10, "lee 30 y devuelve sólo las 10 mejores")
scores = [x["score"] for x in r]
eq(scores, sorted(scores, reverse=True), "las devuelve ordenadas por score")
mejor_fuera_de_10 = max(jobs[10:], key=lambda j: j["score_falso"])
eq(mejor_fuera_de_10["title"] in [x["title"] for x in r], True,
   "una oferta buena en el puesto 11-30 de los embeddings puede llegar al resultado")
r_all = sm.rank_and_explain("cv", [dict(j) for j in jobs], embedding_top_k=30, explain_top_n=10)
eq(len(r_all), 10, "sin show_top_n devuelve todas las que leyó (uso de notificaciones_semanales.py)")

print("\n== completar_descripciones ==")
import sources.computrabajo as ct  # noqa: E402

pedidas = []
ct.fetch_full_description = lambda url: (pedidas.append(url), "" if "rota" in url else f"Descripción de {url}")[1]
finalistas = [
    {"title": "A", "source": "computrabajo", "url": "https://ct/a", "description": ""},
    {"title": "B", "source": "computrabajo", "url": "https://ct/b", "description": "ya tenía"},
    {"title": "C", "source": "jooble", "url": "https://jb/c", "description": ""},
    {"title": "D", "source": "computrabajo", "url": "https://ct/rota", "description": ""},
]
n = sm.completar_descripciones(finalistas)
eq(n, 1, "completa sólo las de Computrabajo sin descripción que se pudieron traer")
eq(finalistas[0]["description"], "Descripción de https://ct/a", "la descripción queda en la oferta")
eq(finalistas[1]["description"], "ya tenía", "no pisa una descripción que ya existía")
eq("https://jb/c" in pedidas, False, "no le pide nada a otros portales")
eq(finalistas[3]["description"], "", "si falla la descarga, la oferta sigue igual")

print()
if _fallos:
    print(f"FALLARON {len(_fallos)} test(s).")
    sys.exit(1)
print("Todos los tests pasaron.")
