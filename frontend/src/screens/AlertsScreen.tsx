import React, { useState, useEffect, useRef, useCallback } from 'react';
import { TrendingUp, BarChart2, Bell, RefreshCw, CheckSquare, Square } from 'lucide-react';
import { api } from '@/lib/api';

// ─── Types ────────────────────────────────────────────────────────────────────

type AlertType = 'price' | 'volume' | 'announcement';

interface Alert {
  id: string;
  type: AlertType;
  ticker: string;
  description: string;
  timestamp: string;
}

interface Thresholds {
  price_move_pct: number;
  volume_multiple: number;
  categories: string[];
}

// ─── Constants ────────────────────────────────────────────────────────────────

const ALL_CATEGORIES = [
  { key: 'results', label: 'Results' },
  { key: 'M&A', label: 'M&A' },
  { key: 'management_change', label: 'Mgmt Change' },
  { key: 'litigation', label: 'Litigation' },
  { key: 'fund_raise', label: 'Fund Raise' },
  { key: 'credit_rating', label: 'Credit Rating' },
  { key: 'capex', label: 'Capex' },
];

const DEFAULT_THRESHOLDS: Thresholds = {
  price_move_pct: 5,
  volume_multiple: 2,
  categories: ALL_CATEGORIES.map((c) => c.key),
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

// ─── Alert Card ───────────────────────────────────────────────────────────────

const ALERT_META: Record<
  AlertType,
  { icon: React.ReactNode; border: string; iconColor: string }
> = {
  price: {
    icon: <TrendingUp size={15} />,
    border: 'border-l-[#EF4444]',
    iconColor: 'text-[#EF4444]',
  },
  announcement: {
    icon: <Bell size={15} />,
    border: 'border-l-[#EF4444]',
    iconColor: 'text-[#EF4444]',
  },
  volume: {
    icon: <BarChart2 size={15} />,
    border: 'border-l-[#F97316]',
    iconColor: 'text-[#F97316]',
  },
};

const AlertCard: React.FC<{ alert: Alert }> = ({ alert }) => {
  const meta = ALERT_META[alert.type];
  return (
    <div
      className={`flex items-start gap-3 bg-[#1E293B] rounded-xl px-4 py-3 border-l-4 ${meta.border}`}
    >
      <span className={`mt-0.5 flex-shrink-0 ${meta.iconColor}`}>{meta.icon}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span className="text-xs font-bold tracking-wide text-white bg-[#263548] px-2 py-0.5 rounded">
            {alert.ticker}
          </span>
          <span className="text-[11px] text-[#64748B]">{relativeTime(alert.timestamp)}</span>
        </div>
        <p className="text-xs text-[#CBD5E1] leading-snug">{alert.description}</p>
      </div>
    </div>
  );
};

// ─── Number Input ─────────────────────────────────────────────────────────────

const NumericInput: React.FC<{
  value: number;
  min: number;
  max: number;
  step: number;
  suffix: string;
  onChange: (v: number) => void;
}> = ({ value, min, max, step, suffix, onChange }) => {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = parseFloat(e.target.value);
    if (!isNaN(v) && v >= min && v <= max) onChange(v);
  };

  return (
    <div className="flex items-center gap-2">
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={handleChange}
        className="flex-1 accent-[#3B82F6] h-1.5"
      />
      <div className="flex items-center gap-1 bg-[#263548] rounded-lg px-3 py-1.5 min-w-[64px] justify-center">
        <input
          type="number"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={handleChange}
          className="w-8 bg-transparent text-sm font-bold text-white text-center outline-none"
        />
        <span className="text-xs text-[#64748B]">{suffix}</span>
      </div>
    </div>
  );
};

// ─── Category Toggle ──────────────────────────────────────────────────────────

const CategoryToggle: React.FC<{
  categories: string[];
  onChange: (cats: string[]) => void;
}> = ({ categories, onChange }) => {
  const toggle = (key: string) => {
    if (categories.includes(key)) {
      onChange(categories.filter((c) => c !== key));
    } else {
      onChange([...categories, key]);
    }
  };

  return (
    <div className="flex flex-wrap gap-2">
      {ALL_CATEGORIES.map((cat) => {
        const active = categories.includes(cat.key);
        return (
          <button
            key={cat.key}
            onClick={() => toggle(cat.key)}
            className={`flex items-center gap-1 text-xs font-semibold px-3 py-1.5 rounded-full transition-colors ${
              active
                ? 'bg-[#3B82F6]/20 text-[#3B82F6] border border-[#3B82F6]/40'
                : 'bg-[#1E293B] text-[#64748B] border border-[#263548]'
            }`}
          >
            {active ? <CheckSquare size={11} /> : <Square size={11} />}
            {cat.label}
          </button>
        );
      })}
    </div>
  );
};

// ─── Skeleton ─────────────────────────────────────────────────────────────────

