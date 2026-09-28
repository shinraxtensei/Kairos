import { useCallback, useEffect, useMemo, useState } from "react"
import { ChevronLeft, ChevronRight, ImageOff } from "lucide-react"
import { api, type Queue } from "@/lib/api"
import {
  Banner,
  Button,
  Card,
  EmptyState,
  Kbd,
  Pill,
} from "@/components/ui/primitives"
import { cn } from "@/lib/cn"

/** Review speed is the throughput ceiling for the whole business: at a 1-5%
 *  winner rate, finding winners means reviewing a lot of designs. Ten seconds
 *  per asset instead of two binds harder than generation cost ever will — so
 *  the hands never need to leave the keyboard. */
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

  // Reset the screening for each asset. Carrying ticks across assets would be
  // the same failure as pre-ticking them.
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
          approve
            ? { approve: true, confirmed: [...checked] }
            : { approve: false, reason, note },
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
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT")) {
        return
      }
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

  const megapixels = useMemo(() => {
    if (!asset?.print_spec) return null
    return ((asset.print_spec.pixel_width * asset.print_spec.pixel_height) / 1_000_000).toFixed(0)
  }, [asset])

  if (error && !queue) {
    return <Banner tone="bad" title="Could not reach the API">{error}</Banner>
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Review queue</h1>
          <p className="mt-0.5 text-sm text-text-muted">
            {queue ? (
              queue.total > 0 ? (
                <>
                  <span className="tnum">{index + 1}</span> of{" "}
                  <span className="tnum">{queue.total}</span> awaiting a decision
                </>
              ) : (
                "Nothing awaiting review"
              )
            ) : (
              "Loading…"
            )}
          </p>
        </div>
        {asset ? (
          <div className="flex items-center gap-2">
            <span className="tnum text-xs text-text-faint">{elapsed}s on this asset</span>
            <Button
              size="sm"
              onClick={() => setIndex((i) => Math.max(i - 1, 0))}
              disabled={index === 0}
              aria-label="Previous asset"
            >
              <ChevronLeft className="size-3.5" />
              <Kbd>K</Kbd>
            </Button>
            <Button
              size="sm"
              onClick={() =>
                setIndex((i) => Math.min(i + 1, (queue?.assets.length ?? 1) - 1))
              }
              disabled={!queue || index >= queue.assets.length - 1}
              aria-label="Next asset"
            >
              <Kbd>J</Kbd>
              <ChevronRight className="size-3.5" />
            </Button>
          </div>
        ) : null}
      </header>

      {error ? <Banner tone="bad" title="That decision was refused">{error}</Banner> : null}

      {!asset ? (
        <Card>
          <EmptyState title="Nothing awaiting review">
            Assets appear here once they reach the packaged stage.
          </EmptyState>
        </Card>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
          <div className="flex flex-col gap-4">
            <Card className="overflow-hidden">
              <div className="flex aspect-[4/3] max-h-[48vh] flex-col items-center justify-center gap-2 bg-surface-sunken px-6 text-center">
                <ImageOff className="size-5 text-text-faint" />
                <p className="text-sm text-text-muted">
                  Preview arrives with the image-generator adapter
                </p>
                <p className="text-xs text-text-faint">
                  Everything else on this screen is real
                </p>
              </div>
            </Card>

            <Card className="p-4">
              <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-6 gap-y-2 text-sm xl:grid-cols-[auto_minmax(0,1fr)_auto_minmax(0,1fr)]">
                <dt className="text-text-muted">Niche</dt>
                <dd className="truncate font-medium">{asset.niche_keyword}</dd>
                <dt className="text-text-muted">Variant</dt>
                <dd className="tnum">
                  #{asset.variant_index}
                  {asset.seed !== null ? ` · seed ${asset.seed}` : ""}
                </dd>
                {asset.print_spec ? (
                  <>
                    <dt className="text-text-muted">Print</dt>
                    <dd className="tnum">
                      {asset.print_spec.width_inches}×{asset.print_spec.height_inches}in @{" "}
                      {asset.print_spec.dpi} DPI
                    </dd>
                    <dt className="text-text-muted">Pixels</dt>
                    <dd className="tnum whitespace-nowrap">
                      {asset.print_spec.pixel_width}×{asset.print_spec.pixel_height}
                      <span className="ml-1 text-text-faint">{megapixels}MP</span>
                    </dd>
                  </>
                ) : null}
                <dt className="text-text-muted">Files</dt>
                <dd className="tnum">
                  {asset.files.length} ·{" "}
                  {(asset.files.reduce((a, f) => a + f.size_bytes, 0) / 1_048_576).toFixed(1)}MB
                </dd>
                {asset.cost ? (
                  <>
                    <dt className="text-text-muted">Cost</dt>
                    <dd className="tnum">{asset.cost}</dd>
                  </>
                ) : null}
              </dl>
            </Card>
          </div>

          <div className="flex flex-col gap-4">
            <Card>
              <div className="flex items-baseline justify-between border-b border-line px-4 py-3">
                <h2 className="text-sm font-semibold">IP screening</h2>
                {remaining > 0 ? (
                  <Pill tone="warn">
                    {remaining} left
                  </Pill>
                ) : (
                  <Pill tone="ok">all confirmed</Pill>
                )}
              </div>
              <ul className="flex flex-col p-2">
                {checks.map((check, i) => {
                  const on = checked.has(check.value)
                  return (
                    <li key={check.value}>
                      <button
                        type="button"
                        onClick={() => toggle(check.value)}
                        aria-pressed={on}
                        className={cn(
                          "flex w-full items-center gap-3 rounded-[var(--radius-control)] px-2.5 py-2 text-left text-sm transition-colors",
                          on ? "text-text" : "text-text-muted hover:bg-surface-sunken",
                        )}
                      >
                        <Kbd>{i + 1}</Kbd>
                        <span
                          className={cn(
                            "grid size-4 shrink-0 place-items-center rounded border transition-colors",
                            on
                              ? "border-accent bg-accent text-accent-contrast"
                              : "border-line-strong",
                          )}
                          aria-hidden
                        >
                          {on ? (
                            <svg viewBox="0 0 12 12" className="size-3" fill="none">
                              <path
                                d="M2.5 6.2l2.2 2.2L9.5 3.6"
                                stroke="currentColor"
                                strokeWidth="1.8"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                              />
                            </svg>
                          ) : null}
                        </span>
                        <span className="min-w-0">{check.label}</span>
                      </button>
                    </li>
                  )
                })}
              </ul>
              <div className="border-t border-line p-3">
                <Button
                  variant="primary"
                  className="w-full"
                  disabled={!allConfirmed || busy}
                  onClick={() => void decide(true)}
                >
                  Approve <Kbd>A</Kbd>
                </Button>
                {!allConfirmed ? (
                  <p className="mt-2 text-center text-xs text-text-faint">
                    Nothing is pre-ticked — a pre-ticked box is a box nobody reads
                  </p>
                ) : null}
              </div>
            </Card>

            <Card>
              <div className="border-b border-line px-4 py-3">
                <h2 className="text-sm font-semibold">Reject</h2>
              </div>
              <div className="flex flex-col gap-2.5 p-3">
                <select
                  id="reject-reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  className="rounded-[var(--radius-control)] border border-line bg-surface px-2.5 py-2 text-sm"
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
                  className="rounded-[var(--radius-control)] border border-line bg-surface px-2.5 py-2 text-sm"
                />
                <Button variant="danger" disabled={busy} onClick={() => void decide(false)}>
                  Reject <Kbd>R</Kbd>
                </Button>
              </div>
            </Card>
          </div>
        </div>
      )}

      {asset ? (
        <p className="border-t border-line pt-3 text-xs text-text-faint">
          <Kbd>1</Kbd>–<Kbd>{checks.length}</Kbd> toggle checks · <Kbd>A</Kbd> approve ·{" "}
          <Kbd>R</Kbd> reject · <Kbd>J</Kbd>/<Kbd>K</Kbd> next and previous. Approve stays
          disabled until every check is confirmed.
        </p>
      ) : null}
    </div>
  )
}