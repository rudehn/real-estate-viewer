import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

interface KpiCardProps {
  title: string;
  value: string;
  delta?: number;
  deltaLabel?: string;
  icon?: React.ReactNode;
  isLoading?: boolean;
}

export function KpiCard({ title, value, delta, deltaLabel, icon, isLoading }: KpiCardProps) {
  return (
    <Card>
      <CardHeader className="pb-2 pt-4 px-4">
        <CardTitle className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
          {icon && <span>{icon}</span>}
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        {isLoading ? (
          <Skeleton className="h-8 w-24" />
        ) : (
          <div className="flex items-end gap-2">
            <span className="text-2xl font-bold">{value}</span>
            {delta !== undefined && (
              <Badge
                variant={delta >= 0 ? "default" : "destructive"}
                className="text-xs mb-0.5"
              >
                {delta >= 0 ? "+" : ""}
                {delta.toFixed(1)}% {deltaLabel ?? "YoY"}
              </Badge>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
