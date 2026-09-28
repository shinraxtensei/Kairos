import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react"
import { cn } from "@/lib/cn"

/* Small, owned primitives rather than the whole shadcn surface. Four pages do
   not need forty components, and every one added is one to keep. */

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-[var(--radius-card)] border border-line bg-surface shadow-[var(--shadow-card)]",
        className,
      )}
      {...props}
    />
  )
}

export function CardHeader({
  title,
  hint,
  action,
}: {
  title: ReactNode
  hint?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-line px-5 py-3.5">
      <div className="min-w-0">
        <h2 className="text-sm font-semibold">{title}</h2>
        {hint ? <p className="mt-0.5 text-xs text-text-muted">{hint}</p> : null}
      </div>
      {action}
    </div>
  )
}

type Tone = "neutral" | "ok" | "warn" | "bad" | "accent"

const toneClass: Record<Tone, string> = {
  neutral: "bg-surface-sunken text-text-muted border-line",
  ok: "bg-ok-soft text-ok border-transparent",
  warn: "bg-warn-soft text-warn border-transparent",
  bad: "bg-bad-soft text-bad border-transparent",
  accent: "bg-accent-soft text-accent border-transparent",
}

/** State is encoded in form as well as in words, so it reads at a glance. */
export function Pill({
  tone = "neutral",
  children,
  className,
}: {
  tone?: Tone
  children: ReactNode
  className?: string
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[0.6875rem] font-medium whitespace-nowrap",
        toneClass[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "danger"
  size?: "sm" | "md"
}

export function Button({
  variant = "ghost",
  size = "md",
  className,
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-[var(--radius-control)] border font-medium transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-40",
        size === "sm" ? "px-2.5 py-1 text-xs" : "px-3.5 py-2 text-sm",
        variant === "primary" &&
          "border-transparent bg-accent text-accent-contrast hover:bg-accent-hover disabled:bg-surface-sunken disabled:text-text-faint disabled:opacity-100",
        variant === "ghost" &&
          "border-line bg-surface text-text hover:border-line-strong hover:bg-surface-sunken",
        variant === "danger" && "border-bad/40 bg-transparent text-bad hover:bg-bad-soft",
        className,
      )}
      {...props}
    />
  )
}

/** A proportion bar. Given a semantic state so a breach is visible as colour,
    not only as a number someone has to read. */
export function Meter({
  percent,
  state = "",
  className,
}: {
  percent: number
  state?: "" | "warn" | "over"
  className?: string
}) {
  return (
    <div className={cn("h-2 w-full overflow-hidden rounded-full bg-surface-sunken", className)}>
      <div
        className={cn(
          "h-full rounded-full transition-[width] duration-500",
          state === "over" ? "bg-bad" : state === "warn" ? "bg-warn" : "bg-accent",
        )}
        style={{ width: `${Math.min(Math.max(percent, 0), 100)}%` }}
      />
    </div>
  )
}

export function StatTile({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string
  value: ReactNode
  sub?: ReactNode
  tone?: Tone
}) {
  return (
    <Card className="p-4">
      <p className="eyebrow">{label}</p>
      <p
        className={cn(
          "tnum mt-1.5 text-2xl leading-none font-semibold",
          tone === "bad" && "text-bad",
          tone === "warn" && "text-warn",
          tone === "ok" && "text-ok",
        )}
      >
        {value}
      </p>
      {sub ? <p className="mt-1.5 text-xs text-text-muted">{sub}</p> : null}
    </Card>
  )
}

export function Banner({
  tone = "warn",
  title,
  children,
}: {
  tone?: Tone
  title: string
  children?: ReactNode
}) {
  const border =
    tone === "bad" ? "border-l-bad" : tone === "ok" ? "border-l-ok" : "border-l-warn"
  const bg = tone === "bad" ? "bg-bad-soft" : tone === "ok" ? "bg-ok-soft" : "bg-warn-soft"
  return (
    <div className={cn("rounded-[var(--radius-card)] border-l-[3px] px-4 py-3", border, bg)}>
      <p className="text-sm font-semibold">{title}</p>
      {children ? <p className="mt-1 text-sm/relaxed text-text-muted">{children}</p> : null}
    </div>
  )
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="px-6 py-16 text-center">
      <p className="text-sm font-medium">{title}</p>
      {children ? <div className="mt-2 text-sm text-text-muted">{children}</div> : null}
    </div>
  )
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="tnum inline-flex min-w-[1.4em] items-center justify-center rounded border border-line bg-surface-sunken px-1.5 py-0.5 text-[0.6875rem] text-text-muted">
      {children}
    </kbd>
  )
}
