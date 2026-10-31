import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronDown, ChevronRight, MessageCircle } from 'lucide-react';
import { api } from '@/lib/api';

// ─── Types ───────────────────────────────────────────────────────────────────

type WindowHours = 24 | 168;

interface PriceTick {
  ticker: string;
  price: number;
  change_pct: number;
  volume_ratio: number;
}

interface ResultsEnrichment {
  type: 'results_card';
  qoq: { label: string; value: string; delta?: string }[];
  yoy: { label: string; value: string; delta?: string }[];
}

interface BioEnrichment {
  type: 'management_bio';
  bio: string;
}

type Enrichment = ResultsEnrichment | BioEnrichment | null;

interface Announcement {
  id: string;
  ticker: string;
  category: string;
  headline: string;
  priority: 'high' | 'medium' | 'low';
  timestamp: string;
  enrichment?: Enrichment;
}

interface DigestData {
  high: Announcement[];
  medium: Announcement[];
  low: Announcement[];
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function fmt(n: number, decimals = 2): string {
  return n.toFixed(decimals);
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

const PriorityDot: React.FC<{ priority: Announcement['priority'] }> = ({ priority }) => {
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

// ─── Results Table ────────────────────────────────────────────────────────────

const ResultsTable: React.FC<{ enrichment: ResultsEnrichment }> = ({ enrichment }) => (
  <div className="mt-3 rounded-lg overflow-hidden border border-[#263548] text-xs">
    <table className="w-full">
      <thead>
        <tr className="bg-[#263548] text-[#94A3B8]">
          <th className="text-left px-3 py-1.5 font-medium">Metric</th>
          <th className="text-right px-3 py-1.5 font-medium">QoQ</th>
          <th className="text-right px-3 py-1.5 font-medium">YoY</th>
        </tr>
      </thead>
      <tbody>
        {enrichment.qoq.map((row, i) => {
          const yoyRow = enrichment.yoy[i];
          return (
            <tr key={row.label} className="border-t border-[#263548]">
              <td className="px-3 py-1.5 text-[#CBD5E1]">{row.label}</td>
              <td className="px-3 py-1.5 text-right">
                <span className="text-white">{row.value}</span>
                {row.delta && (
                  <span
                    className={`ml-1 ${
                      row.delta.startsWith('+') ? 'text-[#22C55E]' : 'text-[#EF4444]'
                    }`}
                  >
                    {row.delta}
                  </span>
                )}
              </td>
              <td className="px-3 py-1.5 text-right">
                {yoyRow && (
                  <>
                    <span className="text-white">{yoyRow.value}</span>
                    {yoyRow.delta && (
                      <span
                        className={`ml-1 ${
                          yoyRow.delta.startsWith('+') ? 'text-[#22C55E]' : 'text-[#EF4444]'
                        }`}
                      >
                        {yoyRow.delta}
                      </span>
                    )}
                  </>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  </div>
);

// ─── Announcement Card ────────────────────────────────────────────────────────

const AnnouncementCard: React.FC<{
  item: Announcement;
  onAskFinn: (item: Announcement) => void;
}> = ({ item, onAskFinn }) => {
  const hasEnrichment = !!item.enrichment;

  return (
    <div className="rounded-xl bg-[#1E293B] p-4 space-y-2">
      {/* Header row */}
      <div className="flex flex-wrap items-center gap-2">
        <PriorityDot priority={item.priority} />
        <span className="text-xs font-bold tracking-wider text-white bg-[#263548] px-2 py-0.5 rounded">
          {item.ticker}
        </span>
        <span className="text-[10px] font-semibold text-[#3B82F6] bg-[#3B82F6]/10 px-2 py-0.5 rounded-full uppercase tracking-wide">
          {item.category.replace(/_/g, ' ')}
        </span>
        <span className="ml-auto text-[11px] text-[#64748B]">
          {relativeTime(item.timestamp)}
        </span>
      </div>

      {/* Headline */}
      <p className="text-sm text-[#E2E8F0] leading-snug line-clamp-2">{item.headline}</p>

      {/* Enrichment */}
      {item.enrichment?.type === 'results_card' && (
        <ResultsTable enrichment={item.enrichment} />
      )}
      {item.enrichment?.type === 'management_bio' && (
        <p className="text-xs text-[#94A3B8] leading-relaxed border-l-2 border-[#3B82F6] pl-2 mt-2">
          {item.enrichment.bio}
        </p>
      )}

      {/* Ask FINN */}
      {hasEnrichment && (
        <button
          onClick={() => onAskFinn(item)}
          className="mt-1 flex items-center gap-1.5 text-xs font-semibold text-[#3B82F6] hover:text-white transition-colors"
        >
          <MessageCircle size={13} />
          Ask FINN
        </button>
      )}
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
        className="w-full flex items-center justify-between py-2 px-1"
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
  const [window, setWindow] = useState<WindowHours>(24);
  const [prices, setPrices] = useState<PriceTick[]>([]);
  const [digest, setDigest] = useState<DigestData | null>(null);
  const [loadingPrices, setLoadingPrices] = useState(true);
  const [loadingDigest, setLoadingDigest] = useState(true);

function mapApiAnnouncement(raw: any, idx: number): Announcement {
  let enrichment: Enrichment = null;
  if (raw.enrichment?.type === 'management_bio') {
    enrichment = {
      type: 'management_bio',
      bio: raw.enrichment.bio || '',
    };
  } else if (raw.enrichment?.type === 'results_card') {
    const d = raw.enrichment.data || {};
    const metrics = [
      { key: 'revenue', label: 'Revenue' },
      { key: 'ebitda', label: 'EBITDA' },
      { key: 'pbt', label: 'PBT' },
      { key: 'pat', label: 'PAT' },
    ];
    enrichment = {
      type: 'results_card',
      qoq: metrics.map((m) => {
        const item = d[m.key];
        const val = item?.current != null ? `₹${item.current} Cr` : '-';
        const pct = item?.qoq_pct != null ? `${item.qoq_pct >= 0 ? '+' : ''}${item.qoq_pct}%` : undefined;
        return { label: m.label, value: val, delta: pct };
      }),
      yoy: metrics.map((m) => {
        const item = d[m.key];
        const val = item?.current != null ? `₹${item.current} Cr` : '-';
        const pct = item?.yoy_pct != null ? `${item.yoy_pct >= 0 ? '+' : ''}${item.yoy_pct}%` : undefined;
        return { label: m.label, value: val, delta: pct };
      }),
    };
  }

  return {
    id: `${raw.ticker}-${raw.date || idx}-${idx}`,
    ticker: (raw.ticker || '').replace('.NS', '').replace('.BO', ''),
    category: (raw.category || 'unclassified').toUpperCase(),
    headline: raw.summary || raw.headline || '',
    priority: raw.priority_tier || 'low',
    timestamp: raw.date || new Date().toISOString(),
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

  const fetchDigest = useCallback(async (windowHours: WindowHours) => {
    setLoadingDigest(true);
    try {
      const data = await api.getDigest(windowHours);
      setDigest({
        high: (data.high ?? []).map(mapApiAnnouncement),
        medium: (data.medium ?? []).map(mapApiAnnouncement),
        low: (data.low ?? []).map(mapApiAnnouncement),
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
    fetchDigest(window);
  }, [window, fetchDigest]);

  const handleAskFinn = (item: Announcement) => {
    navigate(`/chat?ticker=${item.ticker}&context=${encodeURIComponent(item.headline)}`);
  };

  const totalItems =
    (digest?.high.length ?? 0) +
    (digest?.medium.length ?? 0) +
    (digest?.low.length ?? 0);

  return (
    <div className="min-h-screen bg-[#0F172A] max-w-[430px] mx-auto flex flex-col">
      {/* Top bar */}
      <header className="sticky top-0 z-20 bg-[#0F172A]/95 backdrop-blur border-b border-[#1E293B] px-4 py-3 flex items-center justify-between">
        <span className="text-lg font-black tracking-tight text-white">
          FINN
        </span>
        <div className="flex bg-[#1E293B] rounded-lg p-0.5 gap-0.5">
          {([24, 168] as WindowHours[]).map((h) => (
            <button
              key={h}
              onClick={() => setWindow(h)}
              className={`text-xs font-semibold px-3 py-1 rounded-md transition-colors ${
                window === h
                  ? 'bg-[#3B82F6] text-white'
                  : 'text-[#64748B] hover:text-white'
              }`}
            >
              {h === 24 ? '24h' : '7d'}
            </button>
          ))}
        </div>
      </header>

      <div className="flex-1 overflow-y-auto pb-6">
        {/* Price strip */}
        <div className="px-4 pt-4">
          <p className="text-[10px] font-semibold text-[#64748B] uppercase tracking-widest mb-2">
            Portfolio
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
              <span className="text-4xl">🌿</span>
              <p className="text-sm text-[#94A3B8]">
                Quiet day — no material events in the last {window === 24 ? '24h' : '7 days'}.
              </p>
            </div>
          ) : (
            <>
              {/* High priority — always visible */}
              {digest!.high.length > 0 && (
                <div className="space-y-3">
                  <p className="text-[10px] font-semibold text-[#64748B] uppercase tracking-widest">
                    Needs Attention
                  </p>
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
                  label="Also Today"
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

              {/* Low priority */}
              {digest!.low.length > 0 && (
                <CollapsibleSection
                  label="Routine"
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
