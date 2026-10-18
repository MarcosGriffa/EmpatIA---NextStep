"""
generar_dataset.py — Genera el dataset SINTÉTICO de evaluación.

Salida (en evals/datos/):
  cvs.jsonl        40 CVs (5 por rubro), con rol, seniority y skills conocidos.
  ofertas.jsonl    200 ofertas (8 rubros × 25), incluye 16 trampas.
  etiquetas.csv    la relevancia "correcta" de TODOS los pares CV × oferta
                   (40 × 200 = 8.000 pares), en escala 0-3.

Escala de relevancia (se calcula por reglas, ver `etiqueta()`):
  3  match fuerte   — mismo rol, mismo seniority, cubre ≥60% de lo que pide
  2  match parcial  — mismo rol, seniority a un paso, cubre ≥40%
  1  relacionado    — mismo rol con gap grande, mismo rubro con otro rol,
                      o rol afín de otro rubro (ver ROLES_AFINES)
  0  no relevante   — otro rubro (incluye las trampas de vocabulario)

Por qué reglas y no un LLM: si la etiqueta la pusiera un modelo, el
sistema que se evalúa (que también es un LLM) se estaría corrigiendo a sí
mismo. Con reglas, la "verdad" se conoce desde que se genera el dato.

Para que no sea trivial para los embeddings:
  - los CVs a veces mencionan las skills sólo dentro de las tareas, sin
    una sección de "Skills";
  - las ofertas mezclan texto de relleno (empresa, beneficios);
  - ~20% de las ofertas de tecnología y marketing están en inglés
    (como las de RemoteOK, Himalayas, etc. en producción);
  - hay trampas: puestos de un rubro escritos con vocabulario de otro.

Uso:
    python evals/generar_dataset.py            (semilla fija → reproducible)
"""

from __future__ import annotations

import sys as _sys

# En la consola de Windows, sin esto los acentos y flechas rompen el print.
if hasattr(_sys.stdout, "reconfigure"):
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import csv
import json
import random
from pathlib import Path

from catalogo import (
    BENEFICIOS, EMPRESAS, NOMBRES, APELLIDOS, ROLES, ROLES_AFINES, RUBROS, SENIORITIES,
    SENIORITY_LABEL, SENIORITY_LABEL_EN, SENIORITY_YEARS, TRAMPAS, ZONAS,
)

SEED = 2026
CVS_POR_RUBRO = 5
OFERTAS_POR_RUBRO = 25
DATA_DIR = Path(__file__).parent / "datos"

LEVEL = {s: i for i, s in enumerate(SENIORITIES)}


# ── Etiqueta (la "verdad") ──────────────────────────────────────
def etiqueta(cv: dict, oferta: dict) -> tuple[int, str]:
    """Devuelve (relevancia 0-3, motivo). El motivo queda en el CSV para
    poder explicar cada etiqueta en el reporte."""
    rol_cv, rol_of = cv["rol"], oferta["rol"]
    if rol_cv == rol_of:
        req = set(oferta["skills_requeridas"])
        cobertura = len(req & set(cv["skills"])) / len(req) if req else 0.0
        gap = abs(LEVEL[cv["seniority"]] - LEVEL[oferta["seniority"]])
        if gap == 0 and cobertura >= 0.6:
            return 3, f"mismo rol y seniority, cubre {cobertura:.0%}"
        if gap <= 1 and cobertura >= 0.4:
            return 2, f"mismo rol, gap de seniority {gap}, cubre {cobertura:.0%}"
        return 1, f"mismo rol pero gap de seniority {gap} / cubre {cobertura:.0%}"
    if cv["rubro"] == oferta["rubro"]:
        return 1, "mismo rubro, otro rol"
    if frozenset({rol_cv, rol_of}) in ROLES_AFINES:
        return 1, "rol afín de otro rubro"
    if oferta.get("trampa_rubro") == cv["rubro"]:
        return 0, "trampa: vocabulario de tu rubro, puesto de otro"
    return 0, "otro rubro"


