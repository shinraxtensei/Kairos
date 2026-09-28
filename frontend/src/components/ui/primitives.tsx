import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react"
import { cn } from "@/lib/cn"

/* Instrument parts. Square corners, hairline edges, no shadows — a panel is a
   bounded readout, not a floating card. */

export function Panel({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("border border-line bg-panel", className)} {...props} />
}

export function PanelHead({
  label,
  children,
}: {
  label: string
  children?: ReactNode
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-line bg-panel-raised px-4 py-2.5">
      <span className="label">{label}</span>
      {children}
    </div>
  )
}

/** Every page opens the same way: a big set title, a machine-readable meta
    line under it, and controls on the right. The rule under it closes the
    block so the page reads as a document with a masthead. */
export function PageHead({
  title,
  meta,
  children,
}: {
  title: string
  meta?: ReactNode
  children?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3 border-b border-line pb-4">
      <div className="min-w-0">
        <h1 className="font-brand text-[clamp(1.375rem,1rem+1.6vw,2rem)] leading-none font-semibold tracking-[-0.05em]">
          {title}
        </h1>
        {meta ? (
          <p className="num mt-2.5 text-[0.6875rem] text-text-faint">{meta}</p>
        ) : null}
      </div>
      {children}
    </div>
  )
}

type Tone = "neutral" | "up" | "down" | "signal"

const chip: Record<Tone, string> = {
  neutral: "border-line-bright text-text-muted",
  up: "border-up/40 bg-up-wash text-up",
  down: "border-down/40 bg-down-wash text-down",
  signal: "border-signal/40 bg-signal-wash text-signal",
}

/** Fully round by design: the only curves in the system are nav and status, so
    a chip reads as a state marker rather than as another box. */
export function Chip({
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
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[0.625rem] tracking-wider uppercase whitespace-nowrap",
        chip[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}

export function Dot({ tone = "signal", pulse }: { tone?: Tone; pulse?: boolean }) {
  const bg =
    tone === "up"
      ? "bg-up"
      : tone === "down"
        ? "bg-down"
        : tone === "signal"
          ? "bg-signal"
          : "bg-text-faint"
  return <span className={cn("size-1.5 shrink-0 rounded-full", bg, pulse && "pulse")} />
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "signal" | "outline" | "danger"
  size?: "sm" | "md"
}

export function Button({
  variant = "outline",
  size = "md",
  className,
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 border font-mono text-xs tracking-wider uppercase transition-colors",
        "disabled:cursor-not-allowed",
        size === "sm" ? "px-2.5 py-1.5" : "px-4 py-2.5",
        variant === "signal" &&
          "border-signal bg-signal font-semibold text-on-signal hover:bg-signal/90 disabled:border-line disabled:bg-transparent disabled:text-text-faint",
        variant === "outline" &&
          "border-line-bright bg-transparent text-text-muted hover:border-signal hover:text-signal disabled:opacity-40",
        variant === "danger" &&
          "border-down/50 bg-transparent text-down hover:bg-down-wash disabled:opacity-40",
        className,
      )}
      {...props}
    />
  )
}

/** A readout bar. Segmented rather than smooth — it reads as a gauge on an
    instrument instead of a progress bar in a web app. */
export function Gauge({
  value,
  tone = "signal",
  segments = 20,
  className,
}: {
  value: number
  tone?: Tone
  segments?: number
  className?: string
}) {
  const filled = Math.round((Math.min(Math.max(value, 0), 100) / 100) * segments)
  const on =
    tone === "down" ? "bg-down" : tone === "up" ? "bg-up" : "bg-signal"
  return (
    <div
      className={cn("flex h-2.5 gap-[2px]", className)}
      role="meter"
      aria-valuenow={Math.round(value)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      {Array.from({ length: segments }, (_, i) => (
        <span
          key={i}
          className={cn("flex-1", i < filled ? on : "bg-line-bright/60")}
        />
      ))}
    </div>
  )
}

export function Readout({
  label,
  value,
  unit,
  sub,
  tone = "neutral",
}: {
  label: string
  value: ReactNode
  unit?: string
  sub?: ReactNode
  tone?: Tone
}) {
  return (
    <Panel className="p-4">
      <span className="label">{label}</span>
      <p className="mt-2 flex items-baseline gap-1.5">
        <span
          className={cn(
            "num text-[1.75rem] leading-none font-semibold",
            tone === "down" && "text-down",
            tone === "up" && "text-up",
            tone === "signal" && "text-signal",
          )}
        >
          {value}
        </span>
        {unit ? <span className="num text-xs text-text-faint">{unit}</span> : null}
      </p>
      {sub ? <div className="mt-3">{sub}</div> : null}
    </Panel>
  )
}

export function Notice({
  tone = "signal",
  title,
  children,
}: {
  tone?: Tone
  title: string
  children?: ReactNode
}) {
  const edge =
    tone === "down" ? "border-l-down" : tone === "up" ? "border-l-up" : "border-l-signal"
  const wash =
    tone === "down" ? "bg-down-wash" : tone === "up" ? "bg-up-wash" : "bg-signal-wash"
  const text = tone === "down" ? "text-down" : tone === "up" ? "text-up" : "text-signal"
  return (
    <div className={cn("border border-line border-l-2", edge, wash)}>
      <div className="px-4 py-3">
        <p className={cn("font-mono text-[0.6875rem] tracking-widest uppercase", text)}>
          {title}
        </p>
        {children ? (
          <p className="mt-1.5 text-[0.8125rem] leading-relaxed text-text-muted">{children}</p>
        ) : null}
      </div>
    </div>
  )
}

export function Key({ children }: { children: ReactNode }) {
  return (
    <kbd className="num inline-flex h-[1.35rem] min-w-[1.35rem] items-center justify-center border border-line-bright bg-inset px-1.5 text-[0.625rem] text-text-muted">
      {children}
    </kbd>
  )
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="px-6 py-20 text-center">
      <p className="label">{title}</p>
      {children ? (
        <div className="mx-auto mt-3 max-w-sm text-[0.8125rem] text-text-muted">{children}</div>
      ) : null}
    </div>
  )
}
