import { useState } from 'react'
import LoginForm from '../components/LoginForm'
import ChildLoginForm from '../components/ChildLoginForm'

export default function Auth({ onLogin }) {
  const [mode, setMode] = useState('login') // 'login', 'child-login'

  return (
    <div className="auth-container">
      {mode === 'login' && (
        <LoginForm
          onLogin={onLogin}
          onSwitchToChild={() => setMode('child-login')}
        />
      )}
      {mode === 'child-login' && (
        <ChildLoginForm
          onLogin={onLogin}
          onSwitchToParent={() => setMode('login')}
        />
      )}
    </div>
  )
}
