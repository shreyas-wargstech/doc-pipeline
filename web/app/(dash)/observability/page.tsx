import { ComingSoon } from "@/components/ComingSoon";

export default function ObservabilityPage() {
  return (
    <ComingSoon
      title="Observability"
      items={[
        "Success rate, latency, and error-rate overview",
        "Request log table with filters",
        "Event detail drawer",
        "Pipeline health timeline",
        "Webhook delivery status (OpenRouter)",
        "Token usage and credit consumption",
      ]}
    />
  );
}
