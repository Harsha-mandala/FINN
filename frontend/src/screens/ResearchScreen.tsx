import React, { useState, useRef } from 'react';
import {
  Search,
  Building2,
  TrendingUp,
  BarChart2,
  CheckSquare,
  AlertCircle,
  FileText,
  Loader2,
} from 'lucide-react';
import { api } from '@/lib/api';

// ─── Types ────────────────────────────────────────────────────────────────────

type VerdictType = 'Met' | 'Missed' | 'Partial' | 'Pending';

interface Commitment {
  statement: string;
  verdict: VerdictType;
  note?: string;
}

interface PromisedDeliveredData {
  commitments: Commitment[];
}

interface GenericCardData {
  content: string;
}

interface ResearchCard {
  id: string;
  type: string;
  label: string;
  data: GenericCardData | PromisedDeliveredData;
  sources?: string[];
}

// ─── Constants ────────────────────────────────────────────────────────────────

const QUICK_TICKERS = ['PERSISTENT', 'DMART', 'BAJFINANCE', 'MOTHERSON'];

const LABEL_MAP: Record<string, string> = {
  snapshot: 'Business & Financial Snapshot',
  trajectory: 'Multi-Year Trajectory',
  guidance: 'Management Guidance',
  promised_vs_delivered: 'Promised vs. Delivered',
  bull_bear: 'Bull vs. Bear Case',
};

const CARD_ICONS: Record<string, React.ReactNode> = {
  snapshot: <Building2 size={14} />,
  trajectory: <TrendingUp size={14} />,
  guidance: <BarChart2 size={14} />,
  promised_vs_delivered: <CheckSquare size={14} />,
  bull_bear: <AlertCircle size={14} />,
  default: <FileText size={14} />,
};

function mapApiResearchCard(c: any, sources?: string[]): ResearchCard {
  const cardType = c.card_type || 'default';
  return {
    id: `${c.ticker || 'tick'}-${cardType}`,
    type: cardType,
    label: LABEL_MAP[cardType] || cardType.toUpperCase().replace('_', ' '),
    data: { content: c.data?.content || '' },
    sources: sources,
  };
}

const VERDICT_STYLES: Record<VerdictType, { bg: string; text: string; label: string }> = {
  Met: { bg: 'bg-[#22C55E]/15', text: 'text-[#22C55E]', label: 'Met' },
  Missed: { bg: 'bg-[#EF4444]/15', text: 'text-[#EF4444]', label: 'Missed' },
  Partial: { bg: 'bg-[#F59E0B]/15', text: 'text-[#F59E0B]', label: 'Partial' },
  Pending: { bg: 'bg-[#64748B]/20', text: 'text-[#94A3B8]', label: 'Pending' },
};

// ─── Simple Markdown Renderer ─────────────────────────────────────────────────

