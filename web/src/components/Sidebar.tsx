"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import {
  BookOpen,
  Brain,
  FridayMark,
  History,
  Server,
  Settings2,
  SquarePen,
  Trash2,
  X,
  Zap,
} from "@/components/icons";
import clsx from "clsx";
import { groupSessions, type ChatSession } from "@/lib/chats";

const NAV = [
  { href: "/activity", label: "Automations", icon: Zap },
  { href: "/skills", label: "Skills", icon: BookOpen },
  { href: "/memory", label: "Memory", icon: Brain },
  { href: "/mcp", label: "MCP Servers", icon: Server },
  { href: "/settings", label: "Customize", icon: Settings2 },
];

function SidebarBody({
  sessions,
  currentId,
  onOpenChat,
  onNewChat,
  onDeleteChat,
  modelLabel,
}: {
  sessions: ChatSession[];
  currentId: string;
  onOpenChat: (id: string) => void;
  onNewChat: () => void;
  onDeleteChat: (id: string) => void;
  modelLabel: string;
}) {
  const groups = groupSessions(sessions);
  return (
    <div className="flex h-full w-full flex-col">
      {/* top actions */}
      <div className="px-2 pt-2">
        <button
          onClick={onNewChat}
          className="group flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13.5px] font-medium text-ink hover:bg-panel-hover"
        >
          <SquarePen className="h-4 w-4 text-ink-secondary" />
          New Chat
          <kbd className="ml-auto rounded border border-edge-subtle px-1.5 py-0.5 text-[10px] text-ink-muted">
            ⌘N
          </kbd>
        </button>
        {NAV.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13.5px] text-ink-secondary hover:bg-panel-hover hover:text-ink"
          >
            <Icon className="h-4 w-4 text-ink-muted" />
            {label}
          </Link>
        ))}
      </div>

      {/* chat history */}
      <div className="mt-4 flex-1 overflow-y-auto px-2 pb-2">
        <p className="px-2.5 pb-1.5 text-[11.5px] font-medium text-ink-muted">Chats</p>
        {sessions.length === 0 && (
          <p className="px-2.5 text-[12.5px] text-ink-muted/70">No chats yet.</p>
        )}
        {groups.map(({ label, items }) => (
          <div key={label} className="mb-3">
            {groups.length > 1 && (
              <p className="px-2.5 pb-1 pt-1 text-[10.5px] uppercase tracking-wide text-ink-muted/60">
                {label}
              </p>
            )}
            <AnimatePresence initial={false}>
              {items.map((s) => (
                <motion.div
                  key={s.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0, height: 0 }}
                  onClick={() => onOpenChat(s.id)}
                  className={clsx(
                    "group flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-[7px]",
                    s.id === currentId ? "bg-panel-active text-ink" : "text-ink-secondary hover:bg-panel-hover"
                  )}
                >
                  <span
                    className={clsx(
                      "h-1.5 w-1.5 shrink-0 rounded-full",
                      s.id === currentId ? "bg-accent" : "bg-ink-muted/50"
                    )}
                  />
                  <span className="min-w-0 flex-1 truncate text-[13px]">{s.title}</span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteChat(s.id);
                    }}
                    title="Delete chat"
                    className="hidden h-5 w-5 shrink-0 items-center justify-center rounded text-ink-muted hover:text-state-err group-hover:flex"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        ))}
      </div>

      {/* profile / settings */}
      <div className="flex items-center gap-2.5 border-t border-edge-subtle px-3 py-2.5">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center text-accent">
          <FridayMark className="h-5 w-5" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-medium text-ink">Friday</span>
          <span className="block truncate font-mono text-[10.5px] text-ink-muted">{modelLabel}</span>
        </span>
        <Link
          href="/activity"
          title="Activity"
          className="flex h-7 w-7 items-center justify-center rounded-md text-ink-muted hover:bg-panel-hover hover:text-ink"
        >
          <History className="h-4 w-4" />
        </Link>
        <Link
          href="/settings"
          title="Settings"
          className="flex h-7 w-7 items-center justify-center rounded-md text-ink-muted hover:bg-panel-hover hover:text-ink"
        >
          <Settings2 className="h-4 w-4" />
        </Link>
      </div>
    </div>
  );
}

export function Sidebar(props: {
  sessions: ChatSession[];
  currentId: string;
  onOpenChat: (id: string) => void;
  onNewChat: () => void;
  onDeleteChat: (id: string) => void;
  modelLabel: string;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}) {
  const { mobileOpen, onCloseMobile, ...body } = props;
  return (
    <>
      {/* desktop: docked */}
      <aside className="hidden h-full w-[260px] shrink-0 border-r border-edge-subtle bg-panel-sidebar lg:block">
        <SidebarBody {...body} />
      </aside>

      {/* mobile: slide-over drawer */}
      <AnimatePresence>
        {mobileOpen && (
          <div className="fixed inset-0 z-50 lg:hidden">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/50"
              onClick={onCloseMobile}
            />
            <motion.aside
              initial={{ x: -290 }}
              animate={{ x: 0 }}
              exit={{ x: -290 }}
              transition={{ type: "spring", stiffness: 380, damping: 36 }}
              className="absolute left-0 top-0 h-full w-[85vw] max-w-[280px] border-r border-edge-subtle bg-panel-sidebar"
            >
              <button
                onClick={onCloseMobile}
                className="absolute right-2 top-2 z-10 flex h-7 w-7 items-center justify-center rounded-md text-ink-muted hover:bg-panel-hover hover:text-ink"
              >
                <X className="h-4 w-4" />
              </button>
              <SidebarBody
                {...body}
                onOpenChat={(id) => {
                  body.onOpenChat(id);
                  onCloseMobile();
                }}
                onNewChat={() => {
                  body.onNewChat();
                  onCloseMobile();
                }}
              />
            </motion.aside>
          </div>
        )}
      </AnimatePresence>
    </>
  );
}
