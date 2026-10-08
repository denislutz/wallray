"use client";

import UISessionS from "@/services/business/UISessionS";
import ReactQueryS from "@/services/tech/ReactQueryS";
import { Toaster } from "@/ui/base/Toaster";
import { SessionProvider } from "next-auth/react";
import { type ReactNode, useState } from "react";

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => ReactQueryS.createClient());

  return (
    <SessionProvider>
      <ReactQueryS.Provider client={queryClient}>
        <UISessionS.UISessionProvider>
          {children}
          <Toaster />
        </UISessionS.UISessionProvider>
      </ReactQueryS.Provider>
    </SessionProvider>
  );
}
