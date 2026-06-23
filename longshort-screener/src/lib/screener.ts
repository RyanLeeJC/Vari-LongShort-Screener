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

export function bucketPicks(
  data: ScreenerData,
  rankMode: RankMode,
  bucket: BucketId,
): { top10: PickRow[]; bottom10: PickRow[] } {
  const ranked = sortDesc(data.listings, rankMode).slice(0, data.universe_top_n)
  const [lo, hi] = BUCKETS[bucket]
  const bucketRows = ranked.slice(lo - 1, hi)

  const withChg = bucketRows
    .filter((r) => r.chg24_pct != null && Number.isFinite(r.chg24_pct))
    .map((r, i) => ({
      ticker: r.ticker,
      chg24_pct: r.chg24_pct as number,
      universe_rank: lo + i,
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

export function copyText(rows: PickRow[]): string {
  return rows.map((r) => `${r.ticker}\t${formatChg(r.chg24_pct)}`).join('\n')
}

export async function loadScreenerData(): Promise<ScreenerData> {
  const res = await fetch(`${import.meta.env.BASE_URL}screener.data.json`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`Failed to load screener data (${res.status})`)
  return res.json() as Promise<ScreenerData>
}
