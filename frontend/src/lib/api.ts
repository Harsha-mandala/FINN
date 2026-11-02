// FINN API client
// All fetch calls go through this. Uses relative /api prefix in production.

const BASE = import.meta.env.VITE_API_URL || '/api'

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`API ${res.status}: ${err}`)
  }
  return res.json()
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
  period_current?: string
  period_qoq?: string
  period_yoy?: string
  metrics?: {
    revenue: MetricDelta
    ebitda: MetricDelta
    pbt: MetricDelta
    pat: MetricDelta
  }
  revenue?: MetricDelta
  ebitda?: MetricDelta
  pbt?: MetricDelta
  pat?: MetricDelta
  filing_url?: string
}

export interface MetricDelta {
  current?: number
  qoq_prev?: number
  qoq_pct?: number
  yoy_prev?: number
  yoy_pct?: number
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

// ── Research ──────────────────────────────────────────────────────────────────

export interface ResearchCard {
  card_type: 'snapshot' | 'trajectory' | 'guidance' | 'promised_vs_delivered' | 'bull_bear'
  ticker: string
  company_name: string
  generated_at: string
  data: { content: string }
}

export interface ResearchResponse {
  status: string
  ticker: string
  company_name: string
  generated_at: string
  cards: ResearchCard[]
  sources_used: string[]
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
    fetchJSON<{ ticker: string; history: Array<{date:string;close:number;volume:number}> }>(
      `/push/prices/${ticker}/history`
    ),

  getAlerts: (params?: { volume_multiple?: number; price_move_pct?: number }) =>
    fetchJSON<AlertsResponse>(
      `/push/alerts?${new URLSearchParams(params as Record<string, string> || {})}`
    ),

  // Research
  getResearch: (ticker: string, force = false) =>
    fetchJSON<ResearchResponse>(`/pull/research/${ticker}${force ? '?force_refresh=true' : ''}`),

  // Chat
  chat: (messages: Array<{role: string; content: string}>, ticker?: string) =>
    fetchJSON<{response: string; generated_at: string}>('/chat', {
      method: 'POST',
      body: JSON.stringify({ messages, ticker }),
    }),
}
