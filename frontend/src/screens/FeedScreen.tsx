import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ChevronDown,
  ChevronRight,
  MessageCircle,
  ExternalLink,
  Layers,
  FileCheck,
  Calendar,
} from 'lucide-react';
import { api, ResultsCard } from '@/lib/api';

// ─── Types ───────────────────────────────────────────────────────────────────

type WindowOption = '24h' | '7d' | '30d' | 'custom';

interface PriceTick {
  ticker: string;
  price: number;
  change_pct: number;
  volume_ratio: number;
}

interface ResultsMetricRow {
  label: string;
  current: string;
  qoq_pct?: number | null;
  yoy_pct?: number | null;
}

interface ResultsEnrichmentView {
  type: 'results_card';
  basis: string;
  period: string;
  provenance?: string;
  filingUrl?: string;
  rows: ResultsMetricRow[];
}

interface BioEnrichmentView {
  type: 'management_bio';
  personName?: string;
  role?: string;
  bio: string;
  sources?: string[];
}

type EnrichmentView = ResultsEnrichmentView | BioEnrichmentView | null;

interface SubItem {
  headline: string;
  date: string;
  attachment_url?: string;
  news_id?: string;
  category?: string;
}

interface AnnouncementView {
  id: string;
  ticker: string;
  category: string;
  headline: string;
  priority: 'high' | 'medium' | 'low';
  timestamp: string;
  attachmentUrl?: string;
  threadCount?: number;
  subItems?: SubItem[];
  enrichment?: EnrichmentView;
}

interface DigestData {
  high: AnnouncementView[];
  medium: AnnouncementView[];
  low: AnnouncementView[];
  dataAsOf?: string;
  routineSummary?: {
    count: number;
    label: string;
  };
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function relativeTime(iso: string): string {
  try {
    const diff = Date.now() - new Date(iso).getTime();
    if (isNaN(diff)) return iso;
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `${Math.max(1, mins)}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  } catch {
    return iso;
  }
}

function fmt(n: number, decimals = 2): string {
  return n.toFixed(decimals);
}

function formatAsOf(iso?: string): string {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleString('en-IN', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

// ─── Skeleton Components ──────────────────────────────────────────────────────

const SkeletonChip: React.FC = () => (
  <div className="flex-shrink-0 w-28 h-16 rounded-xl bg-[#1E293B] animate-pulse" />
);

const SkeletonCard: React.FC = () => (
  <div className="rounded-xl bg-[#1E293B] p-4 space-y-3 animate-pulse">
    <div className="flex gap-2 items-center">
      <div className="w-2 h-2 rounded-full bg-[#263548]" />
      <div className="w-20 h-5 rounded bg-[#263548]" />
      <div className="w-16 h-5 rounded bg-[#263548]" />
    </div>
    <div className="h-4 rounded bg-[#263548] w-full" />
    <div className="h-4 rounded bg-[#263548] w-4/5" />
    <div className="h-3 rounded bg-[#263548] w-16" />
  </div>
);

// ─── Price Strip ─────────────────────────────────────────────────────────────

const PriceChip: React.FC<{ tick: PriceTick }> = ({ tick }) => {
  const positive = tick.change_pct >= 0;
  return (
    <div className="flex-shrink-0 flex flex-col gap-1 px-3 py-2.5 rounded-xl bg-[#1E293B] min-w-[108px]">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-white tracking-wide">
          {tick.ticker}
        </span>
        {tick.volume_ratio >= 2 && (
          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-[#3B82F6]/20 text-[#3B82F6]">
            {fmt(tick.volume_ratio, 1)}x VOL
          </span>
        )}
      </div>
      <span className="text-sm font-bold text-white">
        ₹{tick.price.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
      </span>
      <span
        className={`text-xs font-semibold ${positive ? 'text-[#22C55E]' : 'text-[#EF4444]'}`}
      >
        {positive ? '+' : ''}
        {fmt(tick.change_pct)}%
      </span>
    </div>
  );
};

// ─── Priority Dot ─────────────────────────────────────────────────────────────

const PriorityDot: React.FC<{ priority: AnnouncementView['priority'] }> = ({ priority }) => {
  const colors: Record<string, string> = {
    high: 'bg-[#EF4444]',
    medium: 'bg-[#F59E0B]',
    low: 'bg-[#6B7280]',
  };
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full flex-shrink-0 mt-0.5 ${colors[priority]}`}
    />
  );
};

// ─── Results Table Component ──────────────────────────────────────────────────

