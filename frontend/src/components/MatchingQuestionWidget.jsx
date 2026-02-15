import { useState, useEffect } from 'react'
import MathText from './MathText'

/**
 * MatchingQuestionWidget - Allows students to match items from two columns
 * 
 * Expected question format:
 * - Question text should describe the matching task
 * - metadata.matching_items should contain:
 *   {
 *     columnA: ["Item 1", "Item 2", ...],
 *     columnB: ["Match 1", "Match 2", ...]
 *   }
 * 
 * Answer format: JSON string like {"A1": "B2", "A2": "B1", ...}
 * or array of pairs: [["A1", "B2"], ["A2", "B1"], ...]
 */
export default function MatchingQuestionWidget({ question, answer, onChange, disabled }) {
  // Parse matching items from metadata
  const matchingItems = question?.metadata?.matching_items || {
    columnA: [],
    columnB: []
  }
  
  const columnA = matchingItems.columnA || []
  const columnB = matchingItems.columnB || []
  
  // Parse current answer
  const [matches, setMatches] = useState({})
  
  useEffect(() => {
    if (answer) {
      try {
        // Try to parse as JSON
        const parsed = typeof answer === 'string' ? JSON.parse(answer) : answer
        if (typeof parsed === 'object' && parsed !== null) {
          setMatches(parsed)
        }
      } catch (e) {
        // If parsing fails, initialize empty matches
        setMatches({})
      }
    } else {
      setMatches({})
    }
  }, [answer])
  
  const handleMatch = (itemAIndex, itemBIndex) => {
    const itemAKey = `A${itemAIndex}`
    const newMatches = { ...matches }
    
    // If this A item already has a match, remove it
    if (newMatches[itemAKey] !== undefined) {
      delete newMatches[itemAKey]
    }
    
    // If this B item is already matched to another A, remove that match
    Object.keys(newMatches).forEach(key => {
      if (newMatches[key] === `B${itemBIndex}`) {
        delete newMatches[key]
      }
    })
    
    // Set new match
    newMatches[itemAKey] = `B${itemBIndex}`
    setMatches(newMatches)
    
    // Notify parent
    const answerString = JSON.stringify(newMatches)
    onChange(answerString)
  }
  
  const handleUnmatch = (itemAIndex) => {
    const itemAKey = `A${itemAIndex}`
    const newMatches = { ...matches }
    delete newMatches[itemAKey]
    setMatches(newMatches)
    
    const answerString = JSON.stringify(newMatches)
    onChange(answerString)
  }
  
  const getMatchedBIndex = (itemAIndex) => {
    const itemAKey = `A${itemAIndex}`
    const matchedB = matches[itemAKey]
    if (matchedB && matchedB.startsWith('B')) {
      return parseInt(matchedB.substring(1))
    }
    return null
  }
  
  const isBMatched = (itemBIndex) => {
    return Object.values(matches).includes(`B${itemBIndex}`)
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
        🔗 Match each item in Column A with the corresponding item in Column B
      </div>
      
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: '1.5rem',
        marginBottom: '1rem'
      }}>
        {/* Column A */}
        <div>
          <div style={{
            fontSize: '0.875rem',
            fontWeight: '600',
            marginBottom: '0.75rem',
            color: 'var(--text-primary)',
            paddingBottom: '0.5rem',
            borderBottom: '2px solid var(--border-color)'
          }}>
            Column A
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {columnA.map((item, index) => {
              const matchedBIndex = getMatchedBIndex(index)
              return (
                <div
                  key={index}
                  style={{
                    padding: '0.75rem',
                    border: `2px solid ${matchedBIndex !== null ? 'var(--primary-color)' : 'var(--border-color)'}`,
                    borderRadius: 'var(--radius-md)',
                    background: matchedBIndex !== null ? 'var(--primary-color-light)' : 'transparent',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    minHeight: '48px'
                  }}
                >
                  <div style={{ flex: 1 }}>
                    <MathText text={item} inline />
                  </div>
                  {matchedBIndex !== null && (
                    <button
                      type="button"
                      onClick={() => handleUnmatch(index)}
                      disabled={disabled}
                      style={{
                        marginLeft: '0.5rem',
                        padding: '0.25rem 0.5rem',
                        background: 'var(--error-bg, #f8d7da)',
                        color: 'var(--error-text, #721c24)',
                        border: '1px solid var(--error-text, #721c24)',
                        borderRadius: 'var(--radius-sm)',
                        cursor: disabled ? 'not-allowed' : 'pointer',
                        fontSize: '0.75rem',
                        opacity: disabled ? 0.6 : 1
                      }}
                      title="Remove match"
                    >
                      ✕
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        </div>
        
        {/* Column B */}
        <div>
          <div style={{
            fontSize: '0.875rem',
            fontWeight: '600',
            marginBottom: '0.75rem',
            color: 'var(--text-primary)',
            paddingBottom: '0.5rem',
            borderBottom: '2px solid var(--border-color)'
          }}>
            Column B
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {columnB.map((item, index) => {
              const isMatched = isBMatched(index)
              return (
                <button
                  key={index}
                  type="button"
                  onClick={() => {
                    // Find which A item to match (if any A item is currently selected)
                    // For simplicity, allow clicking B to match with the first unmatched A
                    // In a more sophisticated version, you could highlight A items on hover
                    const unmatchedAIndex = columnA.findIndex((_, aIdx) => getMatchedBIndex(aIdx) === null)
                    if (unmatchedAIndex !== -1 && !isMatched) {
                      handleMatch(unmatchedAIndex, index)
                    }
                  }}
                  disabled={disabled || isMatched}
                  style={{
                    padding: '0.75rem',
                    border: `2px solid ${isMatched ? 'var(--primary-color)' : 'var(--border-color)'}`,
                    borderRadius: 'var(--radius-md)',
                    background: isMatched ? 'var(--primary-color-light)' : 'transparent',
                    cursor: disabled || isMatched ? 'default' : 'pointer',
                    textAlign: 'left',
                    minHeight: '48px',
                    opacity: disabled || isMatched ? 0.6 : 1,
                    transition: 'all 0.2s'
                  }}
                  onMouseEnter={(e) => {
                    if (!disabled && !isMatched) {
                      e.target.style.background = 'var(--bg-secondary)'
                      e.target.style.borderColor = 'var(--primary-color)'
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!disabled && !isMatched) {
                      e.target.style.background = 'transparent'
                      e.target.style.borderColor = 'var(--border-color)'
                    }
                  }}
                >
                  <MathText text={item} inline />
                </button>
              )
            })}
          </div>
        </div>
      </div>
      
      {/* Instructions */}
      <div style={{
        fontSize: '0.875rem',
        color: 'var(--text-muted)',
        fontStyle: 'italic',
        marginTop: '0.5rem'
      }}>
        {Object.keys(matches).length === 0 
          ? 'Click on items in Column B to match them with items in Column A'
          : `${Object.keys(matches).length} of ${columnA.length} items matched`}
      </div>
    </div>
  )
}
