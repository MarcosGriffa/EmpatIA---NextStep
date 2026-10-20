"""
notificaciones_semanales.py — Chequeo automático de matches nuevos, y aviso
por mail. Corre una vez por semana (ver .github/workflows/notificaciones.yml),
disparado por GitHub Actions — NO es un endpoint de la API, no lo llama el
navegador de nadie.

Plan completo (decisiones tomadas y confirmadas por Marcos el 19/08/2026):

  - Semanal, no diario — conserva cupo (ver el punto de Jooble abajo) y es
    una cadencia razonable para alguien buscando trabajo.
  - Solo chequea a quien prendió el interruptor (opt-in, apagado por
    defecto) — nadie recibe esto sin haberlo pedido.
  - NO usa Jooble. Nada. Solo Computrabajo + las 4 fuentes tech (todas sin
    límite de cupo). Jooble se reserva 100% para búsquedas manuales, donde
    la persona está esperando el resultado ahí mismo — un chequeo en
    segundo plano no amerita gastar ese cupo escaso.
  - No vuelve a clasificar el CV con IA — reusa el perfil ya guardado
    (search_queries, is_tech) de la última vez que la persona lo subió.
    Ahorra una llamada a Groq por usuario, cada semana, para nada nuevo.
  - Solo se le "explica" con el modelo grande de Groq a las ofertas que la
    persona NUNCA vio (ni por una búsqueda manual, ni por un chequeo
    anterior) — ver seen_jobs. Si no hay ofertas nuevas, no se gasta un
    solo llamado a IA para ese usuario esa semana.
  - Solo se manda mail si, de las ofertas nuevas explicadas, alguna llega
    al puntaje mínimo (UMBRAL_SCORE_MINIMO) — no todo lo "nuevo" amerita
    interrumpir a alguien por mail.
  - No comparte cupo con el límite de 2 búsquedas/día (api/rate_limit.py):
    ese límite vive pegado al endpoint HTTP /api/match, que este script ni
    toca — llama directo a las funciones internas del pipeline.

Cómo correrlo a mano (para probar):
    python notificaciones_semanales.py
    python notificaciones_semanales.py --solo-un-usuario <user_id>   # depurar de a uno
"""

from __future__ import annotations

import argparse
import os
import sys
import time

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv()

import geo
from pipeline import collect_jobs, EMBEDDING_TOP_K
from semantic_match import rank_and_explain
from sources.computrabajo import ComputrabajoSource
from sources.getonboard import GetOnBoardSource
from sources.careerjet import CareerjetSource

from api import storage
from api.emailer import enviar_resumen_semanal
from api.job_utils import make_job_id

# Sin Jooble a propósito — ver el docstring de arriba. Get on Board no tiene
# cupo y Careerjet no tiene tope de por vida, así que sí van.
FUENTES_AUTOMATICAS = [ComputrabajoSource(), GetOnBoardSource(), CareerjetSource()]

# Cuántas ofertas nuevas, como máximo, se le explican con IA a una persona
# en una corrida — protege contra un caso raro donde de golpe aparecen
# cientos de ofertas nuevas (no debería pasar nunca en la práctica, pero
# si pasa, no queremos una factura de Groq sorpresa).
MAX_OFERTAS_NUEVAS_A_EXPLICAR = 10

# Puntaje mínimo para que una oferta nueva amerite un mail. Ajustable.
UMBRAL_SCORE_MINIMO = 70


def _mail_del_usuario(admin_client, user_id: str) -> tuple[str, str | None] | None:
    """(mail, nombre) de esta cuenta, o None si no se pudo obtener (cuenta
    borrada, etc. — no debería pasar, pero no vale la pena tumbar toda la
    corrida por un usuario raro)."""
    try:
        u = admin_client.auth.admin.get_user_by_id(user_id).user
        if not u or not u.email:
            return None
        meta = u.user_metadata or {}
        nombre = meta.get("full_name") or meta.get("name")
        return u.email, nombre
    except Exception as e:
        print(f"    [!] no se pudo obtener el mail de {user_id}: {e}")
        return None


