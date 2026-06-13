import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Typography from "@mui/material/Typography";

type Tone = "foreground" | "ok" | "warn" | "danger" | "info";

const TONE_COLOR: Record<Tone, string> = {
  foreground: "text.primary",
  ok: "success.main",
  warn: "warning.main",
  danger: "error.main",
  info: "info.main",
};

export function KpiCard({ label, value, tone = "foreground" }: { label: string; value: number | string; tone?: Tone }) {
  return (
    <Card variant="outlined">
      <CardContent sx={{ display: "flex", flexDirection: "column", gap: 0.5 }}>
        <Typography variant="caption" sx={{ textTransform: "uppercase", letterSpacing: 0.5 }} color="text.secondary">
          {label}
        </Typography>
        <Typography variant="h5" className="tnum" sx={{ fontWeight: 600, color: TONE_COLOR[tone] }}>
          {value}
        </Typography>
      </CardContent>
    </Card>
  );
}
