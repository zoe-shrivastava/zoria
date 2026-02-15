import { useState, useEffect } from 'react'
import MathText from './MathText'

/**
 * FillInBlankWidget - Renders question text with inline input fields for blanks
 * 
 * Expected question format:
 * - Question text should contain blanks marked as: ___, [blank], or {blank}
 * - metadata.blank_count (optional) - number of blanks expected
 * 
 * Answer format: JSON array like ["answer1", "answer2", ...] or delimited string
 */
export default function FillInBlankWidget({ question, answer, onChange, disabled }) {
  const questionText = question?.text || ''
  
  // Detect blank patterns: ___, [blank], {blank}, or similar
  const blankPatterns = [
    /_{3,}/g,           // Three or more underscores
    /\[blank\]/gi,      // [blank] or [BLANK]
    /\{blank\}/gi,      // {blank} or {BLANK}
    /\[_+\]/g,          // [_] or [___]
    /\{_+\}/g           // {_} or {___}
  ]
  
  // Find all blanks in the text
  const [blanks, setBlanks] = useState([])
  const [blankAnswers, setBlankAnswers] = useState([])
  
  useEffect(() => {
    // Find all blank positions
    const foundBlanks = []
    let processedText = questionText
    let offset = 0
    
    // Try each pattern
    for (const pattern of blankPatterns) {
      const matches = [...questionText.matchAll(pattern)]
      if (matches.length > 0) {
        matches.forEach((match, index) => {
          foundBlanks.push({
            index: index,
            start: match.index,
            end: match.index + match[0].length,
            original: match[0]
          })
        })
        break // Use first pattern that finds matches
      }
    }
    
    // Sort by position
    foundBlanks.sort((a, b) => a.start - b.start)
    setBlanks(foundBlanks)
    
    // Initialize blank answers
    const initialAnswers = new Array(foundBlanks.length).fill('')
    setBlankAnswers(initialAnswers)
  }, [questionText])
  
  // Parse existing answer
  useEffect(() => {
    if (answer) {
      try {
        const parsed = typeof answer === 'string' ? JSON.parse(answer) : answer
        if (Array.isArray(parsed)) {
          setBlankAnswers(parsed)
        } else if (typeof parsed === 'object') {
          // If it's an object with keys like "blank1", "blank2", etc.
          const answers = Object.keys(parsed)
            .sort()
            .map(key => parsed[key])
          setBlankAnswers(answers)
        }
      } catch (e) {
        // If parsing fails, try splitting by delimiter
        if (typeof answer === 'string') {
          const parts = answer.split('|').map(s => s.trim())
          if (parts.length === blanks.length) {
            setBlankAnswers(parts)
          }
        }
      }
    } else {
      setBlankAnswers(new Array(blanks.length).fill(''))
    }
  }, [answer, blanks.length])
  
  const handleBlankChange = (blankIndex, value) => {
    const newAnswers = [...blankAnswers]
    newAnswers[blankIndex] = value
    setBlankAnswers(newAnswers)
    
    // Notify parent with JSON array
    const answerString = JSON.stringify(newAnswers)
    onChange(answerString)
  }
  
  // Render question text with input fields
  const renderQuestionWithBlanks = () => {
    if (blanks.length === 0) {
      // No blanks found, render as regular text
      return <MathText text={questionText} />
    }
    
    const parts = []
    let lastIndex = 0
    
    blanks.forEach((blank, blankIndex) => {
      // Add text before blank
      if (blank.start > lastIndex) {
        const textBefore = questionText.substring(lastIndex, blank.start)
        parts.push(
          <span key={`text-${blankIndex}`}>
            <MathText text={textBefore} inline />
          </span>
        )
      }
      
      // Add input field for blank
      parts.push(
        <input
          key={`blank-${blankIndex}`}
          type="text"
          value={blankAnswers[blankIndex] || ''}
          onChange={(e) => handleBlankChange(blankIndex, e.target.value)}
          disabled={disabled}
          placeholder="___"
          style={{
            display: 'inline-block',
            minWidth: '120px',
            padding: '0.5rem',
            margin: '0 0.25rem',
            border: '2px solid var(--primary-color)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '1rem',
            fontFamily: 'inherit',
            background: 'white',
            textAlign: 'center',
            verticalAlign: 'middle'
          }}
        />
      )
      
      lastIndex = blank.end
    })
    
    // Add remaining text after last blank
    if (lastIndex < questionText.length) {
      const textAfter = questionText.substring(lastIndex)
      parts.push(
        <span key="text-after">
          <MathText text={textAfter} inline />
        </span>
      )
    }
    
    return <div style={{ lineHeight: '1.8' }}>{parts}</div>
  }
  
  return (
    <div style={{ marginBottom: '1rem' }}>
      <div style={{
        marginBottom: '0.75rem',
        padding: '0.75rem',
        background: 'var(--primary-color-light)',
        border: '1px solid var(--primary-color)',
        borderRadius: 'var(--radius-md)',
        fontSize: '0.95rem',
        color: 'var(--primary-color)',
        fontWeight: '500',
      }}>
        ✍️ Fill in each blank with the correct answer
      </div>
      
      <div style={{
        padding: '1rem',
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border-color)',
        borderRadius: 'var(--radius-md)',
        marginBottom: '1rem'
      }}>
        {renderQuestionWithBlanks()}
      </div>
      
      {/* Progress indicator */}
      {blanks.length > 0 && (
        <div style={{
          fontSize: '0.875rem',
          color: 'var(--text-muted)',
          fontStyle: 'italic'
        }}>
          {blankAnswers.filter(a => a.trim() !== '').length} of {blanks.length} blanks filled
        </div>
      )}
    </div>
  )
}
