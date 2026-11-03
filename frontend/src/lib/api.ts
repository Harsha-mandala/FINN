// FINN API client
// All fetch calls go through this. Uses relative /api prefix in production.

const BASE = import.meta.env.VITE_API_URL || '/api'

export const isColdStarting = { value: false }
const listeners: Array<(waking: boolean) => void> = []

export function onColdStartChange(cb: (waking: boolean) => void) {
  listeners.push(cb)
  return () => {
    const idx = listeners.indexOf(cb)
    if (idx !== -1) listeners.splice(idx, 1)
  }
}

function notifyColdStart(waking: boolean) {
  isColdStarting.value = waking
  listeners.forEach((l) => l(waking))
}

export function warmUpBackend() {
  try {
    fetch(`${BASE}/health`, { method: 'GET' }).catch(() => {})
  } catch {}
}

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const maxAttempts = 6
  const timeoutMs = 10000
  let lastError: any = null

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    let wokeNotice = false
    const timer = setTimeout(() => {
      wokeNotice = true
      notifyColdStart(true)
    }, 1500)

    const controller = new AbortController()
    const abortTimer = setTimeout(() => controller.abort(), timeoutMs)

    try {
      const res = await fetch(`${BASE}${path}`, {
        headers: { 'Content-Type': 'application/json', ...options?.headers },
        signal: controller.signal,
        ...options,
      })
      clearTimeout(timer)
      clearTimeout(abortTimer)
      if (wokeNotice) notifyColdStart(false)

      if (!res.ok) {
        if ([502, 503, 504].includes(res.status) && attempt < maxAttempts - 1) {
          notifyColdStart(true)
          await new Promise((r) => setTimeout(r, Math.min(1000 * Math.pow(1.5, attempt), 4000)))
          continue
        }
        const err = await res.text()
        throw new Error(`API ${res.status}: ${err}`)
      }
      return await res.json()
    } catch (e: any) {
      clearTimeout(timer)
      clearTimeout(abortTimer)
      lastError = e
      if (attempt < maxAttempts - 1) {
        notifyColdStart(true)
        await new Promise((r) => setTimeout(r, Math.min(1000 * Math.pow(1.5, attempt), 4000)))
      }
    }
  }
  notifyColdStart(false)
  throw lastError || new Error('Request failed after retries')
}

// ── Push ──────────────────────────────────────────────────────────────────────

export interface Announcement {
  ticker: string
  source: string
  headline: string
  category: string
  priority: number
  priority_tier: 'high' | 'medium' | 'low'
  date: string
  attachment_url?: string
  news_id?: string
  summary?: string
  sub_items?: Array<{
    headline: string
    date: string
    attachment_url?: string
    news_id?: string
    category?: string
  }>
  thread_count?: number
  enrichment?: {
    type: 'management_bio' | 'results_card'
    person_name?: string
    role?: string
    bio?: string
    sources?: string[]
    data?: ResultsCard
  }
}

export interface ResultsCard {
  status?: string
  basis?: string
  is_bank?: boolean
  period_current?: string
  period_qoq?: string
  period_yoy?: string
  metrics?: {
    revenue?: MetricDelta
    ebitda?: MetricDelta
    pbt?: MetricDelta
    pat?: MetricDelta
    total_income?: MetricDelta
    nii?: MetricDelta
  }
  revenue?: MetricDelta
  ebitda?: MetricDelta
  pbt?: MetricDelta
  pat?: MetricDelta
  filing_url?: string
}

export interface MetricDelta {
  current?: number | null
  qoq_prev?: number | null
  qoq_pct?: number | null
  yoy_prev?: number | null
  yoy_pct?: number | null
  not_applicable?: boolean
}

export interface DigestResponse {
  window?: string
  window_hours: number
  data_as_of?: string
  generated_at: string
  high: Announcement[]
  medium: Announcement[]
  low: Announcement[]
  routine_summary?: {
    count: number
    label: string
  }
  low_count: number
  total: number
}

export interface TickerSummary {
  ticker: string
  latest_date: string
  latest_close: number
  prev_close: number
  price_change_pct: number
  volume_latest: number
  volume_20d_avg: number
  volume_ratio: number
  error?: string
}

