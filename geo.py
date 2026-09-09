"""
geo.py — Ubicación física: normalización jerárquica + privacidad.

Dos responsabilidades, las dos alrededor de "dónde":

1. NORMALIZAR ubicaciones de texto libre (heterogéneas por fuente) a una
   jerarquía propia, sin geocoding ni APIs externas:

       misma localidad/partido  >  misma zona metro  >  misma provincia
       >  mismo país  >  otro país / desconocido

   La fuente que trae ubicación accionable es Computrabajo, y viene ya
   semi-estructurada como "Localidad, Provincia" (ej. "Recoleta, Capital
   Federal", "Villa Luzuriaga, Buenos Aires-GBA"). Con una tabla de alias
   de provincias + una tabla de partidos del GBA por zona alcanza para la
   enorme mayoría del pool real. Ver la conversación de diseño: se descartó
   geocodificar por costo/latencia/otra API key, y porque el candidato
   argentino razona por zona ("¿es CABA / mi zona del conurbano / mi
   provincia?"), no por kilómetros. Si algún día el volumen lo justifica,
   este es el único archivo a tocar para enchufar geocoding.

2. REDACTAR la dirección exacta (calle + altura + piso/depto) del texto de
   un CV ANTES de persistirlo. La ubicación del candidato es dato personal
   de un tercero (los usuarios del producto): se guarda sólo a nivel
   ciudad/partido, nunca la dirección. Ver redact_address() y su uso en
   api/matching.py.

Sin dependencias fuera de la librería estándar.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


# ─────────────────────────────────────────────────────────────────────
#  Utilidades de texto
# ─────────────────────────────────────────────────────────────────────

def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def _norm(s: str) -> str:
    """minúsculas, sin acentos, sin espacios de más — para comparar nombres."""
    s = _strip_accents((s or "").strip().lower())
    s = re.sub(r"[.°º]", "", s)  # puntos y símbolos de grado
    s = re.sub(r"\s+", " ", s)
    return s


# ─────────────────────────────────────────────────────────────────────
#  Provincias argentinas + alias
# ─────────────────────────────────────────────────────────────────────

# clave normalizada (_norm) -> nombre canónico de provincia
_PROVINCE_ALIASES: dict[str, str] = {}


def _reg_prov(canonico: str, *alias: str) -> None:
    _PROVINCE_ALIASES[_norm(canonico)] = canonico
    for a in alias:
        _PROVINCE_ALIASES[_norm(a)] = canonico


_reg_prov(
    "CABA",
    "caba", "c a b a", "capital federal", "capital", "ciudad de buenos aires",
    "ciudad autonoma de buenos aires", "ciudad autónoma de buenos aires",
    "ciudad autonoma bs as", "cdad de buenos aires", "capfed",
)
# Provincia de Buenos Aires. El sufijo "-GBA" que agrega Computrabajo se
# maneja aparte (marca conurbano); acá sólo interesa la provincia.
_reg_prov(
    "Buenos Aires",
    "buenos aires", "buenos aires-gba", "buenos aires gba", "gran buenos aires",
    "gba", "provincia de buenos aires", "pcia de buenos aires",
    "pcia buenos aires", "prov de buenos aires", "bs as", "bsas", "pba",
)
_reg_prov("Córdoba", "cordoba")
_reg_prov("Santa Fe", "santa fe")
_reg_prov("Mendoza", "mendoza")
_reg_prov("Tucumán", "tucuman")
_reg_prov("Salta", "salta")
_reg_prov("Entre Ríos", "entre rios")
_reg_prov("Chaco", "chaco")
_reg_prov("Corrientes", "corrientes")
_reg_prov("Misiones", "misiones")
_reg_prov("San Juan", "san juan")
_reg_prov("San Luis", "san luis")
_reg_prov("Jujuy", "jujuy")
_reg_prov("Neuquén", "neuquen")
_reg_prov("Río Negro", "rio negro")
_reg_prov("Formosa", "formosa")
_reg_prov("Chubut", "chubut")
_reg_prov("Santiago del Estero", "santiago del estero")
_reg_prov("Catamarca", "catamarca")
_reg_prov("La Rioja", "la rioja")
_reg_prov("La Pampa", "la pampa")
_reg_prov("Santa Cruz", "santa cruz")
_reg_prov("Tierra del Fuego", "tierra del fuego", "tierra del fuego aias")

# Tokens que NO son Argentina (blobs de región de las fuentes remote, o
# países sueltos). Sirven para no confundirlos con una provincia.
_NON_AR_TOKENS = {
    "usa", "us", "united states", "eeuu", "estados unidos", "europe", "europa",
    "emea", "latam", "apac", "canada", "canadá", "uk", "united kingdom",
    "portugal", "spain", "españa", "espana", "brazil", "brasil", "mexico",
    "méxico", "chile", "uruguay", "colombia", "peru", "perú", "germany",
    "france", "worldwide", "global", "anywhere", "international",
}

_REMOTE_RE = re.compile(
    r"\b(remot[oa]?|remote|teletrabajo|home\s?office|trabajo desde casa|"
    r"desde casa|anywhere|worldwide|100\s?%?\s?remoto)\b",
    re.IGNORECASE,
)


# ─────────────────────────────────────────────────────────────────────
#  Zonas del AMBA (Área Metropolitana de Buenos Aires)
# ─────────────────────────────────────────────────────────────────────
#
# El candidato elige su zona de un <select> fijo en la web; las ofertas de
# Computrabajo traen el partido (o una localidad dentro del partido). Esta
# tabla mapea partido -> zona. Si no reconocemos el partido/localidad, la
# zona queda en None y el match cae al nivel "misma provincia".

_ZONA_NORTE = "GBA Norte"
_ZONA_OESTE = "GBA Oeste"
_ZONA_SUR = "GBA Sur"
_ZONA_LA_PLATA = "La Plata"
_ZONA_CABA = "CABA"

_GBA_PARTIDO_ZONA: dict[str, str] = {}


def _reg_gba(zona: str, *partidos: str) -> None:
    for p in partidos:
        _GBA_PARTIDO_ZONA[_norm(p)] = zona


_reg_gba(
    _ZONA_NORTE,
    "vicente lopez", "san isidro", "san fernando", "tigre", "san miguel",
    "jose c paz", "jose clemente paz", "malvinas argentinas", "pilar",
    "escobar", "campana", "zarate", "general san martin", "san martin",
    "gral san martin",
)
_reg_gba(
    _ZONA_OESTE,
    "la matanza", "moron", "merlo", "moreno", "ituzaingo", "hurlingham",
    "marcos paz", "general rodriguez", "gral rodriguez", "lujan",
    "tres de febrero", "general las heras", "gral las heras",
)
_reg_gba(
    _ZONA_SUR,
    "avellaneda", "lanus", "lomas de zamora", "quilmes", "berazategui",
    "florencio varela", "almirante brown", "alte brown", "esteban echeverria",
    "ezeiza", "presidente peron", "pte peron", "san vicente", "canuelas",
    "berisso", "ensenada",
)
_reg_gba(_ZONA_LA_PLATA, "la plata")

# Localidades / barrios sueltos -> partido del GBA (los que más aparecen
# etiquetados en los portales). Sólo los comunes: si falta uno, se degrada
# con elegancia al nivel provincia, no rompe nada.
_GBA_LOCALIDAD_PARTIDO: dict[str, str] = {}


def _reg_loc(partido: str, *localidades: str) -> None:
    for loc in localidades:
        _GBA_LOCALIDAD_PARTIDO[_norm(loc)] = _norm(partido)


_reg_loc("vicente lopez", "olivos", "florida", "munro", "la lucila", "carapachay", "villa martelli", "vicente lopez")
_reg_loc("san isidro", "martinez", "beccar", "boulogne", "acassuso", "villa adelina")
_reg_loc("san martin", "villa ballester", "san andres", "jose leon suarez", "villa maipu", "billinghurst")
_reg_loc("tres de febrero", "caseros", "ciudadela", "santos lugares", "el palomar", "saenz pena", "villa bosch")
_reg_loc("la matanza", "ramos mejia", "san justo", "isidro casanova", "gregorio de laferrere",
         "gonzalez catan", "villa luzuriaga", "lomas del mirador", "tapiales", "aldo bonzi",
         "rafael castillo", "ciudad evita", "virrey del pino")
_reg_loc("moron", "castelar", "haedo", "el palomar moron", "villa sarmiento")
_reg_loc("ituzaingo", "villa udaondo")
_reg_loc("hurlingham", "william morris", "villa tesei")
_reg_loc("merlo", "san antonio de padua", "libertad", "parque san martin")
_reg_loc("moreno", "paso del rey", "francisco alvarez", "cuartel v", "trujui")
_reg_loc("avellaneda", "sarandi", "wilde", "villa dominico", "gerli", "piñeyro", "pineyro", "dock sud")
_reg_loc("lanus", "lanus oeste", "lanus este", "remedios de escalada", "monte chingolo", "valentin alsina")
_reg_loc("lomas de zamora", "banfield", "temperley", "turdera", "llavallol", "ingeniero budge")
_reg_loc("quilmes", "bernal", "don bosco", "ezpeleta", "san francisco solano")
_reg_loc("almirante brown", "adrogue", "burzaco", "longchamps", "glew", "claypole", "rafael calzada", "san jose")
_reg_loc("esteban echeverria", "monte grande", "9 de abril", "el jaguel", "canning")
_reg_loc("berazategui", "hudson", "ranelagh", "villa espana", "plátanos", "platanos")
_reg_loc("florencio varela", "bosques", "ingeniero allan", "gobernador costa")
_reg_loc("tigre", "don torcuato", "general pacheco", "gral pacheco", "el talar", "benavidez", "nordelta", "rincon de milberg", "troncos del talar")
_reg_loc("escobar", "belen de escobar", "garin", "maquinista savio", "ingeniero maschwitz", "matheu")
_reg_loc("pilar", "del viso", "manuel alberti", "presidente derqui", "villa rosa", "fatima")
_reg_loc("malvinas argentinas", "grand bourg", "los polvorines", "tortuguitas", "pablo nogues", "ing pablo nogues")
_reg_loc("san miguel", "bella vista", "muñiz", "muniz", "campo de mayo")

# Nombres de zona tal cual los manda el <select> de la web.
_ZONA_LABELS = {
    _norm("CABA"): (_ZONA_CABA, "CABA"),
    _norm("Ciudad de Buenos Aires"): (_ZONA_CABA, "CABA"),
    _norm("GBA Norte"): (_ZONA_NORTE, "Buenos Aires"),
    _norm("Zona Norte"): (_ZONA_NORTE, "Buenos Aires"),
    _norm("GBA Oeste"): (_ZONA_OESTE, "Buenos Aires"),
    _norm("Zona Oeste"): (_ZONA_OESTE, "Buenos Aires"),
    _norm("GBA Sur"): (_ZONA_SUR, "Buenos Aires"),
    _norm("Zona Sur"): (_ZONA_SUR, "Buenos Aires"),
    _norm("La Plata"): (_ZONA_LA_PLATA, "Buenos Aires"),
}


# ─────────────────────────────────────────────────────────────────────
#  Estructura de una ubicación parseada
# ─────────────────────────────────────────────────────────────────────

@dataclass
class Location:
    raw: str = ""
    localidad: str | None = None      # partido/barrio/ciudad, normalizado (_norm)
    localidad_display: str | None = None  # igual pero con acentos/mayúsculas originales
    partido: str | None = None        # partido del GBA si se pudo resolver
    zona: str | None = None           # "CABA" | "GBA Norte/Oeste/Sur" | "La Plata" | None
    provincia: str | None = None      # nombre canónico, o None
    pais: str | None = None           # "AR" | None (desconocido / no-AR)
    is_remote: bool = False
    _empty: bool = field(default=False, repr=False)

    @property
    def is_unknown(self) -> bool:
        """No sabemos nada útil para comparar cercanía."""
        return not self.is_remote and not self.zona and not self.provincia and not self.localidad


def parse_location(raw: str | None) -> Location:
    """Parsea un string de ubicación (de una oferta o del candidato) a la
    estructura jerárquica. Tolera:
      - "Recoleta, Capital Federal"        (formato Computrabajo)
      - "Villa Luzuriaga, Buenos Aires-GBA"
      - "Remoto (Argentina)"               (Jooble)
      - "Europe,  USA" / "APAC,  EMEA, ..." (blobs de fuentes remote)
      - "GBA Norte" / "CABA" / "Córdoba"   (valores del <select> de la web)
      - "" / None
    Nunca lanza excepción.
    """
    raw = (raw or "").strip()
    if not raw:
        return Location(raw="", _empty=True)

    loc = Location(raw=raw)
    low = raw.lower()

    if _REMOTE_RE.search(low):
        loc.is_remote = True
        # "Remoto (Argentina)" igual nos dice el país
        if "argentina" in low or re.search(r"\bar\b", low):
            loc.pais = "AR"
        return loc

    # Etiqueta de zona directa desde el <select>
    label_hit = _ZONA_LABELS.get(_norm(raw))
    if label_hit:
        loc.zona, loc.provincia = label_hit
        loc.pais = "AR"
        return loc

    if "argentina" in low:
        loc.pais = "AR"

    # Partir en componentes por coma / barra / guión largo
    parts = [p.strip() for p in re.split(r"[,/;|]|\s[–-]\s", raw) if p.strip()]
    if not parts:
        return loc

    # ¿El último componente es una provincia conocida?
    tail_norm = _norm(parts[-1])
    tail_norm = re.sub(r"[()]", "", tail_norm).strip()
    prov = _PROVINCE_ALIASES.get(tail_norm)
    gba_flag = "gba" in tail_norm or "gran buenos aires" in tail_norm

    if prov:
        loc.provincia = prov
        loc.pais = "AR"
        if prov == "CABA":
            loc.zona = _ZONA_CABA
        head = parts[0] if len(parts) >= 2 else ""
        if head:
            _set_localidad(loc, head)
            _resolve_gba_zone(loc, gba_flag)
        elif prov == "Buenos Aires" and gba_flag:
            # "Buenos Aires-GBA" sin localidad -> sabemos que es conurbano
            pass
        return loc

    # Sin provincia reconocible. ¿Es un país / región no-AR?
    for p in parts:
        if _norm(re.sub(r"[()]", "", p)) in _NON_AR_TOKENS:
            loc.pais = None  # explícitamente fuera de AR / desconocido
            return loc

    # ¿Un único token que es un partido/localidad del GBA? (ej. "Rosario"
    # no lo es, pero "Quilmes" sí)
    single = _norm(parts[0])
    if single in _GBA_PARTIDO_ZONA:
        _set_localidad(loc, parts[0])
        loc.partido = single
        loc.zona = _GBA_PARTIDO_ZONA[single]
        loc.provincia = "Buenos Aires"
        loc.pais = "AR"
        return loc
    if single in _GBA_LOCALIDAD_PARTIDO:
        _set_localidad(loc, parts[0])
        _resolve_gba_zone(loc, gba_flag=True)
        loc.provincia = "Buenos Aires"
        loc.pais = "AR"
        return loc

    # Ciudad grande del interior sin provincia explícita: casos comunes que
    # aparecen sueltos en el pool real.
    _CIUDAD_PROV = {
        "rosario": "Santa Fe", "cordoba": "Córdoba", "mendoza": "Mendoza",
        "la plata": "Buenos Aires", "mar del plata": "Buenos Aires",
        "san miguel de tucuman": "Tucumán", "tucuman": "Tucumán",
        "salta": "Salta", "neuquen": "Neuquén", "bahia blanca": "Buenos Aires",
    }
    if single in _CIUDAD_PROV:
        _set_localidad(loc, parts[0])
        loc.provincia = _CIUDAD_PROV[single]
        loc.pais = "AR"
        if single == "la plata":
            loc.zona = _ZONA_LA_PLATA
        return loc

    # No pudimos ubicarlo. Dejamos localidad como pista pero sin nivel.
    if single:
        _set_localidad(loc, parts[0])
    return loc


def _set_localidad(loc: Location, texto: str) -> None:
    """Fija localidad (normalizada, para comparar) y localidad_display (con
    acentos/mayúsculas, para mostrar)."""
    texto = (texto or "").strip()
    loc.localidad = _norm(texto) or None
    _MINUS = {"de", "del", "la", "las", "los", "y"}
    palabras = [
        w if (w.lower() in _MINUS and i > 0) else w[:1].upper() + w[1:].lower()
        for i, w in enumerate(texto.split())
    ]
    loc.localidad_display = " ".join(palabras) or None


def _resolve_gba_zone(loc: Location, gba_flag: bool) -> None:
    """Dado loc.localidad, intenta completar partido + zona del GBA."""
    if not loc.localidad:
        return
    key = loc.localidad
    if key in _GBA_PARTIDO_ZONA:
        loc.partido = key
        loc.zona = _GBA_PARTIDO_ZONA[key]
        return
    partido = _GBA_LOCALIDAD_PARTIDO.get(key)
    if partido:
        loc.partido = partido
        loc.zona = _GBA_PARTIDO_ZONA.get(partido)


# ─────────────────────────────────────────────────────────────────────
#  Cercanía candidato ↔ oferta
# ─────────────────────────────────────────────────────────────────────

_PROX_MISMA_LOCALIDAD = 1.0
_PROX_MISMA_ZONA = 0.8
_PROX_MISMA_PROVINCIA = 0.5   # también: misma área metro (AMBA), aunque cruce CABA↔GBA
_PROX_MISMO_PAIS = 0.25
_PROX_LEJOS = 0.0

# Zonas que forman un mismo mercado laboral (AMBA). CABA y el conurbano son
# la misma área a efectos de "¿me queda cerca?" aunque sean jurisdicciones
# distintas — Vicente López limita con CABA. La Plata se deja aparte (viaje
# real de +1 h, es su propia aglomeración).
_ZONAS_AMBA = {_ZONA_CABA, _ZONA_NORTE, _ZONA_OESTE, _ZONA_SUR}


def _is_amba(loc: Location) -> bool:
    if loc.zona in _ZONAS_AMBA:
        return True
    # "Buenos Aires-GBA" sin localidad reconocida: sabemos que es conurbano
    return loc.provincia == "Buenos Aires" and "gba" in _norm(loc.raw)


def proximity_score(
    cand: Location | None, job: Location, modality: str
) -> float | None:
    """
    Devuelve un score de cercanía geográfica 0-1, o None cuando la cercanía
    NO debe influir (y por lo tanto no se penaliza nada):
      - la oferta es remota
      - la modalidad no es 'presencial' ni 'hibrido' (desconocida / vacía)
      - no conocemos la ubicación del candidato
      - no podemos ubicar la oferta
    """
    modality = _norm(modality or "")
    if job.is_remote or modality not in ("presencial", "hibrido"):
        return None
    if cand is None or cand.is_unknown:
        return None
    if job.is_unknown:
        return None

    # Oferta explícitamente en otro país
    if job.pais is not None and job.pais != "AR":
        return _PROX_LEJOS
    if job.pais is None and job.provincia is None and job.zona is None:
        return None

    # Misma localidad / partido
    if cand.localidad and job.localidad and cand.localidad == job.localidad:
        return _PROX_MISMA_LOCALIDAD
    if cand.partido and job.partido and cand.partido == job.partido:
        return _PROX_MISMA_LOCALIDAD

    # Misma zona metro (CABA, GBA Norte/Oeste/Sur, La Plata)
    if cand.zona and job.zona and cand.zona == job.zona:
        return _PROX_MISMA_ZONA

    # Misma área metropolitana (AMBA): CABA + conurbano cuentan como un
    # mismo mercado laboral aunque crucen la General Paz. Evita castigar
    # "Vicente López (candidato) ↔ Palermo (oferta)" como si fuera otra
    # provincia.
    if _is_amba(cand) and _is_amba(job):
        return _PROX_MISMA_PROVINCIA

    # Misma provincia
    if cand.provincia and job.provincia and cand.provincia == job.provincia:
        return _PROX_MISMA_PROVINCIA

    # Ambas en Argentina pero distinta provincia/zona
    cand_ar = cand.pais == "AR" or cand.provincia is not None or cand.zona is not None
    job_ar = job.pais == "AR" or job.provincia is not None or job.zona is not None
    if cand_ar and job_ar:
        return _PROX_MISMO_PAIS

    return None


# proximity -> (factor presencial, factor híbrido). Piso 0.5; nunca esconde
# del todo un buen match lejano (mudanza, la persona viaja igual).
_FACTOR_TABLE: dict[float, tuple[float, float]] = {
    _PROX_MISMA_LOCALIDAD: (1.00, 0.95),
    _PROX_MISMA_ZONA:      (1.00, 0.90),
    _PROX_MISMA_PROVINCIA: (0.65, 0.82),
    _PROX_MISMO_PAIS:      (0.50, 0.75),
    _PROX_LEJOS:           (0.50, 0.75),
}


def factor_geo(prox: float | None, modality: str) -> float:
    """Multiplicador para el score del LLM. 1.0 = no penaliza."""
    if prox is None:
        return 1.0
    presencial, hibrido = _FACTOR_TABLE.get(prox, (1.0, 1.0))
    return hibrido if _norm(modality or "") == "hibrido" else presencial


def proximity_label(
    cand: Location | None, job: Location, modality: str, prox: float | None
) -> str:
    """Texto corto para el chip de la tarjeta. Siempre devuelve algo."""
    if job.is_remote:
        return "Remoto"
    mod = _norm(modality or "")
    mod_txt = {"presencial": "Presencial", "hibrido": "Híbrido"}.get(mod, "")

    if prox is None:
        if mod_txt and (cand is None or cand.is_unknown):
            return f"{mod_txt} · agregá tu zona para ver cercanía"
        if mod_txt:
            return f"{mod_txt} · ubicación no especificada"
        return "Modalidad no confirmada"

    lugar = _job_place_str(job)
    if prox >= _PROX_MISMA_LOCALIDAD:
        base = "tu zona"
    elif prox >= _PROX_MISMA_ZONA:
        base = "misma zona"
    elif prox >= _PROX_MISMA_PROVINCIA:
        # 0.5 puede ser "misma provincia" o "misma área metro (AMBA)" cuando
        # cruza CABA↔GBA — distinguirlo para que el chip no diga algo falso.
        cross_amba = cand is not None and _is_amba(cand) and _is_amba(job) and cand.zona != job.zona
        base = "área metro" if cross_amba else "misma provincia"
    else:
        base = "otra provincia"
    rel = f"{base} ({lugar})" if lugar else base
    return f"{mod_txt} · {rel}" if mod_txt else rel


def _job_place_str(job: Location) -> str:
    if job.localidad:
        return job.localidad_display or job.localidad.title()
    if job.zona:
        return job.zona
    if job.provincia:
        return job.provincia
    return ""


def annotate_job(job: dict, cand: Location | None) -> None:
    """Agrega al dict de la oferta, in-place:
        proximity        float 0-1 | None
        proximity_label  str  (para el chip)
        factor_geo       float 0.5-1.0
        score_final      int  = round(score * factor_geo)   [score del LLM intacto]
    Si la oferta no tiene 'score' todavía, score_final queda = score.
    """
    jloc = parse_location(job.get("location", ""))
    modality = job.get("modality") or ""
    prox = proximity_score(cand, jloc, modality)
    factor = factor_geo(prox, modality)

    job["proximity"] = prox
    job["proximity_label"] = proximity_label(cand, jloc, modality, prox)
    job["factor_geo"] = round(factor, 3)

    score = job.get("score")
    if isinstance(score, (int, float)):
        job["score_final"] = int(round(score * factor))
    else:
        job["score_final"] = score


def sort_key_score_final(job: dict):
    """Para ordenar resultados: score ya ajustado por cercanía, desc."""
    val = job.get("score_final")
    if val is None:
        val = job.get("score", 0)
    return val


# ─────────────────────────────────────────────────────────────────────
#  Ubicación del candidato: normalización a nivel ciudad
# ─────────────────────────────────────────────────────────────────────

def normalize_candidate_location(raw: str | None) -> str | None:
    """Toma lo que dijo el CV (o el <select> de la web) y devuelve un string
    a nivel CIUDAD/PARTIDO — NUNCA una dirección. Estructuralmente no puede
    contener calle/altura porque se reconstruye desde los componentes que
    parse_location() supo identificar.

    "Calle Falsa 123, Vicente López, Buenos Aires" -> "Vicente López, Buenos Aires"
    "CABA"                                          -> "CABA"
    "Palermo, Capital Federal"                      -> "Palermo, CABA"
    "no figura"                                     -> None
    """
    raw = (raw or "").strip()
    if not raw or _norm(raw) in {"", "n/a", "na", "no figura", "no especifica",
                                 "sin datos", "null", "none", "-"}:
        return None

    # Primero sacamos cualquier rastro de dirección del texto suelto.
    raw = redact_address(raw).replace(ADDRESS_PLACEHOLDER, " ")
    raw = re.sub(r"\s*,\s*,\s*", ", ", raw).strip(" ,")
    if not raw:
        return None

    loc = parse_location(raw)

    partes: list[str] = []
    if loc.localidad:
        partes.append(loc.localidad_display or loc.localidad.title())
    if loc.zona and loc.zona not in (l for l in partes):
        if not (loc.provincia == "CABA" and loc.zona == _ZONA_CABA and partes):
            partes.append(loc.zona)
    if loc.provincia and loc.provincia not in partes:
        partes.append(loc.provincia)

    if partes:
        # Evitar "CABA, CABA"
        dedup = list(dict.fromkeys(partes))
        return ", ".join(dedup)

    if loc.is_remote:
        return None
    # No lo pudimos estructurar: devolvemos el texto limpio, capado a los
    # últimos 2 componentes (lo más específico suele ir primero, la
    # provincia al final) y sin números.
    limpio = re.sub(r"\d+", "", raw)
    limpio = re.sub(r"\s+", " ", limpio).strip(" ,")
    comps = [c.strip() for c in limpio.split(",") if c.strip()]
    return ", ".join(comps[-2:]) if comps else None


# ─────────────────────────────────────────────────────────────────────
#  Redacción de dirección exacta en el texto de un CV
# ─────────────────────────────────────────────────────────────────────

ADDRESS_PLACEHOLDER = "[dirección omitida]"

# Tipos de vía que, seguidos de un nombre y una altura, son inequívocamente
# una dirección postal. Deliberadamente NO se incluyen palabras ambiguas
# ("camino", "acceso", "manzana"): el objetivo es no comerse texto legítimo
# del CV, aun a costa de dejar pasar alguna dirección rara.
_VIA = (
    r"calle|av\.?|avda\.?|avenida|bv\.?|blvd\.?|boulevard|bulevar|diag\.?|"
    r"diagonal|pje\.?|pasaje|ruta|autopista|mza\.?|mz\.?"
)

# Complementos que suelen venir pegados a la altura (piso, depto, etc.).
_COMPLEMENTO = (
    r"(?:\s*[,\-–]?\s*(?:piso|p\.?|pb|depto\.?|dpto\.?|dto\.?|dep)\s*"
    r"\.?\s*[\wº°]{1,4})"
)

# 1) Vía + nombre + altura (+ complementos).  Ej: "Av. Corrientes 1234, Piso 4"
_ADDR_VIA_RE = re.compile(
    rf"\b(?:{_VIA})\s+"
    rf"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9'’.\-]+(?:\s+[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9'’.\-]+){{0,4}}?"
    rf"\s+(?:n[º°\.]?\s*)?\d{{1,5}}"
    rf"(?:{_COMPLEMENTO}){{0,3}}",
    re.IGNORECASE,
)

# 2) Línea rotulada.  Ej: "Domicilio: San Martín 2450, Vicente López"
#    Se reemplaza TODO el valor (la ciudad, si hace falta, se recupera del
#    perfil que arma la IA sobre el texto ORIGINAL, antes de redactar).
#    "Dirección" EXIGE dos puntos inmediatos, para no pisar "Dirección de
#    correo", "Dirección web", etc. "Domicilio"/"Residencia" son inequívocos.
_ADDR_LABEL_RE = re.compile(
    r"(?im)^([ \t]*(?:(?:domicilio|residencia)[ \t]*:?[ \t]*"
    r"|direcci[oó]n[ \t]*:[ \t]*)).+$"
)

# 3) Nombre + altura + complemento SIN tipo de vía, pero con piso/depto
#    explícito (fuerte señal de dirección).  Ej: "Rivadavia 5600 3º B"
_ADDR_BARE_RE = re.compile(
    r"\b[A-ZÁÉÍÓÚÜÑ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ'’.\-]+(?:\s+[A-ZÁÉÍÓÚÜÑ0-9][A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9'’.\-]+){0,3}?"
    r"\s+\d{2,5}\s*[,\-–]?\s*(?:piso|p\.?|pb|depto\.?|dpto\.?|dto\.?)\s*\.?\s*[\wº°]{1,4}\b",
    re.IGNORECASE,
)


def redact_address(text: str) -> str:
    """Reemplaza direcciones postales exactas (calle + altura + piso/depto)
    por un marcador, sin tocar el resto del CV.

    Conservador a propósito: exige un tipo de vía ("calle/av/…") + altura, o
    un rótulo explícito ("Domicilio:"), o altura + piso/depto. NO toca:
      - fechas (03/10/2024)               -> no hay tipo de vía ni piso
      - versiones (Python 3.11, n8n)      -> idem
      - "Gestión de 12 personas"          -> idem
      - "Casa del Deporte", "Las Dellas"  -> no hay altura
      - "Piso" como parte de otra palabra -> \\b + exige altura previa
    """
    if not text:
        return text

    text = _ADDR_LABEL_RE.sub(rf"\1{ADDRESS_PLACEHOLDER}", text)
    text = _ADDR_VIA_RE.sub(ADDRESS_PLACEHOLDER, text)
    text = _ADDR_BARE_RE.sub(ADDRESS_PLACEHOLDER, text)
    # Colapsar un placeholder pegado a comas sobrantes: "X, [dir], Y" queda igual,
    # pero "[dir], , Y" -> "[dir], Y"
    text = re.sub(rf"({re.escape(ADDRESS_PLACEHOLDER)})(\s*,\s*)+", r"\1, ", text)
    return text
