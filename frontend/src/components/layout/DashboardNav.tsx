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
  SlidersHorizontal,
  Sun,
  Table2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useFilters } from "@/lib/hooks/useFilters";
import { MobileFilterSheet } from "@/components/filters/FilterSidebar";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Overview", short: "Overview", Icon: LayoutDashboard },
  { href: "/dashboard/map", label: "Map", short: "Map", Icon: Map },
  { href: "/dashboard/analytics", label: "Analytics", short: "Analytics", Icon: ChartNoAxesCombined },
  { href: "/dashboard/transactions", label: "Transactions", short: "Sales", Icon: Table2 },
  { href: "/dashboard/investors", label: "Investors", short: "Investors", Icon: Landmark },
  { href: "/dashboard/owners", label: "Owners", short: "Owners", Icon: Search },
];

// Pages whose data responds to the global filters; only these offer the
// Filters button on phones.
const FILTERED_PATHS = [
  "/dashboard",
  "/dashboard/map",
  "/dashboard/analytics",
  "/dashboard/transactions",
  "/dashboard/parcels",
];

function isActive(pathname: string, href: string) {
  return href === "/dashboard" ? pathname === "/dashboard" : pathname.startsWith(href);
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  // Render only after mount: the server doesn't know the visitor's theme.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return <div className="w-9 h-9" />;

  const isDark = resolvedTheme === "dark";
  return (
    <button
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className="w-9 h-9 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
    >
      {isDark ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}

function MobileFiltersButton() {
  const pathname = usePathname();
  const { activeCount } = useFilters();
  const [open, setOpen] = useState(false);
  if (!FILTERED_PATHS.includes(pathname)) return null;

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="lg:hidden flex h-9 items-center gap-1.5 rounded-md border px-3 text-sm font-medium hover:bg-muted"
      >
        <SlidersHorizontal size={15} />
        Filters
        {activeCount > 0 && (
          <span className="ml-0.5 rounded-full bg-primary px-1.5 text-xs leading-5 text-primary-foreground">
            {activeCount}
          </span>
        )}
      </button>
      <MobileFilterSheet open={open} onClose={() => setOpen(false)} />
    </>
  );
}

export function DashboardNav() {
  const pathname = usePathname();
  return (
    <nav className="flex items-center gap-1 px-4 border-b h-14 shrink-0 bg-background pt-[env(safe-area-inset-top)] box-content">
      <Link
        href="/dashboard"
        className="flex items-center gap-1.5 font-semibold text-sm mr-4 text-foreground/80 whitespace-nowrap"
      >
        <Building2 size={16} />
        RE Analytics
      </Link>
      <div className="hidden lg:flex items-center gap-1">
        {NAV_ITEMS.map(({ href, label, Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors",
              isActive(pathname, href)
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground hover:bg-muted"
            )}
          >
            <Icon size={15} />
            {label}
          </Link>
        ))}
      </div>
      <div className="ml-auto flex items-center gap-2">
        <MobileFiltersButton />
        <ThemeToggle />
      </div>
    </nav>
  );
}

/** Phones and tablets: primary navigation pinned to the bottom of the screen. */
export function MobileTabBar() {
  const pathname = usePathname();
  return (
    <nav
      aria-label="Primary"
      className="lg:hidden fixed inset-x-0 bottom-0 z-[1500] border-t bg-background/95 backdrop-blur pb-[env(safe-area-inset-bottom)]"
    >
      <div className="grid grid-cols-6">
        {NAV_ITEMS.map(({ href, short, Icon }) => {
          const active = isActive(pathname, href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex h-14 flex-col items-center justify-center gap-0.5 text-[11px] font-medium transition-colors",
                active ? "text-primary" : "text-muted-foreground hover:text-foreground"
              )}
            >
              <Icon size={20} strokeWidth={active ? 2.25 : 1.75} />
              {short}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
