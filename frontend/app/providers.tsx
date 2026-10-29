"use client";

import * as RTooltip from "@radix-ui/react-tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Toaster } from "sonner";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { staleTime: 15_000, refetchOnWindowFocus: false, retry: 1 } },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <RTooltip.Provider>
        {children}
        <Toaster
          theme="dark"
          position="bottom-right"
          toastOptions={{
            style: {
              background: "#21262D",
              border: "1px solid #30363D",
              color: "#E6EDF3",
              borderRadius: 4,
              fontSize: 12,
            },
          }}
        />
      </RTooltip.Provider>
    </QueryClientProvider>
  );
}
