import { useState, useEffect } from 'react'
import Header from '../components/Header'
import LLMLogsViewer from '../components/LLMLogsViewer'
import { admin, isAuthError } from '../services/api'
import { showNotification } from '../utils/notifications'

export default function AdminSettings({ user, onLogout, onNavigateToDashboard }) {
  const [activeTab, setActiveTab] = useState('parents')
  const [parents, setParents] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreateParent, setShowCreateParent] = useState(false)
  const [newParentEmail, setNewParentEmail] = useState('')
  const [newParentPassword, setNewParentPassword] = useState('')
  const [newParentRole, setNewParentRole] = useState('parent')
  const [timestampSettings, setTimestampSettings] = useState({
    show_document_timestamps: true,
    show_test_timestamps: true,
    show_study_guide_timestamps: true,
  })
  const [savingTimestamps, setSavingTimestamps] = useState(false)

  useEffect(() => {
    loadParents()
    loadTimestampSettings()
  }, [])

  const loadParents = async () => {
    try {
      setLoading(true)
      const data = await admin.listParents()
      setParents(Array.isArray(data) ? data : [])
    } catch (error) {
      if (!isAuthError(error)) {
        showNotification(error.message || 'Failed to load parents', 'error')
      }
    } finally {
      setLoading(false)
    }
  }

  const loadTimestampSettings = async () => {
    try {
      const data = await admin.getTimestampSettings()
      setTimestampSettings({
        show_document_timestamps: data?.show_document_timestamps ?? true,
        show_test_timestamps: data?.show_test_timestamps ?? true,
        show_study_guide_timestamps: data?.show_study_guide_timestamps ?? true,
      })
    } catch (error) {
      if (!isAuthError(error)) {
        showNotification(error.message || 'Failed to load timestamp settings', 'error')
      }
    }
  }

  const handleCreateParent = async (e) => {
    e.preventDefault()
    if (!newParentEmail || !newParentPassword) {
      showNotification('Email and password are required', 'error')
      return
    }

    try {
      await admin.createParent(newParentEmail, newParentPassword, newParentRole)
      showNotification('Parent created successfully', 'success')
      setNewParentEmail('')
      setNewParentPassword('')
      setNewParentRole('parent')
      setShowCreateParent(false)
      loadParents()
    } catch (error) {
      showNotification(error.message || 'Failed to create parent', 'error')
    }
  }

  const handleDeleteParent = async (parentId) => {
    if (!window.confirm('Are you sure you want to deactivate this parent account?')) {
      return
    }

    try {
      await admin.deleteParent(parentId)
      showNotification('Parent deactivated successfully', 'success')
      loadParents()
    } catch (error) {
      if (!isAuthError(error)) {
        showNotification(error.message || 'Failed to deactivate parent', 'error')
      }
    }
  }

  const handleSaveTimestampSettings = async (e) => {
    e.preventDefault()
    try {
      setSavingTimestamps(true)
      await admin.updateTimestampSettings(timestampSettings)
      showNotification('Display settings saved', 'success')
    } catch (error) {
      if (!isAuthError(error)) {
        showNotification(error.message || 'Failed to save display settings', 'error')
      }
    } finally {
      setSavingTimestamps(false)
    }
  }

  return (
    <div className="dashboard">
      <Header user={user} onLogout={onLogout} />
      <div className="dashboard-content">
        <div style={{ marginBottom: '1.5rem' }}>
          <button onClick={onNavigateToDashboard} className="btn-secondary">
            ← Back to Dashboard
          </button>
        </div>

        <div className="dashboard-section">
          <h2>Admin Settings</h2>
          <p className="section-description">
            Manage parent accounts, system settings, and view LLM usage.
          </p>

          {/* Tab Navigation */}
          <div style={{
            display: 'flex',
            gap: '0.5rem',
            marginBottom: '2rem',
            borderBottom: '2px solid var(--border)'
          }}>
            <button
              onClick={() => setActiveTab('parents')}
              style={{
                padding: '0.75rem 1.5rem',
                border: 'none',
                backgroundColor: 'transparent',
                cursor: 'pointer',
                borderBottom: activeTab === 'parents' ? '2px solid var(--accent)' : '2px solid transparent',
                marginBottom: '-2px',
                color: activeTab === 'parents' ? 'var(--accent)' : 'var(--text-muted)',
                fontWeight: activeTab === 'parents' ? '600' : '400'
              }}
            >
              Parent Management
            </button>
            <button
              onClick={() => setActiveTab('llm-logs')}
              style={{
                padding: '0.75rem 1.5rem',
                border: 'none',
                backgroundColor: 'transparent',
                cursor: 'pointer',
                borderBottom: activeTab === 'llm-logs' ? '2px solid var(--accent)' : '2px solid transparent',
                marginBottom: '-2px',
                color: activeTab === 'llm-logs' ? 'var(--accent)' : 'var(--text-muted)',
                fontWeight: activeTab === 'llm-logs' ? '600' : '400'
              }}
            >
              LLM Logs & Usage
            </button>
          </div>

          {activeTab === 'llm-logs' ? (
            <LLMLogsViewer />
          ) : (
            <>

          <div style={{ marginBottom: '2rem' }}>
            <h3 style={{ marginBottom: '1rem' }}>Parent Management</h3>
            {showCreateParent ? (
              <form onSubmit={handleCreateParent} style={{ maxWidth: '400px' }}>
                <div className="form-group">
                  <label htmlFor="email">Email</label>
                  <input
                    type="email"
                    id="email"
                    value={newParentEmail}
                    onChange={(e) => setNewParentEmail(e.target.value)}
                    required
                    placeholder="parent@example.com"
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="password">Password</label>
                  <input
                    type="password"
                    id="password"
                    value={newParentPassword}
                    onChange={(e) => setNewParentPassword(e.target.value)}
                    required
                    minLength={8}
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="role">Role</label>
                  <select
                    id="role"
                    value={newParentRole}
                    onChange={(e) => setNewParentRole(e.target.value)}
                  >
                    <option value="parent">Parent</option>
                    <option value="admin">Admin</option>
                  </select>
                </div>
                <div style={{ display: 'flex', gap: '0.75rem' }}>
                  <button
                    type="button"
                    onClick={() => setShowCreateParent(false)}
                    className="btn-secondary"
                    style={{ flex: 1 }}
                  >
                    Cancel
                  </button>
                  <button type="submit" className="btn-primary" style={{ flex: 1 }}>
                    Create
                  </button>
                </div>
              </form>
            ) : (
              <button
                onClick={() => setShowCreateParent(true)}
                className="btn-primary"
                style={{ marginBottom: '1.5rem', width: 'auto' }}
              >
                + Create Parent
              </button>
            )}

            {loading ? (
              <p className="loading-text">Loading parents...</p>
            ) : parents.length === 0 ? (
              <div className="empty-state">
                <p>No parents found.</p>
              </div>
            ) : (
              <div className="settings-list">
                {parents.map((parent) => (
                  <div key={parent.id} className="setting-item">
                    <div className="setting-header">
                      <div>
                        <div className="setting-label">{parent.email}</div>
                        <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                          Role: {parent.role} • Created: {(() => {
                            let dateStr = parent.created_at
                            if (!dateStr.includes('Z') && !dateStr.match(/[+-]\d{2}:\d{2}$/)) {
                              dateStr = dateStr.endsWith('Z') ? dateStr : dateStr + 'Z'
                            }
                            return new Date(dateStr).toLocaleString(undefined, {
                              year: 'numeric',
                              month: 'short',
                              day: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit',
                              timeZoneName: 'short'
                            })
                          })()}
                        </div>
                      </div>
                      <div className="setting-actions">
                        <button
                          onClick={() => handleDeleteParent(parent.id)}
                          className="btn-secondary btn-small"
                        >
                          Deactivate
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div style={{ marginBottom: '2rem', marginTop: '1.5rem' }}>
            <h3 style={{ marginBottom: '1rem' }}>Display Settings</h3>
            <p className="section-description" style={{ marginBottom: '1rem' }}>
              Control whether timestamps are shown in admin views for documents, tests, and study guides.
            </p>
            <form onSubmit={handleSaveTimestampSettings} style={{ maxWidth: '480px', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem' }}>
                <input
                  type="checkbox"
                  checked={timestampSettings.show_document_timestamps}
                  onChange={(e) =>
                    setTimestampSettings(prev => ({
                      ...prev,
                      show_document_timestamps: e.target.checked,
                    }))
                  }
                />
                <span>Show document upload & processing timestamps</span>
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem' }}>
                <input
                  type="checkbox"
                  checked={timestampSettings.show_test_timestamps}
                  onChange={(e) =>
                    setTimestampSettings(prev => ({
                      ...prev,
                      show_test_timestamps: e.target.checked,
                    }))
                  }
                />
                <span>Show test creation timestamps</span>
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem' }}>
                <input
                  type="checkbox"
                  checked={timestampSettings.show_study_guide_timestamps}
                  onChange={(e) =>
                    setTimestampSettings(prev => ({
                      ...prev,
                      show_study_guide_timestamps: e.target.checked,
                    }))
                  }
                />
                <span>Show study guide generated timestamps</span>
              </label>
              <div style={{ marginTop: '1rem' }}>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={savingTimestamps}
                >
                  {savingTimestamps ? 'Saving…' : 'Save display settings'}
                </button>
              </div>
            </form>
          </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