const ResultsTable: React.FC<{ enrichment: ResultsEnrichmentView }> = ({ enrichment }) => (
  <div className="mt-3 rounded-lg overflow-hidden border border-[#263548] bg-[#0F172A]/80 text-xs">
    {/* Card sub-header with basis & period */}
    <div className="flex items-center justify-between px-3 py-2 bg-[#1A2438] border-b border-[#263548]">
      <div className="flex items-center gap-2">
        <FileCheck size={14} className="text-[#3B82F6]" />
        <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-[#3B82F6]/20 text-[#60A5FA]">
          {enrichment.basis}
        </span>
        <span className="text-xs font-medium text-[#E2E8F0]">
          {enrichment.period}
        </span>
      </div>
      {enrichment.filingUrl && (
        <a
          href={enrichment.filingUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[11px] text-[#3B82F6] hover:underline flex items-center gap-1"
        >
          Filing <ExternalLink size={10} />
        </a>
      )}
    </div>

    {/* Metrics Table */}
    <table className="w-full">
      <thead>
        <tr className="bg-[#1E293B] text-[#94A3B8]">
          <th className="text-left px-3 py-1.5 font-medium">Metric</th>
          <th className="text-right px-3 py-1.5 font-medium">Value (₹ Cr)</th>
          <th className="text-right px-3 py-1.5 font-medium">QoQ</th>
          <th className="text-right px-3 py-1.5 font-medium">YoY</th>
        </tr>
      </thead>
      <tbody>
        {enrichment.rows.map((row) => (
          <tr key={row.label} className="border-t border-[#263548]/80 hover:bg-[#1E293B]/40">
            <td className="px-3 py-1.5 text-[#CBD5E1] font-medium">{row.label}</td>
            <td className="px-3 py-1.5 text-right font-mono text-white">
              {row.current}
            </td>
            <td className="px-3 py-1.5 text-right font-mono">
              {row.qoq_pct != null ? (
                <span
                  className={row.qoq_pct >= 0 ? 'text-[#22C55E]' : 'text-[#EF4444]'}
                >
                  {row.qoq_pct >= 0 ? '+' : ''}
                  {row.qoq_pct}%
                </span>
              ) : (
                <span className="text-[#64748B]">—</span>
              )}
            </td>
            <td className="px-3 py-1.5 text-right font-mono">
              {row.yoy_pct != null ? (
                <span
                  className={row.yoy_pct >= 0 ? 'text-[#22C55E]' : 'text-[#EF4444]'}
                >
                  {row.yoy_pct >= 0 ? '+' : ''}
                  {row.yoy_pct}%
                </span>
              ) : (
                <span className="text-[#64748B]">—</span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>

    {/* Provenance Footer */}
    {enrichment.provenance && (
      <div className="px-3 py-1 bg-[#1A2438]/50 border-t border-[#263548] text-[10px] text-[#64748B] truncate">
        {enrichment.provenance}
      </div>
    )}
  </div>
);

// ─── Announcement Card ────────────────────────────────────────────────────────

const AnnouncementCard: React.FC<{
  item: AnnouncementView;
  onAskFinn: (item: AnnouncementView) => void;
}> = ({ item, onAskFinn }) => {
  const [threadOpen, setThreadOpen] = useState(false);
  const hasEnrichment = !!item.enrichment;
  const hasThread = !!(item.subItems && item.subItems.length > 0);

  return (
    <div className="rounded-xl bg-[#1E293B] p-4 space-y-2 border border-[#263548]/40 shadow-sm">
      {/* Header row */}
      <div className="flex flex-wrap items-center gap-2">
        <PriorityDot priority={item.priority} />
        <span className="text-xs font-bold tracking-wider text-white bg-[#263548] px-2 py-0.5 rounded">
          {item.ticker}
        </span>
        <span className="text-[10px] font-semibold text-[#3B82F6] bg-[#3B82F6]/10 px-2 py-0.5 rounded-full uppercase tracking-wide">
          {item.category.replace(/_/g, ' ')}
        </span>

        {hasThread && (
          <button
            onClick={() => setThreadOpen((p) => !p)}
            className="flex items-center gap-1 text-[10px] font-medium text-[#A78BFA] bg-[#8B5CF6]/15 hover:bg-[#8B5CF6]/25 px-2 py-0.5 rounded-full transition-colors"
          >
            <Layers size={10} />
            <span>Thread ({item.threadCount || item.subItems!.length + 1})</span>
            {threadOpen ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
          </button>
        )}

        <span className="ml-auto text-[11px] text-[#64748B]">
          {relativeTime(item.timestamp)}
        </span>
      </div>

      {/* Headline */}
      <p className="text-sm text-[#E2E8F0] leading-snug">{item.headline}</p>

      {/* Results Enrichment Card */}
      {item.enrichment?.type === 'results_card' && (
        <ResultsTable enrichment={item.enrichment} />
      )}

      {/* Management Bio Enrichment Card */}
      {item.enrichment?.type === 'management_bio' && (
        <div className="mt-2.5 p-3 rounded-lg bg-[#0F172A]/80 border-l-2 border-[#3B82F6] space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-white">
              {item.enrichment.personName || 'Management Appointment'}
            </span>
            {item.enrichment.role && (
              <span className="text-[10px] text-[#94A3B8] font-medium">
                {item.enrichment.role}
              </span>
            )}
          </div>
          <p className="text-xs text-[#CBD5E1] leading-relaxed">
            {item.enrichment.bio}
          </p>
        </div>
      )}

      {/* Collapsible Thread Sub-items */}
      {hasThread && threadOpen && (
        <div className="mt-2.5 pt-2 border-t border-[#263548] space-y-2">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-[#64748B]">
            Related Filings
          </p>
          {item.subItems!.map((sub, idx) => (
            <div
              key={idx}
              className="text-xs text-[#94A3B8] pl-2 border-l-2 border-[#3B82F6]/40 flex items-start justify-between gap-2"
            >
              <div className="space-y-0.5">
                <p className="text-[#CBD5E1] text-[11px] leading-tight">
                  {sub.headline}
                </p>
                <span className="text-[10px] text-[#64748B]">
                  {relativeTime(sub.date)}
                </span>
              </div>
              {sub.attachment_url && (
                <a
                  href={sub.attachment_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex-shrink-0 text-[10px] text-[#3B82F6] hover:underline"
                >
                  PDF
                </a>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Action footer */}
      <div className="flex items-center justify-between pt-1">
        {item.attachmentUrl ? (
          <a
            href={item.attachmentUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[11px] text-[#64748B] hover:text-[#94A3B8] flex items-center gap-1"
          >
            Original Filing <ExternalLink size={10} />
          </a>
        ) : <div />}

        <button
          onClick={() => onAskFinn(item)}
          className="flex items-center gap-1.5 text-xs font-semibold text-[#3B82F6] hover:text-white transition-colors py-0.5 px-2 rounded hover:bg-[#3B82F6]/10"
        >
          <MessageCircle size={13} />
          Ask FINN
        </button>
      </div>
    </div>
  );
};

// ─── Collapsible Section ──────────────────────────────────────────────────────

const CollapsibleSection: React.FC<{
  label: string;
  count: number;
  defaultOpen?: boolean;
  children: React.ReactNode;
}> = ({ label, count, defaultOpen = false, children }) => {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button
        onClick={() => setOpen((p) => !p)}
        className="w-full flex items-center justify-between py-2 px-1 hover:bg-[#1E293B]/30 rounded-lg transition-colors"
      >
        <span className="text-xs font-semibold text-[#94A3B8] uppercase tracking-widest">
          {label}{' '}
          <span className="text-[#64748B] font-normal normal-case tracking-normal">
            ({count})
          </span>
        </span>
        {open ? (
          <ChevronDown size={14} className="text-[#64748B]" />
        ) : (
          <ChevronRight size={14} className="text-[#64748B]" />
        )}
      </button>
      {open && <div className="space-y-3 mt-1">{children}</div>}
    </div>
  );
};

// ─── Main Screen ──────────────────────────────────────────────────────────────

const FeedScreen: React.FC = () => {
  const navigate = useNavigate();
  const [windowOpt, setWindowOpt] = useState<WindowOption>('24h');
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [prices, setPrices] = useState<PriceTick[]>([]);
  const [digest, setDigest] = useState<DigestData | null>(null);
  const [loadingPrices, setLoadingPrices] = useState(true);
  const [loadingDigest, setLoadingDigest] = useState(true);

  function mapApiAnnouncement(raw: any, idx: number): AnnouncementView {
    let enrichment: EnrichmentView = null;

    if (raw.enrichment?.type === 'management_bio') {
      enrichment = {
        type: 'management_bio',
        personName: raw.enrichment.person_name,
        role: raw.enrichment.role,
        bio: raw.enrichment.bio || '',
        sources: raw.enrichment.sources,
      };
    } else if (raw.enrichment?.type === 'results_card') {
      const cardData = (raw.enrichment.data || {}) as ResultsCard;
      const metricsObj = (cardData.metrics || cardData) as any;

      const metricDefs = [
        { key: 'revenue', label: 'Revenue' },
        { key: 'ebitda', label: 'EBITDA' },
        { key: 'pbt', label: 'PBT' },
        { key: 'pat', label: 'PAT' },
      ];

      const rows: ResultsMetricRow[] = metricDefs.map((m) => {
        const item = metricsObj[m.key] || {};
        const val =
          item.current != null
            ? `₹${Number(item.current).toLocaleString('en-IN')}`
            : '—';
        return {
          label: m.label,
          current: val,
          qoq_pct: item.qoq_pct,
          yoy_pct: item.yoy_pct,
        };
      });

      enrichment = {
        type: 'results_card',
        basis: (cardData.basis || 'consolidated').toUpperCase(),
        period: cardData.period_current || 'Quarterly Results',
        provenance: (cardData as any).provenance,
        filingUrl: (cardData as any).filing_url || raw.attachment_url,
        rows,
      };
    }

    return {
      id: `${raw.ticker}-${raw.date || idx}-${idx}`,
      ticker: (raw.ticker || '').replace('.NS', '').replace('.BO', ''),
      category: (raw.category || 'unclassified').toUpperCase(),
      headline: raw.summary || raw.headline || '',
      priority: raw.priority_tier || 'low',
      timestamp: raw.date || new Date().toISOString(),
      attachmentUrl: raw.attachment_url,
      threadCount: raw.thread_count,
      subItems: raw.sub_items,
      enrichment,
    };
  }

  const fetchPrices = useCallback(async () => {
    setLoadingPrices(true);
    try {
      const data = await api.getPrices();
      const ticks: PriceTick[] = Object.values(data.tickers ?? {})
        .filter((t) => !t.error && t.latest_close != null)
        .map((t) => ({
          ticker: t.ticker.replace('.NS', '').replace('.BO', ''),
          price: t.latest_close,
          change_pct: t.price_change_pct,
          volume_ratio: t.volume_ratio,
        }));
      setPrices(ticks);
    } catch {
      setPrices([]);
    } finally {
      setLoadingPrices(false);
    }
  }, []);

  const fetchDigest = useCallback(async (win: WindowOption, start?: string, end?: string) => {
    setLoadingDigest(true);
    try {
      let data;
      if (win === 'custom' && start && end) {
        data = await api.getDigest('custom', { start_date: start, end_date: end, include_low: false });
      } else {
        data = await api.getDigest(win, { include_low: false });
      }

      setDigest({
        high: (data.high ?? []).map(mapApiAnnouncement),
        medium: (data.medium ?? []).map(mapApiAnnouncement),
        low: (data.low ?? []).map(mapApiAnnouncement),
        dataAsOf: data.data_as_of,
        routineSummary: data.routine_summary,
      });
    } catch {
      setDigest({ high: [], medium: [], low: [] });
    } finally {
      setLoadingDigest(false);
    }
  }, []);

  useEffect(() => {
    fetchPrices();
  }, [fetchPrices]);

  useEffect(() => {
    if (windowOpt !== 'custom') {
      fetchDigest(windowOpt);
    }
  }, [windowOpt, fetchDigest]);

  const handleCustomApply = () => {
    if (startDate && endDate) {
      fetchDigest('custom', startDate, endDate);
    }
  };

  const handleAskFinn = (item: AnnouncementView) => {
    navigate(`/chat?ticker=${item.ticker}&context=${encodeURIComponent(item.headline)}`);
  };

  const totalItems =
    (digest?.high.length ?? 0) +
    (digest?.medium.length ?? 0) +
    (digest?.low.length ?? 0);

  return (
    <div className="min-h-screen bg-[#0F172A] max-w-[430px] mx-auto flex flex-col">
      {/* Top bar */}
      <header className="sticky top-0 z-20 bg-[#0F172A]/95 backdrop-blur border-b border-[#1E293B] px-4 py-3 space-y-2">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-lg font-black tracking-tight text-white">
              FINN
            </span>
            {digest?.dataAsOf && (
              <span className="ml-2 text-[10px] text-[#64748B]">
                as of {formatAsOf(digest.dataAsOf)}
              </span>
            )}
          </div>

          {/* Window Tabs: 24h | 7d | 30d | Custom */}
          <div className="flex bg-[#1E293B] rounded-lg p-0.5 gap-0.5">
            {(['24h', '7d', '30d', 'custom'] as WindowOption[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setWindowOpt(tab)}
                className={`text-[11px] font-semibold px-2.5 py-1 rounded-md transition-colors ${
                  windowOpt === tab
                    ? 'bg-[#3B82F6] text-white shadow-sm'
                    : 'text-[#64748B] hover:text-white'
                }`}
              >
                {tab === 'custom' ? 'Custom' : tab}
              </button>
            ))}
          </div>
        </div>

        {/* Custom Date Range Picker */}
        {windowOpt === 'custom' && (
          <div className="flex items-center gap-2 pt-1 pb-0.5 text-xs">
            <Calendar size={13} className="text-[#3B82F6] flex-shrink-0" />
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="bg-[#1E293B] text-white text-[11px] px-2 py-1 rounded border border-[#263548] focus:outline-none focus:border-[#3B82F6]"
            />
            <span className="text-[#64748B]">to</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="bg-[#1E293B] text-white text-[11px] px-2 py-1 rounded border border-[#263548] focus:outline-none focus:border-[#3B82F6]"
            />
            <button
              onClick={handleCustomApply}
              disabled={!startDate || !endDate}
              className="px-2.5 py-1 bg-[#3B82F6] hover:bg-[#2563EB] text-white rounded text-[11px] font-semibold disabled:opacity-40"
            >
              Apply
            </button>
          </div>
        )}
      </header>

      <div className="flex-1 overflow-y-auto pb-6">
        {/* Price strip */}
        <div className="px-4 pt-4">
          <p className="text-[10px] font-semibold text-[#64748B] uppercase tracking-widest mb-2">
            Watchlist
          </p>
          <div className="flex gap-2 overflow-x-auto pb-2 -mx-4 px-4 scrollbar-none">
            {loadingPrices
              ? Array.from({ length: 5 }).map((_, i) => <SkeletonChip key={i} />)
              : prices.map((tick) => <PriceChip key={tick.ticker} tick={tick} />)}
          </div>
        </div>

        {/* Digest body */}
        <div className="px-4 mt-5 space-y-5">
          {loadingDigest ? (
            <>
              <p className="text-[10px] font-semibold text-[#64748B] uppercase tracking-widest">
                Needs Attention
              </p>
              <div className="space-y-3">
                {Array.from({ length: 3 }).map((_, i) => (
                  <SkeletonCard key={i} />
                ))}
              </div>
            </>
          ) : totalItems === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center gap-3">
              <span className="text-3xl">🌿</span>
              <p className="text-sm text-[#94A3B8]">
                No filings found in the{' '}
                <span className="text-white font-medium">{windowOpt}</span> window.
              </p>
              <div className="flex gap-2 mt-1">
                <button
                  onClick={() => setWindowOpt('7d')}
                  className="px-3 py-1.5 text-xs font-semibold bg-[#1E293B] text-[#3B82F6] hover:bg-[#263548] rounded-lg transition-colors"
                >
                  View 7d
                </button>
                <button
                  onClick={() => setWindowOpt('30d')}
                  className="px-3 py-1.5 text-xs font-semibold bg-[#1E293B] text-[#3B82F6] hover:bg-[#263548] rounded-lg transition-colors"
                >
                  View 30d
                </button>
              </div>
            </div>
          ) : (
            <>
              {/* High priority — always visible */}
              {digest!.high.length > 0 && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="text-[10px] font-semibold text-[#64748B] uppercase tracking-widest">
                      Needs Attention ({digest!.high.length})
                    </p>
                  </div>
                  {digest!.high.map((item) => (
                    <AnnouncementCard
                      key={item.id}
                      item={item}
                      onAskFinn={handleAskFinn}
                    />
                  ))}
                </div>
              )}

              {/* Medium priority */}
              {digest!.medium.length > 0 && (
                <CollapsibleSection
                  label="Also Noteworthy"
                  count={digest!.medium.length}
                  defaultOpen
                >
                  {digest!.medium.map((item) => (
                    <AnnouncementCard
                      key={item.id}
                      item={item}
                      onAskFinn={handleAskFinn}
                    />
                  ))}
                </CollapsibleSection>
              )}

              {/* Routine summary row or low items */}
              {digest!.routineSummary && digest!.routineSummary.count > 0 && (
                <div className="p-3 rounded-lg bg-[#1E293B]/60 border border-[#263548] text-xs text-[#64748B] flex items-center justify-between">
                  <span>{digest!.routineSummary.label}</span>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-[#263548] text-[#94A3B8]">
                    Filtered
                  </span>
                </div>
              )}

              {/* Low priority (if included) */}
              {digest!.low.length > 0 && (
                <CollapsibleSection
                  label="Routine Filings"
                  count={digest!.low.length}
                  defaultOpen={false}
                >
                  {digest!.low.map((item) => (
                    <AnnouncementCard
                      key={item.id}
                      item={item}
                      onAskFinn={handleAskFinn}
                    />
                  ))}
                </CollapsibleSection>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default FeedScreen;