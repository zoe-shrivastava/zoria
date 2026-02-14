import { useState, useEffect } from 'react'
import { children } from '../services/api'
import { showNotification } from '../utils/notifications'

export default function EditChild({ child, onChildUpdated, onCancel }) {
  const [name, setName] = useState('')
  const [pin, setPin] = useState('')
  const [grade, setGrade] = useState('')
  const [age, setAge] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (child) {
      setName(child.name || '')
      setGrade(child.grade || '')
      setAge(child.age ? String(child.age) : '')
      setPin('') // Don't pre-fill PIN for security
    }
  }, [child])

  const handleSubmit = async (e) => {
    e.preventDefault()
    
    // Validate PIN format if provided
    if (pin && (pin.length < 4 || pin.length > 6)) {
      showNotification('PIN must be 4-6 digits', 'error')
      return
    }
    
    setLoading(true)
    try {
      const updateData = {
        name,
        grade: grade.trim() || undefined,
        age: age ? parseInt(age) : undefined
      }
      
      // Only include PIN if it was changed
      if (pin) {
        updateData.pin = pin
      }
      
      await children.update(child.id, updateData)
      showNotification('Child profile updated successfully', 'success')
      if (onChildUpdated) {
        onChildUpdated()
      }
    } catch (error) {
      showNotification(error.message || 'Failed to update child profile', 'error')
    } finally {
      setLoading(false)
    }
  }

  if (!child) {
    return null
  }

  return (
    <form onSubmit={handleSubmit} className="create-child-form">
      <div className="form-group">
        <label htmlFor="name">Name *</label>
        <input
          type="text"
          id="name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          disabled={loading}
          placeholder="Child's name"
        />
      </div>
      
      <div className="form-group">
        <label htmlFor="pin">PIN (4-6 digits) - Leave blank to keep current</label>
        <input
          type="text"
          id="pin"
          value={pin}
          onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 6))}
          disabled={loading}
          placeholder="Enter new PIN or leave blank"
          maxLength={6}
        />
        <p className="form-hint">Only enter if you want to change the PIN</p>
      </div>
      
      <div className="form-group">
        <label htmlFor="grade">Grade</label>
        <input
          type="text"
          id="grade"
          value={grade}
          onChange={(e) => setGrade(e.target.value)}
          disabled={loading}
          placeholder="e.g., 5th Grade"
        />
      </div>
      
      <div className="form-group">
        <label htmlFor="age">Age</label>
        <input
          type="number"
          id="age"
          value={age}
          onChange={(e) => setAge(e.target.value)}
          disabled={loading}
          placeholder="Enter age"
          min="1"
          max="18"
        />
      </div>
      
      <div style={{ display: 'flex', gap: '0.75rem' }}>
        {onCancel && (
          <button 
            type="button" 
            onClick={onCancel}
            className="btn-secondary"
            disabled={loading}
            style={{ flex: 1 }}
          >
            Cancel
          </button>
        )}
        <button 
          type="submit" 
          disabled={loading || !name} 
          className="btn-primary"
          style={{ flex: 1 }}
        >
          {loading ? 'Updating...' : 'Update Child Profile'}
        </button>
      </div>
    </form>
  )
}
