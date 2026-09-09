import { NextRequest, NextResponse } from "next/server";
import { FASTAPI_URL } from "@/lib/config";
import { getAccessToken } from "@/lib/supabase/server";

// Corre el pipeline completo (clasificar CV + buscar en portales + matchear
// con IA) — puede tardar 1-2 minutos. No le ponemos límite de tiempo propio,
// dejamos que corra lo que tenga que correr en desarrollo local.
export const maxDuration = 300;

export async function POST(request: NextRequest) {
  // Fase 3: el user_id ya NO lo manda el cliente — se saca del token de
  // sesión, verificado del lado del motor (api/auth.py). Sin sesión, ni
  // siquiera intentamos: /subir-cv ya está protegida por proxy.ts, pero
  // esta ruta también se cubre sola por si alguien le pega directo.
  const token = await getAccessToken();
  if (!token) {
    return NextResponse.json({ error: "Iniciá sesión para subir tu CV." }, { status: 401 });
  }

  let incoming: FormData;
  try {
    incoming = await request.formData();
  } catch {
    return NextResponse.json({ error: "No se pudo leer el archivo enviado." }, { status: 400 });
  }

  const file = incoming.get("file");
  if (!(file instanceof Blob)) {
    return NextResponse.json({ error: "Falta el archivo del CV." }, { status: 400 });
  }

  const forward = new FormData();
  const filename = file instanceof File ? file.name : "cv.pdf";
  forward.append("file", file, filename);

  // Zona elegida a mano (opcional). El backend sólo la usa si el CV no trae
  // la ubicación. No es dato sensible a nivel dirección — es zona/ciudad.
  const zona = incoming.get("zona");
  if (typeof zona === "string" && zona.trim()) {
    forward.append("zona", zona.trim());
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${FASTAPI_URL}/api/match`, {
      method: "POST",
      body: forward,
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    return NextResponse.json(
      { error: "No se pudo conectar con el motor de matching. ¿Está corriendo el backend (api/main.py)?" },
      { status: 502 }
    );
  }

  const data = await upstream.json().catch(() => null);
  if (!upstream.ok) {
    return NextResponse.json(
      { error: data?.detail || "El motor de matching devolvió un error." },
      { status: upstream.status }
    );
  }

  return NextResponse.json(data);
}
