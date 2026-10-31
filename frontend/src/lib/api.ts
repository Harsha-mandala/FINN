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
  summary?: string
  enrichment?: {
    type: 'management_bio' | 'results_card'
    bio?: string
    data?: ResultsCard
  }
}

export interface ResultsCard {
  period_current: string
  period_qoq?: string
  period_yoy?: string
  revenue: MetricDelta
  ebitda: MetricDelta
  pbt: MetricDelta
  pat: MetricDelta
}

export interface MetricDelta {
  current?: number
  qoq_prev?: number
  qoq_pct?: number
  yoy_prev?: number
  yoy_pct?: number
}

export interface DigestResponse {
  window_hours: number
  generated_at: string
  high: Announcement[]
  medium: Announcement[]
  low: Announcement[]
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
  getDigest: (window_hours = 24, include_low = false) =>
    fetchJSON<DigestResponse>(`/push/digest?window_hours=${window_hours}&include_low=${include_low}`),

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
