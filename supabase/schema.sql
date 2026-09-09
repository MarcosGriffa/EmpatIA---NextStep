-- schema.sql — Tablas de persistencia para EmpatIA | NextStep (Fase 2)
--
-- Cómo correrlo (una sola vez, lo hace Marcos desde el dashboard, no hace
-- falta instalar nada):
--   1. Entrá a https://supabase.com/dashboard -> tu proyecto
--   2. En el menú de la izquierda, "SQL Editor" -> "New query"
--   3. Pegá TODO este archivo y apretá "Run"
--   4. Listo — deberías ver "Success. No rows returned".
--
-- Es seguro correrlo más de una vez (todo tiene IF NOT EXISTS).
--
-- Nota de seguridad: se habilita Row Level Security (RLS) en las 3 tablas
-- SIN ninguna política — eso significa que la API pública de Supabase (la
-- que usaría la PUBLISHABLE_KEY, si el frontend alguna vez hablara directo
-- con Supabase) no puede leer ni escribir nada. Solo el backend (api/),
-- que usa la SECRET_KEY, puede — esa key salta las políticas de RLS por
-- diseño. Esto es intencional: hoy no hay login, así que no hay manera de
-- verificar "este usuario es dueño de esta fila" todavía.

create extension if not exists "pgcrypto"; -- para gen_random_uuid()

-- CVs subidos y su perfil clasificado por IA (área, seniority, skills, etc.)
--
-- cv_text: se guarda con la dirección exacta YA REDACTADA (calle+altura+piso
--   → "[dirección omitida]") — ver geo.redact_address, aplicado en
--   api/matching.py antes de este insert. El matching corre sobre el texto
--   completo en memoria; a la base va la versión sin dirección.
-- profile.ubicacion: string a nivel ciudad/partido (ej. "Vicente López,
--   Buenos Aires") o null. Vive dentro del jsonb "profile", no en una
--   columna aparte — no requiere migración. Sólo se usa para priorizar
--   ofertas presenciales/híbridas cercanas.
create table if not exists cv_profiles (
  id          uuid primary key default gen_random_uuid(),
  user_id     text not null,
  filename    text,
  cv_text     text,
  profile     jsonb,
  created_at  timestamptz not null default now()
);
create index if not exists cv_profiles_user_id_created_at_idx
  on cv_profiles (user_id, created_at desc);

-- Cada corrida de matching (resultado del pipeline para un CV puntual)
create table if not exists match_results (
  id          uuid primary key default gen_random_uuid(),
  user_id     text not null,
  cv_id       uuid references cv_profiles(id),
  profile     jsonb,
  results     jsonb not null,
  created_at  timestamptz not null default now()
);
create index if not exists match_results_user_id_created_at_idx
  on match_results (user_id, created_at desc);

-- Qué ofertas marcó cada usuario como "ya aplicado" (job_id = hash estable
-- de la oferta, calculado en api/job_utils.py)
create table if not exists applied_jobs (
  user_id     text not null,
  job_id      text not null,
  applied     boolean not null default true,
  applied_at  timestamptz not null default now(),
  primary key (user_id, job_id)
);

alter table cv_profiles   enable row level security;
alter table match_results enable row level security;
alter table applied_jobs  enable row level security;

-- ── Avisos por mail (19/08/2026) ────────────────────────────────────
-- Ver notificaciones_semanales.py — un chequeo automático, semanal, que
-- reusa el CV ya subido (no vuelve a pedir clasificarlo con IA) y avisa
-- por mail solo las ofertas NUEVAS que la persona todavía no vio.

-- Qué ofertas ya vio cada usuario (por búsqueda manual O por un chequeo
-- automático) — evita mandar dos veces la misma oferta por mail, y evita
-- que el chequeo automático vuelva a gastar IA explicando algo que ya
-- había considerado antes (aunque no haya llegado al mail, por puntaje bajo).
create table if not exists seen_jobs (
  user_id   text not null,
  job_id    text not null,
  seen_at   timestamptz not null default now(),
  primary key (user_id, job_id)
);

-- El interruptor de encendido/apagado. Apagado por defecto (opt-in) —
-- nadie queda anotado solo por crear una cuenta.
create table if not exists user_settings (
  user_id                text primary key,
  notificaciones_activas boolean not null default false,
  updated_at             timestamptz not null default now()
);

alter table seen_jobs      enable row level security;
alter table user_settings  enable row level security;
