import { useEffect, useState } from "react"
import { NavLink, Outlet } from "react-router-dom"
import { Banknote, ClipboardCheck, Menu, Moon, Sun, TrendingUp, X } from "lucide-react"
import { cn } from "@/lib/cn"

const NAV = [
  { to: "/review", label: "Review queue", icon: ClipboardCheck, hint: "Approve or reject designs" },
  { to: "/niches", label: "Niches", icon: TrendingUp, hint: "Ranked opportunities" },
  { to: "/budget", label: "Budget", icon: Banknote, hint: "Spend against caps" },
]

type Theme = "light" | "dark" | "system"

function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      return (localStorage.getItem("kairos-theme") as Theme) ?? "system"
    } catch {
      return "system"
    }
  })

  useEffect(() => {
    const root = document.documentElement
    if (theme === "system") root.removeAttribute("data-theme")
    else root.setAttribute("data-theme", theme)
    try {
      localStorage.setItem("kairos-theme", theme)
    } catch {
      /* private window — the page still renders correctly without it */
    }
  }, [theme])

  return { theme, setTheme }
}

function NavItems({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="flex flex-col gap-0.5">
      {NAV.map(({ to, label, icon: Icon, hint }) => (
        <NavLink
          key={to}
          to={to}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "group flex items-start gap-3 rounded-[var(--radius-control)] px-3 py-2.5 transition-colors",
              isActive
                ? "bg-accent-soft text-accent"
                : "text-text-muted hover:bg-surface-sunken hover:text-text",
            )
          }
        >
          {({ isActive }) => (
            <>
              <Icon className="mt-0.5 size-4 shrink-0" strokeWidth={2} />
              <span className="min-w-0">
                <span className="block text-sm font-medium">{label}</span>
                <span
                  className={cn(
                    "block text-xs",
                    isActive ? "text-accent/70" : "text-text-faint",
                  )}
                >
                  {hint}
                </span>
              </span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}

function ThemeToggle({ theme, setTheme }: { theme: Theme; setTheme: (t: Theme) => void }) {
  const next: Theme = theme === "dark" ? "light" : "dark"
  return (
    <button
      onClick={() => setTheme(next)}
      aria-label={`Switch to ${next} theme`}
      className="flex items-center gap-2 rounded-[var(--radius-control)] border border-line px-2.5 py-1.5 text-xs text-text-muted transition-colors hover:bg-surface-sunken hover:text-text"
    >
      {theme === "dark" ? <Sun className="size-3.5" /> : <Moon className="size-3.5" />}
      <span className="capitalize">{theme}</span>
    </button>
  )
}

function Wordmark() {
  return (
    <div className="flex items-baseline gap-2">
      <span className="font-display text-lg leading-none font-semibold tracking-tight">
        Kairos
      </span>
      {/* The name is the thesis: the opportune moment, not linear time. */}
      <span className="text-[0.6875rem] text-text-faint">the opportune moment</span>
    </div>
  )
}

export function Shell() {
  const { theme, setTheme } = useTheme()
  const [open, setOpen] = useState(false)

  return (
    <div className="min-h-full lg:grid lg:grid-cols-[17rem_1fr]">
      {/* Mobile bar */}
      <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-line bg-ground/90 px-4 py-3 backdrop-blur lg:hidden">
        <Wordmark />
        <div className="flex items-center gap-2">
          <ThemeToggle theme={theme} setTheme={setTheme} />
          <button
            onClick={() => setOpen((v) => !v)}
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            className="rounded-[var(--radius-control)] border border-line p-1.5 text-text-muted"
          >
            {open ? <X className="size-4" /> : <Menu className="size-4" />}
          </button>
        </div>
      </header>

      {open ? (
        <div className="border-b border-line bg-surface px-4 py-3 lg:hidden">
          <NavItems onNavigate={() => setOpen(false)} />
        </div>
      ) : null}

      {/* Desktop rail */}
      <aside className="sticky top-0 hidden h-screen flex-col gap-6 border-r border-line bg-surface px-4 py-5 lg:flex">
        <Wordmark />
        <NavItems />
        <div className="mt-auto flex flex-col gap-3">
          <ThemeToggle theme={theme} setTheme={setTheme} />
          <p className="text-[0.6875rem] leading-relaxed text-text-faint">
            Every design passes a human before it can be listed. That gate is
            permanent.
          </p>
        </div>
      </aside>

      <main className="min-w-0 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        <Outlet />
      </main>
    </div>
  )
}
