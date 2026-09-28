/** Thin client over the JSON API the backend already exposes. */

export type Breakdown = {
  demand_component: number | null
  momentum_component: number | null
  competition_penalty: number | null
  applied_weights: Record<string, number>
}

export type Niche = {
  keyword: string
  score: number | null
  confidence: "low" | "medium" | "high" | null
  status: "shortlisted" | "rejected" | "candidate"
  needs_corroboration: boolean
  breakdown: Breakdown | null
  scored_at: string | null
}

export type IpCheck = { value: string; label: string }

export type QueueAsset = {
  asset_id: string
  niche_keyword: string
  variant_index: number
  seed: number | null
  print_spec: {
    width_inches: number
    height_inches: number
    dpi: number
    pixel_width: number
    pixel_height: number
  } | null
  files: { filename: string; size_bytes: number }[]
  cost: string | null
}

export type Queue = {
  total: number
  ip_checks: IpCheck[]
  rejection_reasons: { value: string; label: string }[]
  assets: QueueAsset[]
}

export type Meter = {
  period: "daily" | "monthly"
  cap: string
  spent: string
  remaining: string
  percent: number
  state: "" | "warn" | "over"
}

export type Budget = {
  currency: string
  paused: boolean
  meters: Meter[]
  by_category: {
    category: string
    label: string
    total: string
    count: number
    metered: boolean
  }[]
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { accept: "application/json" } })
  if (!res.ok) throw new Error(`${path} returned ${res.status}`)
  return res.json() as Promise<T>
}

export const api = {
  niches: () => get<Niche[]>("/api/niches"),
  queue: () => get<Queue>("/api/review/queue"),
  budget: () => get<Budget>("/api/budget"),

  async decide(
    assetId: string,
    body: { approve: true; confirmed: string[] } | { approve: false; reason: string; note?: string },
  ) {
    const form = new URLSearchParams()
    let path: string
    if (body.approve) {
      path = `/review/${assetId}/approve`
      for (const c of body.confirmed) form.append("confirmed", c)
    } else {
      path = `/review/${assetId}/reject`
      form.set("reason", body.reason)
      form.set("note", body.note ?? "")
    }
    const res = await fetch(path, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: form,
      redirect: "follow",
    })
    // The domain refuses an incomplete screening with a 500 rather than
    // silently accepting it. Surface that instead of pretending it worked.
    if (!res.ok) throw new Error(`decision refused (${res.status})`)
  },
}
