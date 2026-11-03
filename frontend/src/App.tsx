import { useEffect, useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import FeedScreen from './screens/FeedScreen'
import ResearchScreen from './screens/ResearchScreen'
import AlertsScreen from './screens/AlertsScreen'
import BottomNav from './components/BottomNav'
import { warmUpBackend, onColdStartChange } from './lib/api'
import { Loader2 } from 'lucide-react'

export default function App() {
  const [isWaking, setIsWaking] = useState(false)

  useEffect(() => {
    // Ping backend on launch (non-blocking)
    warmUpBackend()
    // Subscribe to cold-start indicator
    const unsubscribe = onColdStartChange((waking) => setIsWaking(waking))
    return () => unsubscribe()
  }, [])

  return (
    <div className="min-h-dvh bg-[#0B1120] text-[#E2E8F0] flex flex-col relative selection:bg-[#3B82F6]/30">
      {/* Cold Start Notice Banner (only shown if backend takes >1.5s on free-tier wake up) */}
      {isWaking && (
        <div className="fixed top-0 left-0 right-0 z-50 bg-[#1E293B]/95 border-b border-[#3B82F6]/30 px-4 py-2 flex items-center justify-center gap-2 text-xs text-[#94A3B8] backdrop-blur shadow-md">
          <Loader2 size={13} className="text-[#38BDF8] animate-spin flex-shrink-0" />
          <span>Waking up the backend server... All cached filings and prices remain immediately available.</span>
        </div>
      )}

      {/* Main Layout Container with Desktop Side Rail offset */}
      <div className="flex-1 flex flex-col lg:pl-64">
        <main className="flex-1 w-full max-w-4xl mx-auto pb-20 lg:pb-8">
          <Routes>
            <Route path="/" element={<Navigate to="/feed" replace />} />
            <Route path="/feed" element={<FeedScreen />} />
            <Route path="/alerts" element={<AlertsScreen />} />
            <Route path="/research" element={<ResearchScreen />} />
            <Route path="*" element={<Navigate to="/feed" replace />} />
          </Routes>
        </main>
      </div>

      {/* Navigation (Side Rail on >=1024px, Bottom Nav on mobile) */}
      <BottomNav />
    </div>
  )
}
