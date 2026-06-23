import { useEffect, useMemo, useState } from 'react'
import {
  bucketPicks,
  copyText,
  formatChg,
  formatMetric,
  loadScreenerData,
  rankModeLabel,
  type BucketId,
  type PickRow,
  type RankMode,
  type ScreenerData,
} from './lib/screener'

const BUCKETS: BucketId[] = ['B1', 'B2', 'B3', 'B4']
const RANK_MODES: { id: RankMode; label: string }[] = [
  { id: 'mcap', label: 'MCap' },
  { id: 'volume', label: 'Volume' },
  { id: 'oi', label: 'OI' },
]

function CopyIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="9" y="9" width="11" height="11" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M7 15H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v1" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  )
}

function ToggleGroup<T extends string>(props: {
  label: string
  value: T
  options: { id: T; label: string }[]
  onChange: (value: T) => void
}) {
  return (
    <div className="toggle-group">
      <span className="toggle-label">{props.label}</span>
      <div className="toggle-row" role="group" aria-label={props.label}>
        {props.options.map((opt) => (
          <button
            key={opt.id}
            type="button"
            className={`toggle-btn${props.value === opt.id ? ' active' : ''}`}
            onClick={() => props.onChange(opt.id)}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  )
}

function PickPanel(props: {
  title: string
  subtitle: string
  rows: PickRow[]
  rankMode: RankMode
  copyKey: string
  copiedKey: string | null
  onCopy: (key: string, text: string) => void
}) {
  const metricLabel = rankModeLabel(props.rankMode)
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2 className="panel-title">{props.title}</h2>
          <p className="panel-subtitle">{props.subtitle}</p>
        </div>
        <button
          type="button"
          className={`copy-btn${props.copiedKey === props.copyKey ? ' copied' : ''}`}
          title="Copy list"
          aria-label={`Copy ${props.title}`}
          onClick={() => props.onCopy(props.copyKey, copyText(props.rows, props.rankMode))}
        >
          <CopyIcon />
        </button>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Ticker</th>
              <th>24h chg%</th>
              <th className="metric">{metricLabel}</th>
              <th>Rank</th>
            </tr>
          </thead>
          <tbody>
            {props.rows.map((row, idx) => (
              <tr key={row.ticker}>
                <td>{idx + 1}</td>
                <td className="ticker">{row.ticker}</td>
                <td className={`chg ${row.chg24_pct >= 0 ? 'pos' : 'neg'}`}>{formatChg(row.chg24_pct)}</td>
                <td className="metric">{formatMetric(row.rank_metric)}</td>
                <td>{row.universe_rank}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {props.rows.length === 0 ? <div className="empty">No tickers with 24h change data in this bucket.</div> : null}
      </div>
    </section>
  )
}

export default function App() {
  const [data, setData] = useState<ScreenerData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [bucket, setBucket] = useState<BucketId>('B1')
  const [rankMode, setRankMode] = useState<RankMode>('volume')
  const [copiedKey, setCopiedKey] = useState<string | null>(null)

  useEffect(() => {
    loadScreenerData()
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Failed to load data'))
  }, [])

  const picks = useMemo(() => {
    if (!data) return { top10: [], bottom10: [] }
    return bucketPicks(data, rankMode, bucket)
  }, [data, rankMode, bucket])

  const bucketRange =
    bucket === 'B1' ? '1–50' : bucket === 'B2' ? '51–100' : bucket === 'B3' ? '101–150' : '151–200'

  const rankLabel = RANK_MODES.find((m) => m.id === rankMode)?.label ?? rankMode

  async function handleCopy(key: string, text: string) {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedKey(key)
      window.setTimeout(() => setCopiedKey((k) => (k === key ? null : k)), 1500)
    } catch {
      setCopiedKey(null)
    }
  }

  return (
    <div className="app">
      <header>
        <div>
          <h1>Vari Long/Short Screener</h1>
          {data ? <div className="meta">Updated {data.fetched_at}</div> : null}
        </div>
        <div className="controls">
          <ToggleGroup label="Bucket" value={bucket} options={BUCKETS.map((b) => ({ id: b, label: b }))} onChange={setBucket} />
          <ToggleGroup label="Universe rank" value={rankMode} options={RANK_MODES} onChange={setRankMode} />
        </div>
      </header>

      {error ? <div className="error">{error}</div> : null}
      {!data && !error ? <div className="loading">Loading screener data…</div> : null}

      {data ? (
        <main>
          <PickPanel
            title="Top 10"
            subtitle={`${bucket} (${bucketRange}) · ${rankLabel} · long candidates`}
            rows={picks.top10}
            rankMode={rankMode}
            copyKey="top10"
            copiedKey={copiedKey}
            onCopy={handleCopy}
          />
          <PickPanel
            title="Bottom 10"
            subtitle={`${bucket} (${bucketRange}) · ${rankLabel} · short candidates`}
            rows={picks.bottom10}
            rankMode={rankMode}
            copyKey="bottom10"
            copiedKey={copiedKey}
            onCopy={handleCopy}
          />
        </main>
      ) : null}
    </div>
  )
}
