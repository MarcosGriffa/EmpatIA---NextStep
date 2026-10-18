import { IconNetwork, IconMatch, IconCheckCircle, IconGlobe } from "./illustrations/icons";

/**
 * HeroStats — bloque de números del hero (17/08/2026). Reemplaza a la
 * composición de los 3 profesionales conectados al logo "TUS MATCHES"
 * (ver HeroMindMap.tsx, que quedó sin uso pero no se borró por si se
 * quiere reubicar en otra sección).
 *
 * ⚠️ REGLA para tocar estos números: solo pueden reflejar capacidades
 * REALES y verificables del sistema. Nada de métricas de uso inventadas
 * ("usuarios activos", "tasa de éxito", "personas contratadas") porque
 * todavía no tenemos usuarios reales y sería marketing falso.
 *
 * De dónde sale cada uno, para poder revisarlos si el sistema cambia:
 *   - 6 portales  -> GENERAL_SOURCES + TECH_SOURCES en pipeline.py
 *                    (Computrabajo, Jooble + RemoteOK, Jobicy, Himalayas,
 *                    WeWorkRemotely)
 *   - +150 avisos -> corridas reales medidas: 179, 221 y 241 avisos únicos.
 *                    Se usa 150 como piso conservador, no un promedio
 *                    inflado.
 *   - 10 matches  -> SHOW_TOP_N en pipeline.py (el LLM lee EXPLAIN_TOP_N = 30)
 *   - Todos       -> el motor no tiene lista de rubros; clasifica el CV
 *                    que le den. Es la promesa del título del hero.
 */

const stats = [
  {
    Icon: IconNetwork,
    valor: "6",
    etiqueta: "portales de empleo en una sola búsqueda",
    color: "text-olive",
    fondo: "bg-olive-tint",
  },
  {
    Icon: IconMatch,
    valor: "+150",
    etiqueta: "avisos revisados cada vez que subís tu CV",
    color: "text-terracota",
    fondo: "bg-terracota-tint",
  },
  {
    Icon: IconCheckCircle,
    valor: "10",
    etiqueta: "matches explicados uno por uno, con sus puntos flojos",
    color: "text-mustard-tint-dark",
    fondo: "bg-mustard-tint",
  },
  {
    Icon: IconGlobe,
    valor: "Todos",
    etiqueta: "los rubros, no solo tecnología",
    color: "text-olive",
    fondo: "bg-olive-tint",
  },
];

export function HeroStats() {
  return (
    <div className="mx-auto w-full max-w-lg">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {stats.map((s) => (
          <div
            key={s.etiqueta}
            className="rounded-3xl border border-brown-title/10 bg-white p-6"
          >
            <span className={`flex h-11 w-11 items-center justify-center rounded-full ${s.fondo} ${s.color}`}>
              <s.Icon className="h-5 w-5" />
            </span>
            <p className="mt-4 text-4xl font-extrabold leading-none text-brown-title">{s.valor}</p>
            <p className="mt-2 text-sm leading-snug text-brown-body">{s.etiqueta}</p>
          </div>
        ))}
      </div>

    </div>
  );
}
