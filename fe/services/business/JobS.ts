import HttpS from "@/services/tech/HttpS";
import type { TFn } from "@/services/tech/I18nS";
import type { components } from "@/types/api";

// ============================================================================
// Private
// ============================================================================

const isAxiosError = (
  err: unknown
): err is { response: { status: number; data?: { detail?: { limit?: number } } } } =>
  typeof err === "object" && err !== null && "response" in err;

// defect_type is a free-form identifier the vision LLM assigns (see
// AnthropicAdapter._ASSESS_SYSTEM_PROMPT) — these have translations; anything
// else is humanized (snake_case → Title Case) rather than shown raw.
const KNOWN_DEFECT_TYPES = new Set([
  "crack",
  "water_damage",
  "mould",
  "spalling",
  "none",
  // Repair Methodology Matrix canonical types (docs/business/DOMAIN_EXPERT_FEEDBACK.md §18)
  "rising_damp",
  "concrete_spalling",
  "paint_blistering",
  "efflorescence_crack",
  "interior_compound_damp",
  "hidden_column_leak",
  "balcony_junction_damp",
  "boundary_wall_crack",
  "biological_streak",
  "facade_delamination",
  // Promoted clusters (CLUSTERS.md)
  "window_opening_crack",
  "ac_condensate_leak",
]);

const KNOWN_SEVERITIES = new Set(["low", "medium", "high", "critical"]);

const humanize = (identifier: string): string =>
  identifier
    .split("_")
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(" ");

// Filename-safe slug: lowercase, spaces/underscores collapsed to single hyphens, anything
// that isn't a letter (incl. non-Latin scripts for DE/RU/EL reports), digit, or hyphen dropped.
const slugify = (text: string): string =>
  text
    .toLowerCase()
    .replace(/[_\s]+/g, "-")
    .replace(/[^\p{L}\p{N}-]/gu, "")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");

const filenameDate = (isoDate: string): string => {
  const d = new Date(isoDate);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}${pad(d.getMonth() + 1)}${String(d.getFullYear()).slice(2)}`;
};

// ============================================================================
// Public service API
// ============================================================================

export type ReportStatus = components["schemas"]["ReportStatus"];
export type VerificationItem = components["schemas"]["VerificationItem"];
export type Report = components["schemas"]["ReportItem"];

export class FreeTierError extends Error {
  readonly limit: number;

  constructor(limit: number) {
    super("Free tier limit reached");
    this.name = "FreeTierError";
    this.limit = limit;
  }
}

const listReports = (token: string): Promise<Report[]> => HttpS.get<Report[]>("/jobs", token);

const upload = async (
  files: File[],
  description: string,
  token: string,
  name?: string | null,
  language = "en"
): Promise<{ id: string }> => {
  const formData = new FormData();
  for (const file of files) formData.append("files", file);
  formData.append("description", description);
  if (name) formData.append("name", name);
  formData.append("language", language);
  try {
    const raw = await HttpS.postForm<{ job_id: string }>("/upload", formData, token);
    return { id: raw.job_id };
  } catch (err) {
    if (isAxiosError(err) && err.response.status === 402) {
      throw new FreeTierError(err.response.data?.detail?.limit ?? 0);
    }
    throw err;
  }
};

const getReport = (id: string, token: string): Promise<Report> =>
  HttpS.get<Report>(`/report/${id}`, token);

export type RespondBody =
  | { reply: string | null }
  | { requestExpertReview: true; assignedExpertId: string };

const respond = (id: string, body: RespondBody, token: string): Promise<{ ok: boolean }> => {
  const payload =
    "requestExpertReview" in body
      ? {
          request_expert_review: body.requestExpertReview,
          assigned_expert_id: body.assignedExpertId,
        }
      : { reply: body.reply };
  return HttpS.post<{ ok: boolean }>(`/jobs/${id}/respond`, payload, token);
};

const defectTypeLabel = (t: TFn, defectType: string | null): string | null => {
  if (!defectType) return null;
  if (!KNOWN_DEFECT_TYPES.has(defectType)) return humanize(defectType);
  return t(`report_defect_type_${defectType}` as Parameters<TFn>[0]) || humanize(defectType);
};

const severityLabel = (t: TFn, severity: string | null): string | null => {
  if (!severity) return null;
  if (!KNOWN_SEVERITIES.has(severity)) return humanize(severity);
  return t(`report_severity_${severity}` as Parameters<TFn>[0]) || humanize(severity);
};

// A contextual, localized name for the downloaded PDF instead of the generic "report.pdf" —
// e.g. "water-damage-assessment-130726.pdf" (EN) or "wasserschaden-bewertung-130726.pdf" (DE).
const reportFilename = (t: TFn, report: Report): string => {
  const defect = defectTypeLabel(t, report.defect_type ?? null) ?? "report";
  const word = t("report_filename_word");
  const date = filenameDate(report.created_at);
  return `${slugify(`${defect}-${word}`)}-${date}.pdf`;
};

const JobS = {
  listReports,
  upload,
  getReport,
  respond,
  defectTypeLabel,
  severityLabel,
  reportFilename,
};
export default JobS;
