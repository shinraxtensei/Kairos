import { useEffect, useState } from "react"
import { api, type Budget as BudgetData } from "@/lib/api"
import {
  Chip,
  Dot,
  Empty,
  Gauge,
  Notice,
  PageHead,
  Panel,
  PanelHead,
  Readout,
} from "@/components/ui/primitives"
import { cn } from "@/lib/cn"

export function Budget() {
  const [data, setData] = useState<BudgetData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .budget()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "could not load the budget"))
  }, [])

  if (error) return <Notice tone="down" title="API unreachable">{error}</Notice>

  return (
    <div className="flex flex-col gap-4">
      <PageHead
        title="Budget"
        meta={data ? `${data.currency} · CAPS ARE PLACEHOLDERS` : "LOADING…"}
      >
        <Chip tone={data?.paused ? "down" : "up"}>
          <Dot tone={data?.paused ? "down" : "up"} />
          {data?.paused ? "generation paused" : "generation running"}
        </Chip>
      </PageHead>

      {data?.paused ? (
        <Notice tone="down" title="Pipeline paused">
          Trend discovery and generation stop on a breached cap. Curation and analytics keep
          running — reviewing work already paid for costs nothing.
        </Notice>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        {(data?.meters ?? []).map((m) => (
          <Readout
            key={m.period}
            label={m.period === "daily" ? "Spent today" : "Spent this month"}
            value={m.spent.split(" ")[0]}
            unit={m.spent.split(" ")[1]}
            tone={m.state === "over" ? "down" : m.state === "warn" ? "signal" : "neutral"}
            sub={
              <div className="flex flex-col gap-2">
                <Gauge
                  value={m.percent}
                  tone={m.state === "over" ? "down" : "signal"}
                  segments={28}
                />
                <div className="num flex justify-between text-[0.625rem] text-text-faint">
                  <span>CAP {m.cap}</span>
                  <span>{m.remaining} LEFT</span>
                </div>
              </div>
            }
          />
        ))}
      </div>

      <Panel>
        <PanelHead label="Spend by category">
          <span className="num text-[0.625rem] text-text-faint">THIS MONTH</span>
        </PanelHead>
        {data && data.by_category.length === 0 ? (
          <Empty title="No spend recorded" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[34rem] border-collapse">
              <thead>
                <tr className="border-b border-line bg-panel-raised">
                  <th className="label px-4 py-2.5 text-left">Category</th>
                  <th className="label px-4 py-2.5 text-right">Total</th>
                  <th className="label px-4 py-2.5 text-right">Events</th>
                  <th className="label px-4 py-2.5 text-left">Counts toward cap</th>
                </tr>
              </thead>
              <tbody>
                {(data?.by_category ?? []).map((row) => (
                  <tr
                    key={row.category}
                    className={cn(
                      "border-b border-line last:border-0 hover:bg-panel-raised",
                      !row.metered && "opacity-70",
                    )}
                  >
                    <td className="px-4 py-3 text-[0.8125rem]">{row.label}</td>
                    <td className="num px-4 py-3 text-right text-[0.8125rem]">{row.total}</td>
                    <td className="num px-4 py-3 text-right text-[0.8125rem] text-text-muted">
                      {row.count}
                    </td>
                    <td className="px-4 py-3">
                      <Chip tone={row.metered ? "signal" : "neutral"}>
                        {row.metered ? "metered" : "selling fee"}
                      </Chip>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <p className="text-[0.75rem] leading-relaxed text-text-faint">
        Etsy's listing and transaction fees are recorded but never metered. They follow from
        selling rather than from choosing to spend, so counting them toward a generation cap
        would pause generation because something sold.
      </p>
    </div>
  )
}
