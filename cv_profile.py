"""
cv_profile.py — Clasificador universal de CV con IA.

Lee un CV (PDF o texto), y usa un modelo chico de Groq para extraer:
  - área/rubro profesional (ej: "Data/Analytics", "Ventas", "Biología")
  - si el área es tech/IT o no (decide si se activa la capa de portales tech)
  - nivel de seniority (junior / semi senior / senior)
  - skills clave
  - términos de búsqueda para usar en los portales de empleo (español)
  - términos de búsqueda en inglés (solo si es_tech=true — para portales
    tech internacionales como RemoteOK/Jobicy/WeWorkRemotely, que son en
    inglés y no traen resultados si les mandás queries en español)

No está hardcodeado a IT — funciona con cualquier CV, de cualquier rubro.
Usa un modelo chico y rápido (ver CLASSIFIER_MODEL) porque esta tarea
es extracción estructurada simple, no requiere razonamiento pesado
(ver conversación sobre costos: esto cuesta centavos de dólar por CV).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pymupdf as fitz  # PyMuPDF (nombre nuevo del paquete)
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

# Modelo chico y rápido. Cambiado el 17/08/2026: Groq dio de baja toda la
# línea Llama 3.x y `llama-3.1-8b-instant` empezó a devolver 404
# ("model_not_found"), lo que rompía la subida de CV desde la web.
# Reemplazo verificado contra la lista real de modelos de la cuenta.
CLASSIFIER_MODEL = "openai/gpt-oss-20b"

SYSTEM_PROMPT = """\
Sos un analista de RRHH experto en cualquier rubro (no solo tecnología).
Vas a recibir el texto de un CV. Tu trabajo es analizarlo y devolver
ÚNICAMENTE un JSON válido (sin markdown, sin texto extra) con este esquema:

{
  "area": "string — el rubro/área profesional principal, en español, ej: 'Data/Analytics', 'Ventas', 'Biología', 'Marketing', 'Salud', 'Administración'",
  "is_tech": boolean — true SOLO si el área es tecnología/IT/desarrollo/datos,
  "seniority": "junior" | "semi senior" | "senior",
  "skills": ["lista", "de", "5 a 10 skills clave", "detectadas en el CV"],
  "search_queries": ["3 a 5 términos de búsqueda", "cortos y realistas", "para usar en portales de empleo argentinos", "en español, como los escribiría alguien buscando trabajo en este rubro"],
  "search_queries_en": ["2 a 3 términos equivalentes en inglés", "SOLO si is_tech es true", "ej: 'data analyst', 'python developer'", "si is_tech es false, devolvé una lista vacía []"],
  "ubicacion": "string | null — SOLO ciudad/partido y provincia de la persona, ej: 'Vicente López, Buenos Aires', 'CABA', 'Córdoba'. NUNCA calle ni número ni piso. Si el CV no dice de dónde es, devolvé null (no lo inventes ni lo deduzcas del lugar de trabajo de una experiencia pasada)."
}

Reglas:
- El área y las queries deben reflejar el CV real, no asumas que es IT.
- Los search_queries tienen que ser términos que existan como categorías de
  búsqueda reales en portales de empleo (ej: "analista de datos junior",
  "vendedor sin experiencia", "biologo laboratorio"), no descripciones largas.
- search_queries_en solo tiene sentido para perfiles tech (is_tech=true),
  porque se usan en portales de empleo remoto en inglés. Para cualquier
  otro rubro, devolvé search_queries_en como lista vacía.
- Si el CV no tiene experiencia clara, inferí seniority "junior".
- ubicacion: es el domicilio/ciudad de la PERSONA, no el de sus trabajos
  anteriores. A nivel ciudad, nunca la dirección. Si hay duda, null.
- Devolvé SOLO el JSON, nada más.
"""


def extract_cv_text(path: str | Path) -> str:
    """Extrae texto de un CV en PDF o .txt"""
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        doc = fitz.open(path)
        text = "".join(page.get_text() for page in doc)
        doc.close()
        return text.strip()
    return path.read_text(encoding="utf-8").strip()


def _get_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta GROQ_API_KEY en el .env. Sacá una gratis en console.groq.com "
            "y ponela en el archivo .env (ver .env.example)."
        )
    return Groq(api_key=api_key)


def classify_cv(cv_text: str) -> dict:
    """
    Devuelve un dict con: area, is_tech, seniority, skills, search_queries,
    search_queries_en. Lanza excepción si Groq no devuelve un JSON parseable
    (con 1 reintento).
    """
    client = _get_client()

    for attempt in range(2):
        resp = client.chat.completions.create(
            model=CLASSIFIER_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": cv_text[:6000]},  # margen de sobra para un CV
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content.strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # A veces el modelo envuelve el JSON en ```json ... ``` pese a la instrucción
            cleaned = raw.strip("`").replace("json\n", "", 1)
            try:
                data = json.loads(cleaned)
            except json.JSONDecodeError:
                if attempt == 0:
                    continue
                raise ValueError(f"El modelo no devolvió JSON válido:\n{raw}")

        # Validación mínima de esquema (search_queries_en es opcional por
        # compatibilidad — si falta, la completamos vacía en vez de fallar).
        required = {"area", "is_tech", "seniority", "skills", "search_queries"}
        if not required.issubset(data.keys()):
            if attempt == 0:
                continue
            raise ValueError(f"JSON incompleto del modelo: {data}")

        data.setdefault("search_queries_en", [])

        # Ubicación: nivel ciudad SIEMPRE, aunque el modelo haya desobedecido
        # y devuelto una dirección. normalize_candidate_location() reconstruye
        # el string desde componentes (localidad/zona/provincia), así que
        # estructuralmente no puede quedar calle ni altura. Ver geo.py.
        import geo

        data["ubicacion"] = geo.normalize_candidate_location(data.get("ubicacion"))

        return data

    raise RuntimeError("No se pudo clasificar el CV después de 2 intentos.")


if __name__ == "__main__":
    import sys

    cv_path = sys.argv[1] if len(sys.argv) > 1 else "test_cvs/cv_marcos.txt"
    text = extract_cv_text(cv_path)
    print(f"CV leído: {len(text)} caracteres\n")

    profile = classify_cv(text)
    print(json.dumps(profile, indent=2, ensure_ascii=False))
