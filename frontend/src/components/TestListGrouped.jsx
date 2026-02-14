import { useState, useEffect } from 'react'
import { tests, isAuthError } from '../services/api'
import { showNotification } from '../utils/notifications'
import LoadingSpinner from './LoadingSpinner'
import TestList from './TestList'

export default function TestListGrouped({ statusFilter = null, onTestSelect, isAdmin = false, onTestDeleted, refreshKey = 0 }) {
  const [groupedTests, setGroupedTests] = useState({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadGroupedTests()
  }, [statusFilter, refreshKey])

  const loadGroupedTests = async () => {
    try {
      setLoading(true)
      const data = await tests.listAllGrouped(statusFilter)
      setGroupedTests(data || {})
    } catch (error) {
      if (!isAuthError(error)) {
        showNotification(error.message || 'Failed to load tests', 'error')
      }
    } finally {
      setLoading(false)
    }
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

  const handleDelete = async (testId) => {
    try {
      await tests.delete(testId)
      showNotification('Test deleted successfully', 'success')
      if (onTestDeleted) {
        onTestDeleted(testId)
      }
      // Reload grouped tests
      loadGroupedTests()
    } catch (error) {
      if (!isAuthError(error)) {
        showNotification(error.message || 'Failed to delete test', 'error')
      }
    }
  }

  if (loading) {
    return <LoadingSpinner />
  }

  const childIds = Object.keys(groupedTests)
  if (childIds.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
        <p>No tests found{statusFilter ? ` with status "${statusFilter}"` : ''}.</p>
      </div>
    )
  }

  return (
    <div className="test-list-grouped">
      {childIds.map((childId) => {
        const group = groupedTests[childId]
        if (!group || !group.tests || group.tests.length === 0) return null

        return (
          <div
            key={childId}
            style={{
              marginBottom: '2rem',
              border: '1px solid var(--border-color)',
              borderRadius: 'var(--radius-md)',
              overflow: 'hidden',
            }}
          >
            {/* Child Header */}
            <div
              style={{
                background: 'linear-gradient(135deg, var(--primary-color) 0%, var(--primary-color-dark) 100%)',
                color: 'white',
                padding: '1.25rem 1.5rem',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                borderBottom: '3px solid rgba(255, 255, 255, 0.2)',
              }}
            >
              <div>
                <div style={{ fontSize: '0.75rem', opacity: 0.8, marginBottom: '0.25rem', textTransform: 'uppercase', letterSpacing: '1px' }}>
                  Child Profile
                </div>
                <h3 style={{ margin: 0, fontSize: '1.5rem', fontWeight: '700' }}>
                  {group.child_name || 'Unknown Child'}
                </h3>
                {group.child_grade && (
                  <div style={{ fontSize: '0.875rem', opacity: 0.95, marginTop: '0.5rem', fontWeight: '500' }}>
                    📚 Grade {group.child_grade}
                  </div>
                )}
              </div>
              <div style={{ 
                fontSize: '1rem', 
                opacity: 0.95, 
                fontWeight: '600',
                background: 'rgba(255, 255, 255, 0.2)',
                padding: '0.5rem 1rem',
                borderRadius: 'var(--radius-md)',
                backdropFilter: 'blur(10px)'
              }}>
                {group.total || group.tests.length} test{group.total !== 1 ? 's' : ''}
              </div>
            </div>

            {/* Tests List */}
            <div style={{ padding: '1rem', background: 'var(--bg-secondary)' }}>
              {group.tests.map((test) => (
                <div
                  key={test.id}
                  style={{
                    background: 'var(--bg-tertiary)',
                    border: '1px solid var(--border-color)',
                    borderRadius: 'var(--radius-md)',
                    padding: '1rem',
                    marginBottom: '0.75rem',
                    cursor: test.status !== 'draft' ? 'pointer' : 'not-allowed',
                    transition: 'all 0.2s',
                    opacity: test.status !== 'draft' ? 1 : 0.7,
                  }}
                  onMouseEnter={(e) => {
                    if (test.status !== 'draft') {
                      e.currentTarget.style.borderColor = 'var(--primary-color)'
                      e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)'
                    }
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = 'var(--border-color)'
                    e.currentTarget.style.boxShadow = 'none'
                  }}
                  onClick={() => {
                    if (test.status !== 'draft' && onTestSelect) {
                      onTestSelect(test)
                    } else if (test.status === 'draft') {
                      showNotification('Test is still being generated. Please wait...', 'info')
                    }
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                        <span style={{ 
                          fontSize: '0.75rem', 
                          fontWeight: '600', 
                          color: 'var(--primary-color)',
                          background: 'var(--primary-color-light)',
                          padding: '0.25rem 0.5rem',
                          borderRadius: 'var(--radius-sm)',
                          textTransform: 'uppercase',
                          letterSpacing: '0.5px'
                        }}>
                          {group.child_name || 'Unknown Child'}
                        </span>
                        {group.child_grade && (
                          <span style={{ 
                            fontSize: '0.75rem', 
                            color: 'var(--text-muted)',
                            background: 'var(--bg-secondary)',
                            padding: '0.25rem 0.5rem',
                            borderRadius: 'var(--radius-sm)'
                          }}>
                            Grade {group.child_grade}
                          </span>
                        )}
                      </div>
                      <h4 style={{ margin: 0, marginBottom: '0.5rem', fontSize: '1rem' }}>{test.title}</h4>
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
                      <div
                        style={{
                          padding: '0.25rem 0.75rem',
                          borderRadius: 'var(--radius-sm)',
                          background:
                            (test.status === 'active' ? 'var(--warning-color)' :
                             test.status === 'completed' ? 'var(--success-color)' :
                             test.status === 'draft' ? 'var(--primary-color)' :
                             'var(--text-muted)') + '20',
                          color:
                            test.status === 'active' ? 'var(--warning-color)' :
                            test.status === 'completed' ? 'var(--success-color)' :
                            test.status === 'draft' ? 'var(--primary-color)' :
                            'var(--text-muted)',
                          fontSize: '0.875rem',
                          fontWeight: '500',
                          textTransform: 'capitalize',
                        }}
                      >
                        {test.status === 'draft' ? 'Processing' : test.status}
                      </div>
                      {isAdmin && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            if (window.confirm(`Are you sure you want to delete test "${test.title}"?`)) {
                              handleDelete(test.id)
                            }
                          }}
                          style={{
                            padding: '0.25rem 0.75rem',
                            borderRadius: 'var(--radius-sm)',
                            background: 'var(--error-color)',
                            color: 'white',
                            border: 'none',
                            cursor: 'pointer',
                            fontSize: '0.875rem',
                          }}
                          title="Delete test"
                        >
                          🗑️
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}
