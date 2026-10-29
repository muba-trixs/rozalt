"use client";

import {
  Activity,
  BarChart3,
  ChevronsLeft,
  ChevronsRight,
  Database,
  FileSearch,
  LayoutDashboard,
  PanelRightClose,
  PanelRightOpen,
  Radar,
  Search,
  Settings,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { cn } from "@/lib/format";
import { useHotkey, usePersistentState } from "@/lib/hooks";
import { CommandPalette } from "./CommandPalette";
import { DefaultIntelFeed } from "./IntelFeed";

export const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard, key: "o" },
  { href: "/analytics", label: "Demand Analytics", icon: BarChart3, key: "a" },
  { href: "/anomalies", label: "Anomaly Explorer", icon: Activity, key: "x" },
  { href: "/investigations", label: "Investigations", icon: FileSearch, key: "i" },
  { href: "/events", label: "Event Intelligence", icon: Radar, key: "e" },
  { href: "/data", label: "Data Sources", icon: Database, key: "d" },
  { href: "/settings", label: "Settings", icon: Settings, key: "s" },
];

interface ShellCtx {
  panelEl: HTMLElement | null;
  panelOwners: number;
  claimPanel: () => () => void;
  openPanel: () => void;
}
const Ctx = createContext<ShellCtx | null>(null);

/** Render children into the right-hand Intelligence Panel (replacing the default feed). */
export function IntelPanel({ children }: { children: ReactNode }) {
  const ctx = useContext(Ctx);
  useEffect(() => ctx?.claimPanel(), [ctx]);
  if (!ctx?.panelEl) return null;
  return createPortal(children, ctx.panelEl);
}