def procesar_usuario(user_id: str, admin_client) -> None:
    cv_entry = storage.get_cv_profile(user_id)
    if not cv_entry or not cv_entry.get("cv_text"):
        print("    sin CV guardado todavía — se saltea.")
        return

    perfil = cv_entry.get("profile") or {}
    search_queries = perfil.get("search_queries") or []
    search_queries_en = perfil.get("search_queries_en") or []
    is_tech = bool(perfil.get("is_tech"))
    if not search_queries:
        print("    el perfil guardado no tiene search_queries — se saltea (CV viejo, pre-Fase alguna).")
        return

    jobs = collect_jobs(search_queries, search_queries_en, is_tech, general_sources=FUENTES_AUTOMATICAS)
    for job in jobs:
        job["job_id"] = make_job_id(job)

    aplicadas = storage.get_applied_job_ids(user_id)
    vistas = storage.get_seen_job_ids(user_id)
    candidatas_nuevas = [j for j in jobs if j["job_id"] not in aplicadas and j["job_id"] not in vistas]

    print(f"    {len(jobs)} ofertas encontradas, {len(candidatas_nuevas)} nunca vistas por este usuario.")
    if not candidatas_nuevas:
        return

    cv_text = cv_entry["cv_text"]
    # Ubicación del candidato guardada en el perfil (CVs clasificados desde
    # la Fase de cercanía en adelante). Los perfiles viejos no la tienen →
    # cand_location = None → no se penaliza nada por cercanía.
    ubic_guardada = perfil.get("ubicacion")
    cand_location = geo.parse_location(ubic_guardada) if ubic_guardada else None
    explicadas = rank_and_explain(
        cv_text, candidatas_nuevas, embedding_top_k=EMBEDDING_TOP_K,
        explain_top_n=MAX_OFERTAS_NUEVAS_A_EXPLICAR, cand_location=cand_location,
    )

    # Se marcan como vistas TODAS las que se llegaron a explicar (aunque no
    # lleguen al umbral de mail) — no tiene sentido volver a gastar IA
    # explicando la misma oferta floja la semana que viene.
    storage.mark_jobs_seen(user_id, [o["job_id"] for o in explicadas])

    para_mail = [o for o in explicadas if o.get("score", 0) >= UMBRAL_SCORE_MINIMO]
    if not para_mail:
        print(f"    {len(explicadas)} explicadas, ninguna llega a {UMBRAL_SCORE_MINIMO}/100 — no se manda mail.")
        return

    datos = _mail_del_usuario(admin_client, user_id)
    if not datos:
        return
    mail, nombre = datos

    enviar_resumen_semanal(mail, nombre, para_mail)
    print(f"    ✓ mail enviado a {mail}: {len(para_mail)} oferta(s) nueva(s) (de {len(explicadas)} explicadas).")


def main(solo_un_usuario: str | None = None) -> None:
    print("=" * 60)
    print("  Chequeo semanal de matches nuevos")
    print("=" * 60)

    if solo_un_usuario:
        usuarios = [solo_un_usuario]
    else:
        usuarios = storage.get_users_with_notifications_enabled()

    print(f"\n{len(usuarios)} usuario(s) con avisos activados.\n")
    if not usuarios:
        return

    from supabase import create_client

    admin_client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SECRET_KEY"))

    for i, user_id in enumerate(usuarios, 1):
        print(f"[{i}/{len(usuarios)}] {user_id}")
        try:
            procesar_usuario(user_id, admin_client)
        except Exception as e:
            # Un usuario con un error no tumba la corrida de los demás.
            print(f"    [!] ERROR procesando este usuario, se sigue con el próximo: {e}")
        time.sleep(1)  # margen chico entre usuarios, no golpear las fuentes de una


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--solo-un-usuario", default=None, help="user_id puntual, para probar sin recorrer a todos")
    args = parser.parse_args()
    main(args.solo_un_usuario)
