export default function Header({ user, onLogout }) {
  const getRoleBadge = () => {
    if (!user?.role) return null
    const roleColors = {
      admin: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
      parent: 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)',
      child: 'linear-gradient(135deg, #10b981 0%, #059669 100%)'
    }
    return (
      <span 
        className="role-badge"
        style={{ background: roleColors[user.role] || roleColors.parent }}
      >
        {user.role.toUpperCase()}
      </span>
    )
  }

  return (
    <header className="header">
      <div className="header-content">
        <h1>Zoria</h1>
        <div className="header-actions">
          {user && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              {getRoleBadge()}
              <span className="user-email">
                {user.role === 'child' ? (user.name || user.id || 'Child') : user.email}
              </span>
            </div>
          )}
          <button onClick={onLogout} className="btn-secondary">
            Logout
          </button>
        </div>
      </div>
    </header>
  )
}
