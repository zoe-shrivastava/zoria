import { useState } from 'react'
import { children } from '../services/api'
import { showNotification } from '../utils/notifications'

export default function CreateChild({ onChildCreated, onCancel }) {
  const [name, setName] = useState('')
  const [pin, setPin] = useState('')
  const [grade, setGrade] = useState('')
  const [age, setAge] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    
    // Validate PIN format
    if (!pin || pin.length < 4 || pin.length > 6) {
      showNotification('PIN must be 4-6 digits', 'error')
      return
    }
    
    setLoading(true)
    try {
      await children.create({
        name,
        pin,
        grade: grade.trim() || undefined,
        age: age ? parseInt(age) : undefined
      })
      showNotification('Child profile created successfully', 'success')
      // Reset form
      setName('')
      setPin('')
      setGrade('')
      setAge('')
      if (onChildCreated) {
        onChildCreated()
      }
    } catch (error) {
      showNotification(error.message || 'Failed to create child profile', 'error')
    } finally {
      setLoading(false)
    }
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
        <label htmlFor="pin">PIN * (4-6 digits)</label>
        <input
          type="text"
          id="pin"
          value={pin}
          onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 6))}
          disabled={loading}
          placeholder="4-6 digit PIN"
          maxLength={6}
          required
        />
        <p className="form-hint">Child will use this PIN to log in</p>
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
          disabled={loading || !name || !pin} 
          className="btn-primary"
          style={{ flex: 1 }}
        >
          {loading ? 'Creating...' : 'Create Child Profile'}
        </button>
      </div>
    </form>
  )
}
