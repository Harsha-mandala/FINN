import { Routes, Route, Navigate } from 'react-router-dom'
import FeedScreen from './screens/FeedScreen'
import ResearchScreen from './screens/ResearchScreen'
import AlertsScreen from './screens/AlertsScreen'
import ChatScreen from './screens/ChatScreen'
import BottomNav from './components/BottomNav'

export default function App() {
  return (
    <div className="min-h-dvh bg-surface flex flex-col max-w-[430px] mx-auto relative">
      {/* Main content area */}
      <main className="flex-1 overflow-hidden pb-20">
        <Routes>
          <Route path="/" element={<Navigate to="/feed" replace />} />
          <Route path="/feed" element={<FeedScreen />} />
          <Route path="/research" element={<ResearchScreen />} />
          <Route path="/alerts" element={<AlertsScreen />} />
          <Route path="/chat" element={<ChatScreen />} />
        </Routes>
      </main>

      {/* Bottom navigation */}
      <BottomNav />
    </div>
  )
}
