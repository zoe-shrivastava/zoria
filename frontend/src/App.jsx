import { useState, useEffect, useCallback } from 'react'
import Auth from './pages/Auth'
import Dashboard from './pages/Dashboard'
import AdminSettings from './pages/AdminSettings'
import NotificationContainer, { useNotifications } from './components/NotificationContainer'
import { auth, admin } from './services/api'
import { setNotificationHandler } from './utils/notifications'
import './styles/index.css'

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [user, setUser] = useState(null)
  const [isAdmin, setIsAdmin] = useState(false)
  const [currentPage, setCurrentPage] = useState('dashboard')
  const [loading, setLoading] = useState(true)
  const { notifications, showNotification, removeNotification } = useNotifications()

  useEffect(() => {
    setNotificationHandler(showNotification)
  }, [showNotification])

  useEffect(() => {
    const token = localStorage.getItem('token') || sessionStorage.getItem('token')
    if (!token) {
      setLoading(false)
      return
    }
    let cancelled = false
    const initFromToken = async () => {
      try {
        const payload = JSON.parse(atob(token.split('.')[1]))
        if (!payload.role) {
          setLoading(false)
          return
        }
        setIsAdmin(payload.role === 'admin')
        setUser({
          email: payload.email || payload.user_id,
          role: payload.role,
          id: payload.user_id || payload.child_id || payload.parent_id,
          name: payload.name || payload.child_name || payload.email
        })
        setIsAuthenticated(true)
        // Hydrate user from /auth/me so parent/admin always get email (covers old tokens without email in JWT)
        try {
          const me = await auth.getMe()
          if (!cancelled && me?.user) {
            const u = me.user
            setUser({
              ...u,
              id: u.id || payload.user_id || payload.child_id || payload.parent_id,
              name: u.name || u.child_name || u.email
            })
          }
        } catch (_) {
          // Keep user from token if /me fails (e.g. network)
        }
      } catch (e) {
        localStorage.removeItem('token')
        sessionStorage.removeItem('token')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    initFromToken()
    return () => { cancelled = true }
  }, [])

  const handleLogin = async (token, userData) => {
    localStorage.setItem('token', token)
    setUser(userData)
    setIsAuthenticated(true)
    setIsAdmin(userData?.role === 'admin')
  }

  const handleLogout = useCallback(() => {
    localStorage.removeItem('token')
    sessionStorage.removeItem('token')
    setUser(null)
    setIsAdmin(false)
    setIsAuthenticated(false)
    setCurrentPage('dashboard')
  }, [])

  const sessionExpiredNotifiedRef = { current: false }
  
  useEffect(() => {
    const handleSessionExpired = () => {
      if (sessionExpiredNotifiedRef.current) {
        return
      }
      sessionExpiredNotifiedRef.current = true
      window._sessionExpiredHandled = true
      handleLogout()
      showNotification('Your session has expired. Please log in again.', 'warning')
      setTimeout(() => {
        sessionExpiredNotifiedRef.current = false
        window._sessionExpiredHandled = false
      }, 5000)
    }
    
    window.addEventListener('session-expired', handleSessionExpired)
    return () => {
      window.removeEventListener('session-expired', handleSessionExpired)
    }
  }, [handleLogout, showNotification])

  // Inactivity timeout: 15 minutes
  useEffect(() => {
    if (!isAuthenticated) {
      return
    }

    const INACTIVITY_TIMEOUT = 15 * 60 * 1000 // 15 minutes in milliseconds
    let inactivityTimer = null

    const resetTimer = () => {
      if (inactivityTimer) {
        clearTimeout(inactivityTimer)
      }
      inactivityTimer = setTimeout(() => {
        handleLogout()
        showNotification('You have been logged out due to inactivity (15 minutes).', 'warning')
      }, INACTIVITY_TIMEOUT)
    }

    // Reset timer on user activity
    const activityEvents = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart', 'click']
    activityEvents.forEach(event => {
      document.addEventListener(event, resetTimer, true)
    })

    // Start the timer
    resetTimer()

    // Cleanup
    return () => {
      if (inactivityTimer) {
        clearTimeout(inactivityTimer)
      }
      activityEvents.forEach(event => {
        document.removeEventListener(event, resetTimer, true)
      })
    }
  }, [isAuthenticated, handleLogout, showNotification])

  if (loading) {
    return (
      <div className="loading">
        <div className="loading-spinner">
          <div className="spinner-ring"></div>
          <div className="spinner-ring"></div>
          <div className="spinner-ring"></div>
        </div>
        <p>Loading...</p>
      </div>
    )
  }

  if (!isAuthenticated) {
    return (
      <>
        <Auth onLogin={handleLogin} />
        <NotificationContainer 
          notifications={notifications} 
          removeNotification={removeNotification} 
        />
      </>
    )
  }

  return (
    <div className="app">
      {currentPage === 'admin' && isAdmin ? (
        <AdminSettings 
          user={user} 
          onLogout={handleLogout}
          onNavigateToDashboard={() => setCurrentPage('dashboard')}
        />
      ) : (
        <Dashboard 
          user={user} 
          onLogout={handleLogout}
          isAdmin={isAdmin}
          onNavigateToAdmin={() => setCurrentPage('admin')}
        />
      )}
      <NotificationContainer 
        notifications={notifications} 
        removeNotification={removeNotification} 
      />
    </div>
  )
}

export default App
