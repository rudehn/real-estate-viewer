"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import {
  Building2,
  ChartNoAxesCombined,
  Landmark,
  LayoutDashboard,
  Map,
  Moon,
  Search,
  Sun,
  Table2,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Overview", Icon: LayoutDashboard },
  { href: "/dashboard/map", label: "Map", Icon: Map },
  { href: "/dashboard/analytics", label: "Analytics", Icon: ChartNoAxesCombined },
  { href: "/dashboard/transactions", label: "Transactions", Icon: Table2 },
  { href: "/dashboard/investors", label: "Investors", Icon: Landmark },
  { href: "/dashboard/owners", label: "Owners", Icon: Search },
];

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  // Render only after mount: the server doesn't know the visitor's theme.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return <div className="w-8 h-8" />;

  const isDark = resolvedTheme === "dark";
  return (
    <button
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className="w-8 h-8 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
    >
      {isDark ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}

export function DashboardNav() {
  const pathname = usePathname();
  return (
    <nav className="flex items-center gap-1 px-4 border-b h-14 bg-background">
      <span className="flex items-center gap-1.5 font-semibold text-sm mr-4 text-foreground/80">
        <Building2 size={16} />
        RE Analytics
      </span>
      {NAV_ITEMS.map(({ href, label, Icon }) => {
        const isActive =
          href === "/dashboard" ? pathname === "/dashboard" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors",
              isActive
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground hover:bg-muted"
            )}
          >
            <Icon size={15} />
            {label}
          </Link>
        );
      })}
      <div className="ml-auto">
        <ThemeToggle />
      </div>
    </nav>
  );
}
