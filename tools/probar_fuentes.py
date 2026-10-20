"""
probar_fuentes.py — Prueba cada portal de empleo por separado y muestra
cuántas ofertas trae, para saber cuáles andan y cuáles no.

Uso (desde la raíz del repo):
    python tools/probar_fuentes.py                 # todas, con "analista de datos"
    python tools/probar_fuentes.py getonboard      # sólo una
    python tools/probar_fuentes.py todas "vendedor"
"""

from __future__ import annotations

import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import GENERAL_SOURCES, TECH_SOURCES  # noqa: E402


def main():
    filtro = sys.argv[1].lower() if len(sys.argv) > 1 else "todas"
    query = sys.argv[2] if len(sys.argv) > 2 else "analista de datos"
    fuentes = [s for s in GENERAL_SOURCES + TECH_SOURCES if filtro in ("todas", s.name)]
    if not fuentes:
        print(f"No hay una fuente llamada '{filtro}'.")
        return
    print(f"Búsqueda de prueba: '{query}'\n")
    for f in fuentes:
        q = query if not f.is_tech_vertical else "data analyst"
        t0 = time.perf_counter()
        jobs = f.search(q, max_results=10)
        dur = time.perf_counter() - t0
        estado = "OK " if jobs else "0  "
        print(f"  [{estado}] {f.name:15} {len(jobs):3d} ofertas en {dur:4.1f}s")
        for j in jobs[:2]:
            desc = "con descripción" if j.get("description") else "SIN descripción"
            print(f"         · {j['title'][:60]} — {j['company'][:25]} ({desc})")
    print("\nSi una fuente da 0, mirá el mensaje [ERROR] que imprimió arriba.")


if __name__ == "__main__":
    main()
