import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Search,
  Building2,
  TrendingUp,
  TrendingDown,
  BarChart2,
  CheckSquare,
  AlertCircle,
  FileText,
  Loader2,
  ExternalLink,
  ShieldCheck,
  ChevronRight,
  Sparkles,
  Calendar,
  FileSpreadsheet,
} from 'lucide-react';
import {
  api,
  TickerOverviewResponse,
  ResearchResponse,
  ResearchCard as ApiResearchCard,
  ResultsCard as ApiResultsCard,
  PrimaryDocLink,
  RecentFiling,
} from '@/lib/api';

// ─── Constants ────────────────────────────────────────────────────────────────

const SHOWCASE_TICKERS = [
  'RELIANCE',
  'PERSISTENT',
  'HDFCBANK',
  'DMART',
  'BAJFINANCE',
  'TRENT',
  'INFY',
  'TCS',
];

const ALL_PORTFOLIO_TICKERS = [
  'RELIANCE', 'HDFCBANK', 'INFY', 'TCS', 'ICICIBANK',
  'SUNPHARMA', 'TRENT', 'POLYCAB', 'DIXON', 'HBLPOWER',
  'KALYANKJIL', 'CAMS', 'LALPATHLAB', 'ASTRAL', 'ZOMATO',
  'IRCTC', 'CDSL', 'IDEAFORGE', 'PERSISTENT', 'DMART',
  'BAJFINANCE', 'MOTHERSON',
];

const LABEL_MAP: Record<string, string> = {
  snapshot: 'Business & Financial Snapshot',
  trajectory: 'Multi-Year Trajectory',
  guidance: 'Management Guidance',
  promised_vs_delivered: 'Promised vs. Delivered',
  bull_bear: 'Bull vs. Bear Case',
};

const CARD_ICONS: Record<string, React.ReactNode> = {
  snapshot: <Building2 size={15} />,
  trajectory: <TrendingUp size={15} />,
  guidance: <BarChart2 size={15} />,
  promised_vs_delivered: <CheckSquare size={15} />,
  bull_bear: <AlertCircle size={15} />,
  default: <FileText size={15} />,
};

type VerdictType = 'Met' | 'Missed' | 'Partial' | 'Pending' | 'insufficient_data';

const VERDICT_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  Met: { bg: 'bg-[#22C55E]/15', text: 'text-[#22C55E]', label: 'Met' },
  met: { bg: 'bg-[#22C55E]/15', text: 'text-[#22C55E]', label: 'Met' },
  Missed: { bg: 'bg-[#EF4444]/15', text: 'text-[#EF4444]', label: 'Missed' },
  missed: { bg: 'bg-[#EF4444]/15', text: 'text-[#EF4444]', label: 'Missed' },
  Partial: { bg: 'bg-[#F59E0B]/15', text: 'text-[#F59E0B]', label: 'Partial' },
  partial: { bg: 'bg-[#F59E0B]/15', text: 'text-[#F59E0B]', label: 'Partial' },
  Pending: { bg: 'bg-[#64748B]/20', text: 'text-[#94A3B8]', label: 'Pending' },
  pending: { bg: 'bg-[#64748B]/20', text: 'text-[#94A3B8]', label: 'Pending' },
  insufficient_data: { bg: 'bg-[#475569]/20', text: 'text-[#64748B]', label: 'No Data' },
};

// ─── Sparkline Component ──────────────────────────────────────────────────────

