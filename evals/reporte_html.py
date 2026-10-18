"""
reporte_html.py — Arma el reporte HTML interactivo a partir de resumen.json.

Salida:
  evals/salida/reporte.html            página completa, se abre con doble clic
  evals/salida/reporte_fragmento.html  la misma página sin <html>/<head>, para
                                       publicarla como Artifact en claude.ai

Uso:
    python evals/reporte_html.py          (o --mock)
"""

from __future__ import annotations

import sys as _sys

# En la consola de Windows, sin esto los acentos y flechas rompen el print.
if hasattr(_sys.stdout, "reconfigure"):
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import argparse
import csv
import json
from pathlib import Path

from catalogo import ROLES

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--salida", default="")
    ap.add_argument("--por-rubro", type=int, default=0)  # lo pasa run_evals; resumen.json ya viene filtrado
    args = ap.parse_args()
    out = Path(args.salida) if args.salida else HERE / ("salida_mock" if args.mock else "salida")

    data = json.loads((out / "resumen.json").read_text(encoding="utf-8"))
    cvs = {}
    with open(HERE / "datos" / "cvs.jsonl", encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            cvs[c["cv_id"]] = c
    ofertas = {}
    with open(HERE / "datos" / "ofertas.jsonl", encoding="utf-8") as f:
        for line in f:
            o = json.loads(line)
            ofertas[o["oferta_id"]] = o

    scored = []
    with open(out / "bi" / "fact_llm_llamadas.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["repeticion"] == "0" and r["score"] not in ("", "None"):
                cv = cvs[r["cv_id"]]
                lab = f"{ROLES[cv['rol']]['nombre']} ({cv['seniority']}) → {ofertas[r['oferta_id']]['titulo']}"
                scored.append([int(r["relevancia"]), int(float(r["score"])), lab])
    data["scored"] = scored
    data["cv_labels"] = {k: f"{ROLES[c['rol']]['nombre']} {c['seniority']}" for k, c in cvs.items()}
    data.pop("ejemplos_error", None) if not data.get("ejemplos_error") else None
    data.setdefault("ejemplos_error", [])

    plantilla = (HERE / "plantilla_reporte.html").read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    fragmento = plantilla.replace("/*__DATA__*/null", payload)
    (out / "reporte_fragmento.html").write_text(fragmento, encoding="utf-8")
    completo = ("<!doctype html>\n<html lang=\"es\"><head><meta charset=\"utf-8\">"
                "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
                + fragmento.replace("<div class=\"wrap\">", "</head><body>\n<div class=\"wrap\">", 1)
                + "\n</body></html>\n")
    (out / "reporte.html").write_text(completo, encoding="utf-8")
    print(f"Reporte: {out / 'reporte.html'}")


if __name__ == "__main__":
    main()
