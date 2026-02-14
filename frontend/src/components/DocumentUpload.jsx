import { useState } from 'react'
import { documents } from '../services/api'
import { showNotification } from '../utils/notifications'

export default function DocumentUpload({ childId, childList = [], onUploadComplete }) {
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedChildIds, setSelectedChildIds] = useState(childId ? [childId] : [])
  
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
    
    // For parents with multiple children, require at least one selection
    // For single child or child users, use childId
    const childIdsToUse = childList.length > 0 ? selectedChildIds : (childId ? [childId] : [])
    
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
          <span>⚠</span>
          <span>{error}</span>
        </div>
      )}
      
      {childList.length > 0 && (
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
      
      <div className="form-group">
        <label htmlFor="file">Select PDF File *</label>
        <input
          type="file"
          id="file"
          accept=".pdf"
          onChange={handleFileChange}
          disabled={loading}
          required
        />
        {file && <p className="file-info" style={{ marginTop: '0.5rem', color: 'var(--text-muted)' }}>Selected: {file.name}</p>}
      </div>
      
      <button type="submit" disabled={loading || !file} className="btn-primary">
        {loading ? 'Uploading...' : 'Upload PDF'}
      </button>
      
      <p className="form-hint" style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '0.5rem', fontStyle: 'italic' }}>
        * Document will be processed automatically. Processing may take a minute.
      </p>
    </form>
  )
}
