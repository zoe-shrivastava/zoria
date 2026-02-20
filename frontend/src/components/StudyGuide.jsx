import { useState, useEffect, useMemo, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import { tests } from '../services/api'
import LoadingSpinner from './LoadingSpinner'
import MathText from './MathText'
import RevisionCard from './RevisionCard'
import { showNotification } from '../utils/notifications'

// Import remark-gfm for GitHub Flavored Markdown table support
// Install with: npm install remark-gfm
// eslint-disable-next-line import/no-unresolved
import remarkGfm from 'remark-gfm'

export default function StudyGuide({ 
  guideId, 
  onClose,
  contextPayload = null,
  onNavigateToCards = null,
  preferredLanguage = null,
}) {
  const [guide, setGuide] = useState(null)
  const [loading, setLoading] = useState(true)
  const [regenerating, setRegenerating] = useState(false)
  const [currentCardIndex, setCurrentCardIndex] = useState(0)
  const [showRevisionCards, setShowRevisionCards] = useState(false)
  const contentRef = useRef(null)

  useEffect(() => {
    loadGuide()
  }, [guideId])

  const loadGuide = async () => {
    try {
      setLoading(true)
      const data = await tests.getStudyGuide(guideId)
      setGuide(data)
      // If backend is still regenerating, show generating state and poll until ready
      if (data?.metadata?.regeneration_status === 'in_progress') {
        setRegenerating(true)
        try {
          await tests.pollStudyGuideUntilReady(guideId)
          const updated = await tests.getStudyGuide(guideId)
          setGuide(updated)
        } finally {
          setRegenerating(false)
        }
      }
    } catch (err) {
      console.error('Failed to load study guide:', err)
      showNotification(err.message || 'Failed to load study guide', 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleRegenerate = async () => {
    if (!guideId) return

    let isAlreadyInProgress = false
    try {
      setRegenerating(true)
      const result = await tests.regenerateStudyGuide(guideId, preferredLanguage)
      // 202 Accepted: regeneration started in background; poll until ready
      if (result?.guide_id != null && result.guide === undefined) {
        showNotification('Regeneration started. This may take a few minutes.', 'info')
        await tests.pollStudyGuideUntilReady(guideId)
        await loadGuide()
        showNotification('Study guide regenerated successfully', 'success')
      } else {
        await loadGuide()
        showNotification('Study guide regenerated successfully', 'success')
      }
    } catch (err) {
      console.error('Failed to regenerate study guide:', err)
      // 409 = generation already in progress; keep disabled and poll until the other generation finishes
      isAlreadyInProgress = err.status === 409 || (err.message && String(err.message).includes('already in progress'))
      showNotification(err.message || 'Failed to regenerate study guide', isAlreadyInProgress ? 'info' : 'error')
      if (isAlreadyInProgress) {
        try {
          await tests.pollStudyGuideUntilReady(guideId)
          await loadGuide()
        } finally {
          setRegenerating(false)
        }
      }
    } finally {
      if (!isAlreadyInProgress) setRegenerating(false)
    }
  }

  // Generate revision cards from study guide data
  // Priority: Use LLM-generated cards from backend, fallback to regex extraction
  const revisionCards = useMemo(() => {
    if (!guide) return []
    
    // First, try to use revision cards from backend (LLM-generated)
    if (guide.metadata && guide.metadata.revision_cards) {
      const llmCards = guide.metadata.revision_cards
      if (Array.isArray(llmCards) && llmCards.length > 0) {
        // Validate and format LLM-generated cards
        const validCards = llmCards
          .filter(card => card && card.front && card.back)
          .map(card => ({
            front: String(card.front).trim(),
            back: String(card.back).trim()
          }))
          .filter(card => card.front && card.back)
        
        if (validCards.length > 0) {
          return validCards
        }
      }
    }
    
    // Fallback to regex-based extraction if no LLM cards available
    const cards = []
    const content = guide.content || ''
    
    // 1. Extract Important Definitions - ONE CARD PER DEFINITION
    const definitions = []
    
    // Pattern 1: "Term: Definition" format
    const termDefPattern = /(?:^|\n)(?:#{1,4}\s*)?\*\*?([A-Z][^*:\n]{1,60})\*\*?[:\s]+([^\n]+(?:\n(?!\n|#{1,4}|[A-Z][^*:\n]{1,60}:\s)[^\n]+)*)/g
    let match
    while ((match = termDefPattern.exec(content)) !== null) {
      const term = match[1].trim()
      const definition = match[2].trim()
      if (term && definition && definition.length > 10 && definition.length < 500) {
        definitions.push({ term, definition })
      }
    }
    
    // Pattern 2: "Definition: ..." format
    const defPattern = /(?:^|\n)(?:#{1,4}\s*)?(?:Definition|\*\*Definition\*\*)[:\s]+([^\n]+(?:\n(?!\n|#{1,4})[^\n]+)*)/gi
    while ((match = defPattern.exec(content)) !== null) {
      const definition = match[1].trim()
      if (definition && definition.length > 10 && definition.length < 500) {
        // Try to extract term from definition
        const termMatch = definition.match(/^([A-Z][^:]{1,50}):\s*(.+)$/)
        if (termMatch) {
          definitions.push({ term: termMatch[1].trim(), definition: termMatch[2].trim() })
        } else {
          definitions.push({ term: 'Definition', definition })
        }
      }
    }
    
    // Also look for definitions in key points
    if (guide.key_points) {
      guide.key_points.forEach(point => {
        const parts = point.split(':').map(p => p.trim())
        if (parts.length >= 2 && parts[0].length < 50 && parts[0].length > 2) {
          definitions.push({ term: parts[0], definition: parts.slice(1).join(': ') })
        }
      })
    }
    
    // Create ONE card per definition
    definitions.forEach((def, idx) => {
      cards.push({
        front: `What is ${def.term}?`,
        back: def.definition
      })
    })
    
    // 2. Extract Important Formulas - ONE CARD PER FORMULA
    const formulas = []
    
    // Pattern 1: Display math $$...$$
    const displayMathPattern = /\$\$([^$]+)\$\$/g
    while ((match = displayMathPattern.exec(content)) !== null) {
      const formula = match[1].trim()
      if (formula && formula.length < 300) {
        formulas.push({ formula: `$$${formula}$$`, name: null })
      }
    }
    
    // Pattern 2: Inline math $...$ (but only if it looks like a formula, not just a variable)
    const inlineMathPattern = /\$([^$\n]{5,100})\$/g
    while ((match = inlineMathPattern.exec(content)) !== null) {
      const formula = match[1].trim()
      // Check if it's a formula (contains =, or multiple variables/operators)
      if (formula.includes('=') || /[a-zA-Z]\s*[+\-*/^]\s*[a-zA-Z]/.test(formula)) {
        if (formula.length < 200) {
          formulas.push({ formula: `$${formula}$`, name: null })
        }
      }
    }
    
    // Pattern 3: "Variable = expression" format
    const varEqPattern = /(?:^|\n)(?:#{1,4}\s*)?([A-Z][a-zA-Z\s]{1,40})\s*=\s*([^\n]+)/g
    while ((match = varEqPattern.exec(content)) !== null) {
      const varName = match[1].trim()
      const expression = match[2].trim()
      // Check if it looks like a formula
      if (expression && (expression.includes('$') || /[a-zA-Z]\s*[+\-*/]/.test(expression) || expression.length > 5)) {
        if (expression.length < 200) {
          formulas.push({ 
            formula: `${varName} = ${expression}`, 
            name: varName 
          })
        }
      }
    }
    
    // Pattern 4: "Formula: ..." or "Equation: ..."
    const formulaLabelPattern = /(?:^|\n)(?:#{1,4}\s*)?(?:Formula|Equation|\*\*Formula\*\*|\*\*Equation\*\*)[:\s]+([^\n]+)/gi
    while ((match = formulaLabelPattern.exec(content)) !== null) {
      const formula = match[1].trim()
      if (formula && formula.length < 200) {
        formulas.push({ formula, name: null })
      }
    }
    
    // Remove duplicates and create ONE card per formula
    const seenFormulas = new Set()
    formulas.forEach((form, idx) => {
      const formulaKey = form.formula.replace(/\s+/g, ' ').toLowerCase()
      if (!seenFormulas.has(formulaKey)) {
        seenFormulas.add(formulaKey)
        const frontText = form.name 
          ? `What is the formula for ${form.name}?`
          : `Formula ${idx + 1}`
        cards.push({
          front: frontText,
          back: form.formula
        })
      }
    })
    
    // 3. Extract Step-by-step guides for sample questions - ONE CARD PER COMPLETE SOLUTION
    const stepByStepSolutions = []
    
    // Pattern: Look for "Example 1:", "Problem 1:", "Question 1:", etc. followed by steps
    const exampleHeaderPattern = /(?:^|\n)(?:#{1,4}\s*)?(?:Example|Problem|Question|Sample Question)\s*(\d+)[:\s]*([^\n]+(?:\n(?!#{1,4})[^\n]+)*?)(?=\n#{1,4}|\n\n\n|$)/gi
    while ((match = exampleHeaderPattern.exec(content)) !== null) {
      const exampleNum = match[1]
      const exampleContent = match[2] || match[0]
      
      // Extract all steps from this example
      const steps = []
      const stepPattern = /(?:^|\n)(?:Step\s*)?(\d+)[\.:]\s*([^\n]+(?:\n(?!\d+[\.:]|Step\s*\d+)[^\n]+)*?)(?=\n\d+[\.:]|\nStep\s*\d+|\n#{1,4}|$)/g
      let stepMatch
      const exampleText = exampleContent
      while ((stepMatch = stepPattern.exec(exampleText)) !== null) {
        const stepNum = stepMatch[1]
        const stepText = stepMatch[2].trim()
        if (stepText.length > 10) {
          steps.push({ num: stepNum, text: stepText })
        }
      }
      
      // If we found steps, create a card for this complete solution
      if (steps.length > 0) {
        const questionText = exampleContent.split(/Step\s*\d+/i)[0].trim()
        const stepsText = steps.map(s => `Step ${s.num}: ${s.text}`).join('\n\n')
        stepByStepSolutions.push({
          question: questionText.substring(0, 150),
          solution: stepsText
        })
      }
    }
    
    // Also look for standalone step sequences in "Section 4: Detailed Worked Examples"
    // Look for consecutive numbered steps (1., 2., 3., etc.) that form a complete solution
    const section4Match = content.match(/##\s*Section\s*4[^\n]*\n([\s\S]*?)(?=##\s*Section\s*5|$)/i)
    if (section4Match) {
      const section4Content = section4Match[1]
      // Find all step sequences in this section
      const allSteps = []
      const stepRegex = /(?:^|\n)(?:Step\s*)?(\d+)[\.:]\s*([^\n]+(?:\n(?!\d+[\.:]|Step\s*\d+|#{1,4})[^\n]+)*?)(?=\n\d+[\.:]|\nStep\s*\d+|\n#{1,4}|$)/g
      let stepMatch
      let currentSolution = []
      let lastStepNum = 0
      
      while ((stepMatch = stepRegex.exec(section4Content)) !== null) {
        const stepNum = parseInt(stepMatch[1])
        const stepText = stepMatch[2].trim()
        
        // If this is step 1 or a step that doesn't follow sequentially, start a new solution
        if (stepNum === 1 || (lastStepNum > 0 && stepNum !== lastStepNum + 1)) {
          // Save previous solution if it has at least 2 steps
          if (currentSolution.length >= 2) {
            const stepsText = currentSolution.map(s => `Step ${s.num}: ${s.text}`).join('\n\n')
            stepByStepSolutions.push({
              question: `Example ${stepByStepSolutions.length + 1}`,
              solution: stepsText
            })
          }
          currentSolution = []
        }
        
        if (stepText.length > 10) {
          currentSolution.push({ num: String(stepNum), text: stepText })
          lastStepNum = stepNum
        }
      }
      
      // Save last solution if it has at least 2 steps
      if (currentSolution.length >= 2) {
        const stepsText = currentSolution.map(s => `Step ${s.num}: ${s.text}`).join('\n\n')
        stepByStepSolutions.push({
          question: `Example ${stepByStepSolutions.length + 1}`,
          solution: stepsText
        })
      }
    }
    
    // Create ONE card per complete step-by-step solution
    stepByStepSolutions.forEach((solution, idx) => {
      cards.push({
        front: `Sample Problem ${idx + 1}: ${solution.question.substring(0, 80)}${solution.question.length > 80 ? '...' : ''}`,
        back: solution.solution
      })
    })
    
    // Fallback: if no cards created, create a basic one
    if (cards.length === 0) {
      cards.push({
        front: guide.concept_name || 'Study Guide',
        back: `Focus Area: ${guide.focus_area || 'General'}\n\nReview the full study guide content below for detailed information.`
      })
    }
    
    return cards
  }, [guide])
  
  const handleCardFlip = (isFlipped) => {
    // Optional: track card interactions
  }
  
  const handleNextCard = () => {
    setCurrentCardIndex((prev) => {
      if (revisionCards.length === 0) return 0
      return (prev + 1) % revisionCards.length
    })
  }
  
  const handlePrevCard = () => {
    setCurrentCardIndex((prev) => {
      if (revisionCards.length === 0) return 0
      return (prev - 1 + revisionCards.length) % revisionCards.length
    })
  }
  
  // Reset card index when revision cards change
  useEffect(() => {
    if (revisionCards.length > 0 && currentCardIndex >= revisionCards.length) {
      setCurrentCardIndex(0)
    }
  }, [revisionCards.length, currentCardIndex])

  // Auto-scroll to relevant section when context is provided
  useEffect(() => {
    if (contextPayload?.relatedError && guide && contentRef.current) {
      const errorType = contextPayload.relatedError.errorType
      
      // Map error types to section IDs
      const sectionMap = {
        'Conceptual': 'section-5', // Common Errors section
        'Arithmetic': 'section-4', // Examples section
        'Procedural': 'section-3', // Problem-Solving Method
      }
      
      const targetId = sectionMap[errorType] || 'section-5'
      
      // Wait for content to render, then scroll
      setTimeout(() => {
        const element = document.getElementById(targetId) || 
                       contentRef.current?.querySelector(`#${targetId}`) ||
                       contentRef.current?.querySelector(`[id*="${targetId}"]`)
        
        if (element) {
          element.scrollIntoView({ behavior: 'smooth', block: 'start' })
          // Highlight the section temporarily
          const originalBg = element.style.background
          element.style.background = 'rgba(255, 193, 7, 0.1)'
          element.style.transition = 'background 0.3s'
          setTimeout(() => {
            element.style.background = originalBg
          }, 3000)
        }
      }, 500)
    }
  }, [guide, contextPayload])

  if (loading) return <LoadingSpinner />
  if (!guide) return <div>Study guide not found</div>

  // Helper function to extract text from React children
  const extractText = (node) => {
    if (typeof node === 'string') return node
    if (typeof node === 'number') return String(node)
    if (Array.isArray(node)) return node.map(extractText).join('')
    if (node?.props?.children) return extractText(node.props.children)
    return ''
  }

  return (
    <div ref={contentRef} style={{ padding: '2rem', maxWidth: '900px', margin: '0 auto' }}>
      {onClose && (
        <button 
          onClick={onClose} 
          className="btn-secondary"
          style={{ marginBottom: '1rem' }}
        >
          ← Back
        </button>
      )}

      {/* Contextual Header */}
      {contextPayload && (
        <div style={{
          padding: '1rem',
          background: 'var(--primary-color-light)',
          borderRadius: 'var(--radius-md)',
          marginBottom: '1.5rem',
          border: '1px solid var(--primary-color)'
        }}>
          <div style={{ fontWeight: '600', marginBottom: '0.5rem' }}>
            Focus: {contextPayload.activeTopic}
          </div>
          {contextPayload.relatedError && (
            <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
              Error Type: {contextPayload.relatedError.errorType}
              {contextPayload.relatedError.misconceptions?.length > 0 && (
                <div style={{ marginTop: '0.5rem' }}>
                  Misconceptions: {contextPayload.relatedError.misconceptions.join(', ')}
                </div>
              )}
            </div>
          )}
        </div>
      )}
      

      {/* Revision Cards Section - Removed (now handled by LearningDrawer tabs) */}
      {false && showRevisionCards && revisionCards.length > 0 && (() => {
        // Ensure currentCardIndex is within bounds
        const safeIndex = Math.max(0, Math.min(currentCardIndex, revisionCards.length - 1))
        const currentCard = revisionCards[safeIndex]
        
        // If card is invalid, don't render
        if (!currentCard || !currentCard.front || !currentCard.back) {
          return null
        }
        
        return (
          <div style={{
            background: 'var(--bg-secondary)',
            padding: '2rem',
            borderRadius: 'var(--radius-md)',
            marginBottom: '2rem',
            border: '1px solid var(--border-color)'
          }}>
            <div style={{ 
              display: 'flex', 
              justifyContent: 'space-between', 
              alignItems: 'center',
              marginBottom: '1.5rem'
            }}>
              <h3 style={{ 
                margin: 0,
                fontSize: '1.375rem',
                fontWeight: '600',
                color: 'var(--text-primary)',
                borderBottom: '2px solid var(--border-color)',
                paddingBottom: '0.5rem'
              }}>Revision Cards</h3>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <button
                  onClick={handlePrevCard}
                  className="btn-secondary"
                  disabled={revisionCards.length <= 1}
                  style={{ padding: '0.5rem 1rem' }}
                >
                  ← Prev
                </button>
                <span style={{ 
                  padding: '0.5rem 1rem',
                  background: 'var(--bg-primary)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '0.875rem'
                }}>
                  {safeIndex + 1} / {revisionCards.length}
                </span>
                <button
                  onClick={handleNextCard}
                  className="btn-secondary"
                  disabled={revisionCards.length <= 1}
                  style={{ padding: '0.5rem 1rem' }}
                >
                  Next →
                </button>
              </div>
            </div>
            
            <RevisionCard
              front={currentCard.front}
              back={currentCard.back}
              cardNumber={safeIndex + 1}
              totalCards={revisionCards.length}
              onFlip={handleCardFlip}
            />
            
            <div style={{ 
              marginTop: '1.5rem', 
              textAlign: 'center',
              fontSize: '0.875rem',
              color: 'var(--text-muted)'
            }}>
              Click the card to flip it. Use the navigation buttons to move between cards.
            </div>
          </div>
        )
      })()}

      {/* Key Points */}
      {guide.key_points && guide.key_points.length > 0 && (
        <div style={{
          background: 'var(--primary-color-light)',
          padding: '1.5rem',
          borderRadius: 'var(--radius-md)',
          marginBottom: '2rem',
          border: '1px solid var(--primary-color)'
        }}>
          <h3 style={{ marginBottom: '1rem', color: 'var(--primary-color)' }}>Key Points</h3>
          <ul style={{ margin: 0, paddingLeft: '1.5rem' }}>
            {guide.key_points.map((point, idx) => (
              <li key={idx} style={{ marginBottom: '0.5rem', lineHeight: 1.6 }}>
                <MathText text={point} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Study Guide Content */}
      <div style={{
        background: 'var(--bg-primary)',
        padding: '2.5rem',
        borderRadius: 'var(--radius-md)',
        lineHeight: 1.8,
        border: '1px solid var(--border-color)',
        boxShadow: '0 2px 4px rgba(0, 0, 0, 0.05)'
      }}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          children={(() => {
            // Preprocess: lines of only = or - (Setext underlines / decorative lines) -> --- so they render as a visible horizontal rule
            const raw = guide.content || ''
            return raw.replace(/\n\s*=+\s*\n/g, '\n---\n').replace(/\n\s*-{3,}\s*\n/g, '\n---\n')
          })()}
          components={{
            // Helper to extract text from React children for LaTeX rendering
            // eslint-disable-next-line react/prop-types
            p: ({ children }) => {
              const extractText = (node) => {
                if (typeof node === 'string') return node
                if (typeof node === 'number') return String(node)
                if (Array.isArray(node)) return node.map(extractText).join('')
                if (node?.props?.children) return extractText(node.props.children)
                return ''
              }
              const text = extractText(children)
              return (
                <p style={{ marginBottom: '1rem' }}>
                  <MathText text={text} inline={false} />
                </p>
              )
            },
            // Headings with LaTeX support - Enhanced "popping out" formatting
            // eslint-disable-next-line react/prop-types
            h1: ({ children }) => {
              const extractText = (node) => {
                if (typeof node === 'string') return node
                if (typeof node === 'number') return String(node)
                if (Array.isArray(node)) return node.map(extractText).join('')
                if (node?.props?.children) return extractText(node.props.children)
                return ''
              }
              const text = extractText(children)
              return (
                <h1 style={{ 
                  fontSize: '2.5rem', 
                  marginTop: '3rem', 
                  marginBottom: '1.5rem', 
                  fontWeight: '800',
                  color: 'var(--primary-color)',
                  borderBottom: '4px solid var(--primary-color)',
                  paddingBottom: '1rem',
                  paddingTop: '1rem',
                  paddingLeft: '1.5rem',
                  paddingRight: '1.5rem',
                  background: 'linear-gradient(135deg, var(--primary-color-light) 0%, transparent 100%)',
                  borderRadius: 'var(--radius-md)',
                  boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
                  lineHeight: 1.2,
                  letterSpacing: '-0.02em'
                }}>
                  <MathText text={text} inline={false} />
                </h1>
              )
            },
            // eslint-disable-next-line react/prop-types
            h2: ({ children }) => {
              const text = extractText(children)
              // Generate ID from heading text for auto-scroll
              const id = text.toLowerCase()
                .replace(/[^a-z0-9]+/g, '-')
                .replace(/^-|-$/g, '')
              
              // Map section names to IDs for error-based navigation
              let sectionId = id
              if (text.toLowerCase().includes('common error') || text.toLowerCase().includes('error')) {
                sectionId = 'section-5'
              } else if (text.toLowerCase().includes('example') || text.toLowerCase().includes('worked')) {
                sectionId = 'section-4'
              } else if (text.toLowerCase().includes('problem-solving') || text.toLowerCase().includes('method')) {
                sectionId = 'section-3'
              } else {
                sectionId = `section-${id}`
              }
              
              return (
                <h2 
                  id={sectionId}
                  style={{ 
                    fontSize: '1.875rem', 
                    marginTop: '2.5rem', 
                    marginBottom: '1.25rem', 
                    fontWeight: '700',
                    color: 'var(--primary-color)',
                    borderLeft: '5px solid var(--primary-color)',
                    paddingLeft: '1.25rem',
                    paddingTop: '0.75rem',
                    paddingBottom: '0.75rem',
                    paddingRight: '1rem',
                    background: 'linear-gradient(to right, var(--primary-color-light) 0%, rgba(255,255,255,0.1) 50%, transparent 100%)',
                    borderRadius: '0 var(--radius-sm) var(--radius-sm) 0',
                    boxShadow: '0 2px 4px rgba(0, 0, 0, 0.08)',
                    lineHeight: 1.3,
                    letterSpacing: '-0.01em'
                  }}
                >
                  <MathText text={text} inline={false} />
                </h2>
              )
            },
            // eslint-disable-next-line react/prop-types
            h3: ({ children }) => {
              const extractText = (node) => {
                if (typeof node === 'string') return node
                if (typeof node === 'number') return String(node)
                if (Array.isArray(node)) return node.map(extractText).join('')
                if (node?.props?.children) return extractText(node.props.children)
                return ''
              }
              const text = extractText(children)
              return (
                <h3 style={{ 
                  fontSize: '1.5rem', 
                  marginTop: '2rem', 
                  marginBottom: '1rem', 
                  fontWeight: '650',
                  color: 'var(--text-primary)',
                  borderBottom: '3px solid var(--primary-color)',
                  paddingBottom: '0.75rem',
                  paddingTop: '0.5rem',
                  paddingLeft: '0.75rem',
                  background: 'linear-gradient(to bottom, var(--primary-color-light) 0%, transparent 100%)',
                  borderRadius: 'var(--radius-sm) var(--radius-sm) 0 0',
                  lineHeight: 1.4
                }}>
                  <MathText text={text} inline={false} />
                </h3>
              )
            },
            // eslint-disable-next-line react/prop-types
            h4: ({ children }) => {
              const extractText = (node) => {
                if (typeof node === 'string') return node
                if (typeof node === 'number') return String(node)
                if (Array.isArray(node)) return node.map(extractText).join('')
                if (node?.props?.children) return extractText(node.props.children)
                return ''
              }
              const text = extractText(children)
              return (
                <h4 style={{ 
                  fontSize: '1.25rem', 
                  marginTop: '1.5rem', 
                  marginBottom: '0.75rem', 
                  fontWeight: '600',
                  color: 'var(--text-primary)',
                  paddingLeft: '1rem',
                  paddingTop: '0.5rem',
                  paddingBottom: '0.5rem',
                  borderLeft: '4px solid var(--primary-color-light)',
                  background: 'rgba(0, 0, 0, 0.02)',
                  borderRadius: '0 var(--radius-sm) var(--radius-sm) 0',
                  lineHeight: 1.5
                }}>
                  <MathText text={text} inline={false} />
                </h4>
              )
            },
            // Lists
            // eslint-disable-next-line react/prop-types
            ul: ({ children }) => <ul style={{ marginBottom: '1rem', paddingLeft: '1.5rem' }}>{children}</ul>,
            // eslint-disable-next-line react/prop-types
            ol: ({ children }) => <ol style={{ marginBottom: '1rem', paddingLeft: '1.5rem' }}>{children}</ol>,
            // eslint-disable-next-line react/prop-types
            li: ({ children }) => {
              const extractText = (node) => {
                if (typeof node === 'string') return node
                if (typeof node === 'number') return String(node)
                if (Array.isArray(node)) return node.map(extractText).join('')
                if (node?.props?.children) return extractText(node.props.children)
                return ''
              }
              const text = extractText(children)
              return (
                <li style={{ marginBottom: '0.5rem' }}>
                  <MathText text={text} inline={false} />
                </li>
              )
            },
            // Code blocks
            // eslint-disable-next-line react/prop-types
            code: ({ children, className }) => {
              const code = String(children || '').trim()
              const isLatexBlock = className && (className.includes('latex') || className === 'language-math')
              if (isLatexBlock && (code.includes('$$') || code.includes('$'))) {
                // Render ```latex ... $$...$$ ... ``` as math instead of raw code
                return (
                  <div style={{ marginBottom: '1rem', marginTop: '0.5rem' }}>
                    <MathText text={code} inline={false} />
                  </div>
                )
              }
              if (className?.startsWith('language-')) {
                return (
                  <pre style={{ 
                    background: 'var(--bg-secondary)', 
                    padding: '1rem', 
                    borderRadius: 'var(--radius-sm)',
                    overflowX: 'auto',
                    marginBottom: '1rem',
                    border: '1px solid var(--border-color)'
                  }}>
                    <code style={{ background: 'none', padding: 0, fontFamily: 'monospace' }}>{code}</code>
                  </pre>
                )
              }
              return (
                <code style={{ 
                  background: 'var(--bg-secondary)', 
                  padding: '0.2rem 0.4rem', 
                  borderRadius: 'var(--radius-sm)',
                  fontFamily: 'monospace',
                  fontSize: '0.9em',
                  border: '1px solid var(--border-color)'
                }}>
                  {code}
                </code>
              )
            },
            // Tables with LaTeX support
            // eslint-disable-next-line react/prop-types
            table: ({ children }) => (
              <div style={{ overflowX: 'auto', marginBottom: '1.5rem', marginTop: '1rem' }}>
                <table style={{
                  width: '100%',
                  borderCollapse: 'collapse',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-sm)',
                  overflow: 'hidden',
                  boxShadow: '0 2px 4px rgba(0, 0, 0, 0.05)'
                }}>
                  {children}
                </table>
              </div>
            ),
            // eslint-disable-next-line react/prop-types
            thead: ({ children }) => (
              <thead style={{ background: 'var(--primary-color-light)' }}>{children}</thead>
            ),
            // eslint-disable-next-line react/prop-types
            tbody: ({ children }) => <tbody>{children}</tbody>,
            // eslint-disable-next-line react/prop-types
            tr: ({ children }) => (
              <tr style={{ 
                borderBottom: '1px solid var(--border-color)'
              }}>
                {children}
              </tr>
            ),
            // eslint-disable-next-line react/prop-types
            th: ({ children }) => {
              // Helper to check if children contains already-rendered React elements (like KaTeX)
              const hasReactElements = (node) => {
                if (node === null || node === undefined) return false
                if (typeof node === 'string' || typeof node === 'number') return false
                if (Array.isArray(node)) return node.some(hasReactElements)
                // If it's an object with type, it's likely a React element
                if (typeof node === 'object' && node !== null) {
                  return node.type !== undefined || node.props !== undefined
                }
                return false
              }
              
              // Helper to extract text from React children for LaTeX rendering
              const extractText = (node) => {
                if (typeof node === 'string') return node
                if (typeof node === 'number') return String(node)
                if (Array.isArray(node)) return node.map(extractText).join('')
                if (node?.props?.children) return extractText(node.props.children)
                return ''
              }
              
              // If children contains React elements (already rendered LaTeX), preserve them
              if (hasReactElements(children)) {
                return (
                  <th style={{
                    padding: '0.75rem 1rem',
                    textAlign: 'left',
                    fontWeight: '600',
                    color: 'var(--primary-color)',
                    borderRight: '1px solid var(--border-color)'
                  }}>
                    {children}
                  </th>
                )
              }
              
              // Otherwise, extract text and render with MathText
              const text = extractText(children)
              return (
                <th style={{
                  padding: '0.75rem 1rem',
                  textAlign: 'left',
                  fontWeight: '600',
                  color: 'var(--primary-color)',
                  borderRight: '1px solid var(--border-color)'
                }}>
                  <MathText text={text} inline={true} />
                </th>
              )
            },
            // eslint-disable-next-line react/prop-types
            td: ({ children }) => {
              // Helper to check if children contains already-rendered React elements (like KaTeX)
              const hasReactElements = (node) => {
                if (node === null || node === undefined) return false
                if (typeof node === 'string' || typeof node === 'number') return false
                if (Array.isArray(node)) return node.some(hasReactElements)
                // If it's an object with type, it's likely a React element
                if (typeof node === 'object' && node !== null) {
                  return node.type !== undefined || node.props !== undefined
                }
                return false
              }
              
              // Helper to extract text from React children for LaTeX rendering
              const extractText = (node) => {
                if (typeof node === 'string') return node
                if (typeof node === 'number') return String(node)
                if (Array.isArray(node)) return node.map(extractText).join('')
                if (node?.props?.children) return extractText(node.props.children)
                return ''
              }
              
              // If children contains React elements (already rendered LaTeX), preserve them
              if (hasReactElements(children)) {
                return (
                  <td style={{
                    padding: '0.75rem 1rem',
                    borderRight: '1px solid var(--border-color)'
                  }}>
                    {children}
                  </td>
                )
              }
              
              // Otherwise, extract text and render with MathText
              const text = extractText(children)
              return (
                <td style={{
                  padding: '0.75rem 1rem',
                  borderRight: '1px solid var(--border-color)'
                }}>
                  <MathText text={text} inline={true} />
                </td>
              )
            },
            // Blockquotes with LaTeX support
            // eslint-disable-next-line react/prop-types
            blockquote: ({ children }) => {
              const extractText = (node) => {
                if (typeof node === 'string') return node
                if (typeof node === 'number') return String(node)
                if (Array.isArray(node)) return node.map(extractText).join('')
                if (node?.props?.children) return extractText(node.props.children)
                return ''
              }
              const text = extractText(children)
              return (
                <blockquote style={{
                  margin: '1.5rem 0',
                  padding: '1rem 1.5rem',
                  borderLeft: '4px solid var(--primary-color)',
                  background: 'var(--primary-color-light)',
                  borderRadius: '0 var(--radius-sm) var(--radius-sm) 0',
                  fontStyle: 'italic',
                  color: 'var(--text-primary)'
                }}>
                  <MathText text={text} inline={false} />
                </blockquote>
              )
            },
            // Strong/Bold with LaTeX support
            // eslint-disable-next-line react/prop-types
            strong: ({ children }) => {
              const extractText = (node) => {
                if (typeof node === 'string') return node
                if (typeof node === 'number') return String(node)
                if (Array.isArray(node)) return node.map(extractText).join('')
                if (node?.props?.children) return extractText(node.props.children)
                return ''
              }
              const text = extractText(children)
              return (
                <strong style={{ fontWeight: '600', color: 'var(--text-primary)' }}>
                  <MathText text={text} inline={true} />
                </strong>
              )
            },
            // Emphasis/Italic with LaTeX support
            // eslint-disable-next-line react/prop-types
            em: ({ children }) => {
              const extractText = (node) => {
                if (typeof node === 'string') return node
                if (typeof node === 'number') return String(node)
                if (Array.isArray(node)) return node.map(extractText).join('')
                if (node?.props?.children) return extractText(node.props.children)
                return ''
              }
              const text = extractText(children)
              return (
                <em style={{ fontStyle: 'italic', color: 'var(--text-primary)' }}>
                  <MathText text={text} inline={true} />
                </em>
              )
            },
            // Links
            // eslint-disable-next-line react/prop-types
            a: ({ href, children }) => (
              <a href={href} style={{ color: 'var(--primary-color)', textDecoration: 'underline' }} target="_blank" rel="noopener noreferrer">
                {children}
              </a>
            ),
          }}
        />
      </div>

      {/* Practice Recommendations */}
      {guide.practice_recommendations && guide.practice_recommendations.length > 0 && (
        <div style={{
          background: 'var(--success-color-light)',
          padding: '1.5rem',
          borderRadius: 'var(--radius-md)',
          marginTop: '2rem',
          border: '1px solid var(--success-color)'
        }}>
          <h3 style={{ 
            marginBottom: '1rem', 
            marginTop: 0,
            color: 'var(--success-color)',
            fontSize: '1.375rem',
            fontWeight: '600',
            borderBottom: '2px solid var(--success-color)',
            paddingBottom: '0.5rem'
          }}>Practice Recommendations</h3>
          <ul style={{ margin: 0, paddingLeft: '1.5rem' }}>
            {guide.practice_recommendations.map((rec, idx) => (
              <li key={idx} style={{ marginBottom: '0.5rem', lineHeight: 1.6 }}>
                {rec}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Common Errors */}
      {guide.common_errors && guide.common_errors.length > 0 && (() => {
        // Filter out None, empty, or invalid error entries
        const validErrors = guide.common_errors.filter(
          error => error && typeof error === 'string' && error.trim() && 
          error.toLowerCase() !== 'none' && error.toLowerCase() !== 'null'
        )
        
        if (validErrors.length === 0) return null

        // Friendly labels for error types (display only)
        const errorLabelMap = {
          'No_Answer': 'Skipped or unanswered questions',
          'Partial_Credit': 'Partial credit',
          'Unit_Mismatch': 'Unit errors',
          'Conceptual': 'Conceptual misunderstanding',
          'Procedural': 'Procedural errors',
          'Arithmetic': 'Calculation errors',
          'Incorrect': 'Incorrect answers'
        }
        const getLabel = (type) => (errorLabelMap[type] || type).trim()

        return (
          <div style={{
            background: 'var(--error-color-light)',
            padding: '1.5rem',
            borderRadius: 'var(--radius-md)',
            marginTop: '2rem',
            border: '1px solid var(--error-color)'
          }}>
            <h3 style={{ 
              marginBottom: '0.5rem', 
              marginTop: 0,
              color: 'var(--error-color)',
              fontSize: '1.375rem',
              fontWeight: '600',
              borderBottom: '2px solid var(--error-color)',
              paddingBottom: '0.5rem'
            }}>Common Errors to Avoid</h3>
            <p style={{ margin: '0 0 1rem 0', fontSize: '0.9375rem', color: 'var(--text-color)' }}>
              Focus on these to improve next time.
            </p>
            <ul style={{ margin: 0, paddingLeft: '1.5rem' }}>
              {validErrors.map((error, idx) => {
                const colonIdx = error.indexOf(': ')
                const type = colonIdx >= 0 ? error.slice(0, colonIdx).trim() : ''
                const advice = colonIdx >= 0 ? error.slice(colonIdx + 2).trim() : error
                const label = type ? getLabel(type) : ''
                return (
                  <li key={idx} style={{ marginBottom: '1rem', lineHeight: 1.6, listStyle: 'disc' }}>
                    {label ? (
                      <>
                        <strong style={{ color: 'var(--error-color)' }}>{label}</strong>
                        <span> — </span>
                        <MathText text={advice} inline />
                      </>
                    ) : (
                      <MathText text={error} inline={false} />
                    )}
                  </li>
                )
              })}
            </ul>
          </div>
        )
      })()}

      {/* Related Concepts */}
      {guide.related_concepts && guide.related_concepts.length > 0 && (
        <div style={{
          background: 'var(--bg-secondary)',
          padding: '1.5rem',
          borderRadius: 'var(--radius-md)',
          marginTop: '2rem',
          border: '1px solid var(--border-color)'
        }}>
          <h3 style={{ 
            marginBottom: '1rem', 
            marginTop: 0,
            fontSize: '1.375rem',
            fontWeight: '600',
            borderBottom: '2px solid var(--border-color)',
            paddingBottom: '0.5rem'
          }}>Related Concepts to Review</h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
            {guide.related_concepts.map((concept, idx) => (
              <span 
                key={idx}
                style={{
                  padding: '0.5rem 1rem',
                  background: 'var(--bg-primary)',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-color)'
                }}
              >
                {concept}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
