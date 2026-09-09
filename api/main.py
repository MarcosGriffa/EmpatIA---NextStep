"""
main.py — API web del motor de matching (Fase 2).

Expone el pipeline que ya funciona por consola (cv_profile.py,
semantic_match.py, pipeline.py) como una API HTTP para que la web
(carpeta web/, Next.js) lo pueda usar. No modifica ni reemplaza el
pipeline — lo importa y lo corre igual que `python pipeline.py`.

Cómo levantarlo (ver README_FASE2.md para la guía completa):

    python -m uvicorn api.main:app --reload --port 8000

IMPORTANTE: se corre desde la carpeta raíz del proyecto (job_scraping/),
no desde adentro de api/, para que los imports a cv_profile.py,
pipeline.py, etc. funcionen.
"""

from __future__ import annotations

import sys

# Bug real encontrado corriendo el flujo completo por la web (12/08/2026):
# cuando este proceso corre "atrás" de uvicorn (no en una consola interactiva
# con UTF-8), la salida estándar de Windows cae a un codepage viejo (charmap)
# que no sabe escribir '→' y otros caracteres — y como pipeline.py y los
# conectores en sources/ usan print() con esos caracteres para loguear el
# progreso, CADA búsqueda tiraba una excepción no controlada y el resultado
# terminaba en 0 ofertas encontradas, sin ningún error visible para quien
# usa la web. Se arregla acá (punto de entrada de la API), forzando UTF-8
# en stdout/stderr, sin tocar pipeline.py ni sources/.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import os
import shutil
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import rate_limit, storage
from .auth import get_verified_user_id
from .matching import run_full_pipeline
from .tailor import TailorError, generate_tailored_cv

app = FastAPI(title="EmpatIA | NextStep — API")

# CORS. La web llama a esta API desde sus propias rutas de servidor (no
# desde el navegador directo), así que en rigor ni haría falta abrir nada.
# Igual lo dejamos configurable: en local, sin ALLOWED_ORIGINS en el .env,
# queda abierto para no trabar el desarrollo; en producción (Render), la
# variable de entorno lo restringe al dominio real de la web en Vercel.
_allowed = os.getenv("ALLOWED_ORIGINS", "").strip()
allow_origins = [o.strip() for o in _allowed.split(",") if o.strip()] if _allowed else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ROOT_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = ROOT_DIR / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".txt"}


def _friendly_storage_error(e: Exception) -> str:
    """Si Supabase está configurado pero todavía no se corrió
    supabase/schema.sql, la librería tira un error técnico ("Could not find
    the table..."). Lo traducimos a algo que Marcos pueda entender y
    accionar sin ayuda, en vez de un mensaje de Postgres en inglés."""
    msg = str(e)
    if "PGRST205" in msg or "schema cache" in msg:
        return (
            "Falta un paso en Supabase: todavía no se crearon las tablas. "
            "Pegá el contenido de supabase/schema.sql en el SQL Editor de tu "
            "proyecto de Supabase (dashboard -> SQL Editor -> New query -> Run) y volvé a intentar."
        )
    return msg


@app.get("/health")
def health():
    return {"status": "ok", "storage_backend": storage.BACKEND}


@app.post("/api/match")
async def upload_and_match(
    file: UploadFile = File(...),
    zona: str = Form(""),
    user_id: str = Depends(get_verified_user_id),
):
    """Recibe un CV (PDF o .txt), corre todo el pipeline (clasificar → buscar
    → matchear) y devuelve los resultados. Puede tardar bastante (hay varias
    llamadas a IA y scraping de portales) — un minuto o dos es normal.

    zona: opcional — la zona que la persona eligió en el formulario. Sólo se
    usa como ubicación del candidato si el CV no la trae (ver api/matching.py).

    Fase 3: requiere sesión real (ver api/auth.py) — el user_id NUNCA se
    toma de lo que mande el cliente, se verifica del token."""

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Formato no soportado ({suffix or 'sin extensión'}). Subí un PDF o un .txt.")

    # Freno contra abuso — ver api/rate_limit.py. Se chequea ANTES de
    # guardar el archivo y de gastar cupo de scraping/IA.
    try:
        rate_limit.verificar_y_reservar(user_id)
    except rate_limit.LimiteAlcanzado as e:
        raise HTTPException(429, str(e))

    try:
        safe_name = f"{uuid.uuid4().hex[:8]}{suffix}"
        dest_path = UPLOAD_DIR / safe_name
        with open(dest_path, "wb") as out:
            shutil.copyfileobj(file.file, out)

        try:
            result = run_full_pipeline(
                user_id=user_id, cv_path=str(dest_path),
                filename=file.filename or safe_name, zona=zona,
            )
        except RuntimeError as e:
            # Típicamente: falta GROQ_API_KEY, o Groq no devolvió JSON válido.
            raise HTTPException(500, str(e))
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, _friendly_storage_error(e))
    finally:
        rate_limit.liberar(user_id)

    return result


