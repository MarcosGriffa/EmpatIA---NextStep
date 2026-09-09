"""
test_modality.py — Tests de sources.base.detect_modality.

No usa pytest. Corré:  python tests/test_modality.py

Los casos "chip" salen de HTML real de Computrabajo verificado en vivo el
09/09/2026: el aviso mixto se etiqueta "Presencial y remoto" (= híbrido).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sources.base import detect_modality  # noqa: E402

_fallos: list[str] = []


def eq(got, want, msg):
    ok = got == want
    print(f"  [{'ok  ' if ok else 'FALLA'}] {msg}  (esperado={want!r}, obtenido={got!r})")
    if not ok:
        _fallos.append(msg)


print("\n== chip real de Computrabajo ==")
eq(detect_modality("Analista Contable", "... Parque Patricios, Capital Federal Presencial y remoto Ayer Postular"),
   "hibrido", "'Presencial y remoto' (chip Computrabajo) -> hibrido, NO remoto")
eq(detect_modality("REF 21105 Analista Administrativo Contable/ Híbrido", "... Vista 3,6 ADN Presencial y remoto"),
   "hibrido", "título '/ Híbrido' + chip -> hibrido")
eq(detect_modality("Administrativa Contable y Tesorería Presencial", "..."),
   "presencial", "'Presencial' en el título -> presencial")
eq(detect_modality("Vendedoras/es para Shopping de GBA. Presencial. Full Time.", ""),
   "presencial", "'Presencial.' en el título -> presencial")

print("\n== remoto puro ==")
eq(detect_modality("Data Analyst", "100% remoto, equipo distribuido"), "remoto", "'100% remoto' -> remoto")
eq(detect_modality("Soporte IT", "modalidad: teletrabajo"), "remoto", "'teletrabajo' -> remoto")
eq(detect_modality("Dev", "Full Remote position"), "remoto", "'Full Remote' -> remoto")
eq(detect_modality("QA", "home office"), "remoto", "'home office' -> remoto")

print("\n== híbrido explícito y variantes ==")
eq(detect_modality("Analista", "esquema híbrido 3 días oficina"), "hibrido", "'esquema híbrido' -> hibrido")
eq(detect_modality("Dev", "hybrid work"), "hibrido", "'hybrid' -> hibrido")
eq(detect_modality("X", "remoto/presencial a convenir"), "hibrido", "'remoto/presencial' -> hibrido")
eq(detect_modality("X", "trabajo parcialmente remoto"), "hibrido", "'parcialmente remoto' -> hibrido")

print("\n== sin señal -> '' (no se penaliza cercanía) ==")
eq(detect_modality("Analista de Datos Junior", "Buscamos analista con SQL y Python"), "", "sin palabra de modalidad -> ''")
eq(detect_modality("", ""), "", "vacío -> ''")
eq(detect_modality("Vendedor", "Atención al cliente en local"), "", "'local' solo no alcanza -> ''")

print("\n" + "=" * 60)
if _fallos:
    print(f"  {len(_fallos)} FALLO(S):")
    for f in _fallos:
        print(f"   - {f}")
    sys.exit(1)
print("  TODO OK")
