"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Overview", icon: "📊" },
  { href: "/dashboard/map", label: "Map", icon: "🗺️" },
  { href: "/dashboard/analytics", label: "Analytics", icon: "📈" },
  { href: "/dashboard/transactions", label: "Transactions", icon: "📋" },
  { href: "/dashboard/investors", label: "Investors", icon: "🏦" },
  { href: "/dashboard/owners", label: "Owners", icon: "🔍" },
];

export function DashboardNav() {
  const pathname = usePathname();
  return (
    <nav className="flex items-center gap-1 px-4 border-b h-14 bg-background">
      <span className="font-semibold text-sm mr-4 text-foreground/80">🏠 RE Analytics</span>
      {NAV_ITEMS.map((item) => {
        const isActive =
          item.href === "/dashboard"
            ? pathname === "/dashboard"
            : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors",
              isActive
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground hover:bg-muted"
            )}
          >
            <span>{item.icon}</span>
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
