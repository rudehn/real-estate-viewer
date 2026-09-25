"use client";

import { useEffect, useState } from "react";

/** True while the CSS media query matches; false during SSR and first render. */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    const mql = window.matchMedia(query);
    setMatches(mql.matches);
    const onChange = (e: MediaQueryListEvent) => setMatches(e.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

/** Tailwind's `sm` breakpoint and below (phones). */
export function useIsPhone(): boolean {
  return useMediaQuery("(max-width: 639px)");
}
