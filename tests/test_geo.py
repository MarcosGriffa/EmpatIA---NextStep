"""
test_geo.py — Tests de geo.py (parseo de ubicación + cercanía).

No usa pytest (no está en requirements). Corré:  python tests/test_geo.py

Los valores de ubicación de oferta salen de corridas REALES guardadas en
data/resultados_*.csv (ver la columna 'location'):
  - Computrabajo: "Barrio/Localidad, Provincia"
  - fuentes remote: "Remoto", "Europe,  USA", "APAC,  EMEA,  LATAM, ..."
  - Jooble: "Remoto (Argentina)"
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import geo  # noqa: E402

_fallos: list[str] = []


def check(cond: bool, msg: str) -> None:
    marca = "ok  " if cond else "FALLA"
    print(f"  [{marca}] {msg}")
    if not cond:
        _fallos.append(msg)


def eq(got, want, msg: str) -> None:
    check(got == want, f"{msg}  (esperado={want!r}, obtenido={got!r})")


# ────────────────────────────────────────────────────────────────────
print("\n== parse_location: valores reales de Computrabajo ==")

l = geo.parse_location("Recoleta, Capital Federal")
eq(l.provincia, "CABA", "Recoleta -> provincia CABA")
eq(l.zona, "CABA", "Recoleta -> zona CABA")
eq(l.localidad, "recoleta", "Recoleta -> localidad")
eq(l.pais, "AR", "Recoleta -> país AR")
eq(l.is_remote, False, "Recoleta -> no remoto")

l = geo.parse_location("Villa Luzuriaga, Buenos Aires-GBA")
eq(l.provincia, "Buenos Aires", "Villa Luzuriaga -> provincia Buenos Aires")
eq(l.zona, "GBA Oeste", "Villa Luzuriaga (La Matanza) -> GBA Oeste")
eq(l.partido, "la matanza", "Villa Luzuriaga -> partido La Matanza")

l = geo.parse_location("San Martín, Buenos Aires-GBA")
eq(l.zona, "GBA Norte", "San Martín -> GBA Norte")

l = geo.parse_location("Vicente López, Buenos Aires-GBA")
eq(l.zona, "GBA Norte", "Vicente López -> GBA Norte")

l = geo.parse_location("Lomas de Zamora, Buenos Aires-GBA")
eq(l.zona, "GBA Sur", "Lomas de Zamora -> GBA Sur")

l = geo.parse_location("Gral. Las Heras, Buenos Aires")
eq(l.provincia, "Buenos Aires", "Gral. Las Heras -> provincia Buenos Aires")
eq(l.zona, "GBA Oeste", "Gral. Las Heras -> GBA Oeste (aunque el tag no diga -GBA)")

l = geo.parse_location("Gral. Deheza, Córdoba")
eq(l.provincia, "Córdoba", "Gral. Deheza -> Córdoba")
eq(l.zona, None, "Gral. Deheza -> sin zona metro")
eq(l.localidad, "gral deheza", "Gral. Deheza -> localidad")

l = geo.parse_location("Rosario, Santa Fe")
eq(l.provincia, "Santa Fe", "Rosario, Santa Fe -> provincia Santa Fe")

l = geo.parse_location("Córdoba, Córdoba")
eq(l.provincia, "Córdoba", "Córdoba, Córdoba -> provincia Córdoba")

l = geo.parse_location("Cipolletti, Río Negro")
eq(l.provincia, "Río Negro", "Cipolletti -> Río Negro (alias sin acento)")

l = geo.parse_location("San Luis, San Luis")
eq(l.provincia, "San Luis", "San Luis, San Luis -> provincia San Luis")

l = geo.parse_location("Granadero Baigorria, Santa Fe")
eq(l.provincia, "Santa Fe", "Granadero Baigorria -> Santa Fe (localidad no mapeada, degrada bien)")
eq(l.zona, None, "Granadero Baigorria -> sin zona")


# ────────────────────────────────────────────────────────────────────
print("\n== parse_location: casos de borde (remoto / blobs / vacío) ==")

l = geo.parse_location("")
eq(l.is_unknown, True, "'' -> is_unknown")
eq(l.is_remote, False, "'' -> no remoto")

l = geo.parse_location(None)
eq(l.is_unknown, True, "None -> is_unknown")

l = geo.parse_location("Remoto (Argentina)")
eq(l.is_remote, True, "'Remoto (Argentina)' -> is_remote")
eq(l.pais, "AR", "'Remoto (Argentina)' -> país AR")

l = geo.parse_location("Remoto")
eq(l.is_remote, True, "'Remoto' -> is_remote")

l = geo.parse_location("Europe,  USA")
eq(l.is_remote, False, "'Europe, USA' -> no es 'remoto' per se")
eq(l.provincia, None, "'Europe, USA' -> sin provincia AR")
eq(l.is_unknown, True, "'Europe, USA' -> is_unknown (no comparable)")

l = geo.parse_location("APAC,  EMEA,  LATAM,  Canada,  USA")
eq(l.provincia, None, "blob de regiones -> sin provincia")
eq(l.is_unknown, True, "blob de regiones -> is_unknown")

l = geo.parse_location("EMEA,  Portugal")
eq(l.is_unknown, True, "'EMEA, Portugal' -> is_unknown")

l = geo.parse_location("Europe")
eq(l.is_unknown, True, "'Europe' -> is_unknown")


# ────────────────────────────────────────────────────────────────────
print("\n== parse_location: alias raros de provincia + <select> web ==")

for raw in ["CABA", "C.A.B.A.", "Capital Federal", "Ciudad Autónoma de Buenos Aires"]:
    l = geo.parse_location(raw)
    eq(l.provincia, "CABA", f"'{raw}' -> provincia CABA")
    eq(l.zona, "CABA", f"'{raw}' -> zona CABA")

for raw in ["GBA Norte", "Zona Norte"]:
    l = geo.parse_location(raw)
    eq(l.zona, "GBA Norte", f"'{raw}' -> zona GBA Norte")
    eq(l.provincia, "Buenos Aires", f"'{raw}' -> provincia Buenos Aires")

l = geo.parse_location("La Plata")
eq(l.zona, "La Plata", "'La Plata' -> zona La Plata")

l = geo.parse_location("bs as")
eq(l.provincia, "Buenos Aires", "'bs as' -> Buenos Aires")

l = geo.parse_location("Pcia. de Buenos Aires")
eq(l.provincia, "Buenos Aires", "'Pcia. de Buenos Aires' -> Buenos Aires")

l = geo.parse_location("cordoba")
eq(l.provincia, "Córdoba", "'cordoba' (sin acento) -> Córdoba")

l = geo.parse_location("Quilmes")
eq(l.zona, "GBA Sur", "'Quilmes' suelto -> GBA Sur")
eq(l.provincia, "Buenos Aires", "'Quilmes' suelto -> Buenos Aires")


# ────────────────────────────────────────────────────────────────────
print("\n== proximity_score + factor_geo ==")

caba = geo.parse_location("CABA")
gba_norte = geo.parse_location("GBA Norte")
gba_sur = geo.parse_location("GBA Sur")
cordoba = geo.parse_location("Córdoba")

# candidato CABA
job = geo.parse_location("Recoleta, Capital Federal")
eq(geo.proximity_score(caba, job, "presencial"), 0.8, "CABA cand + oferta CABA presencial -> 0.8 (misma zona)")
eq(geo.factor_geo(0.8, "presencial"), 1.0, "factor: misma zona presencial -> 1.0 (no penaliza)")

job = geo.parse_location("Rosario, Santa Fe")
eq(geo.proximity_score(caba, job, "presencial"), 0.25, "CABA cand + Rosario presencial -> 0.25 (otra provincia)")
eq(geo.factor_geo(0.25, "presencial"), 0.5, "factor: otra provincia presencial -> 0.5 (piso)")

job = geo.parse_location("Gral. Deheza, Córdoba")
eq(geo.proximity_score(cordoba, job, "presencial"), 0.5, "Córdoba cand + oferta Córdoba (otra loc) -> 0.5 misma provincia")
eq(geo.factor_geo(0.5, "presencial"), 0.65, "factor: misma provincia presencial -> 0.65")
eq(geo.factor_geo(0.5, "hibrido"), 0.82, "factor: misma provincia híbrido -> 0.82 (más suave que presencial)")

# candidatos de zonas opuestas del conurbano
job = geo.parse_location("Villa Luzuriaga, Buenos Aires-GBA")  # Oeste
eq(geo.proximity_score(gba_sur, job, "presencial"), 0.5, "GBA Sur cand + oferta GBA Oeste -> 0.5 (misma provincia, distinta zona)")
eq(geo.proximity_score(gba_norte, geo.parse_location("Vicente López, Buenos Aires-GBA"), "presencial"), 0.8,
   "GBA Norte cand + Vicente López -> 0.8 (misma zona)")

# AMBA: CABA y conurbano son el mismo mercado laboral (no "otra provincia")
job_caba = geo.parse_location("Palermo, Capital Federal")
eq(geo.proximity_score(gba_norte, job_caba, "hibrido"), 0.5,
   "Vicente López (GBA Norte) cand + Palermo (CABA) -> 0.5 AMBA, NO 0.25 otra provincia")
eq(geo.proximity_score(caba, geo.parse_location("Vicente López, Buenos Aires-GBA"), "presencial"), 0.5,
   "CABA cand + oferta Vicente López -> 0.5 AMBA")
j = {"location": "Palermo, Capital Federal", "modality": "hibrido", "score": 88}
geo.annotate_job(j, gba_norte)
eq(j["score_final"], 72, "AMBA híbrido: 88 * 0.82 = 72 (antes daba 66 con 0.75)")
check("área metro" in j["proximity_label"], f"label AMBA dice 'área metro': {j['proximity_label']!r}")
# La Plata NO es AMBA a estos efectos
eq(geo.proximity_score(geo.parse_location("La Plata"), job_caba, "presencial"), 0.25,
   "La Plata cand + CABA -> 0.25 (La Plata es su propia aglomeración)")


# ────────────────────────────────────────────────────────────────────
print("\n== proximity_score: NUNCA penaliza en estos casos ==")

job_pres = geo.parse_location("Recoleta, Capital Federal")
job_remoto = geo.parse_location("Remoto (Argentina)")
job_blob = geo.parse_location("Europe,  USA")

eq(geo.proximity_score(caba, job_remoto, "remoto"), None, "oferta remota -> None (no penaliza)")
eq(geo.proximity_score(caba, job_pres, ""), None, "modalidad vacía -> None (no penaliza)")
eq(geo.proximity_score(caba, job_pres, "desconocido"), None, "modalidad desconocida -> None")
eq(geo.proximity_score(None, job_pres, "presencial"), None, "candidato sin ubicación -> None (no penaliza)")
eq(geo.proximity_score(geo.parse_location(""), job_pres, "presencial"), None, "candidato ubicación vacía -> None")
eq(geo.proximity_score(caba, job_blob, "presencial"), None, "oferta no ubicable (blob región) -> None")

eq(geo.factor_geo(None, "presencial"), 1.0, "factor_geo(None) -> 1.0")
eq(geo.factor_geo(None, "hibrido"), 1.0, "factor_geo(None) híbrido -> 1.0")


# ────────────────────────────────────────────────────────────────────
print("\n== annotate_job: no rompe el score del LLM, agrega score_final ==")

j = {"location": "Rosario, Santa Fe", "modality": "presencial", "score": 90}
geo.annotate_job(j, caba)
eq(j["score"], 90, "annotate_job no toca 'score' (queda el del LLM, para BI)")
eq(j["score_final"], 45, "score_final = 90 * 0.5 = 45")
check(j["proximity_label"].startswith("Presencial"), f"label presencial: {j['proximity_label']!r}")

j = {"location": "Remoto", "modality": "remoto", "score": 70}
geo.annotate_job(j, caba)
eq(j["score_final"], 70, "remoto: score_final == score (sin penalización)")
eq(j["proximity_label"], "Remoto", "remoto: label 'Remoto'")

j = {"location": "Recoleta, Capital Federal", "modality": "presencial", "score": 88}
geo.annotate_job(j, None)
eq(j["score_final"], 88, "sin ubicación de candidato: score_final == score")

j = {"location": "Palermo, Capital Federal", "modality": "presencial", "score": 80}
geo.annotate_job(j, caba)
eq(j["score_final"], 80, "CABA cand + CABA oferta presencial: sin penalización")


# ────────────────────────────────────────────────────────────────────
print("\n== normalize_candidate_location: siempre a nivel ciudad ==")

eq(geo.normalize_candidate_location("Calle Falsa 123, Vicente López, Buenos Aires"),
   "Vicente López, GBA Norte, Buenos Aires",
   "dirección completa -> se cae la calle, queda ciudad/zona/provincia")
eq(geo.normalize_candidate_location("Palermo, Capital Federal"),
   "Palermo, CABA", "barrio + Capital Federal -> 'Palermo, CABA'")
eq(geo.normalize_candidate_location("CABA"), "CABA", "'CABA' -> 'CABA'")
eq(geo.normalize_candidate_location(""), None, "'' -> None")
eq(geo.normalize_candidate_location("no figura"), None, "'no figura' -> None")
eq(geo.normalize_candidate_location(None), None, "None -> None")
eq(geo.normalize_candidate_location("Av. Corrientes 1234"), None,
   "sólo una dirección, sin ciudad -> None (no se filtra una calle)")

res = geo.normalize_candidate_location("Domicilio: San Martín 2450, Piso 3, Córdoba")
check(res is None or "2450" not in res, f"nunca deja pasar la altura: {res!r}")


print("\n" + "=" * 60)
if _fallos:
    print(f"  {len(_fallos)} FALLO(S):")
    for f in _fallos:
        print(f"   - {f}")
    sys.exit(1)
print("  TODO OK")