# ── CVs ─────────────────────────────────────────────────────────
def _cv_text(rng: random.Random, cv: dict) -> str:
    rol = ROLES[cv["rol"]]
    yrs = cv["anios"]
    lineas = [cv["nombre"], rol["nombre"] + (" " + SENIORITY_LABEL[cv["seniority"]] if rng.random() < 0.5 else ""),
              f"{cv['zona']} · {cv['email']}", "", "PERFIL"]
    top = ", ".join(cv["skills"][:3])
    lineas.append(
        f"{rol['nombre']} con {yrs} {'año' if yrs == 1 else 'años'} de experiencia. "
        f"Fuerte en {top}. Busco un puesto donde seguir creciendo."
        if yrs > 0 else
        f"Estudiante / primera experiencia como {rol['nombre'].lower()}. Conocimientos de {top}. "
        f"Busco mi primer trabajo formal en el área."
    )
    lineas += ["", "EXPERIENCIA LABORAL"]
    n_trabajos = 1 if yrs <= 2 else (2 if yrs <= 6 else 3)
    tareas = rol["tareas"][:]
    rng.shuffle(tareas)
    skills_en_tareas = cv["skills"][3:]
    for t in range(n_trabajos):
        emp = rng.choice(EMPRESAS)
        lineas.append(f"{emp.upper()} — {rng.choice(rol['titulos'])}")
        for tarea in tareas[t * 2 : t * 2 + 2] or tareas[:2]:
            extra = ""
            if skills_en_tareas and rng.random() < 0.7:
                extra = f" ({skills_en_tareas.pop(0)})"
            lineas.append(f"- {tarea.capitalize()}{extra}.")
    lineas += ["", "EDUCACIÓN", rng.choice(rol["estudios"])]
    # La mitad de los CVs tiene sección de skills explícita; la otra mitad
    # sólo las menciona dentro del perfil y las tareas (más difícil).
    if cv["seccion_skills"]:
        lineas += ["", "HABILIDADES", " · ".join(cv["skills"])]
    return "\n".join(lineas)


def generar_cvs(rng: random.Random) -> list[dict]:
    cvs = []
    for rubro in RUBROS:
        roles = [k for k, r in ROLES.items() if r["rubro"] == rubro]
        for i in range(CVS_POR_RUBRO):
            rol_key = roles[i % len(roles)]
            rol = ROLES[rol_key]
            sen = SENIORITIES[(i + len(cvs)) % 3]
            lo, hi = SENIORITY_YEARS[sen]
            skills_all = [s[0] for s in rol["skills"]]
            n = {"jr": 5, "ssr": 6, "sr": 8}[sen]
            # el núcleo (primeras 6) es más probable que aparezca
            core, resto = skills_all[:6], skills_all[6:]
            elegidas = rng.sample(core, min(n - 1, 6))
            elegidas += rng.sample(resto, max(0, n - len(elegidas)))
            nombre = f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)}"
            cv = {
                "cv_id": f"CV{len(cvs) + 1:03d}",
                "rubro": rubro,
                "rol": rol_key,
                "seniority": sen,
                "anios": rng.randint(lo, hi),
                "skills": elegidas,
                "seccion_skills": rng.random() < 0.5,
                "nombre": nombre,
                "zona": rng.choice(ZONAS),
                "email": nombre.lower().replace(" ", ".").replace("í", "i").replace("á", "a")
                .replace("é", "e").replace("ó", "o").replace("ú", "u") + "@mail.test",
            }
            cv["texto"] = _cv_text(rng, cv)
            cvs.append(cv)
    return cvs


# ── Ofertas ─────────────────────────────────────────────────────
def _oferta_texto(rng: random.Random, of: dict, en: bool, intro_trampa: str = "") -> str:
    rol = ROLES[of["rol"]]
    sk = dict(rol["skills"])
    if en:
        reqs = [sk[s] or s for s in of["skills_requeridas"]]
        tareas = rol["tareas"][:3]
        partes = [
            f"{of['empresa']} is hiring a {of['titulo']}.",
            f"Seniority: {SENIORITY_LABEL_EN[of['seniority']]} ({of['anios_min']}+ years).",
            "Requirements: " + ", ".join(reqs) + ".",
            "You will work with our team on: " + "; ".join(tareas) + " (Spanish-speaking team).",
            "Remote position, LATAM time zones.",
        ]
        return " ".join(partes)
    reqs = of["skills_requeridas"]
    tareas = rol["tareas"][:]
    rng.shuffle(tareas)
    partes = []
    if intro_trampa:
        partes.append(intro_trampa)
    partes += [
        f"{of['empresa']}, empresa líder en su rubro, busca {of['titulo']} para sumarse a su equipo en {of['zona']}.",
        "Responsabilidades: " + "; ".join(tareas[:3]) + ".",
        f"Requisitos: experiencia de {of['anios_min']} años o más"
        if of["anios_min"] else "Requisitos: no se requiere experiencia previa",
    ]
    partes[-1] += "; " + ", ".join(reqs) + "."
    partes.append(rng.choice(BENEFICIOS) + " " + rng.choice(BENEFICIOS))
    return " ".join(partes)