const SkeletonAlert: React.FC = () => (
  <div className="flex items-start gap-3 bg-[#1E293B] rounded-xl px-4 py-3 border-l-4 border-l-[#263548] animate-pulse">
    <div className="w-4 h-4 rounded bg-[#263548] mt-0.5 flex-shrink-0" />
    <div className="flex-1 space-y-2">
      <div className="flex gap-2">
        <div className="w-20 h-4 rounded bg-[#263548]" />
        <div className="w-12 h-4 rounded bg-[#263548]" />
      </div>
      <div className="h-3 rounded bg-[#263548] w-4/5" />
    </div>
  </div>
);

// ─── Main Screen ──────────────────────────────────────────────────────────────

const AlertsScreen: React.FC = () => {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [thresholds, setThresholds] = useState<Thresholds>(DEFAULT_THRESHOLDS);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchAlerts = useCallback(async (t: Thresholds) => {
    setLoading(true);
    try {
      const data = await api.getAlerts({
        volume_multiple: t.volume_multiple,
        price_move_pct: t.price_move_pct,
      });
      const mapped: Alert[] = (data.alerts ?? []).map((a, i) => ({
        id: `${a.ticker}-${i}-${a.alert_type}`,
        type: a.alert_type === 'volume_spike' ? 'volume' : a.alert_type === 'price_move' ? 'price' : 'announcement',
        ticker: a.ticker,
        description: a.description,
        timestamp: a.triggered_at,
      }));
      setAlerts(mapped);
    } catch {
      setAlerts([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Debounce threshold changes
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchAlerts(thresholds);
    }, 500);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [thresholds, fetchAlerts]);

  const updateThreshold = <K extends keyof Thresholds>(key: K, value: Thresholds[K]) => {
    setThresholds((prev) => ({ ...prev, [key]: value }));
  };

  const handleRefresh = () => fetchAlerts(thresholds);

  return (
    <div className="min-h-screen bg-[#0F172A] max-w-[430px] mx-auto flex flex-col">
      {/* Header */}
      <header className="sticky top-0 z-20 bg-[#0F172A]/95 backdrop-blur border-b border-[#1E293B] px-4 py-3 flex items-center justify-between">
        <div>
          <p className="text-[10px] font-semibold text-[#64748B] uppercase tracking-widest">
            Alerts
          </p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={loading}
          className="flex items-center gap-1.5 text-xs font-semibold text-[#3B82F6] hover:text-white transition-colors disabled:opacity-40"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </header>

      <div className="flex-1 overflow-y-auto pb-8">
        {/* Active Alerts */}
        <div className="px-4 pt-4 space-y-3">
          <p className="text-[10px] font-semibold text-[#64748B] uppercase tracking-widest">
            Active Alerts
          </p>

          {loading ? (
            Array.from({ length: 3 }).map((_, i) => <SkeletonAlert key={i} />)
          ) : alerts.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 text-center gap-2 rounded-xl bg-[#1E293B]">
              <Bell size={28} className="text-[#263548]" />
              <p className="text-sm text-[#64748B]">No alerts — all clear</p>
            </div>
          ) : (
            alerts.map((alert) => <AlertCard key={alert.id} alert={alert} />)
          )}
        </div>

        {/* Threshold Settings */}
        <div className="px-4 mt-6">
          <div className="rounded-xl bg-[#1E293B] overflow-hidden">
            <div className="px-4 py-3 border-b border-[#263548]">
              <p className="text-[10px] font-semibold text-[#64748B] uppercase tracking-widest">
                Your Thresholds
              </p>
            </div>

            <div className="px-4 py-4 space-y-5">
              {/* Price move */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-[#CBD5E1]">
                    Price Move Alert
                  </label>
                </div>
                <NumericInput
                  value={thresholds.price_move_pct}
                  min={1}
                  max={25}
                  step={0.5}
                  suffix="%"
                  onChange={(v) => updateThreshold('price_move_pct', v)}
                />
                <p className="text-[11px] text-[#475569]">
                  Alert when a stock moves ±{thresholds.price_move_pct}% in the window.
                </p>
              </div>

              <div className="border-t border-[#263548]" />

              {/* Volume multiple */}
              <div className="space-y-2">
                <label className="text-xs font-semibold text-[#CBD5E1] block">
                  Volume Multiple Alert
                </label>
                <NumericInput
                  value={thresholds.volume_multiple}
                  min={1}
                  max={10}
                  step={0.5}
                  suffix="x"
                  onChange={(v) => updateThreshold('volume_multiple', v)}
                />
                <p className="text-[11px] text-[#475569]">
                  Alert when volume exceeds {thresholds.volume_multiple}× the 30-day average.
                </p>
              </div>

              <div className="border-t border-[#263548]" />

              {/* Category watchlist */}
              <div className="space-y-3">
                <label className="text-xs font-semibold text-[#CBD5E1] block">
                  Category Watchlist
                </label>
                <CategoryToggle
                  categories={thresholds.categories}
                  onChange={(cats) => updateThreshold('categories', cats)}
                />
                <p className="text-[11px] text-[#475569]">
                  Receive alerts only for selected announcement categories.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AlertsScreen;
