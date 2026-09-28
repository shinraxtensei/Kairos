import { useEffect, useState } from "react"
import { api, type Niche } from "@/lib/api"
import { Banner, Card, EmptyState, Meter, Pill } from "@/components/ui/primitives"
import { cn } from "@/lib/cn"

const confidenceTone = { high: "ok", medium: "accent", low: "warn" } as const

export function Niches() {
  const [niches, setNiches] = useState<Niche[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .niches()
      .then(setNiches)
      .catch((e) => setError(e instanceof Error ? e.message : "could not load niches"))
  }, [])

  if (error) return <Banner tone="bad" title="Could not reach the API">{error}</Banner>

  const thin = niches?.filter((n) => n.needs_corroboration).length ?? 0

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5">
      <header>
        <h1 className="text-xl font-semibold">Niches</h1>
        <p className="mt-0.5 text-sm text-text-muted">
          {niches ? `${niches.length} ranked, scored highest first` : "Loading…"}
        </p>
      </header>

      {thin > 0 ? (
        <Banner
          tone="warn"
          title={`${thin} shortlisted ${thin === 1 ? "niche rests" : "niches rest"} on a single source`}
        >
          Google Trends gives momentum only — whether a keyword is rising, not whether it is
          big or how crowded it is. Treat these as leads to check by hand, not as a reason to
          spend on designs.
        </Banner>
      ) : null}

      <Card className="overflow-hidden">
        {niches && niches.length === 0 ? (
          <EmptyState title="Nothing ranked yet">
            Run collection, then ranking, to populate the board.
          </EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[42rem] border-collapse text-sm">
              <thead>
                <tr className="border-b border-line text-left">
                  {["Keyword", "Score", "Confidence", "Status", "Momentum", "Demand", "Competition"].map(
                    (h, i) => (
                      <th
                        key={h}
                        className={cn(
                          "eyebrow px-4 py-2.5 font-semibold whitespace-nowrap",
                          (i >= 4 || i === 1) && "text-right",
                        )}
                      >
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {(niches ?? []).map((n) => {
                  const b = n.breakdown
                  const rejected = n.status === "rejected"
                  return (
                    <tr
                      key={n.keyword}
                      className={cn(
                        "border-b border-line last:border-0 transition-colors hover:bg-surface-sunken/60",
                        rejected && "opacity-55",
                      )}
                    >
                      <td className="px-4 py-3 font-medium whitespace-nowrap">{n.keyword}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-2.5">
                          <Meter percent={n.score ?? 0} className="w-16" />
                          <span className="tnum w-7 text-right font-semibold">{n.score}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        {n.confidence ? (
                          <Pill tone={confidenceTone[n.confidence]}>{n.confidence}</Pill>
                        ) : null}
                      </td>
                      <td className="px-4 py-3">
                        {n.status === "shortlisted" ? (
                          <Pill tone="ok">shortlisted</Pill>
                        ) : (
                          <Pill>{n.status}</Pill>
                        )}
                      </td>
                      <Cell value={b?.momentum_component} />
                      <Cell value={b?.demand_component} />
                      <Cell value={b?.competition_penalty} />
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <p className="text-xs leading-relaxed text-text-faint">
        A dash means no source reported that axis. Until Etsy supplies demand and competition,
        most rows are momentum only — which is why the board can rank a thinly-evidenced niche
        above a corroborated one.
      </p>
    </div>
  )
}

function Cell({ value }: { value: number | null | undefined }) {
  return (
    <td className="tnum px-4 py-3 text-right">
      {value === null || value === undefined ? (
        <span className="text-text-faint">—</span>
      ) : (
        Math.round(value)
      )}
    </td>
  )
}