def _nueva_oferta(rng, idx, rol_key, sen, trampa=None) -> dict:
    rol = ROLES[rol_key]
    skills_all = [s[0] for s in rol["skills"]]
    core, resto = skills_all[:6], skills_all[6:]
    n_req = rng.randint(4, 6)
    req = rng.sample(core, n_req - 1) + rng.sample(resto, 1)
    en = (not trampa) and rol.get("titulos_en") and rng.random() < 0.2
    if trampa:
        titulo = trampa[2]
    else:
        base = rng.choice(rol["titulos_en"] if en else rol["titulos"])
        sen_txt = (SENIORITY_LABEL_EN if en else SENIORITY_LABEL)[sen]
        titulo = f"{base} {sen_txt}" if rng.random() < 0.75 else base
    of = {
        "oferta_id": f"OF{idx:03d}",
        "rubro": rol["rubro"],
        "rol": rol_key,
        "seniority": sen,
        "anios_min": SENIORITY_YEARS[sen][0],
        "skills_requeridas": req,
        "titulo": titulo,
        "empresa": rng.choice(EMPRESAS),
        "zona": rng.choice(ZONAS),
        "idioma": "en" if en else "es",
        "es_trampa": bool(trampa),
        "trampa_rubro": trampa[1] if trampa else "",
        "source": "sintetico",
    }
    of["descripcion"] = _oferta_texto(rng, of, bool(en), trampa[3] if trampa else "")
    return of


def generar_ofertas(rng: random.Random) -> list[dict]:
    ofertas = []
    trampas_por_rubro: dict[str, list] = {r: [] for r in RUBROS}
    for t in TRAMPAS:
        trampas_por_rubro[ROLES[t[0]]["rubro"]].append(t)
    for rubro in RUBROS:
        roles = [k for k, r in ROLES.items() if r["rubro"] == rubro]
        trampas = trampas_por_rubro[rubro]
        normales = OFERTAS_POR_RUBRO - len(trampas)
        for i in range(normales):
            rol_key = roles[i % len(roles)]
            sen = SENIORITIES[(i // len(roles)) % 3]
            ofertas.append(_nueva_oferta(rng, len(ofertas) + 1, rol_key, sen))
        for t in trampas:
            ofertas.append(_nueva_oferta(rng, len(ofertas) + 1, t[0], rng.choice(SENIORITIES), trampa=t))
    return ofertas


def main():
    rng = random.Random(SEED)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cvs = generar_cvs(rng)
    ofertas = generar_ofertas(rng)

    with open(DATA_DIR / "cvs.jsonl", "w", encoding="utf-8") as f:
        for cv in cvs:
            f.write(json.dumps(cv, ensure_ascii=False) + "\n")
    with open(DATA_DIR / "ofertas.jsonl", "w", encoding="utf-8") as f:
        for of in ofertas:
            f.write(json.dumps(of, ensure_ascii=False) + "\n")

    dist = {0: 0, 1: 0, 2: 0, 3: 0}
    sin_relevantes = []
    with open(DATA_DIR / "etiquetas.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cv_id", "oferta_id", "relevancia", "motivo"])
        for cv in cvs:
            n_rel = 0
            for of in ofertas:
                rel, motivo = etiqueta(cv, of)
                dist[rel] += 1
                n_rel += rel >= 2
                w.writerow([cv["cv_id"], of["oferta_id"], rel, motivo])
            if n_rel == 0:
                sin_relevantes.append(cv["cv_id"])

    print(f"CVs: {len(cvs)} | Ofertas: {len(ofertas)} (trampas: {sum(o['es_trampa'] for o in ofertas)}, "
          f"en inglés: {sum(o['idioma'] == 'en' for o in ofertas)})")
    print(f"Pares etiquetados: {sum(dist.values())} → " + ", ".join(f"rel {k}: {v}" for k, v in dist.items()))
    if sin_relevantes:
        print(f"[!] CVs sin ninguna oferta relevante (≥2): {sin_relevantes}")


if __name__ == "__main__":
    main()
