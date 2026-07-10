import { cn } from "@/lib/utils";
import type { Period } from "@/lib/utils/chartHelpers";

const OPTIONS: { value: Period; label: string }[] = [
  { value: "monthly", label: "M" },
  { value: "quarterly", label: "Q" },
  { value: "annual", label: "Y" },
];

interface Props {
  value: Period;
  onChange: (p: Period) => void;
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
