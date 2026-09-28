import { useEffect, useState } from "react"
import { api, type Niche } from "@/lib/api"
import { Chip, Empty, Gauge, Notice, PageHead, Panel, PanelHead } from "@/components/ui/primitives"
import { cn } from "@/lib/cn"

const confTone = { high: "up", medium: "signal", low: "signal" } as const

export function Niches() {
  const [niches, setNiches] = useState<Niche[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .niches()
      .then(setNiches)
      .catch((e) => setError(e instanceof Error ? e.message : "could not load niches"))
  }, [])

  if (error) return <Notice tone="down" title="API unreachable">{error}</Notice>

  const thin = niches?.filter((n) => n.needs_corroboration).length ?? 0
  const shortlisted = niches?.filter((n) => n.status === "shortlisted").length ?? 0
  const top = niches?.length ? Math.max(...niches.map((n) => n.score ?? 0)) : null

  return (
    <div className="flex flex-col gap-4">
      <PageHead
        title="Niche leaderboard"
        meta={
          niches
            ? `${String(niches.length).padStart(2, "0")} RANKED · ${String(shortlisted).padStart(2, "0")} SHORTLISTED`
            : "LOADING…"
        }
      >
        {/* Corroboration is the number that decides whether the board can be
            trusted, so it is stated at the top rather than inferred from the
            rows. */}
        <div className="flex items-stretch divide-x divide-line border border-line bg-panel">
          <Stat label="Top score" value={top === null ? "—" : top} />
          <Stat label="Shortlisted" value={shortlisted} />
          <Stat label="Single source" value={thin} tone={thin > 0 ? "signal" : "neutral"} />
        </div>
      </PageHead>

      {thin > 0 ? (
        <Notice title={`${thin} shortlisted on a single source`}>
          Google Trends reports momentum only — whether a keyword is rising, not whether it
          is big or how crowded it is. Treat these as leads to check by hand, not as a
          reason to spend on designs.
        </Notice>
      ) : null}

      <Panel>
        <PanelHead label="Ranked opportunities">
          <span className="num text-[0.625rem] text-text-faint">SCORED HIGHEST FIRST</span>
        </PanelHead>
        {niches && niches.length === 0 ? (
          <Empty title="Nothing ranked">Run collection, then ranking.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[46rem] border-collapse">
              <thead>
                <tr className="border-b border-line bg-panel-raised">
                  <Th>Keyword</Th>
                  <Th className="w-[14rem]">Score</Th>
                  <Th>Confidence</Th>
                  <Th>Status</Th>
                  <Th right>Momentum</Th>
                  <Th right>Demand</Th>
                  <Th right>Competition</Th>
                </tr>
              </thead>
              <tbody>
                {(niches ?? []).map((n, i) => {
                  const b = n.breakdown
                  const rejected = n.status === "rejected"
                  return (
                    <tr
                      key={n.keyword}
                      className={cn(
                        "border-b border-line transition-colors last:border-0 hover:bg-panel-raised",
                        rejected && "opacity-45",
                      )}
                    >
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className="num mr-3 text-[0.625rem] text-text-faint">
                          {String(i + 1).padStart(2, "0")}
                        </span>
                        <span className="text-[0.8125rem] font-medium">{n.keyword}</span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <Gauge
                            value={n.score ?? 0}
                            tone={rejected ? "neutral" : "signal"}
                            className="w-28"
                          />
                          <span className="num w-6 text-right text-[0.8125rem] font-semibold">
                            {n.score}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        {n.confidence ? (
                          <Chip tone={confTone[n.confidence]}>{n.confidence}</Chip>
                        ) : null}
                      </td>
                      <td className="px-4 py-3">
                        <Chip tone={n.status === "shortlisted" ? "up" : "neutral"}>
                          {n.status}
                        </Chip>
                      </td>
                      <Td v={b?.momentum_component} />
                      <Td v={b?.demand_component} />
                      <Td v={b?.competition_penalty} />
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <p className="text-[0.75rem] leading-relaxed text-text-faint">
        A dash means no source reported that axis. Until Etsy supplies demand and
        competition, most rows are momentum only — which is why the board can rank a
        thinly-evidenced niche above a corroborated one.
      </p>
    </div>
  )
}

function Stat({
  label,
  value,
  tone = "neutral",
}: {
  label: string
  value: React.ReactNode
  tone?: "neutral" | "signal"
}) {
  return (
    <div className="px-4 py-2">
      <span className="label whitespace-nowrap">{label}</span>
      <p
        className={cn(
          "num mt-1 text-lg leading-none font-semibold",
          tone === "signal" && "text-signal",
        )}
      >
        {value}
      </p>
    </div>
  )
}

function Th({
  children,
  right,
  className,
}: {
  children: React.ReactNode
  right?: boolean
  className?: string
}) {
  return (
    <th
      className={cn(
        "label px-4 py-2.5 text-left whitespace-nowrap",
        right && "text-right",
        className,
      )}
    >
      {children}
    </th>
  )
}

function Td({ v }: { v: number | null | undefined }) {
  return (
    <td className="num px-4 py-3 text-right text-[0.8125rem]">
      {v === null || v === undefined ? (
        <span className="text-text-faint">—</span>
      ) : (
        Math.round(v)
      )}
    </td>
  )
}
