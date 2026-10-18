"""
comparar.py — Compara dos corridas de evals (antes / después de un cambio).

Uso:
    python evals/comparar.py evals/salida evals/salida_v2

Escribe <después>/comparacion.json (lo usa el reporte HTML) y
<después>/bi/comparacion.csv (para Power BI), y muestra la tabla en consola.
"""

from __future__ import annotations

import sys as _sys

if hasattr(_sys.stdout, "reconfigure"):
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import csv
import json
import sys
from pathlib import Path

METRICAS = [
    # (clave, sección, nombre, mejor si sube)
    ("recall10_final", "global", "Relevantes que llegan al top 10 final (%)", True),
    ("ndcg10_final", "global", "nDCG@10 del resultado final (%)", True),
    ("p5_final", "global", "Precisión@5 (%)", True),
    ("p10_final", "global", "Precisión@10 (%)", True),
    ("mrr_final", "global", "MRR (primera relevante)", True),
    ("relevantes_no_leidas", "global", "Relevantes que el LLM nunca lee", False),
    ("spearman", "calibracion", "Correlación score ↔ relevancia", True),
    ("delta_promedio", "consistencia", "Variación del score al repetir (pts)", False),
    ("pct_delta_10_o_mas", "consistencia", "Repeticiones con 10+ pts de diferencia (%)", False),
    ("costo_por_busqueda_usd", "costo", "Costo por búsqueda (USD)", False),
    ("latencia_busqueda_ms_promedio", "costo", "Tiempo por búsqueda (ms)", False),
]


def valor(r: dict, clave: str, seccion: str):
    v = r.get(seccion, {}).get(clave)
    if v is None and clave == "recall10_final":  # corridas viejas: el top 10 final = top 10 de embeddings
        v = r["global"].get("recall10_emb")
    return v


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    antes_dir, desp_dir = Path(sys.argv[1]), Path(sys.argv[2])
    a = json.loads((antes_dir / "resumen.json").read_text(encoding="utf-8"))
    d = json.loads((desp_dir / "resumen.json").read_text(encoding="utf-8"))
    if a["dataset"]["n_cvs"] != d["dataset"]["n_cvs"]:
        print(f"[!] Ojo: las corridas tienen distinta cantidad de CVs ({a['dataset']['n_cvs']} vs {d['dataset']['n_cvs']}).")

    filas = []
    for clave, sec, nombre, sube in METRICAS:
        va, vd = valor(a, clave, sec), valor(d, clave, sec)
        delta = None if va is None or vd is None else round(vd - va, 4)
        mejora = None if delta is None or delta == 0 else (delta > 0) == sube
        filas.append({"metrica": nombre, "clave": clave, "antes": va, "despues": vd, "delta": delta,
                      "mejora": mejora})

    def cfg(r):
        m = r["meta"]
        return (f"LLM lee {m['explain_top_n']}, muestra {m.get('show_top_n', m['explain_top_n'])}, "
                f"temperature {m.get('temperature', 0.3)}, razonamiento {m.get('reasoning_effort', 'medium (default)')}, "
                f"{m.get('llm_paralelo', 1)} en paralelo")

    out = {"antes": {"carpeta": str(antes_dir), "config": cfg(a), "fecha": a["meta"]["fecha"]},
           "despues": {"carpeta": str(desp_dir), "config": cfg(d), "fecha": d["meta"]["fecha"]},
           "filas": filas}
    (desp_dir / "comparacion.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    (desp_dir / "bi").mkdir(exist_ok=True)
    with open(desp_dir / "bi" / "comparacion.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)

    print(f"ANTES:   {cfg(a)}\nDESPUÉS: {cfg(d)}\n")
    print(f"{'Métrica':48} {'Antes':>10} {'Después':>10} {'Δ':>9}")
    for f_ in filas:
        marca = {True: "  ✓", False: "  ✗", None: ""}[f_["mejora"]]
        fmt = lambda v: "—" if v is None else (f"{v:.4f}" if isinstance(v, float) and abs(v) < 1 else f"{v:,.1f}")
        print(f"{f_['metrica']:48} {fmt(f_['antes']):>10} {fmt(f_['despues']):>10} {fmt(f_['delta']):>9}{marca}")


if __name__ == "__main__":
    main()
