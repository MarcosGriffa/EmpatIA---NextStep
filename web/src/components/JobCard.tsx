"use client";

import type { JobResult } from "@/lib/types";
import { TailorCvButton } from "./TailorCvButton";

function scoreBadgeClass(score: number | undefined) {
  if (score === undefined) return "bg-brown-body";
  if (score >= 80) return "bg-olive";
  if (score >= 50) return "bg-mustard";
  return "bg-terracota";
}

export function JobCard({
  job,
  onToggleApplied,
}: {
  job: JobResult;
  onToggleApplied: (jobId: string, applied: boolean) => void;
}) {
  const applied = !!job.applied;

  return (
    <article className="rounded-3xl border border-brown-title/10 bg-white p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3
            className={`text-lg font-bold ${
              applied ? "text-brown-body line-through decoration-2" : "text-brown-title"
            }`}
          >
            {job.title}
          </h3>
          <p className="mt-1 text-sm text-brown-body">
            {job.company} {job.location ? `· ${job.location}` : ""} · {job.source}
          </p>
          {job.proximity_label && (
            <p className="mt-2 inline-block rounded-full bg-cream-soft px-3 py-1 text-xs font-semibold text-brown-title">
              📍 {job.proximity_label}
            </p>
          )}
        </div>

        {applied ? (
          <span className="shrink-0 rounded-full bg-olive px-4 py-1 text-xs font-bold text-white">
            Ya aplicaste
          </span>
        ) : (
          <span
            className={`shrink-0 rounded-full px-4 py-1 text-xs font-bold text-white ${scoreBadgeClass(job.score)}`}
          >
            {job.score ?? "?"}/100
          </span>
        )}
      </div>

      {job.explicacion && <p className="mt-4 text-sm text-brown-body">{job.explicacion}</p>}

      {(job.matches?.length || job.gaps?.length) && (
        <div className="mt-4 flex flex-wrap gap-2">
          {job.matches?.map((m) => (
            <span
              key={m}
              className="rounded-full bg-olive/10 px-3 py-1 text-xs font-semibold text-olive-dark"
            >
              ✓ {m}
            </span>
          ))}
          {job.gaps?.map((g) => (
            <span
              key={g}
              className="rounded-full bg-terracota/10 px-3 py-1 text-xs font-semibold text-terracota-dark"
            >
              ✗ {g}
            </span>
          ))}
        </div>
      )}

      <div className="mt-5 flex flex-wrap items-center justify-between gap-4 border-t border-brown-title/10 pt-4">
        <a
          href={job.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm font-bold text-terracota hover:text-terracota-dark"
        >
          Ver aviso →
        </a>

        <TailorCvButton jobId={job.job_id} />

        <label className="flex cursor-pointer items-center gap-2 text-sm font-semibold text-brown-title">
          <input
            type="checkbox"
            checked={applied}
            onChange={(e) => onToggleApplied(job.job_id, e.target.checked)}
            className="h-5 w-5 rounded-md accent-olive"
          />
          Marcar como aplicado
        </label>
      </div>
    </article>
  );
}
