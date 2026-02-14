import { useState } from 'react'
import { auth } from '../services/api'
import { showNotification } from '../utils/notifications'

export default function MFASetup({ 
  email, 
  password, 
  parentId, 
  qrCode, 
  totpSecret,
  onComplete 
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
      const response = await auth.completeMfaSetup(parentId, password, mfaCode)
      if (response.token && response.user) {
        showNotification('MFA setup completed successfully!', 'success')
        if (onComplete) {
          onComplete(response.token, response.user)
        }
      } else {
        throw new Error('MFA setup completed but login failed')
      }
    } catch (error) {
      showNotification(error.message || 'MFA setup failed', 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-card">
      <h2>Set Up Multi-Factor Authentication</h2>
      <div className="mfa-setup">
        <p className="mfa-instructions">
          Scan this QR code with your authenticator app (Google Authenticator, Authy, etc.):
        </p>
        
        {qrCode && (
          <div className="qr-code-container">
            <img 
              src={qrCode} 
              alt="MFA QR Code" 
              className="qr-code"
            />
          </div>
        )}
        
        {totpSecret && (
          <div className="mfa-secret">
            <p>Or enter this secret manually:</p>
            <code className="secret-code">{totpSecret}</code>
          </div>
        )}
        
        <form onSubmit={handleSubmit} className="auth-form">
          <div className="form-group">
            <label htmlFor="mfaCode">Enter 6-digit code from your app</label>
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
            />
          </div>
          <button type="submit" disabled={loading || mfaCode.length !== 6} className="btn-primary">
            {loading ? 'Verifying...' : 'Complete Setup'}
          </button>
        </form>
      </div>
    </div>
  )
}
