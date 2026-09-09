"""
test_redact.py — Tests de geo.redact_address (borrado de dirección exacta
del texto de un CV antes de persistirlo).

No usa pytest. Corré:  python tests/test_redact.py

El criterio: borrar calle+altura+piso/depto y líneas rotuladas
("Domicilio:"), SIN comerse contenido legítimo del CV (fechas, versiones,
cantidades, nombres de calle que también son nombres de empresa, "Piso"
como parte de otra palabra).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import geo  # noqa: E402

PH = geo.ADDRESS_PLACEHOLDER
_fallos: list[str] = []


def redacta(txt: str, msg: str) -> None:
    out = geo.redact_address(txt)
    ok = PH in out
    _log(ok, f"REDACTA  | {msg}", txt, out)


def intacto(txt: str, msg: str) -> None:
    out = geo.redact_address(txt)
    ok = out == txt
    _log(ok, f"INTACTO  | {msg}", txt, out)


def _log(ok: bool, msg: str, txt: str, out: str) -> None:
    print(f"  [{'ok  ' if ok else 'FALLA'}] {msg}")
    if not ok:
        print(f"          in : {txt!r}")
        print(f"          out: {out!r}")
        _fallos.append(msg)


# ────────────────────────────────────────────────────────────────────
print("\n== SÍ se redacta (direcciones reales) ==")

redacta("Vivo en Calle Falsa 123, Piso 4, Vicente López",
        "calle + nombre + altura + piso")
redacta("Av. Corrientes 1234", "avenida abreviada + altura")
redacta("Avenida Rivadavia 5000 2° B", "avenida + altura + piso informal")
redacta("Domicilio: San Martín 2450, CABA", "línea rotulada 'Domicilio:'")
redacta("Dirección: Av. del Libertador 6400", "línea rotulada 'Dirección:'")
redacta("Residencia: Belgrano 456 Dto 2", "línea rotulada 'Residencia:'")
redacta("Bv. España 234, Piso 2, Depto A, Córdoba", "boulevard + piso + depto")
redacta("Diagonal 74 N° 1234", "diagonal + N° + altura")
redacta("Mza. 12 Casa 4, Barrio Belén", "manzana abreviada + número")
redacta("Rivadavia 5600 Piso 3 Depto B", "sin tipo de vía pero con piso+depto explícito")

# La ciudad puede quedar (patrón inline) o irse (línea rotulada) — lo que
# NUNCA debe quedar es la calle+altura.
for txt in [
    "Vivo en Calle Falsa 123, Piso 4, Vicente López",
    "Domicilio: San Martín 2450, CABA",
    "Av. Santa Fe 3200, Recoleta, CABA",
]:
    out = geo.redact_address(txt)
    _log("123" not in out and "2450" not in out and "3200" not in out,
         "no queda ninguna altura", txt, out)


# ────────────────────────────────────────────────────────────────────
print("\n== NO se toca (contenido legítimo del CV) ==")

intacto("FERROSIDER (03/10/2024 - Actualidad)", "fecha dd/mm/yyyy")
intacto("Gerente de Operaciones (1/10/2025 - 4/03/2026)", "rango de fechas")
intacto("Experiencia en Python 3.11, pandas 2.0 y Node.js", "versiones de software")
intacto("Automatización & IA: Groq API/LLM, BeautifulSoup4, n8n", "nombres de herramientas")
intacto("Coordinación integral de un equipo de 12 personas", "cantidad de personas")
intacto("Cumplimiento del 115% del objetivo mensual de venta", "porcentaje")
intacto("E-commerce Automation (Las Dellas)", "nombre de proyecto entre paréntesis")
intacto("Atención en Casa del Deporte (01/2020 - 02/2022)", "empresa 'Casa del ...' + fechas")
intacto("Universidad de Buenos Aires — Lic. en Ciencias de Datos (en curso)", "universidad, sin altura")
intacto("Instituto Dr. Nicolás Avellaneda — Secundario completo", "'Avellaneda' (partido) sin ser dirección")
intacto("Trabajé sobre el piso de producción optimizando procesos", "'piso' como palabra común, sin altura")
intacto("Pisos y Revestimientos SA — Vendedor", "'Pisos' arranca palabra, sin altura")
intacto("Manejo de caja y arqueos diarios en local a la calle", "'calle' sin nombre ni altura")
intacto("Dirección de correo: julieta.fernandez.test@gmail.com", "'Dirección de correo:' NO es domicilio")
intacto("Dirección web: github.com/MarcosGriffa", "'Dirección web:' NO es domicilio")
intacto("Ruta de aprendizaje recomendada para el equipo", "'Ruta' sin altura")
intacto("Objetivo: superar los 5000 tickets resueltos por trimestre", "número grande sin tipo de vía")
intacto("", "string vacío")
intacto("Marcos Griffa\nEstudiante de Ciencias de Datos", "encabezado sin dirección")


# ────────────────────────────────────────────────────────────────────
print("\n== CV completo de prueba: no debe cambiar (no tiene dirección) ==")

cv_marcos = open(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "test_cvs", "cv_marcos.txt"),
    encoding="utf-8",
).read()
out = geo.redact_address(cv_marcos)
_log(out == cv_marcos, "cv_marcos.txt intacto (sin dirección)", "<cv>", "<cv modificado>" if out != cv_marcos else "<cv>")


print("\n" + "=" * 60)
if _fallos:
    print(f"  {len(_fallos)} FALLO(S):")
    for f in _fallos:
        print(f"   - {f}")
    sys.exit(1)
print("  TODO OK")
