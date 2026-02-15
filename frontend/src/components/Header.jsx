import { useState, useRef, useEffect, useMemo } from 'react'
import './TabNavigation.css'

export default function Header({ user, onLogout, tabs = null, activeTab = null, onTabChange = null, userProfile = null }) {
  const [showUserMenu, setShowUserMenu] = useState(false)
  const userMenuRef = useRef(null)

  // Get actual user name from profile
  // Use useMemo to ensure it updates when userProfile changes
  const userName = useMemo(() => {
    // Check userProfile first (for child users, this is childProfile)
    // This should have the actual name from the profile
    if (userProfile?.name) {
      return userProfile.name
    }
    // Also check child_name as fallback (some APIs use this field)
    if (userProfile?.child_name) {
      return userProfile.child_name
    }
    // Check user object (fallback)
    if (user?.name) {
      return user.name
    }
    // Check email as last resort
    if (user?.email) {
      return user.email
    }
    return 'User'
  }, [userProfile, user])

  // Get profile type label
  const getProfileType = () => {
    if (!user?.role) return 'User'
    const roleLabels = {
      admin: 'Administrator',
      parent: 'Parent',
      child: 'Student'
    }
    return roleLabels[user.role] || user.role.charAt(0).toUpperCase() + user.role.slice(1)
  }

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target)) {
        setShowUserMenu(false)
      }
    }

    if (showUserMenu) {
      document.addEventListener('mousedown', handleClickOutside)
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [showUserMenu])

  return (
    <header className="header" style={{ position: 'relative' }}>
      <div className="header-content" style={{ 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'space-between',
        width: '100%',
        gap: '1rem'
      }}>
        {/* Left: Zoria Logo */}
        <h1 style={{ margin: 0, flexShrink: 0 }}>Zoria</h1>

        {/* Middle: Tabs */}
        {tabs && tabs.length > 0 && (
          <div className="tab-navigation" style={{ 
            flex: 1,
            display: 'flex',
            justifyContent: 'center',
            margin: 0,
            border: 'none',
            padding: 0
          }}>
            <div className="tab-list" role="tablist" style={{ display: 'flex', gap: '0.25rem' }}>
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  role="tab"
                  aria-selected={activeTab === tab.id}
                  aria-controls={`panel-${tab.id}`}
                  id={`tab-${tab.id}`}
                  className={`tab-button ${activeTab === tab.id ? 'active' : ''}`}
                  onClick={() => onTabChange?.(tab.id)}
                  style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                >
                  <span className="tab-label">{tab.label}</span>
                  {tab.badge && <span className="tab-badge">{tab.badge}</span>}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Right: User Icon with Dropdown */}
        {user && (
          <div ref={userMenuRef} style={{ position: 'relative', flexShrink: 0 }}>
            <button
              onClick={() => setShowUserMenu(!showUserMenu)}
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                borderRadius: '50%',
                width: '40px',
                height: '40px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                fontSize: '1.25rem',
                color: 'var(--text-color)',
                transition: 'all 0.2s',
                padding: 0
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'var(--primary-color-light)'
                e.currentTarget.style.borderColor = 'var(--primary-color)'
              }}
              onMouseLeave={(e) => {
                if (!showUserMenu) {
                  e.currentTarget.style.background = 'var(--bg-secondary)'
                  e.currentTarget.style.borderColor = 'var(--border-color)'
                }
              }}
              title="User menu"
            >
              👤
            </button>

            {/* User Menu Dropdown */}
            {showUserMenu && (
              <div style={{
                position: 'absolute',
                top: '100%',
                right: 0,
                marginTop: '0.5rem',
                background: 'var(--bg-primary)',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-md)',
                boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
                minWidth: '200px',
                zIndex: 1100,
                padding: '1rem'
              }}>
                <div style={{ marginBottom: '0.75rem', paddingBottom: '0.75rem', borderBottom: '1px solid var(--border-color)' }}>
                  <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
                    {getProfileType()}
                  </div>
                  <div style={{ fontSize: '1rem', fontWeight: '600', color: 'var(--text-color)' }}>
                    {userName}
                  </div>
                </div>
                <button
                  onClick={() => {
                    setShowUserMenu(false)
                    onLogout()
                  }}
                  className="btn-secondary"
                  style={{ 
                    width: '100%',
                    padding: '0.5rem',
                    fontSize: '0.875rem'
                  }}
                >
                  Logout
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  )
}
