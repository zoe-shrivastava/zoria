import { useState, useEffect } from 'react'
import { documents } from '../services/api'
import { showNotification } from '../utils/notifications'

export default function DocumentUpload({ childId, childList = [], onUploadComplete }) {
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedChildIds, setSelectedChildIds] = useState(childId ? [childId] : [])

  // When childId is set (e.g. from shared "Select child" bar), attach only to that child
  useEffect(() => {
    if (childId) {
      setSelectedChildIds([childId])
    } else if (childList.length > 0) {
      setSelectedChildIds([])
    }
  }, [childId, childList.length])
  
  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0]
    if (selectedFile) {
      if (selectedFile.type !== 'application/pdf') {
        showNotification('Only PDF files are supported', 'error')
        return
      }
      if (selectedFile.size > 10 * 1024 * 1024) {
        showNotification('File size must be less than 10MB', 'error')
        return
      }
      setFile(selectedFile)
      setError(null)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    
    if (!file) {
      const errorMsg = 'Please select a file'
      setError(errorMsg)
      showNotification(errorMsg, 'error')
      return
    }
    
    // When childId is provided (selected child from shared bar), use only that child
    const childIdsToUse = childId ? [childId] : (childList.length > 0 ? selectedChildIds : [])
    
    if (childIdsToUse.length === 0) {
      const errorMsg = 'Please select at least one child profile'
      setError(errorMsg)
      showNotification(errorMsg, 'error')
      return
    }
    
    setLoading(true)
    try {
      await documents.upload(file, childIdsToUse)
      showNotification('Document uploaded successfully. Processing in background...', 'success')
      setFile(null)
      setError(null)
      e.target.reset()
      if (onUploadComplete) {
        onUploadComplete()
      }
    } catch (error) {
      const errorMsg = error.message || 'Failed to upload document'
      setError(errorMsg)
      showNotification(errorMsg, 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="document-upload-form">
      {error && (
        <div className="form-error-alert" role="alert" style={{
          padding: '0.75rem',
          background: '#f8d7da',
          color: '#721c24',
          borderRadius: 'var(--radius-md)',
          marginBottom: '1rem',
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem'
        }}>
          <span>{error}</span>
        </div>
      )}
      
      {/* Only show multi-select when no child is pre-selected (e.g. shared "Select child" bar) */}
      {childList.length > 0 && !childId && (
        <div className="form-group">
          <label>Attach to Child Profiles *</label>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginTop: '0.5rem' }}>
            {childList.map((child) => (
              <label key={child.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={selectedChildIds.includes(child.id)}
                  onChange={(e) => {
                    if (e.target.checked) {
                      setSelectedChildIds([...selectedChildIds, child.id])
                    } else {
                      setSelectedChildIds(selectedChildIds.filter(id => id !== child.id))
                    }
                  }}
                  disabled={loading}
                />
                <span>{child.name} {child.grade && `(Grade ${child.grade})`}</span>
              </label>
            ))}
          </div>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
            Select one or more child profiles to attach this document to.
          </p>
        </div>
      )}
      <div
        className="form-group"
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: '0.75rem',
          marginTop: childList.length > 0 && !childId ? '1rem' : 0,
        }}
      >
        {childId && childList.length > 0 && (
          <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            Document will be attached to the child selected above.
          </span>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexShrink: 0 }}>
          <label htmlFor="file" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', margin: 0 }}>
            <span style={{ fontSize: '0.875rem', whiteSpace: 'nowrap' }}>Select PDF File *</span>
            <input
              type="file"
              id="file"
              accept=".pdf"
              onChange={handleFileChange}
              disabled={loading}
              required
              style={{ fontSize: '0.875rem', maxWidth: '12rem' }}
            />
          </label>
          <button type="submit" disabled={loading || !file} className="btn-primary">
            {loading ? 'Uploading...' : 'Upload PDF'}
          </button>
        </div>
        {file && (
          <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>{file.name}</span>
        )}
        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
          * Document will be processed automatically. Processing may take a minute.
        </span>
      </div>
    </form>
  )
}
