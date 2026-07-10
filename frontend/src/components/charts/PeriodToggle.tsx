import { cn } from "@/lib/utils";
import type { Granularity } from "@/lib/types/api";

const OPTIONS: { value: Granularity; label: string }[] = [
  { value: "month", label: "M" },
  { value: "quarter", label: "Q" },
  { value: "year", label: "Y" },
];

interface Props {
  value: Granularity;
  onChange: (p: Granularity) => void;
}

export function PeriodToggle({ value, onChange }: Props) {
  return (
    <div className="flex rounded-md border overflow-hidden text-xs">
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={cn(
            "px-2 py-1 transition-colors",
            value === opt.value
              ? "bg-primary text-primary-foreground"
              : "bg-background text-muted-foreground hover:bg-muted"
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
