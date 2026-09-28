import { useEffect, useState } from "react"
import { NavLink, Outlet } from "react-router-dom"
import { Contrast } from "lucide-react"
import { cn } from "@/lib/cn"
import { Dot } from "@/components/ui/primitives"

const NAV = [
  { to: "/review", label: "Review" },
  { to: "/niches", label: "Niches" },
  { to: "/budget", label: "Budget" },
]

type Theme = "dark" | "light"

function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      return (localStorage.getItem("kairos-theme") as Theme) ?? "dark"
    } catch {
      return "dark"
    }
  })
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme)
    try {
      localStorage.setItem("kairos-theme", theme)
    } catch {
      /* private window — the page renders correctly without it */
    }
  }, [theme])
  return { theme, setTheme }
}

/** UTC, because every timestamp in the system is UTC and a console should not
 *  make you convert in your head. */
function Clock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return (
    <span className="num text-[0.6875rem] text-text-faint">
      {now.toISOString().slice(11, 19)}
      <span className="ml-1 text-text-faint/60">UTC</span>
    </span>
  )
}

function Health() {
  const [ok, setOk] = useState<boolean | null>(null)
  useEffect(() => {
    let alive = true
    const ping = () =>
      fetch("/health")
        .then((r) => alive && setOk(r.ok))
        .catch(() => alive && setOk(false))
    ping()
    const id = setInterval(ping, 30_000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])
  return (
    <span className="flex items-center gap-1.5">
      <Dot tone={ok === false ? "down" : ok ? "up" : "neutral"} pulse={ok === null} />
      <span className="num text-[0.6875rem] text-text-faint">
        {ok === false ? "OFFLINE" : ok ? "LIVE" : "…"}
      </span>
    </span>
  )
}

export function Shell() {
  const { theme, setTheme } = useTheme()

  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-40 border-b border-line bg-ground/85 backdrop-blur-md">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-4 gap-y-2.5 px-4 py-3 sm:px-6">
          {/* Identity left, nav centred, instruments right — the console
              arrangement: who you are, where you are, what the machine is doing. */}
          <div className="flex min-w-0 flex-1 items-center gap-2.5">
            <span className="font-brand text-[0.8125rem] font-bold tracking-[-0.04em]">
              KAIROS
            </span>
            <span className="hidden text-[0.6875rem] text-text-faint sm:inline">
              /&nbsp;the opportune moment
            </span>
          </div>

          {/* Below sm the pill takes a row of its own: squeezed onto the brand
              row it collided with the wordmark. */}
          <nav className="order-last flex shrink-0 basis-full items-center justify-center gap-0.5 rounded-full border border-line bg-panel p-1 sm:order-none sm:basis-auto">
            {NAV.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  cn(
                    "rounded-full px-3.5 py-1.5 font-mono text-[0.6875rem] tracking-widest uppercase transition-colors sm:px-5",
                    isActive
                      ? "bg-signal text-on-signal font-semibold"
                      : "text-text-muted hover:text-text",
                  )
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>

          <div className="flex flex-1 items-center justify-end gap-3">
            <span className="hidden items-center gap-3 md:flex">
              <Health />
              <span className="h-3 w-px bg-line" />
              <Clock />
            </span>
            <button
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
              className="border border-line p-1.5 text-text-faint transition-colors hover:border-signal hover:text-signal"
            >
              <Contrast className="size-3.5" />
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-6 sm:px-6 lg:py-8">
        <Outlet />
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-2 px-4 py-3 sm:px-6">
          <span className="label">
            Every design passes a human before it can be listed
          </span>
          <span className="num text-[0.625rem] text-text-faint">
            KAIROS · ETSY PIPELINE · v0.1
          </span>
        </div>
      </footer>
    </div>
  )
}
