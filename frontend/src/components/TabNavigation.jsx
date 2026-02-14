import './TabNavigation.css'

export default function TabNavigation({ tabs, activeTab, onTabChange, className = '' }) {
  if (!tabs || tabs.length === 0) {
    return null
  }
  
  return (
    <div className={`tab-navigation ${className}`} style={{ display: 'block', visibility: 'visible', width: '100%' }}>
      <div className="tab-list" role="tablist" style={{ display: 'flex', gap: '0.25rem' }}>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`panel-${tab.id}`}
            id={`tab-${tab.id}`}
            className={`tab-button ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => onTabChange(tab.id)}
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}
          >
            <span className="tab-label">{tab.label}</span>
            {tab.badge && <span className="tab-badge">{tab.badge}</span>}
          </button>
        ))}
      </div>
    </div>
  )
}
