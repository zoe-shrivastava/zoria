import { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { documents, isAuthError } from '../services/api'
import { showNotification } from '../utils/notifications'
import KnowledgeGraphViewer from './KnowledgeGraphViewer'
import './DocumentList.css'

export default function DocumentList({ childId, isChild = false, userRole = null, refreshKey = 0 }) {
  const [documentsList, setDocumentsList] = useState([])
  const [loading, setLoading] = useState(true)
  const [processingDocs, setProcessingDocs] = useState(new Set())
  const [knowledgeGraphData, setKnowledgeGraphData] = useState(null)
  const [showMarkdownModal, setShowMarkdownModal] = useState(false)
  const [showConceptsModal, setShowConceptsModal] = useState(false)
  const [showMdEvaluatorModal, setShowMdEvaluatorModal] = useState(false)
  const [mdEvaluationResult, setMdEvaluationResult] = useState(null)
  const [showKgEvaluatorModal, setShowKgEvaluatorModal] = useState(false)
  const [kgEvaluationResult, setKgEvaluationResult] = useState(null)
  const [selectedDocumentData, setSelectedDocumentData] = useState(null)
  const [childrenMap, setChildrenMap] = useState({}) // Map child_id to child name
  const [showTimestamps, setShowTimestamps] = useState(true)
  const [kgRebuildDocs, setKgRebuildDocs] = useState(new Set())
  const [evaluatingMdDocs, setEvaluatingMdDocs] = useState(new Set())
  const [evaluatingKgDocs, setEvaluatingKgDocs] = useState(new Set())

  useEffect(() => {
    if (childId || isChild || userRole === 'admin') {
      loadDocuments()
    }
  }, [childId, isChild, userRole, refreshKey])

  // Load children data for admin users to show child names
  useEffect(() => {
    if (userRole === 'admin') {
      loadChildren()
    }
  }, [userRole])

  // Normalize API value: only show timestamps when explicitly true (hide for false or string "false")
  const applyDocTimestampSetting = (val) =>
    setShowTimestamps(val === true || val === 'true')

  // Load timestamp display settings (admin-configured for all roles); refetch when page becomes visible
  useEffect(() => {
    const loadTimestampSettings = async () => {
      try {
        const { auth } = await import('../services/api')
        const settings = await auth.getTimestampSettings()
        applyDocTimestampSetting(settings?.show_document_timestamps)
      } catch (error) {
        console.error('Failed to load timestamp settings for documents:', error)
        setShowTimestamps(true)
      }
    }
    loadTimestampSettings()
    const onVisible = () => {
      if (document.visibilityState === 'visible') loadTimestampSettings()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [])

  const loadChildren = async () => {
    try {
      const { admin } = await import('../services/api')
      const childrenData = await admin.listChildren()
      const childrenArray = Array.isArray(childrenData) ? childrenData : []
      // Create a map from child_id to child name
      const map = {}
      childrenArray.forEach(child => {
        map[child.id] = child.name
      })
      setChildrenMap(map)
    } catch (error) {
      console.error('Failed to load children:', error)
      // Don't show error notification for this, just log it
    }
  }

  // Poll for status updates by row (only refresh documents that are still processing)
  useEffect(() => {
    const docsNeedingRefresh = documentsList.filter(doc =>
      doc.status === 'processing' || doc.status === 'parsed' || doc.status === 'uploaded'
    )
    if (docsNeedingRefresh.length === 0) return

    const refreshAllProcessing = () => {
      docsNeedingRefresh.forEach(doc => refreshDocumentStatus(doc.id))
    }

    refreshAllProcessing()
    const interval = setInterval(refreshAllProcessing, 3000)
    return () => clearInterval(interval)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentsList.map(d => `${d.id}:${d.status}`).join(',')])

  const loadDocuments = async () => {
    try {
      setLoading(true)
      let docData
      if (userRole === 'admin') {
        // Admin uses admin API
        const { admin } = await import('../services/api')
        docData = await admin.listDocuments({ limit: 100 })
      } else {
        // Parent/Child use regular documents API
        docData = await documents.list(isChild ? null : childId)
      }
      const docArray = Array.isArray(docData) ? docData : (docData.documents || [])
      setDocumentsList(docArray)
    } catch (error) {
      console.error('Failed to load documents:', error)
      if (!isAuthError(error)) {
        showNotification(error.message || 'Failed to load documents', 'error')
      }
      setDocumentsList([])
    } finally {
      setLoading(false)
    }
  }

  // Refresh status for a single document (by row) without refetching the whole list
  const refreshDocumentStatus = async (docId) => {
    try {
      let data
      if (userRole === 'admin') {
        const { admin } = await import('../services/api')
        data = await admin.getDocument(docId)
      } else {
        data = await documents.get(docId)
      }
      if (data && data.id) {
        setDocumentsList(prev =>
          prev.map(d => (d.id === docId ? { ...d, ...data } : d))
        )
      }
    } catch (error) {
      if (!isAuthError(error)) {
        console.warn(`Failed to refresh status for document ${docId}:`, error)
      }
    }
  }

  const handleDelete = async (docId) => {
    if (!window.confirm('Are you sure you want to delete this document?')) {
      return
    }

    try {
      await documents.delete(docId)
      showNotification('Document deleted successfully', 'success')
      loadDocuments()
    } catch (error) {
      if (!isAuthError(error)) {
        showNotification(error.message || 'Failed to delete document', 'error')
      }
    }
  }

  const handleReprocess = async (docId, docStatus) => {
    const needsPhase1 = !docStatus || docStatus === 'uploaded' || docStatus === 'failed'
    
    if (!window.confirm(
      needsPhase1 
        ? 'This will re-run parsing and processing. Continue?'
        : 'This will reprocess the document (existing data will be cleaned). Continue?'
    )) {
      return
    }

    try {
      setProcessingDocs(prev => new Set(prev).add(docId))
      
      if (userRole === 'admin') {
        // Admin uses admin API
        const { admin } = await import('../services/api')
        await admin.reprocessDocument(docId, true, !needsPhase1)
      } else {
        // Regular users use documents API
        await documents.reprocess(docId, true, !needsPhase1)
      }
      
      showNotification('Document reprocessing started', 'success')
      loadDocuments()
    } catch (error) {
      if (!isAuthError(error)) {
        showNotification(error.message || 'Failed to reprocess document', 'error')
      }
    } finally {
      setProcessingDocs(prev => {
        const next = new Set(prev)
        next.delete(docId)
        return next
      })
    }
  }
  
  const handleRebuildKnowledgeGraph = async (docId) => {
    if (!window.confirm(
      'This will rebuild the knowledge graph (concepts, relationships, questions, chunks, embeddings) from existing markdown/concept JSON.\n\nIt will NOT re-parse the original PDF.\n\nContinue?'
    )) {
      return
    }

    try {
      setKgRebuildDocs(prev => new Set(prev).add(docId))
      const { admin } = await import('../services/api')
      await admin.rebuildKnowledgeGraph(docId)
      showNotification('Knowledge graph rebuild started', 'success')
      loadDocuments()
    } catch (error) {
      if (!isAuthError(error)) {
        showNotification(error.message || 'Failed to rebuild knowledge graph', 'error')
      }
    } finally {
      setKgRebuildDocs(prev => {
        const next = new Set(prev)
        next.delete(docId)
        return next
      })
    }
  }
  
  const [knowledgeGraphDocumentId, setKnowledgeGraphDocumentId] = useState(null)

  const handleViewKnowledgeGraph = async (docId) => {
    try {
      const { admin } = await import('../services/api')
      const kgData = await admin.getKnowledgeGraph(docId)
      setKnowledgeGraphData(kgData)
      setKnowledgeGraphDocumentId(docId)
    } catch (error) {
      if (!isAuthError(error)) {
        showNotification(error.message || 'Failed to load knowledge graph', 'error')
      }
    }
  }

  const handleKnowledgeGraphSwitchMode = async (ingestionOnly) => {
    if (!knowledgeGraphDocumentId) return
    try {
      const { admin } = await import('../services/api')
      const kgData = await admin.getKnowledgeGraph(knowledgeGraphDocumentId, ingestionOnly)
      setKnowledgeGraphData(kgData)
    } catch (error) {
      if (!isAuthError(error)) {
        showNotification(error.message || 'Failed to load knowledge graph', 'error')
      }
    }
  }

  const handleViewMarkdown = async (docId) => {
    try {
      const { admin } = await import('../services/api')
      const docData = await admin.getDocument(docId)
      console.log('Document data for markdown:', docData)
      setSelectedDocumentData({
        type: 'markdown',
        content: docData.markdown_content || 'No markdown content available',
        filename: docData.filename
      })
      setShowMarkdownModal(true)
    } catch (error) {
      console.error('Error loading markdown:', error)
      if (!isAuthError(error)) {
        showNotification(error.message || 'Failed to load markdown', 'error')
      }
    }
  }

  const handleViewConcepts = async (docId) => {
    try {
      const { admin } = await import('../services/api')
      const docData = await admin.getDocument(docId)
      console.log('Document data for concepts:', docData)
      setSelectedDocumentData({
        type: 'concepts',
        content: docData.concepts || null,
        filename: docData.filename
      })
      setShowConceptsModal(true)
    } catch (error) {
      console.error('Error loading concepts:', error)
      if (!isAuthError(error)) {
        showNotification(error.message || 'Failed to load concepts', 'error')
      }
    }
  }

  const handleEvaluateMdConcepts = async (docId) => {
    try {
      setEvaluatingMdDocs(prev => new Set(prev).add(docId))
      const { admin } = await import('../services/api')
      const result = await admin.evaluateMarkdownToConcepts(docId)
      setMdEvaluationResult(result)
      setShowMdEvaluatorModal(true)
    } catch (error) {
      console.error('Error evaluating MD -> Concepts:', error)
      if (!isAuthError(error)) {
        showNotification(error.message || 'Failed to evaluate MD -> Concepts', 'error')
      }
    } finally {
      setEvaluatingMdDocs(prev => {
        const updated = new Set(prev)
        updated.delete(docId)
        return updated
      })
    }
  }

  const handleEvaluateConceptsKg = async (docId) => {
    try {
      setEvaluatingKgDocs(prev => new Set(prev).add(docId))
      const { admin } = await import('../services/api')
      const result = await admin.evaluateConceptsToKnowledgeGraph(docId)
      setKgEvaluationResult(result)
      setShowKgEvaluatorModal(true)
    } catch (error) {
      console.error('Error evaluating Concepts -> KG:', error)
      if (!isAuthError(error)) {
        showNotification(error.message || 'Failed to evaluate Concepts -> KG', 'error')
      }
    } finally {
      setEvaluatingKgDocs(prev => {
        const updated = new Set(prev)
        updated.delete(docId)
        return updated
      })
    }
  }

  const getStatusBadge = (status) => {
    const statusColors = {
      uploaded: { bg: '#fff3cd', color: '#856404' },
      parsed: { bg: '#d1ecf1', color: '#0c5460' },
      processing: { bg: '#d4edda', color: '#155724' },
      ready: { bg: '#d4edda', color: '#155724' },
      failed: { bg: '#f8d7da', color: '#721c24' },
    }
    
    const colors = statusColors[status] || { bg: '#e2e3e5', color: '#383d41' }
    
    return (
      <span style={{
        padding: '0.25rem 0.5rem',
        borderRadius: '0.25rem',
        fontSize: '0.75rem',
        fontWeight: 500,
        background: colors.bg,
        color: colors.color,
        textTransform: 'capitalize'
      }}>
        {status || 'unknown'}
      </span>
    )
  }

  const formatDate = (dateString) => {
    if (!dateString) return 'Unknown'
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
      return dateString
    }
  }

  const getChildName = (childId) => {
    return childrenMap[childId] || childId.substring(0, 8) + '...'
  }

  if (loading) {
    return <p className="loading-text">Loading documents...</p>
  }

  if (documentsList.length === 0) {
    return (
      <div className="empty-state">
        <p>No documents uploaded yet.</p>
        <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
          Upload a PDF document to get started.
        </p>
      </div>
    )
  }

  return (
    <>
    {knowledgeGraphData && createPortal(
      <KnowledgeGraphViewer 
        data={knowledgeGraphData} 
        onClose={() => { setKnowledgeGraphData(null); setKnowledgeGraphDocumentId(null) }}
        onSwitchMode={handleKnowledgeGraphSwitchMode}
        userRole={userRole}
      />,
      document.body
    )}
    {(showMarkdownModal || showConceptsModal) && selectedDocumentData && createPortal(
      <DocumentDataModal
        type={selectedDocumentData.type}
        content={selectedDocumentData.content}
        filename={selectedDocumentData.filename}
        onClose={() => {
          setShowMarkdownModal(false)
          setShowConceptsModal(false)
          setSelectedDocumentData(null)
        }}
      />,
      document.body
    )}
    {showMdEvaluatorModal && mdEvaluationResult && createPortal(
      <DocumentMdEvaluatorModal
        result={mdEvaluationResult}
        onClose={() => {
          setShowMdEvaluatorModal(false)
          setMdEvaluationResult(null)
        }}
      />,
      document.body
    )}
    {showKgEvaluatorModal && kgEvaluationResult && createPortal(
      <DocumentKgEvaluatorModal
        result={kgEvaluationResult}
        onClose={() => {
          setShowKgEvaluatorModal(false)
          setKgEvaluationResult(null)
        }}
      />,
      document.body
    )}
      <div className="document-list">
      <div style={{ marginBottom: '1rem', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
        {documentsList.length} {documentsList.length === 1 ? 'document' : 'documents'} uploaded
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        {documentsList.map((doc) => (
          <div
            key={doc.id}
            style={{
              padding: '1rem',
              background: 'var(--bg-secondary)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-color)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: '1rem'
            }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 500, marginBottom: '0.25rem', wordBreak: 'break-word' }}>
                {doc.filename || 'Untitled Document'}
              </div>
              <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', display: 'flex', gap: '0.5rem', alignItems: 'center', marginTop: '0.25rem', flexWrap: 'wrap' }}>
                {showTimestamps && (
                  <span>Uploaded: {formatDate(doc.uploaded_at)}</span>
                )}
                {doc.status && getStatusBadge(doc.status)}
              </div>
              {/* Show linked children for admin users */}
              {userRole === 'admin' && (() => {
                // Get child IDs from either child_ids array or legacy child_id field
                const childIds = doc.child_ids && doc.child_ids.length > 0 
                  ? doc.child_ids 
                  : (doc.child_id ? [doc.child_id] : [])
                
                if (childIds.length === 0) {
                  return (
                    <div style={{ 
                      fontSize: '0.875rem', 
                      color: 'var(--text-muted)', 
                      marginTop: '0.5rem',
                      fontStyle: 'italic'
                    }}>
                      Not linked to any child
                    </div>
                  )
                }
                
                return (
                  <div style={{ 
                    marginTop: '0.5rem',
                    padding: '0.5rem',
                    background: 'var(--bg-primary)',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-color)'
                  }}>
                    <div style={{ 
                      fontSize: '0.875rem', 
                      fontWeight: '600',
                      marginBottom: '0.25rem',
                      color: 'var(--text-primary)'
                    }}>
                      Linked to {childIds.length === 1 ? 'Child' : 'Children'}:
                    </div>
                    <div style={{ 
                      display: 'flex',
                      flexWrap: 'wrap',
                      gap: '0.5rem'
                    }}>
                      {childIds.map((childId) => (
                        <span
                          key={childId}
                          style={{
                            display: 'inline-block',
                            padding: '0.25rem 0.5rem',
                            background: 'var(--accent-light)',
                            color: 'var(--accent)',
                            borderRadius: 'var(--radius-sm)',
                            fontSize: '0.875rem',
                            fontWeight: '500'
                          }}
                        >
                          {getChildName(childId)}
                        </span>
                      ))}
                    </div>
                  </div>
                )
              })()}
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              {(() => {
                const isProcessing = doc.status === 'processing' || processingDocs.has(doc.id) || kgRebuildDocs.has(doc.id)
                const isEvaluatingMd = evaluatingMdDocs.has(doc.id)
                const isEvaluatingKg = evaluatingKgDocs.has(doc.id)
                return (
                  <>
                    {/* Show reprocess button only for admin, not for parent */}
                    {userRole === 'admin' && (doc.status === 'uploaded' || doc.status === 'failed' || doc.status === 'parsed' || doc.status === 'ready') && (
                      <button
                        onClick={() => handleReprocess(doc.id, doc.status)}
                        disabled={isProcessing}
                        className="btn-secondary btn-small"
                        style={{ 
                          background: 'var(--primary-bg, #007bff)', 
                          color: 'white',
                          opacity: isProcessing ? 0.6 : 1,
                          cursor: isProcessing ? 'not-allowed' : 'pointer'
                        }}
                      >
                        {isProcessing ? 'Processing...' : 'Reprocess'}
                      </button>
                    )}
                    {/* Show admin buttons for ready documents */}
                    {userRole === 'admin' && doc.status === 'ready' && (
                      <>
                        <button
                          onClick={() => handleViewKnowledgeGraph(doc.id)}
                          disabled={isProcessing}
                          className="btn-secondary btn-small"
                          style={{ 
                            background: 'var(--success-bg, #28a745)', 
                            color: 'white',
                            opacity: isProcessing ? 0.6 : 1,
                            cursor: isProcessing ? 'not-allowed' : 'pointer'
                          }}
                        >
                          View Graph
                        </button>
                        <button
                          onClick={() => handleRebuildKnowledgeGraph(doc.id)}
                          disabled={isProcessing}
                          className="btn-secondary btn-small"
                          style={{ 
                            background: 'var(--warning-bg, #ffc107)', 
                            color: 'white',
                            opacity: isProcessing ? 0.6 : 1,
                            cursor: isProcessing ? 'not-allowed' : 'pointer'
                          }}
                          title="Rebuild knowledge graph from existing markdown/concepts"
                        >
                          Rebuild KG
                        </button>
                        <button
                          onClick={() => handleViewMarkdown(doc.id)}
                          disabled={isProcessing}
                          className="btn-secondary btn-small"
                          style={{ 
                            background: 'var(--info-bg, #17a2b8)', 
                            color: 'white',
                            fontSize: '0.85rem',
                            opacity: isProcessing ? 0.6 : 1,
                            cursor: isProcessing ? 'not-allowed' : 'pointer'
                          }}
                          title="View Markdown"
                        >
                          Markdown
                        </button>
                        <button
                          onClick={() => handleViewConcepts(doc.id)}
                          disabled={isProcessing || isEvaluatingMd || isEvaluatingKg}
                          className="btn-secondary btn-small"
                          style={{ 
                            background: 'var(--warning-bg, #ffc107)', 
                            color: 'white',
                            fontSize: '0.85rem',
                            opacity: isProcessing ? 0.6 : 1,
                            cursor: isProcessing ? 'not-allowed' : 'pointer'
                          }}
                          title="View Concepts JSON"
                        >
                          Concepts
                        </button>
                        <button
                          onClick={() => handleEvaluateMdConcepts(doc.id)}
                          disabled={isProcessing || isEvaluatingMd || isEvaluatingKg}
                          className="btn-secondary btn-small"
                          style={{
                            background: 'var(--primary-bg, #007bff)',
                            color: 'white',
                            fontSize: '0.85rem',
                            opacity: (isProcessing || isEvaluatingMd || isEvaluatingKg) ? 0.6 : 1,
                            cursor: (isProcessing || isEvaluatingMd || isEvaluatingKg) ? 'not-allowed' : 'pointer'
                          }}
                          title="Evaluate Markdown to Concepts"
                        >
                          {isEvaluatingMd ? 'Evaluating...' : 'Eval MD->Concepts'}
                        </button>
                        <button
                          onClick={() => handleEvaluateConceptsKg(doc.id)}
                          disabled={isProcessing || isEvaluatingMd || isEvaluatingKg}
                          className="btn-secondary btn-small"
                          style={{
                            background: 'var(--secondary-bg, #6c757d)',
                            color: 'white',
                            fontSize: '0.85rem',
                            opacity: (isProcessing || isEvaluatingMd || isEvaluatingKg) ? 0.6 : 1,
                            cursor: (isProcessing || isEvaluatingMd || isEvaluatingKg) ? 'not-allowed' : 'pointer'
                          }}
                          title="Evaluate Concepts to Knowledge Graph"
                        >
                          {isEvaluatingKg ? 'Evaluating...' : 'Eval Concepts->KG'}
                        </button>
                      </>
                    )}
                    <button
                      onClick={() => handleDelete(doc.id)}
                      disabled={isProcessing}
                      className="btn-secondary btn-small"
                      style={{ 
                        background: 'var(--error-bg, #f8d7da)', 
                        color: 'var(--error-text, #721c24)',
                        opacity: isProcessing ? 0.6 : 1,
                        cursor: isProcessing ? 'not-allowed' : 'pointer'
                      }}
                    >
                      Delete
                    </button>
                  </>
                )
              })()}
            </div>
          </div>
        ))}
      </div>
    </div>
    </>
  )
}

// Document Data Modal Component
function DocumentDataModal({ type, content, filename, onClose }) {
  const [copied, setCopied] = useState(false)

  const conceptsJsonString = content ? JSON.stringify(content, null, 2) : null
  const displayContent = type === 'concepts'
    ? (conceptsJsonString ? conceptsJsonString : 'No concepts data available')
    : (content || 'No markdown content available')

  const title = type === 'concepts' ? 'Concepts JSON' : 'Markdown Content'

  const handleCopyConceptsJson = async () => {
    if (!conceptsJsonString) return

    try {
      await navigator.clipboard.writeText(conceptsJsonString)
      setCopied(true)
      showNotification('Concepts JSON copied to clipboard!', 'success')
      setTimeout(() => setCopied(false), 2000)
      return
    } catch (err) {
      // Fallback for environments where clipboard API is unavailable/blocked.
      try {
        const textarea = document.createElement('textarea')
        textarea.value = conceptsJsonString
        textarea.style.position = 'fixed'
        textarea.style.left = '-9999px'
        textarea.style.top = '-9999px'
        textarea.style.opacity = '0'
        document.body.appendChild(textarea)
        textarea.focus()
        textarea.select()
        const ok = document.execCommand('copy')
        document.body.removeChild(textarea)

        if (ok) {
          setCopied(true)
          showNotification('Concepts JSON copied to clipboard!', 'success')
          setTimeout(() => setCopied(false), 2000)
        } else {
          console.error('Copy failed via fallback execCommand')
          showNotification('Copy failed. Please try again.', 'error')
        }
      } catch (e) {
        console.error('Copy failed:', e)
        showNotification('Copy failed. Please try again.', 'error')
      }
    }
  }

  return (
    <div className="document-data-modal-overlay" onClick={onClose}>
      <div className="document-data-modal" onClick={(e) => e.stopPropagation()}>
        <div className="document-data-header">
          <div>
            <h2>{title}</h2>
            <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.9rem', color: 'var(--text-muted, #6b7280)' }}>
              {filename}
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            {type === 'concepts' && conceptsJsonString && (
              <button
                type="button"
                className="document-data-copy-json"
                onClick={handleCopyConceptsJson}
                title="Copy Concepts JSON to clipboard"
              >
                {copied ? 'Copied!' : 'Copy JSON'}
              </button>
            )}
            <button className="document-data-close" onClick={onClose} title="Close">Close</button>
          </div>
        </div>
        <div className="document-data-content">
          <pre>{displayContent}</pre>
        </div>
      </div>
    </div>
  )
}

async function copyJsonToClipboard(text) {
  if (!text) return false
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch (_) {
    try {
      const textarea = document.createElement('textarea')
      textarea.value = text
      textarea.style.position = 'fixed'
      textarea.style.left = '-9999px'
      textarea.style.top = '-9999px'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.focus()
      textarea.select()
      const ok = document.execCommand('copy')
      document.body.removeChild(textarea)
      return !!ok
    } catch {
      return false
    }
  }
}

function DocumentMdEvaluatorModal({ result, onClose }) {
  const [copied, setCopied] = useState(false)
  const reportJsonString = result ? JSON.stringify(result, null, 2) : ''
  const m2c = result?.report || {}
  const m2cAttrs = m2c?.attributes || {}
  const flags = m2c?.quality_flags || {}

  const handleCopyReport = async () => {
    const ok = await copyJsonToClipboard(reportJsonString)
    if (ok) {
      setCopied(true)
      showNotification('Evaluator report copied to clipboard!', 'success')
      setTimeout(() => setCopied(false), 2000)
    } else {
      showNotification('Copy failed. Please try again.', 'error')
    }
  }

  return (
    <div className="document-data-modal-overlay" onClick={onClose}>
      <div className="document-data-modal" onClick={(e) => e.stopPropagation()}>
        <div className="document-data-header">
          <div>
            <h2>MD -> Concepts Evaluator</h2>
            <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.9rem', color: 'var(--text-muted, #6b7280)' }}>
              {result?.filename || 'Unknown file'}
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <button
              type="button"
              className="document-data-copy-json"
              onClick={handleCopyReport}
              title="Copy evaluator report JSON"
            >
              {copied ? 'Copied!' : 'Copy Report'}
            </button>
            <button className="document-data-close" onClick={onClose} title="Close">Close</button>
          </div>
        </div>
        <div className="document-data-content">
          <div style={{ marginBottom: '1rem' }}><strong>Expected vs Actual</strong></div>
          <div style={{ marginBottom: '0.75rem', fontSize: '0.95rem' }}>
            Concepts: {m2cAttrs?.concepts?.expected ?? 0} / {m2cAttrs?.concepts?.actual ?? 0} |{' '}
            Questions: {m2cAttrs?.questions?.expected ?? 0} / {m2cAttrs?.questions?.actual ?? 0} |{' '}
            Unique Question Types: {m2cAttrs?.unique_question_types?.expected ?? 0} / {m2cAttrs?.unique_question_types?.actual ?? 0}
          </div>
          <div style={{ marginBottom: '1rem', fontSize: '0.95rem' }}>
            Topic Count: {m2cAttrs?.topic_count?.expected ?? 0} / {m2cAttrs?.topic_count?.actual ?? 0} |{' '}
            Subtopic Count: {m2cAttrs?.subtopic_count?.expected ?? 0} / {m2cAttrs?.subtopic_count?.actual ?? 0} |{' '}
            Visual Description Links: {m2cAttrs?.visual_description_links?.expected ?? 0} / {m2cAttrs?.visual_description_links?.actual ?? 0}
          </div>

          <div style={{ marginBottom: '1rem' }}>
            <strong>Flags:</strong>{' '}
            {Object.entries(flags).map(([key, value]) => `${key}=${value}`).join(' | ') || 'none'}
          </div>
          <pre>{reportJsonString}</pre>
        </div>
      </div>
    </div>
  )
}

function DocumentKgEvaluatorModal({ result, onClose }) {
  const [copied, setCopied] = useState(false)
  const reportJsonString = result ? JSON.stringify(result, null, 2) : ''
  const c2kg = result?.report || {}
  const c2kgAttrs = c2kg?.attributes || {}
  const availability = c2kg?.availability || {}
  const snapshot = c2kg?.snapshot || null

  const handleCopyReport = async () => {
    const ok = await copyJsonToClipboard(reportJsonString)
    if (ok) {
      setCopied(true)
      showNotification('Evaluator report copied to clipboard!', 'success')
      setTimeout(() => setCopied(false), 2000)
    } else {
      showNotification('Copy failed. Please try again.', 'error')
    }
  }

  return (
    <div className="document-data-modal-overlay" onClick={onClose}>
      <div className="document-data-modal" onClick={(e) => e.stopPropagation()}>
        <div className="document-data-header">
          <div>
            <h2>Concepts -> KG Evaluator</h2>
            <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.9rem', color: 'var(--text-muted, #6b7280)' }}>
              {result?.filename || 'Unknown file'}
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <button type="button" className="document-data-copy-json" onClick={handleCopyReport} title="Copy evaluator report JSON">
              {copied ? 'Copied!' : 'Copy Report'}
            </button>
            <button className="document-data-close" onClick={onClose} title="Close">Close</button>
          </div>
        </div>
        <div className="document-data-content">
          <div style={{ marginBottom: '1rem' }}><strong>Expected vs Actual</strong></div>
          <div style={{ marginBottom: '0.75rem', fontSize: '0.95rem' }}>
            All Nodes: {c2kgAttrs?.all_nodes?.expected ?? 0} / {c2kgAttrs?.all_nodes?.actual ?? 0} |{' '}
            All Edges: {c2kgAttrs?.all_edges?.expected ?? 0} / {c2kgAttrs?.all_edges?.actual ?? 0}
          </div>
          <div style={{ marginBottom: '0.75rem', fontSize: '0.95rem' }}>
            Difficulty (expected): {JSON.stringify(c2kgAttrs?.difficulty?.expected || {})}
          </div>
          <div style={{ marginBottom: '0.75rem', fontSize: '0.95rem' }}>
            Difficulty (actual): {JSON.stringify(c2kgAttrs?.difficulty?.actual || {})}
          </div>
          <div style={{ marginBottom: '1rem', fontSize: '0.95rem' }}>
            Prerequisites (expected): {JSON.stringify(c2kgAttrs?.prerequisites?.expected || {})}
            <br />
            Prerequisites (actual): {JSON.stringify(c2kgAttrs?.prerequisites?.actual || {})}
          </div>
          <div style={{ marginBottom: '1rem', fontSize: '0.95rem' }}>
            Mode: {snapshot?.id ? 'Snapshot' : 'Live KG'}
            {snapshot?.id ? (
              <>
                {' '}| Snapshot ID: <code>{snapshot.id}</code>
                {' '}| Run Type: {snapshot.run_type || 'unknown'}
              </>
            ) : (
              <> | ingestion_only: {String(availability.ingestion_only ?? true)}</>
            )}
          </div>
          {!availability.available && (
            <div style={{ marginBottom: '1rem', color: 'var(--text-muted)' }}>
              {availability.reason || 'Knowledge graph summary is not available yet.'}
            </div>
          )}
          <pre>{reportJsonString}</pre>
        </div>
      </div>
    </div>
  )
}
