export interface CvProfile {
  area: string;
  is_tech: boolean;
  seniority: string;
  skills: string[];
  search_queries: string[];
  search_queries_en?: string[];
  /** Ciudad/partido + provincia. Nunca la dirección exacta. null si no se pudo detectar. */
  ubicacion?: string | null;
}

export interface JobResult {
  job_id: string;
  source: string;
  title: string;
  company: string;
  location: string;
  modality?: string;
  description?: string;
  url: string;
  posted_at?: string;
  scraped_at?: string;
  similarity?: number;
  score?: number;
  /** Score del LLM ya ajustado por cercanía geográfica (score * factor_geo). */
  score_final?: number;
  /** Cercanía candidato↔oferta 0-1, o null si no aplica (remoto / sin ubicación). */
  proximity?: number | null;
  /** Texto para el chip de cercanía, ej. "Presencial · misma zona (Vicente López)". */
  proximity_label?: string;
  factor_geo?: number;
  matches?: string[];
  gaps?: string[];
  explicacion?: string;
  applied?: boolean;
}

export interface MatchRunResponse {
  cv_id: string;
  match_id: string;
  profile: CvProfile;
  results: JobResult[];
}
