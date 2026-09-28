import { useCallback, useEffect, useMemo, useState } from "react"
import type { ReactNode } from "react"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { api, type Queue } from "@/lib/api"
import {
  Button,
  Chip,
  Empty,
  Key,
  Notice,
  PageHead,
  Panel,
  PanelHead,
} from "@/components/ui/primitives"
import { cn } from "@/lib/cn"

/** Review speed is the throughput ceiling for the whole business: at a 1-5%
 *  winner rate, finding winners means reviewing a great many designs, and ten
 *  seconds per asset instead of two binds harder than generation cost ever
 *  will. So the screen is built for hands that never leave the keyboard. */
export function Review() {
  const [queue, setQueue] = useState<Queue | null>(null)
  const [index, setIndex] = useState(0)
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [reason, setReason] = useState("ip_risk")
  const [note, setNote] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [startedAt, setStartedAt] = useState(() => Date.now())
  const [elapsed, setElapsed] = useState(0)

  const load = useCallback(async () => {
    try {
      const next = await api.queue()
      setQueue(next)
      setIndex((i) => Math.min(i, Math.max(next.assets.length - 1, 0)))
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not load the queue")
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const asset = queue?.assets[index]

  // Reset per asset. Carrying ticks across assets is the same failure as
  // pre-ticking them.
  useEffect(() => {
    setChecked(new Set())
    setNote("")
    setStartedAt(Date.now())
  }, [asset?.asset_id])

  useEffect(() => {
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000)
    return () => clearInterval(id)
  }, [startedAt])

  const checks = queue?.ip_checks ?? []
  const allConfirmed = checks.length > 0 && checked.size === checks.length

  const toggle = useCallback((value: string) => {
    setChecked((prev) => {
      const next = new Set(prev)
      if (next.has(value)) next.delete(value)
      else next.add(value)
      return next
    })
  }, [])

  const decide = useCallback(
    async (approve: boolean) => {
      if (!asset || busy) return
      if (approve && !allConfirmed) return
      setBusy(true)
      try {
        await api.decide(
          asset.asset_id,
          approve ? { approve: true, confirmed: [...checked] } : { approve: false, reason, note },
        )
        await load()
      } catch (e) {
        setError(e instanceof Error ? e.message : "the decision was refused")
      } finally {
        setBusy(false)
      }
    },
    [asset, busy, allConfirmed, checked, reason, note, load],
  )

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const el = document.activeElement as HTMLElement | null
      if (el && ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName)) return
      const n = Number.parseInt(e.key, 10)
      if (n >= 1 && n <= checks.length) {
        toggle(checks[n - 1].value)
        e.preventDefault()
        return
      }
      const k = e.key.toLowerCase()
      if (k === "a" && allConfirmed) void decide(true)
      if (k === "r") void decide(false)
      if (k === "j") setIndex((i) => Math.min(i + 1, (queue?.assets.length ?? 1) - 1))
      if (k === "k") setIndex((i) => Math.max(i - 1, 0))
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [checks, toggle, allConfirmed, decide, queue?.assets.length])

  const remaining = checks.length - checked.size
  const mp = useMemo(() => {
    if (!asset?.print_spec) return null
    return ((asset.print_spec.pixel_width * asset.print_spec.pixel_height) / 1_000_000).toFixed(0)
  }, [asset])

  if (error && !queue) return <Notice tone="down" title="API unreachable">{error}</Notice>

  return (
    <div className="flex flex-col gap-4">
      <PageHead
        title="Review queue"
        meta={
          queue
            ? queue.total > 0
              ? `ASSET ${String(index + 1).padStart(2, "0")} / ${String(queue.total).padStart(2, "0")} · ${elapsed}s ON SCREEN`
              : "QUEUE EMPTY"
            : "LOADING…"
        }
      >
        {asset ? (
          <div className="flex items-center gap-1.5">
            <Button
              size="sm"
              onClick={() => setIndex((i) => Math.max(i - 1, 0))}
              disabled={index === 0}
              aria-label="Previous asset"
            >
              <ChevronLeft className="size-3" /> <Key>K</Key>
            </Button>
            <Button
              size="sm"
              onClick={() => setIndex((i) => Math.min(i + 1, (queue?.assets.length ?? 1) - 1))}
              disabled={!queue || index >= queue.assets.length - 1}
              aria-label="Next asset"
            >
              <Key>J</Key> <ChevronRight className="size-3" />
            </Button>
          </div>
        ) : null}
      </PageHead>

      {error ? <Notice tone="down" title="Decision refused">{error}</Notice> : null}

      {!asset ? (
        <Panel>
          <Empty title="Queue empty">
            Assets arrive here once they reach the packaged stage.
          </Empty>
        </Panel>
      ) : (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_25rem]">
          <div className="flex flex-col gap-4">
            <Panel>
              <PanelHead label="Asset preview">
                <span className="num text-[0.625rem] text-text-faint">
                  {asset.asset_id.slice(0, 8)}
                </span>
              </PanelHead>
              {/* Height is capped rather than set by aspect ratio: on a wide
                  screen a 16:10 box pushed the screening checklist — the only
                  thing on this page that gates a publish — below the fold. */}
              <div className="relative flex h-[clamp(13rem,34vh,22rem)] items-center justify-center overflow-hidden bg-inset">
                {/* Registration marks — the frame a print sits in. A placeholder,
                    but the right kind of placeholder. */}
                <div className="absolute inset-6 border border-dashed border-line-bright/50" />
                <div className="absolute top-1/2 right-0 left-0 h-px bg-line-bright/30" />
                <div className="absolute top-0 bottom-0 left-1/2 w-px bg-line-bright/30" />
                <div className="relative z-10 px-6 text-center">
                  <p className="label">No preview</p>
                  <p className="mx-auto mt-2 max-w-xs text-[0.8125rem] text-text-muted">
                    Arrives with the image-generator adapter. Everything else on this
                    screen is live.
                  </p>
                </div>
              </div>
            </Panel>

            <Panel>
              <PanelHead label="Specification" />
              <dl className="grid grid-cols-2 sm:grid-cols-3">
                <Spec k="Niche" v={asset.niche_keyword} />
                <Spec k="Variant" v={`#${asset.variant_index}`} />
                <Spec k="Seed" v={asset.seed ?? "—"} />
                {asset.print_spec ? (
                  <>
                    <Spec
                      k="Print"
                      v={`${asset.print_spec.width_inches}×${asset.print_spec.height_inches}in`}
                    />
                    <Spec k="Density" v={`${asset.print_spec.dpi} DPI`} />
                    <Spec
                      k="Raster"
                      v={`${asset.print_spec.pixel_width}×${asset.print_spec.pixel_height}`}
                      note={`${mp}MP`}
                    />
                  </>
                ) : null}
                <Spec k="Files" v={asset.files.length} />
                <Spec
                  k="Payload"
                  v={`${(asset.files.reduce((a, f) => a + f.size_bytes, 0) / 1_048_576).toFixed(1)}MB`}
                  note="≤20"
                />
                <Spec k="Cost" v={asset.cost ?? "—"} />
              </dl>
            </Panel>
          </div>

          <div className="flex flex-col gap-4">
            <Panel>
              <PanelHead label="IP screening">
                <Chip tone={remaining ? "signal" : "up"}>
                  {remaining ? `${remaining} pending` : "cleared"}
                </Chip>
              </PanelHead>
              <ul>
                {checks.map((check, i) => {
                  const on = checked.has(check.value)
                  return (
                    <li key={check.value} className="border-b border-line last:border-0">
                      <button
                        type="button"
                        onClick={() => toggle(check.value)}
                        aria-pressed={on}
                        className={cn(
                          "flex w-full items-center gap-3 px-4 py-2.5 text-left text-[0.8125rem] transition-colors",
                          on ? "bg-signal-wash text-text" : "text-text-muted hover:bg-panel-raised",
                        )}
                      >
                        <Key>{i + 1}</Key>
                        <span
                          className={cn(
                            "grid size-3.5 shrink-0 place-items-center border transition-colors",
                            on ? "border-signal bg-signal text-on-signal" : "border-line-bright",
                          )}
                          aria-hidden
                        >
                          {on ? (
                            <svg viewBox="0 0 10 10" className="size-2.5" fill="none">
                              <path
                                d="M2 5.2l2 2L8 2.8"
                                stroke="currentColor"
                                strokeWidth="1.8"
                                strokeLinecap="square"
                              />
                            </svg>
                          ) : null}
                        </span>
                        <span className="min-w-0 flex-1">{check.label}</span>
                      </button>
                    </li>
                  )
                })}
              </ul>
              <div className="border-t border-line p-3">
                <Button
                  variant="signal"
                  className="w-full"
                  disabled={!allConfirmed || busy}
                  onClick={() => void decide(true)}
                >
                  Approve <Key>A</Key>
                </Button>
                <p className="mt-2.5 text-center font-mono text-[0.625rem] leading-relaxed text-text-faint">
                  {allConfirmed
                    ? "All checks confirmed by hand"
                    : "Nothing is pre-ticked — a pre-ticked box is a box nobody reads"}
                </p>
              </div>
            </Panel>

            <Panel>
              <PanelHead label="Reject" />
              <div className="flex flex-col gap-2 p-3">
                <select
                  id="reject-reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  className="border border-line bg-inset px-2.5 py-2 font-mono text-xs text-text"
                >
                  {(queue?.rejection_reasons ?? []).map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
                <input
                  id="reject-note"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Note (optional)"
                  className="border border-line bg-inset px-2.5 py-2 font-mono text-xs text-text placeholder:text-text-faint"
                />
                <Button variant="danger" disabled={busy} onClick={() => void decide(false)}>
                  Reject <Key>R</Key>
                </Button>
              </div>
            </Panel>
          </div>
        </div>
      )}

      {asset ? (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-line pt-3">
          <span className="label">Keys</span>
          {[
            [<Key key="a">1</Key>, "–", <Key key="b">{checks.length}</Key>, " toggle"],
            [<Key key="c">A</Key>, " approve"],
            [<Key key="d">R</Key>, " reject"],
            [<Key key="e">J</Key>, "/", <Key key="f">K</Key>, " step"],
          ].map((parts, i) => (
            <span
              key={i}
              className="flex items-center gap-1 text-[0.6875rem] text-text-faint"
            >
              {parts}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function Spec({ k, v, note }: { k: string; v: ReactNode; note?: string }) {
  return (
    <div className="border-r border-b border-line px-4 py-3">
      <dt className="label">{k}</dt>
      <dd className="num mt-1 truncate text-[0.8125rem] text-text">
        {v}
        {note ? <span className="ml-1.5 text-text-faint">{note}</span> : null}
      </dd>
    </div>
  )
}
