export type EvalLabel = "typed" | "handwritten" | "unknown";

export interface EvalPage {
  page_id: string;
  document_id: string;
  page_num: number;
  s3_key_image: string;
  label: EvalLabel | null;
  height_cv: number | null;
  stroke_cv: number | null;
  n_components: number | null;
  labeled_by?: string | null;
  labeled_at?: string | null;
}

export interface EvalState {
  pages: EvalPage[];
  cursor: number;
}

export const initialEvalState: EvalState = { pages: [], cursor: 0 };

export type EvalAction =
  | { type: "load"; pages: EvalPage[] }
  | { type: "label"; page_id: string; label: EvalLabel }
  | { type: "skip" }
  | { type: "goto"; cursor: number };

function advance(state: EvalState): number {
  return Math.min(state.cursor + 1, Math.max(state.pages.length - 1, 0));
}

export function evalReducer(state: EvalState, action: EvalAction): EvalState {
  switch (action.type) {
    case "load":
      return { pages: action.pages, cursor: 0 };
    case "label": {
      const pages = state.pages.map((p) =>
        p.page_id === action.page_id ? { ...p, label: action.label } : p,
      );
      return { pages, cursor: advance(state) };
    }
    case "skip":
      return { ...state, cursor: advance(state) };
    case "goto":
      return { ...state, cursor: Math.max(0, Math.min(action.cursor, state.pages.length - 1)) };
    default:
      return state;
  }
}