function renderContent(text: string): React.ReactNode {
  return text.split('\n').map((line, i) => {
    const trimmed = line.trim();
    if (!trimmed) return <div key={i} className="h-2" />;

    // Bold header: **text**
    if (/^\*\*(.+)\*\*$/.test(trimmed)) {
      return (
        <p key={i} className="text-xs font-bold text-white mt-3 mb-1 uppercase tracking-wide">
          {trimmed.replace(/\*\*/g, '')}
        </p>
      );
    }

    // Bullet point: starts with - or •
    if (/^[-•]/.test(trimmed)) {
      const content = trimmed.replace(/^[-•]\s*/, '');
      // Inline bold inside bullet
      const parts = content.split(/(\*\*[^*]+\*\*)/g);
      return (
        <div key={i} className="flex gap-2 text-xs text-[#CBD5E1] leading-relaxed">
          <span className="text-[#3B82F6] mt-0.5 flex-shrink-0">•</span>
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

    // Regular line with possible inline bold
    const parts = trimmed.split(/(\*\*[^*]+\*\*)/g);
    return (
      <p key={i} className="text-xs text-[#CBD5E1] leading-relaxed">
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

// ─── Promised vs Delivered Card ───────────────────────────────────────────────

const PromisedDeliveredCard: React.FC<{ data: PromisedDeliveredData }> = ({ data }) => (
  <div className="space-y-2">
    {data.commitments.map((c, i) => {
      const style = VERDICT_STYLES[c.verdict] ?? VERDICT_STYLES['Pending'];
      return (
        <div
          key={i}
          className="rounded-lg border border-[#263548] bg-[#0F172A] p-3 space-y-1"
        >
          <div className="flex items-start gap-2">
            <span
              className={`flex-shrink-0 text-[10px] font-bold px-2 py-0.5 rounded-full mt-0.5 ${style.bg} ${style.text}`}
            >
              {style.label}
            </span>
            <p className="text-xs text-[#E2E8F0] leading-snug">{c.statement}</p>
          </div>
          {c.note && (
            <p className="text-[11px] text-[#64748B] pl-14 leading-snug">{c.note}</p>
          )}
        </div>
      );
    })}
  </div>
);

// ─── Research Card ────────────────────────────────────────────────────────────

const ResearchCardView: React.FC<{ card: ResearchCard }> = ({ card }) => {
  const isPromisedDelivered = card.type === 'promised_delivered';
  const icon = CARD_ICONS[card.type] ?? CARD_ICONS['default'];

  return (
    <div className="rounded-xl bg-[#1E293B] overflow-hidden">
      {/* Card header */}
      <div
        className={`flex items-center gap-2 px-4 py-2.5 ${
          isPromisedDelivered ? 'bg-[#3B82F6]/10 border-b border-[#3B82F6]/20' : 'border-b border-[#263548]'
        }`}
      >
        <span className={isPromisedDelivered ? 'text-[#3B82F6]' : 'text-[#64748B]'}>
          {icon}
        </span>
        <span
          className={`text-[10px] font-bold uppercase tracking-widest ${
            isPromisedDelivered ? 'text-[#3B82F6]' : 'text-[#94A3B8]'
          }`}
        >
          {card.label}
        </span>
      </div>

      {/* Card body */}
      <div className="px-4 py-3">
        {isPromisedDelivered && 'commitments' in card.data ? (
          <PromisedDeliveredCard data={card.data as PromisedDeliveredData} />
        ) : (
          <div className="space-y-0.5">
            {renderContent((card.data as GenericCardData).content)}
          </div>
        )}
      </div>

      {/* Sources footer */}
      {card.sources && card.sources.length > 0 && (
        <div className="px-4 py-2.5 border-t border-[#263548]">
          <p className="text-[10px] text-[#475569]">
            Based on:{' '}
            {card.sources.map((s, i) => (
              <React.Fragment key={s}>
                <span className="text-[#64748B]">{s}</span>
                {i < card.sources!.length - 1 && ', '}
              </React.Fragment>
            ))}
          </p>
        </div>
      )}
    </div>
  );
};

// ─── Skeleton ─────────────────────────────────────────────────────────────────

const SkeletonCard: React.FC = () => (
  <div className="rounded-xl bg-[#1E293B] overflow-hidden animate-pulse">
    <div className="px-4 py-2.5 border-b border-[#263548] flex items-center gap-2">
      <div className="w-3 h-3 rounded bg-[#263548]" />
      <div className="h-3 w-40 rounded bg-[#263548]" />
    </div>
    <div className="px-4 py-3 space-y-2">
      <div className="h-3 rounded bg-[#263548] w-full" />
      <div className="h-3 rounded bg-[#263548] w-5/6" />
      <div className="h-3 rounded bg-[#263548] w-4/6" />
      <div className="h-3 rounded bg-[#263548] w-full mt-3" />
      <div className="h-3 rounded bg-[#263548] w-3/4" />
    </div>
  </div>
);

// ─── Main Screen ──────────────────────────────────────────────────────────────

const ResearchScreen: React.FC = () => {
  const [query, setQuery] = useState('');
  const [activeTicker, setActiveTicker] = useState<string | null>(null);
  const [cards, setCards] = useState<ResearchCard[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const runSearch = async (ticker: string) => {
    const t = ticker.trim().toUpperCase();
    if (!t) return;
    setActiveTicker(t);
    setQuery(t);
    setCards([]);
    setError(null);
    setLoading(true);
    try {
      const data = await api.getResearch(t);
      if (!data || !data.cards || data.cards.length === 0) {
        setError(t);
      } else {
        const mapped = data.cards.map((c) => mapApiResearchCard(c, data.sources_used));
        setCards(mapped);
      }
    } catch {
      setError(t);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    runSearch(query);
  };

  return (
    <div className="min-h-screen bg-[#0F172A] max-w-[430px] mx-auto flex flex-col">
      {/* Header */}
      <header className="sticky top-0 z-20 bg-[#0F172A]/95 backdrop-blur border-b border-[#1E293B] px-4 py-3">
        <p className="text-[10px] font-semibold text-[#64748B] uppercase tracking-widest mb-2">
          Research
        </p>

        {/* Search bar */}
        <form onSubmit={handleSubmit} className="flex gap-2">
          <div className="relative flex-1">
            <Search
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-[#64748B]"
            />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Enter NSE ticker (e.g. RELIANCE)"
              className="w-full bg-[#1E293B] text-sm text-white placeholder-[#475569] pl-8 pr-3 py-2.5 rounded-lg outline-none border border-transparent focus:border-[#3B82F6] transition-colors"
            />
          </div>
          <button
            type="submit"
            disabled={!query.trim()}
            className="px-4 py-2.5 bg-[#3B82F6] text-white text-sm font-semibold rounded-lg disabled:opacity-40 transition-opacity hover:bg-[#2563EB]"
          >
            Go
          </button>
        </form>

        {/* Quick-tap chips */}
        <div className="flex gap-2 mt-2 overflow-x-auto pb-0.5 scrollbar-none">
          {QUICK_TICKERS.map((t) => (
            <button
              key={t}
              onClick={() => runSearch(t)}
              className={`flex-shrink-0 text-xs font-semibold px-3 py-1 rounded-full transition-colors ${
                activeTicker === t
                  ? 'bg-[#3B82F6] text-white'
                  : 'bg-[#1E293B] text-[#94A3B8] hover:text-white'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {/* Loading state */}
        {loading && (
          <>
            <div className="flex items-center gap-2 py-2">
              <Loader2 size={14} className="text-[#3B82F6] animate-spin" />
              <span className="text-sm text-[#94A3B8]">
                Researching{' '}
                <span className="text-white font-semibold">{activeTicker}</span>
                <span className="inline-flex ml-1 gap-0.5">
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className="inline-block w-1 h-1 rounded-full bg-[#3B82F6] animate-pulse"
                      style={{ animationDelay: `${i * 200}ms` }}
                    />
                  ))}
                </span>
              </span>
            </div>
            {Array.from({ length: 3 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </>
        )}

        {/* Un-generated / Not available state */}
        {!loading && error && (
          <div className="flex flex-col items-center justify-center py-16 text-center gap-3">
            <div className="w-10 h-10 rounded-full bg-[#1E293B] flex items-center justify-center text-[#64748B]">
              <FileText size={20} />
            </div>
            <p className="text-sm text-[#94A3B8]">
              Research for <span className="text-white font-semibold">{error}</span> hasn't been generated yet.
            </p>
            <p className="text-xs text-[#475569] max-w-[280px]">
              FINN builds research exclusively from verified audited filings and concall transcripts.
            </p>
          </div>
        )}

        {/* Empty state (before any search) */}
        {!loading && !error && !activeTicker && (
          <div className="flex flex-col items-center justify-center py-16 text-center gap-2">
            <TrendingUp size={32} className="text-[#263548]" />
            <p className="text-sm text-[#475569]">
              Search for any NSE ticker to get a deep-dive research brief.
            </p>
          </div>
        )}

        {/* Research cards */}
        {!loading && cards.length > 0 && (
          <>
            {activeTicker && (
              <div className="flex items-center gap-2 pb-1">
                <span className="text-sm font-bold text-white">{activeTicker}</span>
                <span className="text-xs text-[#64748B]">Research Brief</span>
              </div>
            )}
            {cards.map((card) => (
              <ResearchCardView key={card.id} card={card} />
            ))}
          </>
        )}
      </div>
    </div>
  );
};

export default ResearchScreen;
