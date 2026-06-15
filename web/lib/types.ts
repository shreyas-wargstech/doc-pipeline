export type DocStatus = "received" | "processing" | "processed" | "failed" | "manual_review";
export type MatchStatus = "matched" | "unmatched" | "not_applicable" | "manual_review" | null;
export type OcrStatus = "pending" | "queued" | "done" | "failed" | "skipped";
export type Category = "practitioner" | "letter" | "receipt" | "record" | "other";

export interface DocRow {
  document_id: string;
  document_category: Category;
  document_type: string | null;
  status: DocStatus;
  match_status: MatchStatus;
  page_count: number;
  original_filename: string;
  registration_no: string | null;
  updated_at: string;
  ocr_done: number;
  ocr_total: number;
  bookmarked: boolean;
}

export interface DocumentsResponse { documents: DocRow[]; total: number; offset: number; limit: number; }

export interface PageRow {
  page_id: string;
  document_id: string;
  page_num: number;
  s3_key_image: string;
  page_type: string | null;
  raw_text: string | null; // always null at runtime — OCR text lives in structured_json["raw_text"]; use PageDetailResponse.raw_text
  structured_json: Record<string, unknown> | null;
  confidence_score: number | null;
  language_detected: string | null;
  page_summary: string | null;
  ocr_status: OcrStatus;
  created_at: string;
  updated_at: string;
}

export interface DocFull {
  document_id: string;
  document_category: Category;
  document_type: string | null;
  original_filename: string;
  qr_content: string | null;
  s3_key_pdf: string;
  page_count: number;
  status: DocStatus;
  document_reference_no: string | null;
  application_no: number | null;
  registration_no: string | null;
  applicant_name_raw: string | null;
  dob: string | null;
  gender: string | null;
  reference_data_id: number | null;
  match_status: MatchStatus;
  document_summary: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  bookmarked: boolean;
}

export interface DocDetailResponse { doc: DocFull; pages: PageRow[]; ocr_done: number; structured_done: number; }
export interface PageDetailResponse { page: PageRow; structured_json: Record<string, unknown> | null; raw_text: string | null; }
export interface MetricsResponse { status_counts: Record<string, number>; match_counts: Record<string, number>; }

export interface AuditRow {
  id: number; ts: string; username: string; action: string;
  document_id: string | null; params: Record<string, unknown>;
  result: "ok" | "error"; detail: string | null;
}
export interface AuditResponse { rows: AuditRow[]; }
export interface ActionResult { ok: boolean; message: string; }

export interface CostSummary {
  cost: number; prompt_tokens?: number; completion_tokens?: number;
  total_tokens: number; calls: number; errors: number;
}
export interface CostBreakdownEntry { cost: number; total_tokens: number; calls: number; }
export interface CostsResponse {
  summary: CostSummary;
  by_stage: Record<string, CostBreakdownEntry>;
  by_model: Record<string, CostBreakdownEntry>;
}
export interface CostEventRow {
  id: number; ts: string; stage: string; model: string;
  document_id: string | null; page_num: number | null;
  prompt_tokens: number; completion_tokens: number; total_tokens: number;
  cost: number; status: "ok" | "error"; detail: string | null;
}
export interface CostEventsResponse { rows: CostEventRow[]; }

export interface StreamEvent {
  document_id: string; status: DocStatus; match_status: MatchStatus;
  ocr_done: number; ocr_total: number;
}

export interface EvalScore {
  precision: number;
  recall: number;
  accuracy: number;
  f1: number;
  n: number;
  confusion: { tp: number; fp: number; tn: number; fn: number };
}

export interface SweepCell {
  height_cv_threshold: number;
  stroke_cv_threshold: number;
  accuracy: number;
  typed_precision: number;
}

export interface EvalSweep {
  best: SweepCell;
  cells: SweepCell[];
}

export interface EvalQueueRow {
  document_id: string;
  document_type: string | null;
  applicant_name_raw: string | null;
  registration_no: string | null;
  application_no: number | null;
  document_reference_no: string | null;
  dob: string | null;
  gender: string | null;
  status: DocStatus;
  match_status: MatchStatus;
  updated_at: string;
}

export interface EvalQueueResponse {
  documents: EvalQueueRow[];
  total: number;
  offset: number;
  limit: number;
}

export interface CorrectionPatch {
  registration_no?: string | null;
  applicant_name_raw?: string | null;
  dob?: string | null;
  gender?: string | null;
  application_no?: number | null;
  document_reference_no?: string | null;
}

export interface MatchResultOut {
  match_status: MatchStatus;
  reference_data_id: number | null;
  method: "exact" | "fuzzy" | null;
  score: number | null;
  candidate_registration_no: string | null;
  matched_on: string | null;
}

export interface CorrectionResult {
  doc: DocFull;
  match_result: MatchResultOut;
}

export type RunItemStatus = "pending" | "running" | "done" | "skipped" | "failed";
export type RunStatus = "running" | "paused" | "completed" | "cancelled" | "failed";

export interface RunItem {
  filename: string;
  status: RunItemStatus;
  document_id: string | null;
  stage: string | null;
  error: string | null;
}

export interface RunState {
  run_id: string;
  folder: string;
  category: string;
  force: boolean;
  status: RunStatus;
  total: number;
  done: number;
  skipped: number;
  failed: number;
  running: number;
  items: RunItem[];
}

// SSE frames: {type:"item",...partial item}, {type:"summary"|"update",...RunState},
// {type:"done",...RunState}. The store-backed API emits summary/update/done
// (full RunState); "item" remains for the reducer's partial-item branch.
export interface RunEvent {
  type: "item" | "summary" | "update" | "done";
  filename?: string;
  status?: RunItemStatus;
  stage?: string | null;
  document_id?: string | null;
  error?: string | null;
  // summary/done frames carry the full RunState shape too:
  [key: string]: unknown;
}

export interface RetrievalHit {
  document_id: string;
  s3_key_pdf: string;
  document_type: string | null;
  score: number;
  tier: 1 | 2 | 3;
  why_matched: string;
}
export interface SearchResponse { count: number; hits: RetrievalHit[]; }

export interface SearchPageHit {
  page_id: string;
  page_num: number;
  page_type: string | null;
  s3_key_image: string;
  page_summary: string | null;
  search_keywords: string[];
  entities: { type: string; value: string }[];
  index_status: string;
}
export interface SearchPagesResponse { document_id: string; count: number; hits: SearchPageHit[]; }

export type UserRole = "administrator" | "reviewer" | "operator" | "viewer";

export interface MeResponse {
  user: string;
  role: UserRole;
}

export interface AdminUser {
  username: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface AdminUsersResponse {
  users: AdminUser[];
}
