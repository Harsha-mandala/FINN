import { NavLink } from 'react-router-dom'
import { Bell, TrendingUp, Search, ShieldCheck } from 'lucide-react'

const NAV_ITEMS = [
  { to: '/feed', icon: Bell, label: 'Feed' },
  { to: '/alerts', icon: TrendingUp, label: 'Alerts' },
  { to: '/research', icon: Search, label: 'Research' },
]

export default function BottomNav() {
  return (
    <>
      {/* Desktop Side Rail (>= 1024px) */}
      <aside className="hidden lg:flex fixed left-0 top-0 bottom-0 w-64 border-r border-[#1E293B] bg-[#0B1120] flex-col justify-between p-6 z-30">
        <div className="space-y-8">
          {/* Logo & Brand */}
          <div className="flex items-center gap-3 px-2">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-[#2563EB] to-[#60A5FA] flex items-center justify-center shadow-lg shadow-blue-500/20">
              <span className="text-white font-extrabold text-lg tracking-wider">F</span>
            </div>
            <div>
              <h1 className="text-base font-bold text-white tracking-tight">FINN</h1>
              <p className="text-[11px] text-[#64748B]">First-principles intelligence</p>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="flex flex-col gap-1.5">
            {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `flex items-center gap-3.5 px-4 py-3 rounded-xl font-medium text-sm transition-all ${
                    isActive
                      ? 'bg-[#3B82F6]/15 text-[#60A5FA] font-semibold border border-[#3B82F6]/30 shadow-sm'
                      : 'text-[#94A3B8] hover:text-white hover:bg-[#1E293B]/60'
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <Icon size={20} strokeWidth={isActive ? 2.4 : 1.8} className={isActive ? 'text-[#60A5FA]' : 'text-[#64748B]'} />
                    <span>{label}</span>
                  </>
                )}
              </NavLink>
            ))}
          </nav>
        </div>

        {/* Footer info in side rail */}
        <div className="px-2 pt-4 border-t border-[#1E293B]/60 text-[11px] text-[#64748B] space-y-2">
          <div className="flex items-center gap-1.5 text-[#38BDF8]">
            <ShieldCheck size={14} />
            <span className="font-medium">Audited & Primary Data</span>
          </div>
          <p className="leading-relaxed">Zero hallucinated figures. Built strictly from audited filings & exchanges.</p>
        </div>
      </aside>

      {/* Mobile Bottom Navigation (< 1024px) */}
      <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-30 bg-[#0F172A]/95 backdrop-blur-md border-t border-[#1E293B] px-6 py-2 flex items-center justify-around shadow-2xl">
        {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex flex-col items-center gap-1 px-4 py-1.5 rounded-xl transition-colors ${
                isActive
                  ? 'text-[#38BDF8] font-semibold'
                  : 'text-[#64748B] hover:text-[#94A3B8]'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <Icon size={20} strokeWidth={isActive ? 2.5 : 1.8} />
                <span className="text-[10px] font-medium tracking-wide">{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </>
  )
}
