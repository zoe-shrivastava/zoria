import { useState, useEffect, useRef, createContext, useContext } from 'react'
import EvaluationReport from './EvaluationReport'
import LearningDrawer from './LearningDrawer'
import AICoach from './AICoach'

// Context for shared state across panes
export const LearningContext = createContext()

export const useLearningContext = () => {
  const context = useContext(LearningContext)
  if (!context) {
    throw new Error('useLearningContext must be used within LearningWorkspace')
  }
  return context
}

export default function LearningWorkspace({ childId, daysBack = 30, showAllGuides = false, user = null }) {
  const isParent = user?.role === 'parent'
  const [activeGuideId, setActiveGuideId] = useState(null)
  const [activeContext, setActiveContext] = useState(null)
  const [activeTab, setActiveTab] = useState(isParent ? 'GUIDE' : 'CHAT') // 'CHAT', 'GUIDE', or 'CARDS'
  const [coachOpen, setCoachOpen] = useState(true) // Always open by default
  const [progress, setProgress] = useState({}) // Track section progress
  const workspaceRef = useRef(null)

  // Context value for shared state
  const contextValue = {
    activeGuideId,
    setActiveGuideId,
    activeContext,
    setActiveContext,
    activeTab,
    setActiveTab,
    coachOpen,
    setCoachOpen,
    progress,
    setProgress,
    // Helper to open guide with context
    openGuide: (guideId, context) => {
      setActiveGuideId(guideId)
      setActiveContext(context)
      // Switch to Guide tab when opening a guide
      setActiveTab(context?.navigationState || 'GUIDE')
    },
    // Helper to navigate to cards
    navigateToCards: () => {
      setActiveTab('CARDS')
    },
    // Helper to navigate to guide
    navigateToGuide: () => {
      setActiveTab('GUIDE')
    }
  }

  return (
    <LearningContext.Provider value={contextValue}>
      <div
        ref={workspaceRef}
        style={{
          display: 'flex',
          height: '100vh',
          overflow: 'hidden',
          background: 'var(--bg-primary)'
        }}
      >
        {/* Pane 1: Evaluation Report (40%) */}
        <div
          style={{
            width: '40%',
            flexShrink: 0,
            overflowY: 'auto',
            borderRight: '1px solid var(--border-color)',
            background: 'var(--bg-primary)'
          }}
        >
          <EvaluationReport
            childId={childId}
            daysBack={daysBack}
            showAllGuides={showAllGuides}
            user={user}
            isWorkspaceMode={true}
          />
        </div>

        {/* Pane 2: Zoria (60%) - Always visible, contains Chat/Guide/Cards tabs */}
        <div
          style={{
            width: '60%',
            flexShrink: 0,
            background: 'var(--bg-primary)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden'
          }}
        >
          <AICoach
            isOpen={true}
            onToggle={() => {}}
            guideId={activeGuideId}
            contextPayload={activeContext}
            activeTab={activeTab}
            onNavigateTab={setActiveTab}
            userName={user?.name || user?.email || 'You'}
            isWorkspaceMode={true}
            disableChat={isParent}
          />
        </div>
      </div>
    </LearningContext.Provider>
  )
}
