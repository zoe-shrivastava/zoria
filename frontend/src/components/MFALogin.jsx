import { useState } from 'react'
import { auth } from '../services/api'
import { showNotification } from '../utils/notifications'

export default function MFALogin({ 
  email, 
  password, 
  onLogin 
}) {
  const [mfaCode, setMfaCode] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    
    if (mfaCode.length !== 6) {
      showNotification('Please enter a 6-digit code', 'error')
      return
    }
    
    setLoading(true)
    try {
      const response = await auth.login(email, password, mfaCode)
      if (response.token && response.user) {
        showNotification('Login successful', 'success')
        if (onLogin) {
          onLogin(response.token, response.user)
        }
      } else {
        throw new Error('Invalid response from server')
      }
    } catch (error) {
      showNotification(error.message || 'MFA verification failed', 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-card">
      <h2>Enter MFA Code</h2>
      <p className="mfa-prompt">
        Please enter the 6-digit code from your authenticator app.
      </p>
      <form onSubmit={handleSubmit} className="auth-form">
        <div className="form-group">
          <label htmlFor="mfaCode">MFA Code</label>
          <input
            type="text"
            id="mfaCode"
            value={mfaCode}
            onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            required
            disabled={loading}
            placeholder="000000"
            maxLength={6}
            pattern="[0-9]{6}"
            className="mfa-code-input"
            autoFocus
          />
        </div>
        <button type="submit" disabled={loading || mfaCode.length !== 6} className="btn-primary">
          {loading ? 'Verifying...' : 'Verify & Login'}
        </button>
      </form>
    </div>
  )
}
