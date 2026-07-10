import Link from "next/link";
import { cn } from "@/lib/utils";

/** Owner name that links to the investor profile page. */
export function OwnerLink({ name, className }: { name: string; className?: string }) {
  return (
    <Link
      href={`/dashboard/investors/${encodeURIComponent(name)}`}
      className={cn("hover:underline hover:text-primary", className)}
      title={name}
    >
      {name}
    </Link>
  );
}