@app.get("/api/match/latest")
def latest_match(user_id: str = Depends(get_verified_user_id)):
    """Última corrida de matching guardada de este usuario (para no tener
    que resubir el CV cada vez que se recarga la página de resultados)."""
    try:
        entry = storage.get_match_results(user_id)
    except Exception as e:
        raise HTTPException(500, _friendly_storage_error(e))
    if not entry:
        raise HTTPException(404, "Todavía no hay resultados para este usuario.")
    return entry


class ApplyBody(BaseModel):
    job_id: str
    applied: bool = True


@app.post("/api/jobs/apply")
def apply_job(body: ApplyBody, user_id: str = Depends(get_verified_user_id)):
    """Marca (o desmarca) una oferta como 'aplicada'. Las corridas de
    matching futuras la van a excluir automáticamente (ver matching.py)."""
    try:
        storage.mark_as_applied(user_id, body.job_id, body.applied)
    except Exception as e:
        raise HTTPException(500, _friendly_storage_error(e))
    return {"ok": True, "job_id": body.job_id, "applied": body.applied}


@app.get("/api/jobs/applied")
def applied_jobs(user_id: str = Depends(get_verified_user_id)):
    return {"job_ids": sorted(storage.get_applied_job_ids(user_id))}


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@app.get("/api/cv/tailor")
def tailor_cv(job_id: str = "", user_id: str = Depends(get_verified_user_id)):
    """Devuelve el .docx del CV adaptado a UNA oferta puntual.

    Se genera en el momento (unos segundos) y queda cacheado por CV+oferta,
    así que si se vuelve a pedir sale instantáneo. Nada se pre-genera: solo
    se arma el CV de la oferta que la persona realmente pidió."""
    if not job_id:
        raise HTTPException(400, "Falta job_id.")

    try:
        path, download_name, from_cache = generate_tailored_cv(user_id, job_id)
    except TailorError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:
        # Típicamente: falta GROQ_API_KEY
        raise HTTPException(500, str(e))
    except Exception as e:
        raise HTTPException(500, _friendly_storage_error(e))

    print(f"[tailor] {'cache' if from_cache else 'generado'}: {download_name}")
    return FileResponse(path, media_type=DOCX_MIME, filename=download_name)


class ClaimBody(BaseModel):
    anon_id: str = ""


@app.post("/api/account/claim")
def claim_anonymous_data(body: ClaimBody, user_id: str = Depends(get_verified_user_id)):
    """Fase 3 — al crear una cuenta, re-etiqueta lo que ese navegador tenía
    guardado bajo su id anónimo (cv_profiles/match_results/applied_jobs),
    para que pase a estar bajo la cuenta real. Ver storage.claim_anonymous_data.

    El "anon_id" viene de la ruta de Next.js (web/src/app/api/account/claim),
    que lo lee directo de la cookie del pedido entrante — nunca es un dato
    que el navegador pueda mandar libremente acá, porque quien de verdad
    sos ("user_id") ya está resuelto y verificado antes de llegar a esta
    función (Depends(get_verified_user_id))."""
    try:
        resultado = storage.claim_anonymous_data(body.anon_id, user_id)
    except Exception as e:
        raise HTTPException(500, _friendly_storage_error(e))
    return {"ok": True, "migrado": resultado}


class NotificationSettingBody(BaseModel):
    activas: bool


@app.get("/api/notifications/settings")
def get_notification_settings(user_id: str = Depends(get_verified_user_id)):
    """Estado del interruptor de avisos por mail — apagado si nunca se tocó
    (opt-in, ver notificaciones_semanales.py)."""
    try:
        activas = storage.get_notification_setting(user_id)
    except Exception as e:
        raise HTTPException(500, _friendly_storage_error(e))
    return {"activas": activas}


@app.post("/api/notifications/settings")
def set_notification_settings(body: NotificationSettingBody, user_id: str = Depends(get_verified_user_id)):
    try:
        storage.set_notification_setting(user_id, body.activas)
    except Exception as e:
        raise HTTPException(500, _friendly_storage_error(e))
    return {"ok": True, "activas": body.activas}
