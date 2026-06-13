import { ComingSoon } from "@/components/ComingSoon";

export default function PipelinesPage() {
  return (
    <ComingSoon
      title="Pipelines"
      items={[
        "Current pipeline status per document",
        "Last run history and timing",
        "Queue / pending jobs across stages",
        "Rerun controls with impact explanation",
        "Confirmation for expensive or destructive runs",
      ]}
    />
  );
}
