import { useState, useEffect } from 'react'
import { children } from '../services/api'
import { showNotification } from '../utils/notifications'

const TONE_OPTIONS = [
  { value: '', label: 'Default' },
  { value: 'playful', label: 'Playful' },
  { value: 'encouraging', label: 'Encouraging' },
  { value: 'direct', label: 'Direct' },
  { value: 'gentle', label: 'Gentle' },
]
const EXAMPLE_OPTIONS = [
  { value: '', label: 'Default' },
  { value: 'storytelling', label: 'Storytelling' },
  { value: 'step-by-step', label: 'Step-by-step' },
  { value: 'factual', label: 'Factual' },
]
const LANGUAGE_OPTIONS = [
  { value: '', label: 'Default' },
  { value: 'English', label: 'English' },
  { value: 'French', label: 'French' },
  { value: 'Hindi', label: 'Hindi' },
  { value: 'Spanish', label: 'Spanish' },
]

export default function EditChild({ child, onChildUpdated, onCancel }) {
  const [name, setName] = useState('')
  const [pin, setPin] = useState('')
  const [grade, setGrade] = useState('')
  const [age, setAge] = useState('')
  const [loading, setLoading] = useState(false)
  const [preferredLanguage, setPreferredLanguage] = useState('')
  const [interactionTone, setInteractionTone] = useState('')
  const [examplePreferences, setExamplePreferences] = useState('')
  const [interests, setInterests] = useState('')
  const [sensitiveTopicsToAvoid, setSensitiveTopicsToAvoid] = useState('')
  const [preferIndirectGuidance, setPreferIndirectGuidance] = useState(false)

  useEffect(() => {
    if (child) {
      setName(child.name || '')
      setGrade(child.grade || '')
      setAge(child.age ? String(child.age) : '')
      setPin('') // Don't pre-fill PIN for security
      setPreferredLanguage(child.preferred_language || '')
      setInteractionTone(child.interaction_tone || '')
      setExamplePreferences(child.example_preferences || '')
      setInterests(child.interests || '')
      setSensitiveTopicsToAvoid(child.sensitive_topics_to_avoid || '')
      setPreferIndirectGuidance(!!child.prefer_indirect_guidance)
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
        age: age ? parseInt(age) : undefined,
        preferred_language: preferredLanguage.trim() || undefined,
        interaction_tone: interactionTone.trim() || undefined,
        example_preferences: examplePreferences.trim() || undefined,
        interests: interests.trim() || undefined,
        sensitive_topics_to_avoid: sensitiveTopicsToAvoid.trim() || undefined,
        prefer_indirect_guidance: preferIndirectGuidance,
      }
      
      // Only include PIN if it was changed
      if (pin) {
        updateData.pin = pin
      }
      
      const updated = await children.update(child.id, updateData)
      showNotification('Child profile updated successfully', 'success')
      if (onChildUpdated) {
        onChildUpdated(updated)
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

      <h4 style={{ marginTop: '1rem', marginBottom: '0.5rem', fontSize: '1rem' }}>Study preferences</h4>
      <div className="form-group">
        <label htmlFor="preferred_language">Preferred language</label>
        <select
          id="preferred_language"
          value={preferredLanguage}
          onChange={(e) => setPreferredLanguage(e.target.value)}
          disabled={loading}
        >
          {LANGUAGE_OPTIONS.map((opt) => (
            <option key={opt.value || 'default'} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>
      <div className="form-group">
        <label htmlFor="interaction_tone">Interaction tone</label>
        <select
          id="interaction_tone"
          value={interactionTone}
          onChange={(e) => setInteractionTone(e.target.value)}
          disabled={loading}
        >
          {TONE_OPTIONS.map((opt) => (
            <option key={opt.value || 'default'} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>
      <div className="form-group">
        <label htmlFor="example_preferences">Example style</label>
        <select
          id="example_preferences"
          value={examplePreferences}
          onChange={(e) => setExamplePreferences(e.target.value)}
          disabled={loading}
        >
          {EXAMPLE_OPTIONS.map((opt) => (
            <option key={opt.value || 'default'} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>
      <div className="form-group">
        <label htmlFor="interests">Interests (for examples)</label>
        <input
          type="text"
          id="interests"
          value={interests}
          onChange={(e) => setInterests(e.target.value)}
          disabled={loading}
          placeholder="e.g. sports, animals, music"
        />
      </div>
      <div className="form-group">
        <label htmlFor="sensitive_topics">Topics to avoid</label>
        <input
          type="text"
          id="sensitive_topics"
          value={sensitiveTopicsToAvoid}
          onChange={(e) => setSensitiveTopicsToAvoid(e.target.value)}
          disabled={loading}
          placeholder="Optional: topics to avoid in content"
        />
      </div>
      <div className="form-group" style={{ flexDirection: 'row', alignItems: 'center', gap: '0.5rem' }}>
        <input
          type="checkbox"
          id="prefer_indirect"
          checked={preferIndirectGuidance}
          onChange={(e) => setPreferIndirectGuidance(e.target.checked)}
          disabled={loading}
        />
        <label htmlFor="prefer_indirect" style={{ marginBottom: 0 }}>Prefer indirect guidance for emotional topics</label>
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
