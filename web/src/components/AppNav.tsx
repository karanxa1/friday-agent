"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpen, Bot, Brain, FridayMark, History, MessageSquare, Server, Settings } from "@/components/icons";
import clsx from "clsx";

const LINKS = [
  { href: "/", label: "Chat", icon: MessageSquare },
  { href: "/tasks", label: "Tasks", icon: Bot },
  { href: "/skills", label: "Skills", icon: BookOpen },
  { href: "/memory", label: "Memory", icon: Brain },
  { href: "/activity", label: "Activity", icon: History },
  { href: "/mcp", label: "MCP", icon: Server },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function AppNav() {
  const path = usePathname();
  return (
    <nav className="flex items-center gap-1 overflow-x-auto">
      {LINKS.map(({ href, label, icon: Icon }) => {
        const active = path === href;
        return (
          <Link
            key={href}
            href={href}
            className={clsx(
              "flex h-8 shrink-0 items-center gap-1.5 rounded-md px-2.5 text-[12.5px] font-medium transition-colors",
              active ? "bg-panel-active text-ink" : "text-ink-muted hover:bg-panel-hover hover:text-ink-secondary"
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

export function PageShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex h-screen flex-col bg-panel">
      <header className="flex h-12 shrink-0 items-center gap-3 border-b border-edge-subtle px-4">
        <Link href="/" className="flex items-center gap-2 text-[15px] font-semibold text-accent">
          <FridayMark className="h-5 w-5" />
          Friday
        </Link>
        <AppNav />
      </header>
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-4xl px-5 py-6">
          <h1 className="mb-5 text-[20px] font-semibold text-ink">{title}</h1>
          {children}
        </div>
      </main>
    </div>
  );
}