export interface Alert {
  ticker: string
  alert_type: 'price_move' | 'volume_spike' | 'announcement'
  triggered_at: string
  description: string
  value?: number
  threshold?: number
}

export interface AlertsResponse {
  generated_at: string
  thresholds: {
    volume_multiple: number
    price_move_pct: number
    alert_categories: string[]
  }
  alerts: Alert[]
  count: number
}

// ── Research (Pull) ───────────────────────────────────────────────────────────

export interface ResearchCard {
  card_type: 'snapshot' | 'trajectory' | 'guidance' | 'promised_vs_delivered' | 'bull_bear'
  ticker: string
  company_name: string
  generated_at: string
  data: {
    content?: string
    commitments?: Array<{ statement: string; verdict: string; note?: string }>
    business_summary?: string
    segments?: Array<{ name: string; revenue_share_pct?: number; period?: string; note?: string }>
    key_metrics?: Array<{ name: string; value: any; unit?: string; period?: string; source_ref?: string }>
    series?: any[]
    items?: any[]
    bull?: any[]
    bear?: any[]
  }
  provenance?: {
    model_used?: string
    docs_used?: string[]
    generated_at?: string
    status?: string
  }
}

export interface ResearchResponse {
  status: string
  ticker: string
  company_name: string
  generated_at: string
  cards: ResearchCard[]
  sources_used: string[]
  message?: string
}

export interface PrimaryDocLink {
  title: string
  type: string
  url: string
  date?: string | null
  year?: string | null
}

export interface RecentFiling {
  headline: string
  category: string
  priority: number
  priority_tier: 'high' | 'medium' | 'low'
  date: string
  attachment_url?: string
  news_id?: string
}

export interface TickerOverviewResponse {
  ticker: string
  company_name: string
  latest_results?: ResultsCard | null
  price_volume?: {
    latest_date?: string
    latest_close?: number
    prev_close?: number
    price_change_pct?: number
    volume_latest?: number
    volume_20d_avg?: number
    volume_ratio?: number
    sparkline?: number[]
  } | null
  primary_documents: PrimaryDocLink[]
  recent_filings: RecentFiling[]
  has_deep_research: boolean
  generated_at: string
}

// ── API functions ─────────────────────────────────────────────────────────────

export const api = {
  // Push
  getDigest: (
    window: string | number = '24h',
    options?: { start_date?: string; end_date?: string; include_low?: boolean; window_hours?: number }
  ) => {
    const params = new URLSearchParams()
    if (typeof window === 'number') {
      params.set('window_hours', String(window))
    } else {
      params.set('window', window)
    }
    if (options?.start_date) params.set('start_date', options.start_date)
    if (options?.end_date) params.set('end_date', options.end_date)
    if (options?.include_low !== undefined) params.set('include_low', String(options.include_low))
    if (options?.window_hours) params.set('window_hours', String(options.window_hours))
    return fetchJSON<DigestResponse>(`/push/digest?${params.toString()}`)
  },

  getPrices: (tickers?: string) =>
    fetchJSON<{ generated_at: string; tickers: Record<string, TickerSummary> }>(
      `/push/prices${tickers ? `?tickers=${tickers}` : ''}`
    ),

  getPriceHistory: (ticker: string) =>
    fetchJSON<{ ticker: string; history: Array<{ date: string; close: number; volume: number }> }>(
      `/push/prices/${ticker}/history`
    ),

  getAlerts: (params?: { volume_multiple?: number; price_move_pct?: number }) =>
    fetchJSON<AlertsResponse>(
      `/push/alerts?${new URLSearchParams((params as Record<string, string>) || {})}`
    ),

  // Research
  getOverview: (ticker: string) => fetchJSON<TickerOverviewResponse>(`/pull/overview/${ticker}`),

  getResearch: (ticker: string, force = false) =>
    fetchJSON<ResearchResponse>(`/pull/research/${ticker}${force ? '?force_refresh=true' : ''}`),

  generateResearch: (ticker: string) =>
    fetchJSON<ResearchResponse>('/pull/research', {
      method: 'POST',
      body: JSON.stringify({ ticker, force_refresh: true }),
    }),
}
