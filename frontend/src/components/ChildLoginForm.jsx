import { useState } from 'react'
import { auth } from '../services/api'
import { showNotification } from '../utils/notifications'

export default function ChildLoginForm({ onLogin, onSwitchToParent }) {
  const [childId, setChildId] = useState('')
  const [pin, setPin] = useState('')
  const [showPin, setShowPin] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    
    // Validate inputs
    if (!childId.trim()) {
      showNotification('Please enter your Child ID', 'error')
      return
    }
    if (!pin.trim()) {
      showNotification('Please enter your PIN', 'error')
      return
    }
    
    setLoading(true)
    try {
      const response = await auth.childLogin(childId.trim(), pin.trim())
      
      if (!response || !response.token) {
        throw new Error('Invalid response from server')
      }
      
      const token = response.token
      onLogin(token, response.user)
      showNotification('Login successful', 'success')
    } catch (error) {
      console.error('Child login error:', error)
      
      // Provide user-friendly error messages
      let errorMessage = 'Login failed'
      if (error.message) {
        if (error.message.includes('timeout') || error.message.includes('timed out')) {
          errorMessage = 'Login is taking too long. Please check your connection and try again.'
        } else if (error.message.includes('Failed to connect') || error.message.includes('Network')) {
          errorMessage = 'Cannot connect to server. Please check if the server is running.'
        } else if (error.message.includes('Invalid') || error.message.includes('Invalid child ID')) {
          errorMessage = 'Invalid Child ID or PIN. Please check your credentials.'
        } else {
          errorMessage = error.message
        }
      }
      
      showNotification(errorMessage, 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-card child-login-card">
      <div className="child-login-header">
        <h2>👋 Welcome Back!</h2>
        <p className="child-login-subtitle">Enter your Child ID and PIN to continue</p>
      </div>
      <form onSubmit={handleSubmit} className="auth-form">
        <div className="form-group">
          <label htmlFor="childId">
            <span>Child ID</span>
            <span className="form-help-text">Enter your Child ID (e.g., CHD123ABC)</span>
          </label>
          <input
            type="text"
            id="childId"
            value={childId}
            onChange={(e) => setChildId(e.target.value.toUpperCase())}
            required
            disabled={loading}
            placeholder="CHD123ABC"
            className="child-id-input"
            style={{ textTransform: 'uppercase' }}
          />
        </div>
        <div className="form-group">
          <label htmlFor="pin">
            <span>PIN</span>
            <span className="form-help-text">Your 4-6 digit secret code</span>
          </label>
          <div className="password-input-wrapper">
            <input
              type={showPin ? "text" : "password"}
              id="pin"
              value={pin}
              onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 6))}
              required
              disabled={loading}
              placeholder="Enter your PIN"
              maxLength={6}
              className="pin-input"
              inputMode="numeric"
            />
            <button
              type="button"
              className="password-toggle"
              onClick={() => setShowPin(!showPin)}
              disabled={loading}
              aria-label={showPin ? "Hide PIN" : "Show PIN"}
            >
              {showPin ? (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                  <line x1="1" y1="1" x2="23" y2="23"/>
                </svg>
              ) : (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                  <circle cx="12" cy="12" r="3"/>
                </svg>
              )}
            </button>
          </div>
        </div>
        <button type="submit" disabled={loading} className="btn-primary btn-large">
          {loading ? 'Logging in...' : '🚀 Start Learning'}
        </button>
        {onSwitchToParent && (
          <p className="auth-switch">
            <button type="button" onClick={onSwitchToParent} className="link-button">
              Parent/Admin Login
            </button>
          </p>
        )}
      </form>
    </div>
  )
}