export function useShell() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useShell outside AppShell");
  return ctx;
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [navCollapsed, setNavCollapsed] = usePersistentState("di.nav.collapsed", false);
  const [panelOpen, setPanelOpen] = usePersistentState("di.panel.open", true);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [panelEl, setPanelEl] = useState<HTMLElement | null>(null);
  const [owners, setOwners] = useState(0);
  const gPressed = useRef<number>(0);

  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 30_000, retry: 0 });

  const claimPanel = useCallback(() => {
    setOwners((n) => n + 1);
    return () => setOwners((n) => n - 1);
  }, []);
  const openPanel = useCallback(() => setPanelOpen(true), [setPanelOpen]);

  useHotkey("mod+k", (e) => {
    e.preventDefault();
    setPaletteOpen((v) => !v);
  });
  useHotkey("[", () => setNavCollapsed((v) => !v));
  useHotkey("]", () => setPanelOpen((v) => !v));
  useHotkey("/", (e) => {
    e.preventDefault();
    setPaletteOpen(true);
  });
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || e.metaKey || e.ctrlKey) return;
      if (e.key === "g") {
        gPressed.current = Date.now();
        return;
      }
      if (Date.now() - gPressed.current < 900) {
        const item = NAV.find((n) => n.key === e.key);
        if (item) {
          router.push(item.href);
          gPressed.current = 0;
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router]);

  const crumbs = breadcrumb(pathname);

  return (
    <Ctx.Provider value={{ panelEl, panelOwners: owners, claimPanel, openPanel }}>
      <div className="flex h-screen w-full overflow-hidden bg-bg">
        {/* Sidebar */}
        <aside
          className={cn(
            "flex shrink-0 flex-col border-r border-border bg-sidebar transition-[width] duration-150",
            navCollapsed ? "w-12" : "w-[220px]",
          )}
        >
          <div className="flex h-11 items-center gap-2 border-b border-border px-3">
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-sm border border-accent/50 bg-accent/10 font-mono text-2xs font-semibold text-accent">
              RZ
            </div>
            {!navCollapsed && (
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold leading-4 text-fg">Rozalt</div>
                <div className="truncate font-mono text-2xs leading-3 text-subtle">DEMAND INTELLIGENCE</div>
              </div>
            )}
          </div>
          <nav className="flex-1 space-y-px p-2">
            {NAV.map((n) => {
              const active = n.href === "/" ? pathname === "/" : pathname.startsWith(n.href);
              const Icon = n.icon;
              return (
                <Link
                  key={n.href}
                  href={n.href}
                  title={navCollapsed ? n.label : undefined}
                  className={cn(
                    "group relative flex h-8 items-center gap-2.5 rounded px-2 text-sm transition-colors",
                    active ? "bg-elevated text-fg" : "text-muted hover:bg-elevated/60 hover:text-fg",
                  )}
                >
                  {active && <span className="absolute left-0 top-1.5 h-5 w-0.5 rounded-r bg-accent" />}
                  <Icon className={cn("h-4 w-4 shrink-0", active ? "text-accent" : "")} strokeWidth={1.75} />
                  {!navCollapsed && (
                    <>
                      <span className="flex-1 truncate">{n.label}</span>
                      <span className="hidden font-mono text-2xs text-subtle group-hover:inline">g {n.key}</span>
                    </>
                  )}
                </Link>
              );
            })}
          </nav>
          <div className="border-t border-border p-2">
            {!navCollapsed && (
              <div className="mb-2 space-y-1 px-2 font-mono text-2xs text-subtle">
                <div className="flex items-center gap-1.5">
                  <span className={cn("h-1.5 w-1.5 rounded-full", health.data ? "bg-positive" : health.isError ? "bg-negative" : "bg-warning")} />
                  API {health.data ? "ONLINE" : health.isError ? "OFFLINE" : "…"}
                </div>
                <div className="flex items-center gap-1.5">
                  <span className={cn("h-1.5 w-1.5 rounded-full", health.data?.llm_available ? "bg-cyan" : "bg-subtle")} />
                  {health.data?.llm_available ? `LLM ${health.data.model}` : "DETERMINISTIC MODE"}
                </div>
              </div>
            )}
            <button
              onClick={() => setNavCollapsed((v) => !v)}
              className="flex h-7 w-full items-center justify-center gap-2 rounded text-xs text-subtle hover:bg-elevated hover:text-fg"
              title="Toggle sidebar  [ "
            >
              {navCollapsed ? <ChevronsRight className="h-4 w-4" /> : <><ChevronsLeft className="h-4 w-4" /> Collapse <span className="kbd">[</span></>}
            </button>
          </div>
        </aside>

        {/* Main column */}
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-11 shrink-0 items-center gap-3 border-b border-border bg-bg px-4">
            <div className="flex min-w-0 flex-1 items-center gap-1.5 font-mono text-xs uppercase tracking-wider text-subtle">
              {crumbs.map((c, i) => (
                <span key={i} className="flex items-center gap-1.5 truncate">
                  {i > 0 && <span className="text-border">/</span>}
                  {c.href ? (
                    <Link href={c.href} className="hover:text-fg">
                      {c.label}
                    </Link>
                  ) : (
                    <span className="text-fg">{c.label}</span>
                  )}
                </span>
              ))}
            </div>
            <button
              onClick={() => setPaletteOpen(true)}
              className="flex h-7 w-72 shrink-0 items-center gap-2 rounded border border-border bg-surface px-2 text-sm text-subtle transition-colors hover:border-subtle"
            >
              <Search className="h-3.5 w-3.5" />
              <span className="flex-1 truncate whitespace-nowrap text-left">Search SKUs, anomalies, commands…</span>
              <span className="kbd">Ctrl</span>
              <span className="kbd">K</span>
            </button>
            <button
              onClick={() => setPanelOpen((v) => !v)}
              className="flex h-7 items-center gap-1.5 rounded px-2 text-xs text-muted hover:bg-elevated hover:text-fg"
              title="Toggle intelligence panel  ]"
            >
              {panelOpen ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}
              <span className="kbd">]</span>
            </button>
          </header>

          <div className="flex min-h-0 flex-1">
            <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
            <aside
              className={cn(
                "shrink-0 overflow-hidden border-l border-border bg-sidebar/60 transition-[width] duration-150",
                panelOpen ? "w-[380px] 2xl:w-[420px]" : "w-0 border-l-0",
              )}
            >
              <div className="flex h-full w-[380px] flex-col 2xl:w-[420px]">
                <div ref={setPanelEl} className={cn("min-h-0 flex-1 overflow-y-auto", owners === 0 && "hidden")} />
                {owners === 0 && (
                  <div className="min-h-0 flex-1 overflow-y-auto">
                    <DefaultIntelFeed />
                  </div>
                )}
              </div>
            </aside>
          </div>
        </div>
      </div>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </Ctx.Provider>
  );
}

function breadcrumb(path: string): { label: string; href?: string }[] {
  const root = { label: "Rozalt", href: "/" };
  if (path === "/") return [{ label: "Rozalt" }, { label: "Overview" }];
  const parts = path.split("/").filter(Boolean);
  const nav = NAV.find((n) => n.href === `/${parts[0]}`);
  const out: { label: string; href?: string }[] = [root];
  if (nav) out.push(parts.length > 1 ? { label: nav.label, href: nav.href } : { label: nav.label });
  if (parts.length > 1) out.push({ label: decodeURIComponent(parts[1]) });
  return out;
}
