import { Card } from "@/components/ui/Card";
import { CardContent } from "@/components/ui/Card";
import { List } from "lucide-react";

export function ComingSoon({ title, items }: { title: string; items: string[] }) {
  return (
    <Card className="border max-w-[40rem]">
      <CardContent className="flex flex-col gap-3 p-6">
        <h1 className="font-display text-xl font-semibold text-foreground">{title}</h1>
        <p className="text-sm text-muted-fg">
          This section is planned. Here is what it will include:
        </p>
        <ul className="flex flex-col gap-2">
          {items.map((item) => (
            <li key={item} className="flex items-start gap-2 text-sm text-foreground">
              <List className="mt-0.5 h-4 w-4 shrink-0 text-muted-fg" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
