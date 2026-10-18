"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { getLatestResults, setApplied } from "@/lib/api";
import type { MatchRunResponse } from "@/lib/types";
import { JobCard } from "@/components/JobCard";
import { NotificationToggle } from "@/components/NotificationToggle";

// Cuántas ofertas se muestran. El motor ya devuelve exactamente esta
// cantidad (ver SHOW_TOP_N en pipeline.py), pero recortamos también acá
// para que las corridas viejas —guardadas cuando el motor devolvía 15— se
// vean igual que las nuevas.
const MAX_OFERTAS = 10;

export default function ResultadosPage() {
  const [data, setData] = useState<MatchRunResponse | null | undefined>(undefined); // undefined = cargando
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getLatestResults()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Error desconocido."));
  }, []);

  async function handleToggle(jobId: string, applied: boolean) {
    if (!data) return;
    // Optimista: actualizamos la pantalla ya, y si falla el guardado lo revertimos.
    setData({
      ...data,
      results: data.results.map((r) => (r.job_id === jobId ? { ...r, applied } : r)),
    });
    try {
      await setApplied(jobId, applied);
    } catch {
      setData((prev) =>
        prev
          ? { ...prev, results: prev.results.map((r) => (r.job_id === jobId ? { ...r, applied: !applied } : r)) }
          : prev
      );
    }
  }

  if (error) {
    return (
      <Centered>
        <p className="font-semibold text-terracota-dark">{error}</p>
        <Link href="/subir-cv" className="mt-4 font-bold text-terracota">
          Volver a intentar →
        </Link>
      </Centered>
    );
  }

  if (data === undefined) {
    return (
      <Centered>
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-mustard border-t-transparent" />
      </Centered>
    );
  }

  if (data === null) {
    return (
      <Centered>
        <p className="font-bold text-brown-title">Todavía no subiste ningún CV.</p>
        <Link
          href="/subir-cv"
          className="mt-4 rounded-full bg-terracota px-6 py-3 font-bold text-white hover:bg-terracota-dark"
        >
          Subir mi CV
        </Link>
      </Centered>
    );
  }

  const { profile } = data;
  const results = data.results.slice(0, MAX_OFERTAS);
  const pendientes = results.filter((r) => !r.applied).length;

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-12">
      <Link href="/" className="text-sm font-semibold text-terracota">
        ← Volver al inicio
      </Link>

      <h1 className="mt-4 text-3xl font-extrabold text-brown-title">Tus matches</h1>
      <p className="mt-2 text-brown-body">
        Detectamos tu perfil como <strong className="text-brown-title">{profile.area}</strong>{" "}
        ({profile.seniority}). Encontramos {results.length} ofertas
        {pendientes !== results.length ? `, ${pendientes} todavía sin aplicar` : ""}.
      </p>

      {profile.skills?.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {profile.skills.map((s) => (
            <span key={s} className="rounded-full bg-cream-soft px-3 py-1 text-xs font-semibold text-brown-title">
              {s}
            </span>
          ))}
        </div>
      )}

      <NotificationToggle />

      <div className="mt-8 space-y-5">
        {results.length === 0 && (
          <p className="text-brown-body">
            No encontramos ofertas nuevas esta vez (puede ser que ya hayas aplicado a todas
            las que matcheaban). Probá de nuevo más tarde.
          </p>
        )}
        {results.map((job) => (
          <JobCard key={job.job_id} job={job} onToggleApplied={handleToggle} />
        ))}
      </div>

      <div className="mt-10 text-center">
        <Link href="/subir-cv" className="text-sm font-bold text-terracota hover:text-terracota-dark">
          Subir otro CV / repetir la búsqueda →
        </Link>
      </div>
    </main>
  );
}

function Centered({ children }: { children: ReactNode }) {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">{children}</main>
  );
}
