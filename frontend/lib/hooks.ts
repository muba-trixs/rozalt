"use client";

import { useCallback, useEffect, useState } from "react";

/** State persisted per-browser in localStorage (filters, panel state). Falls back silently. */
export function usePersistentState<T>(key: string, initial: T): [T, (v: T | ((p: T) => T)) => void] {
  const [value, setValue] = useState<T>(initial);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(key);
      if (raw !== null) setValue(JSON.parse(raw) as T);
    } catch {
      /* storage unavailable */
    }
    setLoaded(true);
  }, [key]);

  useEffect(() => {
    if (!loaded) return;
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* storage unavailable */
    }
  }, [key, value, loaded]);

  return [value, setValue];
}

/** Register a global keyboard shortcut; ignored while typing in inputs. */
export function useHotkey(combo: string, handler: (e: KeyboardEvent) => void, enabled = true) {
  const cb = useCallback(handler, [handler]);
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const typing = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable);
      const parts = combo.toLowerCase().split("+");
      const key = parts[parts.length - 1];
      const needMeta = parts.includes("mod");
      if (needMeta && !(e.metaKey || e.ctrlKey)) return;
      if (!needMeta && (e.metaKey || e.ctrlKey || e.altKey)) return;
      if (typing && !needMeta) return;
      if (e.key.toLowerCase() === key) cb(e);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [combo, cb, enabled]);
}
