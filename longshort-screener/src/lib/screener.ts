export type RankMode = 'fdv' | 'volume' | 'oi'
export type BucketId = 'B1' | 'B2' | 'B3' | 'B4'
export type UniverseScope = 'crypto' | 'all'
export type TrimMode = '10' | 'm3'

export const PICK_DEPTH = 13
export const TRIM_WINDOW = 10

export const RWA_INSTRUMENT_TYPE = 'perpetual_rwa_future'
export const MAJOR_TICKERS = ['BTC', 'ETH', 'SOL', 'HYPE'] as const

export type MajorChg = {
  ticker: string
  chg24_pct: number | null
}

export type ListingRow = {
  ticker: string
  instrument_type: string
  fdv: number | null
  vol_24h: number
  oi: number | null
  chg24_pct: number | null
}

export type ScreenerData = {
  fetched_at: string
  universe_top_n: number
  blacklist: string[]
  meta?: {
    data_source?: string
    listings_with_chg24?: number
    listings_with_fdv?: number
    listings_rwa?: number
  }
  majors?: MajorChg[]
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
  if (mode === 'fdv') return row.fdv ?? -1
  if (mode === 'volume') return row.vol_24h
  return row.oi ?? -1
}

function sortDesc(rows: ListingRow[], mode: RankMode): ListingRow[] {
  return [...rows].sort((a, b) => rankValue(b, mode) - rankValue(a, mode))
}

function metricValue(row: ListingRow, mode: RankMode): number | null {
  if (mode === 'fdv') return row.fdv
  if (mode === 'volume') return row.vol_24h
  return row.oi
}

export function filterUniverse(listings: ListingRow[], scope: UniverseScope): ListingRow[] {
  if (scope === 'all') return listings
  return listings.filter((r) => r.instrument_type !== RWA_INSTRUMENT_TYPE)
}

export function applyTrim(rows: PickRow[], trim: TrimMode): PickRow[] {
  if (trim === 'm3') return rows.slice(3, PICK_DEPTH)
  return rows.slice(0, TRIM_WINDOW)
}

export function trimRankOffset(trim: TrimMode): number {
  return trim === 'm3' ? 4 : 1
}

export function bucketPicks(
  data: ScreenerData,
  rankMode: RankMode,
  bucket: BucketId,
  universeScope: UniverseScope = 'crypto',
): { top13: PickRow[]; bottom13: PickRow[] } {
  const universe = filterUniverse(data.listings, universeScope)
  const ranked = sortDesc(universe, rankMode).slice(0, data.universe_top_n)
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
  const top13 = byChgDesc.slice(0, PICK_DEPTH)
  const bottom13 = byChgDesc.slice(-PICK_DEPTH).sort((a, b) => a.chg24_pct - b.chg24_pct)

  return { top13, bottom13 }
}

export function formatUpdatedAt(fetchedAt: string): string {
  const m = fetchedAt.match(/^(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2}):\d{2}\s+SGT$/)
  if (!m) return `Updated ${fetchedAt}`
  const [, year, month, day, hour24, minute] = m
  const h = Number(hour24)
  const ampm = h >= 12 ? 'pm' : 'am'
  const h12 = h % 12 || 12
  return `Updated ${day}-${month}-${year} ${h12}:${minute}${ampm} SGT`
}

export function formatChg(pct: number): string {
  const sign = pct > 0 ? '+' : ''
  return `${sign}${pct.toFixed(2)}%`
}

export function getMajorsChg(data: ScreenerData): MajorChg[] {
  if (data.majors?.length) return data.majors
  const byTicker = new Map(data.listings.map((r) => [r.ticker, r.chg24_pct]))
  return MAJOR_TICKERS.map((ticker) => ({ ticker, chg24_pct: byTicker.get(ticker) ?? null }))
}

export function rankModeLabel(mode: RankMode): string {
  if (mode === 'fdv') return 'FDV'
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

export function copyText(rows: PickRow[]): string {
  return rows.map((r) => `${r.ticker} ${formatChg(r.chg24_pct)}`).join('\n')
}

export async function loadScreenerData(bustCache = false): Promise<ScreenerData> {
  if (bustCache) {
    const refresh = await fetch('/api/refresh', { method: 'POST' })
    if (!refresh.ok) {
      const detail = await refresh.text().catch(() => '')
      throw new Error(`Failed to refresh screener data (${refresh.status})${detail ? `: ${detail}` : ''}`)
    }
    return refresh.json() as Promise<ScreenerData>
  }
  const res = await fetch('/screener.data.json', { cache: 'no-store' })
  if (!res.ok) throw new Error(`Failed to load screener data (${res.status})`)
  return res.json() as Promise<ScreenerData>
}
