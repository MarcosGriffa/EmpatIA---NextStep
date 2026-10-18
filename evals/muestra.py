"""muestra.py — Elige un subconjunto chico y balanceado de CVs (los primeros K
de cada rubro), para correr evals sin gastar todo el cupo diario de Groq."""

from __future__ import annotations


def seleccionar(cvs: list[dict], por_rubro: int) -> list[dict]:
    if not por_rubro:
        return cvs
    vistos: dict[str, int] = {}
    elegidos = []
    for cv in cvs:
        if vistos.get(cv["rubro"], 0) < por_rubro:
            vistos[cv["rubro"]] = vistos.get(cv["rubro"], 0) + 1
            elegidos.append(cv)
    return elegidos