function Sparkline({ data, height = 36, width = 130 }: { data: number[]; height?: number; width?: number }) {
  if (!data || data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const step = width / (data.length - 1);
  const points = data
    .map((val, idx) => {
      const x = idx * step;
      const y = height - ((val - min) / range) * (height - 6) - 3;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  const isPositive = data[data.length - 1] >= data[0];
  const strokeColor = isPositive ? '#22C55E' : '#EF4444';

  return (
    <svg width={width} height={height} className="overflow-visible">
      <polyline
        fill="none"
        stroke={strokeColor}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
      />
    </svg>
  );
}

// ─── Formatters ───────────────────────────────────────────────────────────────

function formatNumber(num?: number | null, unit: string = '₹ Cr'): string {
  if (num === null || num === undefined) return '—';
  if (Math.abs(num) >= 1000) {
    return `${num.toLocaleString('en-IN', { maximumFractionDigits: 1 })} ${unit}`;
  }
  return `${num.toLocaleString('en-IN', { maximumFractionDigits: 2 })} ${unit}`;
}

function formatDelta(delta?: number | null): React.ReactNode {
  if (delta === null || delta === undefined) return <span className="text-[#64748B]">—</span>;
  const isPos = delta > 0;
  const isNeg = delta < 0;
  return (
    <span
      className={`inline-flex items-center gap-0.5 text-xs font-semibold ${
        isPos ? 'text-[#22C55E]' : isNeg ? 'text-[#EF4444]' : 'text-[#94A3B8]'
      }`}
    >
      {isPos ? '+' : ''}
      {delta.toFixed(1)}%
    </span>
  );
}

function renderContent(text: string): React.ReactNode {
  return text.split('\n').map((line, i) => {
    const trimmed = line.trim();
    if (!trimmed) return <div key={i} className="h-1.5" />;

    if (/^\*\*(.+)\*\*$/.test(trimmed)) {
      return (
        <p key={i} className="text-xs font-bold text-white mt-2 mb-0.5 uppercase tracking-wide">
          {trimmed.replace(/\*\*/g, '')}
        </p>
      );
    }

    if (/^[-•]/.test(trimmed)) {
      const content = trimmed.replace(/^[-•]\s*/, '');
      const parts = content.split(/(\*\*[^*]+\*\*)/g);
      return (
        <div key={i} className="flex gap-2 text-xs text-[#CBD5E1] leading-relaxed my-0.5">
          <span className="text-[#38BDF8] mt-0.5 flex-shrink-0">•</span>
          <span>
            {parts.map((part, j) =>
              /^\*\*(.+)\*\*$/.test(part) ? (
                <strong key={j} className="text-white font-semibold">
                  {part.replace(/\*\*/g, '')}
                </strong>
              ) : (
                part
              )
            )}
          </span>
        </div>
      );
    }

    const parts = trimmed.split(/(\*\*[^*]+\*\*)/g);
    return (
      <p key={i} className="text-xs text-[#CBD5E1] leading-relaxed my-0.5">
        {parts.map((part, j) =>
          /^\*\*(.+)\*\*$/.test(part) ? (
            <strong key={j} className="text-white font-semibold">
              {part.replace(/\*\*/g, '')}
            </strong>
          ) : (
            part
          )
        )}
      </p>
    );
  });
}

// ─── Research Card Views ──────────────────────────────────────────────────────

const ResearchCardView: React.FC<{ card: ApiResearchCard }> = ({ card }) => {
  const cardType = card.card_type || 'default';
  const label = LABEL_MAP[cardType] || cardType.toUpperCase().replace(/_/g, ' ');
  const icon = CARD_ICONS[cardType] || CARD_ICONS['default'];
  const data = card.data || {};

  return (
    <div className="rounded-xl bg-[#1E293B] border border-[#263548] overflow-hidden shadow-sm">
      <div className="flex items-center gap-2.5 px-4 py-2.5 bg-[#0F172A]/70 border-b border-[#263548]">
        <span className="text-[#38BDF8]">{icon}</span>
        <span className="text-[11px] font-bold uppercase tracking-wider text-[#E2E8F0]">{label}</span>
      </div>

      <div className="p-4 space-y-3">
        {/* Promised vs Delivered */}
        {cardType === 'promised_vs_delivered' && data.commitments && (
          <div className="space-y-2">
            {data.commitments.map((c: any, idx: number) => {
              const vStyle = VERDICT_STYLES[c.verdict] || VERDICT_STYLES['Pending'];
              return (
                <div key={idx} className="p-3 rounded-lg bg-[#0F172A] border border-[#263548] space-y-1">
                  <div className="flex items-start gap-2.5">
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full flex-shrink-0 mt-0.5 ${vStyle.bg} ${vStyle.text}`}>
                      {vStyle.label}
                    </span>
                    <p className="text-xs text-[#E2E8F0] leading-snug">{c.statement || c.metric}</p>
                  </div>
                  {c.note && <p className="text-[11px] text-[#94A3B8] pl-14">{c.note}</p>}
                </div>
              );
            })}
          </div>
        )}

        {/* Snapshot */}
        {cardType === 'snapshot' && (
          <div className="space-y-3">
            {data.business_summary && (
              <p className="text-xs text-[#CBD5E1] leading-relaxed">{data.business_summary}</p>
            )}
            {data.segments && data.segments.length > 0 && (
              <div className="space-y-1.5 pt-1">
                <p className="text-[10px] font-bold text-[#64748B] uppercase tracking-wider">Revenue Breakdown</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {data.segments.map((seg: any, idx: number) => (
                    <div key={idx} className="p-2 rounded bg-[#0F172A] border border-[#263548] flex justify-between items-center text-xs">
                      <span className="text-[#CBD5E1] truncate pr-2">{seg.name}</span>
                      <span className="text-white font-semibold flex-shrink-0">{seg.revenue_share_pct}%</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {data.content && <div className="space-y-0.5">{renderContent(data.content)}</div>}
          </div>
        )}

        {/* Generic or Trajectory or Bull/Bear */}
        {cardType !== 'promised_vs_delivered' && cardType !== 'snapshot' && (
          <div className="space-y-1">
            {data.content ? (
              renderContent(data.content)
            ) : (
              <pre className="text-xs text-[#94A3B8] whitespace-pre-wrap font-sans">
                {JSON.stringify(data, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>

      {card.provenance && (
        <div className="px-4 py-2 border-t border-[#263548]/60 bg-[#0F172A]/40 flex flex-wrap items-center justify-between gap-2 text-[10px] text-[#64748B]">
          <span>Model: {card.provenance.model_used || 'Gemini'}</span>
          {card.provenance.generated_at && (
            <span>Updated: {new Date(card.provenance.generated_at).toLocaleDateString()}</span>
          )}
        </div>
      )}
    </div>
  );
};

// ─── Main Research Screen ─────────────────────────────────────────────────────

export default function ResearchScreen() {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlTicker = searchParams.get('ticker') || '';

  const [tickerInput, setTickerInput] = useState(urlTicker || 'RELIANCE');
  const [activeTicker, setActiveTicker] = useState(urlTicker || 'RELIANCE');
  const [overview, setOverview] = useState<TickerOverviewResponse | null>(null);
  const [researchData, setResearchData] = useState<ResearchResponse | null>(null);

  const [loadingOverview, setLoadingOverview] = useState(false);
  const [loadingResearch, setLoadingResearch] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  // Load ticker data whenever activeTicker changes
  useEffect(() => {
    if (!activeTicker) return;

    let isMounted = true;
    setLoadingOverview(true);
    setLoadingResearch(true);
    setGenerateError(null);

    // 1. Fetch Baseline Overview (instant cache)
    api
      .getOverview(activeTicker)
      .then((data) => {
        if (isMounted) {
          setOverview(data);
          setLoadingOverview(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          console.error('[OVERVIEW] Error fetching overview:', err);
          setLoadingOverview(false);
        }
      });

    // 2. Fetch Structured Research (if cached)
    api
      .getResearch(activeTicker)
      .then((res) => {
        if (isMounted) {
          if (res && res.cards && res.cards.length > 0) {
            setResearchData(res);
          } else {
            setResearchData(null);
          }
          setLoadingResearch(false);
        }
      })
      .catch(() => {
        if (isMounted) {
          setResearchData(null);
          setLoadingResearch(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [activeTicker]);

  // Handle ticker selection
  const selectTicker = (t: string) => {
    const clean = t.trim().toUpperCase().replace('.NS', '').replace('.BO', '');
    if (!clean) return;
    setActiveTicker(clean);
    setTickerInput(clean);
    setSearchParams({ ticker: clean });
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    selectTicker(tickerInput);
  };

  // On-demand generation
  const handleGenerateResearch = async () => {
    setIsGenerating(true);
    setGenerateError(null);
    try {
      const res = await api.generateResearch(activeTicker);
      if (res && res.cards && res.cards.length > 0) {
        setResearchData(res);
        // Refresh overview as well
        const ov = await api.getOverview(activeTicker);
        setOverview(ov);
      } else {
        setGenerateError('Research generation did not produce cards for this filing set.');
      }
    } catch (e: any) {
      if (e.message && e.message.includes('429')) {
        setGenerateError('Daily research generation limit reached (3 per day). Showing available baseline data.');
      } else {
        setGenerateError(e.message || 'Generation temporarily unavailable. Check backend logs.');
      }
    } finally {
      setIsGenerating(false);
    }
  };

  const latestRes = overview?.latest_results;
  const isBank = latestRes?.is_bank;
  const metrics = latestRes?.metrics || {};
  const priceVol = overview?.price_volume;
  const hasResearchCards = !!(researchData && researchData.cards && researchData.cards.length > 0);

  return (
    <div className="w-full flex flex-col space-y-6 px-4 py-4 md:px-6">
      {/* ── Top Bar & Ticker Selection ────────────────────────────────────────── */}
      <div className="space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
              <span>{activeTicker}</span>
              <span className="text-xs px-2 py-0.5 rounded bg-[#1E293B] text-[#38BDF8] font-medium border border-[#38BDF8]/20">
                NSE
              </span>
            </h1>
            <p className="text-xs text-[#64748B]">Audited Research & Regulatory Dossier</p>
          </div>

          {/* Search Form */}
          <form onSubmit={handleSearchSubmit} className="flex gap-2">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#64748B]" />
              <input
                type="text"
                value={tickerInput}
                onChange={(e) => setTickerInput(e.target.value)}
                placeholder="Search ticker..."
                className="w-44 sm:w-56 bg-[#1E293B] text-xs text-white placeholder-[#475569] pl-8 pr-3 py-2 rounded-lg border border-[#263548] focus:border-[#38BDF8] outline-none"
              />
            </div>
            <button
              type="submit"
              className="px-3 py-2 bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold rounded-lg transition-colors"
            >
              Go
            </button>
          </form>
        </div>

        {/* Showcase Ticker Chips */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
          <span className="text-[10px] uppercase font-bold text-[#64748B] flex-shrink-0 pr-1">Showcase:</span>
          {SHOWCASE_TICKERS.map((t) => (
            <button
              key={t}
              onClick={() => selectTicker(t)}
              className={`flex-shrink-0 text-xs font-semibold px-3 py-1 rounded-full transition-all ${
                activeTicker === t
                  ? 'bg-[#38BDF8] text-[#0F172A] shadow-md shadow-sky-500/20'
                  : 'bg-[#1E293B] text-[#94A3B8] hover:text-white hover:bg-[#263548]'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* ── LAYER 1: ANALYSIS LAYER (Deep Research Cards) ────────────────────── */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles size={16} className="text-[#38BDF8]" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-white">Deep Research Dossier</h2>
          </div>
          {hasResearchCards && (
            <span className="text-[10px] text-[#22C55E] bg-[#22C55E]/10 px-2 py-0.5 rounded-full font-medium">
              Verified Primary Synthesis
            </span>
          )}
        </div>

        {loadingResearch ? (
          <div className="p-8 rounded-xl bg-[#1E293B]/60 border border-[#263548] flex items-center justify-center gap-3 text-xs text-[#94A3B8]">
            <Loader2 size={16} className="animate-spin text-[#38BDF8]" />
            <span>Loading research brief...</span>
          </div>
        ) : hasResearchCards ? (
          <div className="space-y-4">
            {/* Provenance Badge */}
            <div className="p-3 rounded-lg bg-[#0F172A] border border-[#263548] flex items-center justify-between text-xs text-[#94A3B8]">
              <div className="flex items-center gap-2">
                <ShieldCheck size={16} className="text-[#38BDF8]" />
                <span>Synthesized from concall transcripts & annual reports</span>
              </div>
              <span className="text-[10px] text-[#64748B]">
                {researchData?.generated_at ? `Updated ${new Date(researchData.generated_at).toLocaleDateString()}` : 'Live cache'}
              </span>
            </div>

            {/* Render 5 Structured Cards */}
            <div className="space-y-3">
              {researchData!.cards.map((card, idx) => (
                <ResearchCardView key={idx} card={card} />
              ))}
            </div>
          </div>
        ) : (
          /* Calm Empty State for Deep Research */
          <div className="p-5 rounded-xl bg-[#1E293B]/60 border border-[#263548] space-y-3 text-center">
            <div className="flex flex-col items-center gap-2">
              <FileSpreadsheet size={24} className="text-[#64748B]" />
              <h3 className="text-sm font-bold text-white">Deep Research Not Pre-Generated</h3>
              <p className="text-xs text-[#94A3B8] max-w-md mx-auto leading-relaxed">
                FINN generates 5-card comprehensive briefs strictly on-demand to preserve LLM quota.
                Official filing data and price history are available below.
              </p>
            </div>

            {generateError && (
              <div className="p-2.5 rounded-lg bg-[#EF4444]/15 border border-[#EF4444]/30 text-xs text-[#FCA5A5] max-w-md mx-auto">
                {generateError}
              </div>
            )}

            <div className="pt-1">
              <button
                onClick={handleGenerateResearch}
                disabled={isGenerating}
                className="inline-flex items-center gap-2 px-4 py-2 bg-[#2563EB] hover:bg-[#1D4ED8] disabled:opacity-50 text-white text-xs font-semibold rounded-lg transition-all shadow-md shadow-blue-500/20"
              >
                {isGenerating ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    <span>Analyzing audited filings... (Stage 1 & 2)</span>
                  </>
                ) : (
                  <>
                    <Sparkles size={14} />
                    <span>Generate Deep Research Brief</span>
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </section>

      {/* ── LAYER 2: BASELINE LAYER (Zero LLM Required, Instant Cache) ────────── */}
      <section className="space-y-4 pt-2">
        <div className="flex items-center justify-between border-t border-[#1E293B] pt-6">
          <div className="flex items-center gap-2">
            <Building2 size={16} className="text-[#38BDF8]" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-white">Baseline Filing & Market Data</h2>
          </div>
          <span className="text-[10px] text-[#64748B] flex items-center gap-1">
            <ShieldCheck size={12} className="text-[#22C55E]" /> 100% Deterministic Cache
          </span>
        </div>

        {loadingOverview ? (
          <div className="p-8 rounded-xl bg-[#1E293B]/40 border border-[#263548] flex items-center justify-center gap-3 text-xs text-[#94A3B8]">
            <Loader2 size={16} className="animate-spin text-[#38BDF8]" />
            <span>Reading verified filing caches...</span>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* 1. Latest Results Card */}
            <div className="rounded-xl bg-[#1E293B] border border-[#263548] p-4 space-y-3">
              <div className="flex items-center justify-between border-b border-[#263548] pb-2.5">
                <div>
                  <h3 className="text-xs font-bold text-white uppercase tracking-wider">Latest Results (from filing)</h3>
                  <p className="text-[10px] text-[#64748B]">
                    {latestRes?.period_current || 'Quarterly Filing'} • {latestRes?.basis || 'Consolidated'}
                  </p>
                </div>
                {latestRes?.filing_url && (
                  <a
                    href={latestRes.filing_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[11px] text-[#38BDF8] hover:underline flex items-center gap-1"
                  >
                    <span>Filing PDF</span>
                    <ExternalLink size={10} />
                  </a>
                )}
              </div>

              {latestRes ? (
                <div className="space-y-2">
                  <div className="grid grid-cols-3 text-[10px] font-bold text-[#64748B] uppercase tracking-wider pb-1 border-b border-[#263548]/50">
                    <span>Metric</span>
                    <span className="text-right">Current</span>
                    <span className="text-right">QoQ / YoY</span>
                  </div>

                  {/* Standard Corporate vs Bank rows */}
                  {!isBank ? (
                    <>
                      <div className="grid grid-cols-3 text-xs items-center py-1">
                        <span className="text-[#CBD5E1] font-medium">Revenue</span>
                        <span className="text-right text-white font-semibold">{formatNumber(metrics.revenue?.current)}</span>
                        <div className="text-right flex items-center justify-end gap-1.5">
                          {formatDelta(metrics.revenue?.qoq_pct)}
                          <span className="text-[#475569]">/</span>
                          {formatDelta(metrics.revenue?.yoy_pct)}
                        </div>
                      </div>

                      <div className="grid grid-cols-3 text-xs items-center py-1">
                        <span className="text-[#CBD5E1] font-medium">EBITDA</span>
                        <span className="text-right text-white font-semibold">{formatNumber(metrics.ebitda?.current)}</span>
                        <div className="text-right flex items-center justify-end gap-1.5">
                          {formatDelta(metrics.ebitda?.qoq_pct)}
                          <span className="text-[#475569]">/</span>
                          {formatDelta(metrics.ebitda?.yoy_pct)}
                        </div>
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="grid grid-cols-3 text-xs items-center py-1">
                        <span className="text-[#CBD5E1] font-medium">Total Income</span>
                        <span className="text-right text-white font-semibold">{formatNumber(metrics.total_income?.current)}</span>
                        <div className="text-right flex items-center justify-end gap-1.5">
                          {formatDelta(metrics.total_income?.qoq_pct)}
                          <span className="text-[#475569]">/</span>
                          {formatDelta(metrics.total_income?.yoy_pct)}
                        </div>
                      </div>

                      <div className="grid grid-cols-3 text-xs items-center py-1">
                        <span className="text-[#CBD5E1] font-medium">NII</span>
                        <span className="text-right text-white font-semibold">{formatNumber(metrics.nii?.current)}</span>
                        <div className="text-right flex items-center justify-end gap-1.5">
                          {formatDelta(metrics.nii?.qoq_pct)}
                          <span className="text-[#475569]">/</span>
                          {formatDelta(metrics.nii?.yoy_pct)}
                        </div>
                      </div>

                      <div className="grid grid-cols-3 text-xs items-center py-1 text-[#64748B]">
                        <span>EBITDA</span>
                        <span className="text-right italic">N/A (Bank)</span>
                        <span className="text-right">—</span>
                      </div>
                    </>
                  )}

                  <div className="grid grid-cols-3 text-xs items-center py-1">
                    <span className="text-[#CBD5E1] font-medium">PBT</span>
                    <span className="text-right text-white font-semibold">{formatNumber(metrics.pbt?.current)}</span>
                    <div className="text-right flex items-center justify-end gap-1.5">
                      {formatDelta(metrics.pbt?.qoq_pct)}
                      <span className="text-[#475569]">/</span>
                      {formatDelta(metrics.pbt?.yoy_pct)}
                    </div>
                  </div>

                  <div className="grid grid-cols-3 text-xs items-center py-1">
                    <span className="text-[#CBD5E1] font-medium">PAT</span>
                    <span className="text-right text-white font-semibold">{formatNumber(metrics.pat?.current)}</span>
                    <div className="text-right flex items-center justify-end gap-1.5">
                      {formatDelta(metrics.pat?.qoq_pct)}
                      <span className="text-[#475569]">/</span>
                      {formatDelta(metrics.pat?.yoy_pct)}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="py-6 text-center text-xs text-[#64748B]">
                  No structured results filing cached for {activeTicker}.
                </div>
              )}
            </div>

            {/* 2. Price & Volume Card */}
            <div className="rounded-xl bg-[#1E293B] border border-[#263548] p-4 space-y-3">
              <div className="flex items-center justify-between border-b border-[#263548] pb-2.5">
                <div>
                  <h3 className="text-xs font-bold text-white uppercase tracking-wider">Price & Volume (6 Months)</h3>
                  <p className="text-[10px] text-[#64748B]">
                    {priceVol?.latest_date ? `Latest close: ${priceVol.latest_date}` : 'Daily market data'}
                  </p>
                </div>
                {priceVol?.sparkline && (
                  <Sparkline data={priceVol.sparkline} />
                )}
              </div>

              {priceVol ? (
                <div className="grid grid-cols-2 gap-3 pt-1">
                  <div className="p-3 rounded-lg bg-[#0F172A] border border-[#263548] space-y-1">
                    <p className="text-[10px] text-[#64748B] uppercase font-bold">Last Close</p>
                    <p className="text-lg font-black text-white">
                      ₹{priceVol.latest_close?.toFixed(2)}
                    </p>
                    <div className="flex items-center gap-1">
                      {formatDelta(priceVol.price_change_pct)}
                      <span className="text-[10px] text-[#64748B]">1-day</span>
                    </div>
                  </div>

                  <div className="p-3 rounded-lg bg-[#0F172A] border border-[#263548] space-y-1">
                    <p className="text-[10px] text-[#64748B] uppercase font-bold">Volume vs 20D Avg</p>
                    <p className="text-lg font-black text-white">
                      {priceVol.volume_ratio ? `${priceVol.volume_ratio.toFixed(2)}x` : '—'}
                    </p>
                    <p className="text-[10px] text-[#64748B] truncate">
                      Vol: {priceVol.volume_latest?.toLocaleString('en-IN') || '—'}
                    </p>
                  </div>
                </div>
              ) : (
                <div className="py-6 text-center text-xs text-[#64748B]">
                  Price history not available in local cache.
                </div>
              )}
            </div>
          </div>
        )}

        {/* 3. Primary Documents & 4. Recent Filings */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Primary Documents */}
          <div className="rounded-xl bg-[#1E293B] border border-[#263548] p-4 space-y-3">
            <div className="flex items-center justify-between border-b border-[#263548] pb-2.5">
              <h3 className="text-xs font-bold text-white uppercase tracking-wider">Primary Documents</h3>
              <span className="text-[10px] text-[#64748B]">
                {overview?.primary_documents.length || 0} files found
              </span>
            </div>

            {overview?.primary_documents && overview.primary_documents.length > 0 ? (
              <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                {overview.primary_documents.map((doc, idx) => (
                  <a
                    key={idx}
                    href={doc.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-2.5 rounded-lg bg-[#0F172A] border border-[#263548] hover:border-[#38BDF8]/40 transition-colors flex items-start justify-between gap-2 group block"
                  >
                    <div className="space-y-0.5">
                      <p className="text-xs font-medium text-[#E2E8F0] group-hover:text-[#38BDF8] line-clamp-1">
                        {doc.title}
                      </p>
                      <div className="flex items-center gap-2 text-[10px] text-[#64748B]">
                        <span className="capitalize">{doc.type.replace(/_/g, ' ')}</span>
                        {doc.year && <span>• {doc.year}</span>}
                        {doc.date && <span>• {doc.date}</span>}
                      </div>
                    </div>
                    <ExternalLink size={12} className="text-[#64748B] group-hover:text-[#38BDF8] flex-shrink-0 mt-1" />
                  </a>
                ))}
              </div>
            ) : (
              <div className="py-6 text-center text-xs text-[#64748B]">
                No primary documents indexed in `cache/documents/{activeTicker}/`.
              </div>
            )}
          </div>

          {/* Recent Filings */}
          <div className="rounded-xl bg-[#1E293B] border border-[#263548] p-4 space-y-3">
            <div className="flex items-center justify-between border-b border-[#263548] pb-2.5">
              <h3 className="text-xs font-bold text-white uppercase tracking-wider">Recent Priority Filings</h3>
              <span className="text-[10px] text-[#64748B]">Last 5 threads</span>
            </div>

            {overview?.recent_filings && overview.recent_filings.length > 0 ? (
              <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                {overview.recent_filings.map((filing, idx) => (
                  <div
                    key={idx}
                    className="p-2.5 rounded-lg bg-[#0F172A] border border-[#263548] space-y-1"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-xs text-[#E2E8F0] line-clamp-2 leading-snug">
                        {filing.headline}
                      </p>
                      {filing.attachment_url && (
                        <a
                          href={filing.attachment_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[10px] text-[#38BDF8] hover:underline flex-shrink-0"
                        >
                          PDF
                        </a>
                      )}
                    </div>
                    <div className="flex items-center gap-2 text-[10px] text-[#64748B]">
                      <span className="uppercase text-[#38BDF8] bg-[#38BDF8]/10 px-1.5 py-0.2 rounded font-semibold">
                        {filing.category.replace(/_/g, ' ')}
                      </span>
                      <span>• {filing.date}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-6 text-center text-xs text-[#64748B]">
                No recent high/medium priority filings in current snapshot.
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
