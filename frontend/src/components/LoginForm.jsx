import { useState } from 'react'
import { auth } from '../services/api'
import { showNotification } from '../utils/notifications'
import MFALogin from './MFALogin'
import MFASetup from './MFASetup'

export default function LoginForm({ onLogin, onSwitchToChild }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [mfaRequired, setMfaRequired] = useState(false)
  const [mfaSetupRequired, setMfaSetupRequired] = useState(false)
  const [mfaData, setMfaData] = useState(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    
    // Check if user entered a child code instead of email
    if (email.toUpperCase().startsWith('CHD')) {
      showNotification('Looks like you entered a Child ID. Please use "Child Login" instead.', 'info')
      if (onSwitchToChild) {
        onSwitchToChild()
      }
      return
    }
    
    setLoading(true)
    try {
      const response = await auth.login(email, password)
      
      // Check if MFA setup is required
      if (response.mfa_setup_required) {
        setMfaSetupRequired(true)
        setMfaData({
          email,
          password,
          parentId: response.parent_id,
          qrCode: response.qr_code,
          totpSecret: response.totp_secret
        })
        return
      }
      
      // Check if MFA code is required
      if (response.mfa_required) {
        setMfaRequired(true)
        return
      }
      
      // Login successful
      if (response.token && response.user) {
        onLogin(response.token, response.user)
        showNotification('Login successful', 'success')
      } else {
        throw new Error('Invalid response from server')
      }
    } catch (error) {
      showNotification(error.message || 'Login failed', 'error')
    } finally {
      setLoading(false)
    }
  }

  // Show MFA setup screen
  if (mfaSetupRequired && mfaData) {
    return (
      <MFASetup
        email={mfaData.email}
        password={mfaData.password}
        parentId={mfaData.parentId}
        qrCode={mfaData.qrCode}
        totpSecret={mfaData.totpSecret}
        onComplete={(token, user) => {
          onLogin(token, user)
        }}
      />
    )
  }

  // Show MFA login screen
  if (mfaRequired) {
    return (
      <MFALogin
        email={email}
        password={password}
        onLogin={(token, user) => {
          onLogin(token, user)
        }}
      />
    )
  }

  return (
    <div className="auth-card">
      <h2>Login</h2>
      <form onSubmit={handleSubmit} className="auth-form">
        <div className="form-group">
          <label htmlFor="email">Email</label>
          <input
            type="email"
            id="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            disabled={loading}
            placeholder="parent@example.com"
            onBlur={(e) => {
              // Check if user entered a child code
              const value = e.target.value.toUpperCase().trim()
              if (value.startsWith('CHD') && value.length > 3) {
                showNotification('Child IDs should be entered in "Child Login". Click "Child Login" below.', 'info')
              }
            }}
          />
          <p className="form-hint" style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            For child login, use the "Child Login" option below
          </p>
        </div>
        <div className="form-group">
          <label htmlFor="password">Password</label>
          <div className="password-input-wrapper">
            <input
              type={showPassword ? "text" : "password"}
              id="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              disabled={loading}
            />
            <button
              type="button"
              className="password-toggle"
              onClick={() => setShowPassword(!showPassword)}
              disabled={loading}
              aria-label={showPassword ? "Hide password" : "Show password"}
            >
              {showPassword ? (
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
        <button type="submit" disabled={loading} className="btn-primary">
          {loading ? 'Logging in...' : 'Login'}
        </button>
        <p className="auth-switch">
          <button type="button" onClick={onSwitchToChild} className="link-button">
            Child Login
          </button>
        </p>
      </form>
    </div>
  )
}
