export type RankMode = 'mcap' | 'volume' | 'oi'
export type BucketId = 'B1' | 'B2' | 'B3' | 'B4'

export type ListingRow = {
  ticker: string
  market_cap: number | null
  vol_24h: number
  oi: number | null
  chg24_pct: number | null
}

export type ScreenerData = {
  fetched_at: string
  universe_top_n: number
  blacklist: string[]
  listings: ListingRow[]
}

export type PickRow = {
  ticker: string
  chg24_pct: number
  universe_rank: number
  rank_metric: number | null
}

const BUCKETS: Record<BucketId, [number, number]> = {
  B1: [1, 50],
  B2: [51, 100],
  B3: [101, 150],
  B4: [151, 200],
}

function rankValue(row: ListingRow, mode: RankMode): number {
  if (mode === 'mcap') return row.market_cap ?? -1
  if (mode === 'volume') return row.vol_24h
  return row.oi ?? -1
}

function sortDesc(rows: ListingRow[], mode: RankMode): ListingRow[] {
  return [...rows].sort((a, b) => rankValue(b, mode) - rankValue(a, mode))
}

function metricValue(row: ListingRow, mode: RankMode): number | null {
  if (mode === 'mcap') return row.market_cap
  if (mode === 'volume') return row.vol_24h
  return row.oi
}

export function bucketPicks(
  data: ScreenerData,
  rankMode: RankMode,
  bucket: BucketId,
): { top10: PickRow[]; bottom10: PickRow[] } {
  const ranked = sortDesc(data.listings, rankMode).slice(0, data.universe_top_n)
  const rankByTicker = new Map(ranked.map((r, i) => [r.ticker, i + 1]))
  const [lo, hi] = BUCKETS[bucket]
  const bucketRows = ranked.slice(lo - 1, hi)

  const withChg = bucketRows
    .filter((r) => r.chg24_pct != null && Number.isFinite(r.chg24_pct))
    .map((r) => ({
      ticker: r.ticker,
      chg24_pct: r.chg24_pct as number,
      universe_rank: rankByTicker.get(r.ticker) ?? 0,
      rank_metric: metricValue(r, rankMode),
    }))

  const byChgDesc = [...withChg].sort((a, b) => b.chg24_pct - a.chg24_pct)
  const top10 = byChgDesc.slice(0, 10)
  const bottom10 = byChgDesc.slice(-10).sort((a, b) => b.chg24_pct - a.chg24_pct)

  return { top10, bottom10 }
}

export function formatChg(pct: number): string {
  const sign = pct > 0 ? '+' : ''
  return `${sign}${pct.toFixed(2)}%`
}

export function rankModeLabel(mode: RankMode): string {
  if (mode === 'mcap') return 'MCap'
  if (mode === 'volume') return 'Volume'
  return 'OI'
}

export function formatMetric(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return '—'
  const abs = Math.abs(value)
  if (abs >= 1e9) return `$${(value / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `$${(value / 1e6).toFixed(2)}M`
  if (abs >= 1e3) return `$${(value / 1e3).toFixed(2)}K`
  return `$${value.toFixed(2)}`
}

export function copyText(rows: PickRow[], rankMode: RankMode): string {
  const metricLabel = rankModeLabel(rankMode)
  return rows
    .map(
      (r) =>
        `${r.ticker}\t${formatChg(r.chg24_pct)}\t${metricLabel}\t${formatMetric(r.rank_metric)}\t${r.universe_rank}`,
    )
    .join('\n')
}

export async function loadScreenerData(): Promise<ScreenerData> {
  const res = await fetch(`${import.meta.env.BASE_URL}screener.data.json`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`Failed to load screener data (${res.status})`)
  return res.json() as Promise<ScreenerData>
}
