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
  application_number: string | null;
  registration_no: string | null;
  applicant_name_raw: string | null;
  dob: string | null;
  gender: string | null;
  reference_data_id: number | null;
  match_status: MatchStatus;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
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
  height_weight: number;
  accuracy: number;
  typed_precision: number;
}

export interface EvalSweep {
  best: SweepCell;
  cells: SweepCell[];
}
