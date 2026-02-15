import { useState, useEffect } from 'react'
import StudyGuide from './StudyGuide'
import RevisionCardsView from './RevisionCardsView'
import { useLearningContext } from './LearningWorkspace'

export default function LearningDrawer({ 
  isOpen, 
  onClose, 
  guideId, 
  contextPayload = null,
  containerHeight = null,
  onOpenCoach = null,
  isWorkspaceMode = false
}) {
  // Use workspace context if available
  let workspaceContext = null
  try {
    workspaceContext = isWorkspaceMode ? useLearningContext() : null
  } catch (e) {
    workspaceContext = null
  }
  
  const [activeTab, setActiveTab] = useState('GUIDE') // 'GUIDE' or 'CARDS'
  
  // Sync with workspace context
  useEffect(() => {
    if (workspaceContext) {
      setActiveTab(workspaceContext.activeTab)
    }
  }, [workspaceContext?.activeTab])
  
  const handleTabChange = (tab) => {
    setActiveTab(tab)
    if (workspaceContext) {
      workspaceContext.setActiveTab(tab)
    }
  }

  // Reset to GUIDE tab when drawer opens with new context
  useEffect(() => {
    if (isOpen && contextPayload?.navigationState) {
      setActiveTab(contextPayload.navigationState)
    } else if (isOpen) {
      setActiveTab('GUIDE')
    }
  }, [isOpen, contextPayload])

  if (!isOpen && !isWorkspaceMode) {
    return null
  }

  const isMobile = window.innerWidth < 768

  // In workspace mode, render without backdrop and fixed positioning
  if (isWorkspaceMode) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
          overflow: 'hidden',
          background: 'var(--bg-primary)'
        }}
      >
        {/* Header */}
        <div style={{
          padding: '1.5rem',
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: 'var(--bg-secondary)'
        }}>
          <h2 style={{ margin: 0, fontSize: '1.5rem' }}>Study Guide</h2>
          <button
            onClick={onClose}
            className="btn-secondary"
            style={{ padding: '0.5rem 1rem' }}
          >
            ✕ Close
          </button>
        </div>

        {/* Segmented Control */}
        <div style={{
          padding: '1rem 1.5rem',
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          gap: '0.5rem'
        }}>
          <button
            onClick={() => handleTabChange('GUIDE')}
            style={{
              flex: 1,
              padding: '0.75rem 1.5rem',
              border: 'none',
              borderRadius: 'var(--radius-md)',
              background: activeTab === 'GUIDE' ? 'var(--primary-color)' : 'var(--bg-secondary)',
              color: activeTab === 'GUIDE' ? 'white' : 'var(--text-color)',
              cursor: 'pointer',
              fontWeight: '600',
              transition: 'all 0.2s'
            }}
          >
            Guide
          </button>
          <button
            onClick={() => handleTabChange('CARDS')}
            style={{
              flex: 1,
              padding: '0.75rem 1.5rem',
              border: 'none',
              borderRadius: 'var(--radius-md)',
              background: activeTab === 'CARDS' ? 'var(--primary-color)' : 'var(--bg-secondary)',
              color: activeTab === 'CARDS' ? 'white' : 'var(--text-color)',
              cursor: 'pointer',
              fontWeight: '600',
              transition: 'all 0.2s'
            }}
          >
            Cards
          </button>
        </div>

        {/* Content Area with smooth horizontal slide */}
        <div style={{
          flex: 1,
          overflow: 'hidden',
          position: 'relative'
        }}>
          <div style={{
            display: 'flex',
            transition: 'transform 0.3s ease',
            transform: activeTab === 'CARDS' ? 'translateX(-50%)' : 'translateX(0)',
            width: '200%',
            height: '100%'
          }}>
            <div style={{ width: '50%', flexShrink: 0, overflowY: 'auto' }}>
              <StudyGuide 
                guideId={guideId}
                contextPayload={contextPayload}
                onNavigateToCards={() => handleTabChange('CARDS')}
              />
            </div>
            <div style={{ width: '50%', flexShrink: 0, overflowY: 'auto' }}>
              <RevisionCardsView
                guideId={guideId}
                contextPayload={contextPayload}
                onAskCoach={() => onOpenCoach?.(guideId, contextPayload)}
              />
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Non-workspace mode: render as drawer with backdrop
  return (
    <>
      {/* Backdrop */}
      <div
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.5)',
          zIndex: 1000,
          animation: 'fadeIn 0.2s ease-in'
        }}
        onClick={onClose}
      />

      {/* Drawer - Left Side */}
      <div
        className="learning-drawer"
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: isMobile ? '100%' : '45%',
          maxWidth: '800px',
          height: containerHeight ? `${Math.min(containerHeight, window.innerHeight)}px` : '100vh',
          maxHeight: '100vh',
          background: 'var(--bg-primary)',
          boxShadow: '4px 0 12px rgba(0, 0, 0, 0.15)',
          zIndex: 1001,
          display: 'flex',
          flexDirection: 'column',
          animation: 'slideInLeft 0.3s ease-out',
          overflow: 'hidden'
        }}
      >
        {/* Header */}
        <div style={{
          padding: '1.5rem',
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: 'var(--bg-secondary)'
        }}>
          <h2 style={{ margin: 0, fontSize: '1.5rem' }}>Study Guide</h2>
          <button
            onClick={onClose}
            className="btn-secondary"
            style={{ padding: '0.5rem 1rem' }}
          >
            ✕ Close
          </button>
        </div>

        {/* Segmented Control */}
        <div style={{
          padding: '1rem 1.5rem',
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          gap: '0.5rem'
        }}>
          <button
            onClick={() => handleTabChange('GUIDE')}
            style={{
              flex: 1,
              padding: '0.75rem 1.5rem',
              border: 'none',
              borderRadius: 'var(--radius-md)',
              background: activeTab === 'GUIDE' ? 'var(--primary-color)' : 'var(--bg-secondary)',
              color: activeTab === 'GUIDE' ? 'white' : 'var(--text-color)',
              cursor: 'pointer',
              fontWeight: '600',
              transition: 'all 0.2s'
            }}
          >
            Guide
          </button>
          <button
            onClick={() => handleTabChange('CARDS')}
            style={{
              flex: 1,
              padding: '0.75rem 1.5rem',
              border: 'none',
              borderRadius: 'var(--radius-md)',
              background: activeTab === 'CARDS' ? 'var(--primary-color)' : 'var(--bg-secondary)',
              color: activeTab === 'CARDS' ? 'white' : 'var(--text-color)',
              cursor: 'pointer',
              fontWeight: '600',
              transition: 'all 0.2s'
            }}
          >
            Cards
          </button>
        </div>

        {/* Content Area with smooth horizontal slide */}
        <div style={{
          flex: 1,
          overflow: 'hidden',
          position: 'relative'
        }}>
          <div style={{
            display: 'flex',
            transition: 'transform 0.3s ease',
            transform: activeTab === 'CARDS' ? 'translateX(-50%)' : 'translateX(0)',
            width: '200%',
            height: '100%'
          }}>
            <div style={{ width: '50%', flexShrink: 0, overflowY: 'auto' }}>
              <StudyGuide 
                guideId={guideId}
                contextPayload={contextPayload}
                onNavigateToCards={() => handleTabChange('CARDS')}
              />
            </div>
            <div style={{ width: '50%', flexShrink: 0, overflowY: 'auto' }}>
              <RevisionCardsView
                guideId={guideId}
                contextPayload={contextPayload}
                onAskCoach={() => onOpenCoach?.(guideId, contextPayload)}
              />
            </div>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes slideInLeft {
          from {
            transform: translateX(-100%);
          }
          to {
            transform: translateX(0);
          }
        }
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @media (max-width: 768px) {
          .learning-drawer {
            width: 100% !important;
            max-width: 100% !important;
          }
        }
      `}</style>
    </>
  )
}
