import { useState, useEffect } from 'react'
import { admin } from '../services/api'
import { showNotification } from '../utils/notifications'

export default function LLMLogsViewer() {
  const [logs, setLogs] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [expandedLog, setExpandedLog] = useState(null)
  
  // Filters
  const [filters, setFilters] = useState({
    limit: 50,
    offset: 0,
    model: '',
    call_type: '',
    provider: '',
    success: null,
  })
  
  const [total, setTotal] = useState(0)

  useEffect(() => {
    loadLogs()
    loadStats()
  }, [filters.offset, filters.model, filters.call_type, filters.provider, filters.success])

  const loadLogs = async () => {
    try {
      setLoading(true)
      const params = {
        limit: filters.limit,
        offset: filters.offset,
      }
      if (filters.model) params.model = filters.model
      if (filters.call_type) params.call_type = filters.call_type
      if (filters.provider) params.provider = filters.provider
      if (filters.success !== null) params.success = filters.success
      
      const data = await admin.listLLMLogs(params)
      setLogs(data.logs || [])
      setTotal(data.total || 0)
    } catch (error) {
      showNotification(error.message || 'Failed to load LLM logs', 'error')
    } finally {
      setLoading(false)
    }
  }

  const loadStats = async () => {
    try {
      const params = {}
      if (filters.model) params.model = filters.model
      if (filters.call_type) params.call_type = filters.call_type
      
      const data = await admin.getLLMUsageStats(params)
      setStats(data)
    } catch (error) {
      console.error('Failed to load stats:', error)
    }
  }

  const handleFilterChange = (key, value) => {
    setFilters(prev => ({ ...prev, [key]: value, offset: 0 }))
  }

  const formatCost = (cost) => {
    if (!cost) return 'N/A'
    return `$${parseFloat(cost).toFixed(6)}`
  }

  const formatDate = (dateStr) => {
    try {
      // If date string doesn't have timezone info (no 'Z' or +/-), treat it as UTC
      let dateString = dateStr
      if (!dateString.includes('Z') && !dateString.match(/[+-]\d{2}:\d{2}$/)) {
        // Add 'Z' to indicate UTC if not present
        dateString = dateString.endsWith('Z') ? dateString : dateString + 'Z'
      }
      
      const date = new Date(dateString)
      
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

  const truncateText = (text, maxLength = 100) => {
    if (!text) return 'N/A'
    if (text.length <= maxLength) return text
    return text.substring(0, maxLength) + '...'
  }

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text)
    showNotification('Copied to clipboard', 'success')
  }

  const formatMessages = (messages) => {
    if (!messages || !Array.isArray(messages)) return null
    return messages.map((msg, idx) => {
      const role = msg.role || 'unknown'
      const content = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content, null, 2)
      return `[${role.toUpperCase()}]:\n${content}`
    }).join('\n\n---\n\n')
  }

  return (
    <div className="llm-logs-viewer">
      <h3 style={{ marginBottom: '1.5rem' }}>LLM Logs & Usage</h3>
      
      {/* Statistics Summary */}
      {stats && (
        <div className="stats-summary" style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '1rem',
          marginBottom: '2rem',
          padding: '1rem',
          backgroundColor: 'var(--bg-secondary)',
          borderRadius: '8px'
        }}>
          <div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Total Calls</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{stats.total_calls || 0}</div>
          </div>
          <div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Total Tokens</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{(stats.total_tokens || 0).toLocaleString()}</div>
          </div>
          <div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Total Cost</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: 'var(--accent)' }}>
              {formatCost(stats.total_cost_usd)}
            </div>
          </div>
          <div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Avg Latency</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>
              {stats.avg_latency_ms ? `${Math.round(stats.avg_latency_ms)}ms` : 'N/A'}
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="filters" style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
        gap: '1rem',
        marginBottom: '1.5rem',
        padding: '1rem',
        backgroundColor: 'var(--bg-secondary)',
        borderRadius: '8px'
      }}>
        <div className="form-group" style={{ margin: 0 }}>
          <label style={{ fontSize: '0.875rem', marginBottom: '0.25rem' }}>Model</label>
          <select
            value={filters.model}
            onChange={(e) => handleFilterChange('model', e.target.value)}
            style={{ width: '100%', padding: '0.5rem' }}
          >
            <option value="">All Models</option>
            <option value="gpt-5-nano">gpt-5-nano</option>
            <option value="gpt-5-mini">gpt-5-mini</option>
            <option value="gpt-5">gpt-5</option>
            <option value="gpt-5.1">gpt-5.1</option>
            <option value="gpt-5.2">gpt-5.2</option>
          </select>
        </div>
        <div className="form-group" style={{ margin: 0 }}>
          <label style={{ fontSize: '0.875rem', marginBottom: '0.25rem' }}>Call Type</label>
          <select
            value={filters.call_type}
            onChange={(e) => handleFilterChange('call_type', e.target.value)}
            style={{ width: '100%', padding: '0.5rem' }}
          >
            <option value="">All Types</option>
            <option value="llm_service">LLM Service</option>
            <option value="agent_sdk">Agent SDK</option>
            <option value="workflow">Workflow</option>
          </select>
        </div>
        <div className="form-group" style={{ margin: 0 }}>
          <label style={{ fontSize: '0.875rem', marginBottom: '0.25rem' }}>Provider</label>
          <select
            value={filters.provider}
            onChange={(e) => handleFilterChange('provider', e.target.value)}
            style={{ width: '100%', padding: '0.5rem' }}
          >
            <option value="">All Providers</option>
            <option value="openai">OpenAI</option>
            <option value="ollama">Ollama</option>
          </select>
        </div>
        <div className="form-group" style={{ margin: 0 }}>
          <label style={{ fontSize: '0.875rem', marginBottom: '0.25rem' }}>Status</label>
          <select
            value={filters.success === null ? '' : filters.success ? 'true' : 'false'}
            onChange={(e) => handleFilterChange('success', e.target.value === '' ? null : e.target.value === 'true')}
            style={{ width: '100%', padding: '0.5rem' }}
          >
            <option value="">All</option>
            <option value="true">Success</option>
            <option value="false">Failed</option>
          </select>
        </div>
      </div>

      {/* Logs Table */}
      {loading ? (
        <p className="loading-text">Loading logs...</p>
      ) : logs.length === 0 ? (
        <div className="empty-state">
          <p>No LLM logs found.</p>
        </div>
      ) : (
        <>
          <div style={{ marginBottom: '1rem', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            Showing {filters.offset + 1}-{Math.min(filters.offset + filters.limit, total)} of {total} logs
          </div>
          <div className="logs-table" style={{
            backgroundColor: 'var(--bg-secondary)',
            borderRadius: '8px',
            overflow: 'hidden'
          }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ backgroundColor: 'var(--bg-tertiary)', borderBottom: '1px solid var(--border)' }}>
                  <th style={{ padding: '0.75rem', textAlign: 'left', fontSize: '0.875rem' }}>Time</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left', fontSize: '0.875rem' }}>Model</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left', fontSize: '0.875rem' }}>Type</th>
                  <th style={{ padding: '0.75rem', textAlign: 'right', fontSize: '0.875rem' }}>Tokens</th>
                  <th style={{ padding: '0.75rem', textAlign: 'right', fontSize: '0.875rem' }}>Cost</th>
                  <th style={{ padding: '0.75rem', textAlign: 'right', fontSize: '0.875rem' }}>Latency</th>
                  <th style={{ padding: '0.75rem', textAlign: 'center', fontSize: '0.875rem' }}>Status</th>
                  <th style={{ padding: '0.75rem', textAlign: 'center', fontSize: '0.875rem' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '0.75rem', fontSize: '0.875rem' }}>
                      {formatDate(log.created_at)}
                    </td>
                    <td style={{ padding: '0.75rem', fontSize: '0.875rem' }}>{log.model}</td>
                    <td style={{ padding: '0.75rem', fontSize: '0.875rem' }}>
                      <span style={{
                        padding: '0.25rem 0.5rem',
                        borderRadius: '4px',
                        fontSize: '0.75rem',
                        backgroundColor: log.call_type === 'agent_sdk' ? 'var(--accent-light)' : 'var(--bg-tertiary)'
                      }}>
                        {log.call_type}/{log.request_type}
                      </span>
                    </td>
                    <td style={{ padding: '0.75rem', textAlign: 'right', fontSize: '0.875rem' }}>
                      {log.total_tokens ? log.total_tokens.toLocaleString() : 'N/A'}
                    </td>
                    <td style={{ padding: '0.75rem', textAlign: 'right', fontSize: '0.875rem', color: 'var(--accent)' }}>
                      {formatCost(log.total_cost_usd)}
                    </td>
                    <td style={{ padding: '0.75rem', textAlign: 'right', fontSize: '0.875rem' }}>
                      {log.latency_ms ? `${log.latency_ms}ms` : 'N/A'}
                    </td>
                    <td style={{ padding: '0.75rem', textAlign: 'center' }}>
                      <span style={{
                        padding: '0.25rem 0.5rem',
                        borderRadius: '4px',
                        fontSize: '0.75rem',
                        backgroundColor: log.success ? 'var(--success-light)' : 'var(--error-light)',
                        color: log.success ? 'var(--success)' : 'var(--error)'
                      }}>
                        {log.success ? '✓' : '✗'}
                      </span>
                    </td>
                    <td style={{ padding: '0.75rem', textAlign: 'center' }}>
                      <button
                        onClick={() => {
                          const newExpanded = String(expandedLog) === String(log.id) ? null : String(log.id)
                          console.log('Setting expanded log:', newExpanded, 'Current:', expandedLog, 'Log ID:', log.id)
                          setExpandedLog(newExpanded)
                        }}
                        className="btn-secondary btn-small"
                      >
                        {String(expandedLog) === String(log.id) ? 'Hide' : 'View'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Expanded Log Details */}
          {expandedLog && (() => {
            const log = logs.find(l => String(l.id) === String(expandedLog))
            if (!log) {
              console.warn('Log not found for ID:', expandedLog, 'Available IDs:', logs.map(l => l.id))
              return null
            }
            
            // Prepare request content
            const requestContent = log.messages 
              ? formatMessages(log.messages)
              : (log.user_prompt || 'N/A')
            
            // Prepare full request (system + user)
            const fullRequest = [
              log.system_prompt && `[SYSTEM]:\n${log.system_prompt}`,
              requestContent !== 'N/A' && `[USER]:\n${requestContent}`
            ].filter(Boolean).join('\n\n---\n\n')
            
            return (
              <div style={{
                marginTop: '1rem',
                padding: '1.5rem',
                backgroundColor: 'var(--bg-secondary)',
                borderRadius: '8px',
                border: '1px solid var(--border)',
                position: 'relative',
                zIndex: 10
              }}>
                <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                      <h4 style={{ margin: 0 }}>Log Details</h4>
                      <button
                        onClick={() => setExpandedLog(null)}
                        className="btn-secondary btn-small"
                      >
                        Close
                      </button>
                    </div>
                    
                    <div style={{ display: 'grid', gap: '1.5rem' }}>
                      {/* Basic Info */}
                      <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                        gap: '1rem',
                        padding: '1rem',
                        backgroundColor: 'var(--bg-primary)',
                        borderRadius: '4px'
                      }}>
                        <div>
                          <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>ID</div>
                          <div style={{ fontSize: '0.875rem', fontFamily: 'monospace' }}>{log.id.substring(0, 8)}...</div>
                        </div>
                        <div>
                          <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Created</div>
                          <div style={{ fontSize: '0.875rem' }}>{formatDate(log.created_at)}</div>
                        </div>
                        <div>
                          <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Provider/Model</div>
                          <div style={{ fontSize: '0.875rem' }}>{log.provider} / {log.model}</div>
                        </div>
                        <div>
                          <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Type</div>
                          <div style={{ fontSize: '0.875rem' }}>{log.call_type}/{log.request_type}</div>
                        </div>
                        {log.context_source && (
                          <div>
                            <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Context</div>
                            <div style={{ fontSize: '0.875rem' }}>{log.context_source}</div>
                          </div>
                        )}
                        <div>
                          <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Tokens</div>
                          <div style={{ fontSize: '0.875rem' }}>
                            {log.prompt_tokens || 0} + {log.completion_tokens || 0} = {log.total_tokens || 0}
                          </div>
                        </div>
                        <div>
                          <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Cost</div>
                          <div style={{ fontSize: '0.875rem', color: 'var(--accent)', fontWeight: 'bold' }}>
                            {formatCost(log.total_cost_usd)}
                          </div>
                        </div>
                        {log.latency_ms && (
                          <div>
                            <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Latency</div>
                            <div style={{ fontSize: '0.875rem' }}>{log.latency_ms}ms</div>
                          </div>
                        )}
                      </div>

                      {/* REQUEST Section */}
                      <div style={{
                        border: '1px solid var(--border)',
                        borderRadius: '8px',
                        overflow: 'hidden'
                      }}>
                        <div style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          padding: '0.75rem 1rem',
                          backgroundColor: 'var(--bg-tertiary)',
                          borderBottom: '1px solid var(--border)'
                        }}>
                          <strong style={{ fontSize: '1rem' }}>📤 REQUEST</strong>
                          {fullRequest && (
                            <button
                              onClick={() => copyToClipboard(fullRequest)}
                              className="btn-secondary btn-small"
                              style={{ fontSize: '0.75rem' }}
                            >
                              Copy
                            </button>
                          )}
                        </div>
                        <div style={{ padding: '1rem' }}>
                          {log.system_prompt && (
                            <div style={{ marginBottom: '1rem' }}>
                              <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                                System Prompt:
                              </div>
                              <pre style={{
                                margin: 0,
                                padding: '1rem',
                                backgroundColor: 'var(--bg-primary)',
                                borderRadius: '4px',
                                fontSize: '0.875rem',
                                overflow: 'auto',
                                maxHeight: '300px',
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-word'
                              }}>
                                {log.system_prompt}
                              </pre>
                            </div>
                          )}
                          {log.messages && Array.isArray(log.messages) && log.messages.length > 0 ? (
                            <div>
                              <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                                Messages ({log.messages.length}):
                              </div>
                              <pre style={{
                                margin: 0,
                                padding: '1rem',
                                backgroundColor: 'var(--bg-primary)',
                                borderRadius: '4px',
                                fontSize: '0.875rem',
                                overflow: 'auto',
                                maxHeight: '400px',
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-word'
                              }}>
                                {formatMessages(log.messages)}
                              </pre>
                            </div>
                          ) : log.user_prompt ? (
                            <div>
                              <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                                User Prompt:
                              </div>
                              <pre style={{
                                margin: 0,
                                padding: '1rem',
                                backgroundColor: 'var(--bg-primary)',
                                borderRadius: '4px',
                                fontSize: '0.875rem',
                                overflow: 'auto',
                                maxHeight: '400px',
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-word'
                              }}>
                                {log.user_prompt}
                              </pre>
                            </div>
                          ) : (
                            <div style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>No request data available</div>
                          )}
                          {log.temperature !== null && log.temperature !== undefined && (
                            <div style={{ marginTop: '1rem', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                              <strong>Parameters:</strong> Temperature: {log.temperature}
                              {log.max_tokens && `, Max Tokens: ${log.max_tokens}`}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* RESPONSE Section */}
                      <div style={{
                        border: '1px solid var(--border)',
                        borderRadius: '8px',
                        overflow: 'hidden'
                      }}>
                        <div style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          padding: '0.75rem 1rem',
                          backgroundColor: log.success ? 'var(--success-light)' : 'var(--error-light)',
                          borderBottom: '1px solid var(--border)'
                        }}>
                          <strong style={{ fontSize: '1rem', color: log.success ? 'var(--success)' : 'var(--error)' }}>
                            {log.success ? '✓ RESPONSE' : '✗ ERROR'}
                          </strong>
                          {log.response_text && (
                            <button
                              onClick={() => copyToClipboard(log.response_text)}
                              className="btn-secondary btn-small"
                              style={{ fontSize: '0.75rem' }}
                            >
                              Copy
                            </button>
                          )}
                        </div>
                        <div style={{ padding: '1rem' }}>
                          {log.error_message ? (
                            <div style={{ color: 'var(--error)' }}>
                              <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                                Error Message:
                              </div>
                              <pre style={{
                                margin: 0,
                                padding: '1rem',
                                backgroundColor: 'var(--bg-primary)',
                                borderRadius: '4px',
                                fontSize: '0.875rem',
                                overflow: 'auto',
                                maxHeight: '300px',
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-word',
                                color: 'var(--error)'
                              }}>
                                {log.error_message}
                              </pre>
                            </div>
                          ) : log.response_text ? (
                            <div>
                              <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                                Response Text:
                              </div>
                              <pre style={{
                                margin: 0,
                                padding: '1rem',
                                backgroundColor: 'var(--bg-primary)',
                                borderRadius: '4px',
                                fontSize: '0.875rem',
                                overflow: 'auto',
                                maxHeight: '500px',
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-word'
                              }}>
                                {log.response_text}
                              </pre>
                            </div>
                          ) : (
                            <div style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>No response data available</div>
                          )}
                          {log.response_metadata && Object.keys(log.response_metadata).length > 0 && (
                            <div style={{ marginTop: '1rem' }}>
                              <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                                Response Metadata:
                              </div>
                              <pre style={{
                                margin: 0,
                                padding: '1rem',
                                backgroundColor: 'var(--bg-primary)',
                                borderRadius: '4px',
                                fontSize: '0.875rem',
                                overflow: 'auto',
                                maxHeight: '200px',
                                whiteSpace: 'pre-wrap'
                              }}>
                                {JSON.stringify(log.response_metadata, null, 2)}
                              </pre>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Additional Metadata */}
                      {(log.metadata && Object.keys(log.metadata).length > 0) || log.other_params && (
                        <div style={{
                          border: '1px solid var(--border)',
                          borderRadius: '8px',
                          overflow: 'hidden'
                        }}>
                          <div style={{
                            padding: '0.75rem 1rem',
                            backgroundColor: 'var(--bg-tertiary)',
                            borderBottom: '1px solid var(--border)'
                          }}>
                            <strong style={{ fontSize: '0.875rem' }}>Additional Information</strong>
                          </div>
                          <div style={{ padding: '1rem' }}>
                            {log.metadata && Object.keys(log.metadata).length > 0 && (
                              <div style={{ marginBottom: '1rem' }}>
                                <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                                  Metadata:
                                </div>
                                <pre style={{
                                  margin: 0,
                                  padding: '1rem',
                                  backgroundColor: 'var(--bg-primary)',
                                  borderRadius: '4px',
                                  fontSize: '0.875rem',
                                  overflow: 'auto',
                                  maxHeight: '200px',
                                  whiteSpace: 'pre-wrap'
                                }}>
                                  {JSON.stringify(log.metadata, null, 2)}
                                </pre>
                              </div>
                            )}
                            {log.other_params && Object.keys(log.other_params).length > 0 && (
                              <div>
                                <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                                  Other Parameters:
                                </div>
                                <pre style={{
                                  margin: 0,
                                  padding: '1rem',
                                  backgroundColor: 'var(--bg-primary)',
                                  borderRadius: '4px',
                                  fontSize: '0.875rem',
                                  overflow: 'auto',
                                  maxHeight: '200px',
                                  whiteSpace: 'pre-wrap'
                                }}>
                                  {JSON.stringify(log.other_params, null, 2)}
                                </pre>
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
              </div>
            )
          })()}

          {/* Pagination */}
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginTop: '1.5rem'
          }}>
            <button
              onClick={() => handleFilterChange('offset', Math.max(0, filters.offset - filters.limit))}
              disabled={filters.offset === 0}
              className="btn-secondary"
            >
              Previous
            </button>
            <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
              Page {Math.floor(filters.offset / filters.limit) + 1} of {Math.ceil(total / filters.limit)}
            </span>
            <button
              onClick={() => handleFilterChange('offset', filters.offset + filters.limit)}
              disabled={filters.offset + filters.limit >= total}
              className="btn-secondary"
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  )
}
