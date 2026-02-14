import { useState, useEffect } from 'react'
import { tests, isAuthError } from '../services/api'
import { showNotification } from '../utils/notifications'
import LoadingSpinner from './LoadingSpinner'

export default function TestList({ childId, onTestSelect, statusFilter = null, isAdmin = false, onTestDeleted, userRole = null, refreshKey = 0 }) {
  const [testList, setTestList] = useState([])
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState({})

  useEffect(() => {
    loadTests()
  }, [childId, statusFilter, refreshKey])

  // Poll for draft tests to check if they've completed
  useEffect(() => {
    const hasDraftTests = testList.some(test => test.status === 'draft')
    if (!hasDraftTests) return

    const interval = setInterval(() => {
      loadTests()
    }, 3000) // Poll every 3 seconds

    return () => clearInterval(interval)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [testList])

  const loadTests = async () => {
    try {
      setLoading(true)
      const data = await tests.list(childId, statusFilter)
      const testsArray = Array.isArray(data.tests) ? data.tests : []
      setTestList(testsArray)
    } catch (error) {
      if (!isAuthError(error)) {
        showNotification(error.message || 'Failed to load tests', 'error')
      }
    } finally {
      setLoading(false)
    }
  }

  const getStatusColor = (status) => {
    switch (status) {
      case 'active':
        return 'var(--warning-color)'
      case 'completed':
        return 'var(--success-color)'
      case 'expired':
        return 'var(--error-color)'
      case 'draft':
        return 'var(--primary-color)' // Processing status
      case 'failed':
        return 'var(--error-color)'
      default:
        return 'var(--text-muted)'
    }
  }

  const getStatusDisplay = (status) => {
    switch (status) {
      case 'draft':
        return 'Processing'
      default:
        return status.charAt(0).toUpperCase() + status.slice(1)
    }
  }

  const isTestAccessible = (status) => {
    // Only allow access to tests that are active or completed
    return status === 'active' || status === 'completed'
  }

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A'
    try {
      // If date string doesn't have timezone info (no 'Z' or +/-), treat it as UTC
      let dateStr = dateString
      if (!dateStr.includes('Z') && !dateStr.match(/[+-]\d{2}:\d{2}$/)) {
        // Add 'Z' to indicate UTC if not present
        dateStr = dateStr.endsWith('Z') ? dateStr : dateStr + 'Z'
      }
      
      const date = new Date(dateStr)
      
      // Check if date is valid
      if (isNaN(date.getTime())) {
        return 'Invalid date'
      }
      
      // Use browser's local timezone for all roles
      // toLocaleString() automatically converts UTC to local timezone
      return date.toLocaleString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        timeZoneName: 'short'
      })
    } catch (e) {
      return 'Invalid date'
    }
  }

  const handleDelete = async (testId, e) => {
    e.stopPropagation() // Prevent triggering test selection
    
    if (!window.confirm('Are you sure you want to delete this test? This action cannot be undone.')) {
      return
    }

    try {
      setDeleting(prev => ({ ...prev, [testId]: true }))
      await tests.delete(testId)
      showNotification('Test deleted successfully', 'success')
      // Remove from list
      setTestList(prev => prev.filter(t => t.id !== testId))
      if (onTestDeleted) {
        onTestDeleted(testId)
      }
    } catch (error) {
      showNotification(error.message || 'Failed to delete test', 'error')
    } finally {
      setDeleting(prev => {
        const newState = { ...prev }
        delete newState[testId]
        return newState
      })
    }
  }

  if (loading) {
    return <LoadingSpinner />
  }

  if (testList.length === 0) {
    return (
      <div className="empty-state" style={{ padding: '2rem', textAlign: 'center' }}>
        <p>No tests found.</p>
        {statusFilter && <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
          No {statusFilter} tests available.
        </p>}
      </div>
    )
  }

  return (
    <div className="test-list">
      {testList.map((test) => (
        <div
          key={test.id}
          style={{
            background: 'var(--bg-tertiary)',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-md)',
            padding: '1.5rem',
            marginBottom: '1rem',
            cursor: isTestAccessible(test.status) ? 'pointer' : 'not-allowed',
            transition: 'all 0.2s',
            opacity: isTestAccessible(test.status) ? 1 : 0.7,
          }}
          onMouseEnter={(e) => {
            if (isTestAccessible(test.status)) {
              e.currentTarget.style.borderColor = 'var(--primary-color)'
              e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)'
            }
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = 'var(--border-color)'
            e.currentTarget.style.boxShadow = 'none'
          }}
          onClick={() => {
            if (isTestAccessible(test.status) && onTestSelect) {
              onTestSelect(test)
            } else if (!isTestAccessible(test.status)) {
              showNotification('Test is still being generated. Please wait...', 'info')
            }
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '0.75rem' }}>
            <div style={{ flex: 1 }}>
              <h3 style={{ margin: 0, marginBottom: '0.5rem' }}>{test.title}</h3>
              <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                Created: {formatDate(test.created_at)}
              </div>
              {test.status === 'draft' && (
                <div style={{ fontSize: '0.75rem', color: 'var(--primary-color)', marginTop: '0.25rem', fontStyle: 'italic' }}>
                  ⏳ Generating questions...
                </div>
              )}
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <div style={{
                padding: '0.25rem 0.75rem',
                borderRadius: 'var(--radius-sm)',
                background: getStatusColor(test.status) + '20',
                color: getStatusColor(test.status),
                fontSize: '0.875rem',
                fontWeight: '500',
                textTransform: 'capitalize',
              }}>
                {getStatusDisplay(test.status)}
              </div>
              {isAdmin && (
                <button
                  onClick={(e) => handleDelete(test.id, e)}
                  disabled={deleting[test.id]}
                  style={{
                    padding: '0.25rem 0.75rem',
                    borderRadius: 'var(--radius-sm)',
                    background: 'var(--error-color)',
                    color: 'white',
                    border: 'none',
                    cursor: deleting[test.id] ? 'not-allowed' : 'pointer',
                    fontSize: '0.875rem',
                    opacity: deleting[test.id] ? 0.6 : 1,
                  }}
                  title="Delete test"
                >
                  {deleting[test.id] ? 'Deleting...' : '🗑️'}
                </button>
              )}
            </div>
          </div>

          {test.status === 'completed' && test.total_score !== null && (
            <div style={{
              marginTop: '0.75rem',
              padding: '0.75rem',
              background: 'var(--bg-secondary)',
              borderRadius: 'var(--radius-sm)',
            }}>
              <div style={{ fontSize: '1.125rem', fontWeight: '600' }}>
                Score: {test.total_score}/{test.max_score} 
                ({test.max_score > 0 ? ((test.total_score / test.max_score) * 100).toFixed(1) : 0}%)
              </div>
              {test.completed_at && (
                <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                  Completed: {formatDate(test.completed_at)}
                </div>
              )}
            </div>
          )}

          {test.status === 'active' && test.started_at && (
            <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '0.75rem' }}>
              Started: {formatDate(test.started_at)}
            </div>
          )}

          {test.time_limit_minutes && (
            <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
              Time limit: {test.time_limit_minutes} minutes
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
