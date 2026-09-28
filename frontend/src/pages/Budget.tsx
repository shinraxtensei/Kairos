import { useEffect, useState } from "react"
import { api, type Budget as BudgetData } from "@/lib/api"
import { Banner, Card, EmptyState, Meter, Pill, StatTile } from "@/components/ui/primitives"

export function Budget() {
  const [data, setData] = useState<BudgetData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .budget()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "could not load the budget"))
  }, [])

  if (error) return <Banner tone="bad" title="Could not reach the API">{error}</Banner>

  const daily = data?.meters.find((m) => m.period === "daily")
  const monthly = data?.meters.find((m) => m.period === "monthly")

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-5">
      <header>
        <h1 className="text-xl font-semibold">Budget</h1>
        <p className="mt-0.5 text-sm text-text-muted">
          Caps are placeholders until they come out of the unit-economics model
        </p>
      </header>

      {data?.paused ? (
        <Banner tone="bad" title="Pipeline paused">
          Trend discovery and generation stop on a breached cap. Curation and analytics keep
          running — reviewing work already paid for costs nothing.
        </Banner>
      ) : null}

      {/* Big figures only where the figures are the point. */}
      <div className="grid gap-3 sm:grid-cols-2">
        {[daily, monthly].map((m) =>
          m ? (
            <StatTile
              key={m.period}
              label={m.period === "daily" ? "Spent today" : "Spent this month"}
              value={m.spent}
              tone={m.state === "over" ? "bad" : m.state === "warn" ? "warn" : "neutral"}
              sub={
                <span className="flex flex-col gap-1.5">
                  <Meter percent={m.percent} state={m.state} />
                  <span className="tnum flex justify-between">
                    <span>of {m.cap}</span>
                    <span>{m.remaining} left</span>
                  </span>
                </span>
              }
            />
          ) : null,
        )}
      </div>

      <Card className="overflow-hidden">
        <div className="border-b border-line px-5 py-3.5">
          <h2 className="text-sm font-semibold">Spend this month</h2>
        </div>
        {data && data.by_category.length === 0 ? (
          <EmptyState title="No spend recorded yet" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[34rem] border-collapse text-sm">
              <thead>
                <tr className="border-b border-line text-left">
                  <th className="eyebrow px-5 py-2.5">Category</th>
                  <th className="eyebrow px-5 py-2.5 text-right">Total</th>
                  <th className="eyebrow px-5 py-2.5 text-right">Events</th>
                  <th className="eyebrow px-5 py-2.5">Counts toward cap</th>
                </tr>
              </thead>
              <tbody>
                {(data?.by_category ?? []).map((row) => (
                  <tr key={row.category} className="border-b border-line last:border-0">
                    <td className="px-5 py-3 font-medium">{row.label}</td>
                    <td className="tnum px-5 py-3 text-right">{row.total}</td>
                    <td className="tnum px-5 py-3 text-right text-text-muted">{row.count}</td>
                    <td className="px-5 py-3">
                      {row.metered ? (
                        <Pill tone="accent">metered</Pill>
                      ) : (
                        <Pill>selling fee</Pill>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <p className="text-xs leading-relaxed text-text-faint">
        Etsy's listing and transaction fees are recorded but never metered. They follow from
        selling rather than from choosing to spend, so counting them toward a generation cap
        would pause generation because something sold.
      </p>
    </div>
  )
}
