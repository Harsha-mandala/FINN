import { NavLink } from 'react-router-dom'
import { Bell, TrendingUp, MessageSquare, Search } from 'lucide-react'

const NAV_ITEMS = [
  { to: '/feed', icon: Bell, label: 'Feed' },
  { to: '/alerts', icon: TrendingUp, label: 'Alerts' },
  { to: '/research', icon: Search, label: 'Research' },
  { to: '/chat', icon: MessageSquare, label: 'FINN' },
]

export default function BottomNav() {
  return (
    <nav className="bottom-nav">
      {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            `flex flex-col items-center gap-1 px-4 py-2 rounded-xl transition-colors ${
              isActive
                ? 'text-accent'
                : 'text-muted hover:text-subtle'
            }`
          }
        >
          {({ isActive }) => (
            <>
              <Icon size={22} strokeWidth={isActive ? 2.5 : 1.8} />
              <span className="text-[10px] font-medium tracking-wide">{label}</span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
