"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

const ToastCtx = createContext<((msg: string) => void) | null>(null);

/** Lives in the portal layout, so a confirmation survives when the reviewed item leaves the page. */
export function Toaster({ children }: { children: React.ReactNode }) {
  const [msg, setMsg] = useState<{ text: string; n: number } | null>(null);
  const show = useCallback((text: string) => setMsg((m) => ({ text, n: (m?.n ?? 0) + 1 })), []);
  useEffect(() => {
    if (!msg) return;
    // Long messages stay up long enough to read.
    const t = setTimeout(() => setMsg(null), Math.min(15000, Math.max(5000, msg.text.length * 70)));
    return () => clearTimeout(t);
  }, [msg]);
  return (
    <ToastCtx.Provider value={show}>
      {children}
      <div className="toast-region" role="status" aria-live="polite">
        {msg && <div className="toast" key={msg.n}>{msg.text}</div>}
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);
