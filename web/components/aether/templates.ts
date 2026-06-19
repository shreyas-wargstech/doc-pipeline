export interface QueryTemplate {
  id: string;
  group: "Diagnose" | "Find" | "System";
  label: string;
  hint: string;
  icon: string;
  query: string;
  needsDoc: boolean;
  llm: boolean;
}

export const TEMPLATES: QueryTemplate[] = [
  {
    id: "autopsy",
    group: "Diagnose",
    label: "Autopsy a document",
    hint: "Why did <doc> fail or go to review?",
    icon: "stethoscope",
    query: "Why did doc <id> fail?",
    needsDoc: true,
    llm: false,
  },
  {
    id: "identity",
    group: "Diagnose",
    label: "Verify identity",
    hint: "Cross-page consistency score.",
    icon: "shield",
    query: "Verify identity of <id>",
    needsDoc: true,
    llm: false,
  },
  {
    id: "inspector",
    group: "Diagnose",
    label: "Inspect pipeline",
    hint: "Stage-by-stage progress.",
    icon: "route",
    query: "Inspect <id>",
    needsDoc: true,
    llm: false,
  },
  {
    id: "search",
    group: "Find",
    label: "Pages for a practitioner",
    hint: "Everything owned by a person.",
    icon: "users",
    query: "Find all pages for ",
    needsDoc: false,
    llm: false,
  },
  {
    id: "narrative",
    group: "Find",
    label: "Summarize a document",
    hint: "Plain-language narrative.",
    icon: "file",
    query: "Summarize doc <id>",
    needsDoc: true,
    llm: false,
  },
  {
    id: "context",
    group: "Find",
    label: "Related documents",
    hint: "Context around a document.",
    icon: "link",
    query: "Related docs for <id>",
    needsDoc: true,
    llm: false,
  },
  {
    id: "health",
    group: "System",
    label: "System health",
    hint: "Queues, DBs, credit balance.",
    icon: "activity",
    query: "System health",
    needsDoc: false,
    llm: false,
  },
];
