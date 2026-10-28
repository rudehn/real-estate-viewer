"use client";

import { createContext, useContext } from "react";

// Browser-visible keys read from the server's environment at request time
// (see app/dashboard/layout.tsx). NEXT_PUBLIC_* would be inlined at build time,
// baking deploy-specific values into the published image.
export interface PublicConfig {
  cartoApiKey: string;
  googleMapsApiKey: string;
}

const PublicConfigContext = createContext<PublicConfig>({
  cartoApiKey: "",
  googleMapsApiKey: "",
});

export function PublicConfigProvider({
  config,
  children,
}: {
  config: PublicConfig;
  children: React.ReactNode;
}) {
  return <PublicConfigContext.Provider value={config}>{children}</PublicConfigContext.Provider>;
}

export function usePublicConfig(): PublicConfig {
  return useContext(PublicConfigContext);
}
