"""
test_collect.py — Tests de pipeline.collect_jobs con fuentes FALSAS (sin red).
Verifica que la búsqueda en paralelo devuelve lo mismo que en serie, más
rápido, y respetando el tope de pedidos simultáneos por fuente.

Corré:  python tests/test_collect.py
"""

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pipeline  # noqa: E402

_fallos: list[str] = []


def eq(got, want, msg):
    ok = got == want
    print(f"  [{'ok  ' if ok else 'FALLA'}] {msg}  (esperado={want!r}, obtenido={got!r})")
    if not ok:
        _fallos.append(msg)


class Falsa:
    def __init__(self, name, demora):
        self.name, self.demora = name, demora
        self.activos = 0
        self.max_activos = 0
        self.lock = threading.Lock()

    def search(self, query, max_results=25):
        with self.lock:
            self.activos += 1
            self.max_activos = max(self.max_activos, self.activos)
        time.sleep(self.demora)
        with self.lock:
            self.activos -= 1
        if query == "rompe":
            raise RuntimeError("fuente caída (simulado)")
        return [{"title": f"{self.name} {query} {i}", "company": f"Emp {self.name}", "url": f"https://{self.name}/{query}/{i}"}
                for i in range(2)]


ct, jb = Falsa("computrabajo", 0.2), Falsa("jooble", 0.1)
queries = ["analista", "datos", "bi", "sql", "rompe"]

t0 = time.perf_counter()
jobs = pipeline.collect_jobs(queries, [], False, general_sources=[ct, jb])
dur = time.perf_counter() - t0

print("\n== collect_jobs en paralelo ==")
eq(len(jobs), 2 * 4 * 2, "trae todas las ofertas (una query falla y el resto sigue)")
eq([j["title"] for j in jobs][:2], ["computrabajo analista 0", "computrabajo analista 1"], "respeta el orden fuente → query")
eq(ct.max_activos <= 2, True, "nunca más de 2 pedidos a la vez a Computrabajo")
serie = 5 * 0.2 + 5 * 0.1
eq(dur < serie * 0.7, True, f"tarda menos que en serie ({dur:.2f}s vs {serie:.2f}s)")

print("\n== deduplicación: se queda la versión con descripción ==")


class ConDesc(Falsa):
    def search(self, query, max_results=25):
        return [{"title": "Analista de Datos", "company": "Acme", "url": "https://jooble/x", "source": "jooble",
                 "description": "Buscamos analista con SQL y Power BI."}]


class SinDesc(Falsa):
    def search(self, query, max_results=25):
        return [{"title": "Analista de datos", "company": "ACME", "url": "https://ct/x", "source": "computrabajo",
                 "description": ""}]


r = pipeline.collect_jobs(["q"], [], False, general_sources=[SinDesc("computrabajo", 0), ConDesc("jooble", 0)])
eq(len(r), 1, "el mismo aviso en dos portales queda una sola vez")
eq(r[0]["description"], "Buscamos analista con SQL y Power BI.", "se queda con la descripción más completa")
eq(r[0].get("fuentes"), ["computrabajo", "jooble"], "anota en qué portales apareció")

print()
if _fallos:
    print(f"FALLARON {len(_fallos)} test(s).")
    sys.exit(1)
print("Todos los tests pasaron.")
