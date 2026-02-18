import { useState, useMemo } from 'react'
import MathText from './MathText'

/** Find index just after the first complete $...$ or $$...$$ block. Returns -1 if none. */
function findEndOfFirstMathBlock(s) {
  const dollarIdx = s.indexOf('$')
  if (dollarIdx === -1) return -1
  if (s[dollarIdx + 1] === '$') {
    const close = s.indexOf('$$', dollarIdx + 2)
    return close === -1 ? -1 : close + 2
  }
  // Inline $...$: find matching $ while tracking brace depth; skip \ and next char
  let depth = 0
  for (let j = dollarIdx + 1; j < s.length; j++) {
    if (s[j] === '\\') {
      j++
      continue
    }
    if (s[j] === '{') depth++
    else if (s[j] === '}') depth--
    else if (s[j] === '$' && depth === 0) return j + 1
  }
  return -1
}

/**
 * RevisionCard - A flashcard-style component for studying
 * Shows front (question/concept) and back (answer/explanation)
 */
export default function RevisionCard({ 
  front, 
  back, 
  cardNumber, 
  totalCards,
  onFlip 
}) {
  const [isFlipped, setIsFlipped] = useState(false)

  const handleFlip = () => {
    setIsFlipped(!isFlipped)
    if (onFlip) onFlip(!isFlipped)
  }

  // Display-only: literal \n -> newline, close math before "Step", and (on back) \n -> <br> with math protected.
  // LaTeX repair is done in the backend (normalize_revision_card_latex); do not add repair here so study guide and quiz (MathText) stay unchanged.
  const normalizeLaTeX = (text, isBack = false) => {
    if (!text || typeof text !== 'string') return text

    let normalized = text.replace(/\\n/g, '\n')
    normalized = normalized.replace(/\}\s*\n\s*Step/g, '}$\n\nStep')

    if (isBack) {
      const mathExpressions = []
      let mathIndex = 0
      normalized = normalized.replace(/\$\$[\s\S]*?\$\$/g, (match) => {
        const placeholder = `__MATH_DISPLAY_${mathIndex}__`
        mathExpressions.push({ placeholder, content: match })
        mathIndex++
        return placeholder
      })
      normalized = normalized.replace(/\\\[[\s\S]*?\\\]/g, (match) => {
        const placeholder = `__MATH_BACKSLASH_${mathIndex}__`
        mathExpressions.push({ placeholder, content: match })
        mathIndex++
        return placeholder
      })
      normalized = normalized.replace(/\$[^$\n]+?\$/g, (match) => {
        const placeholder = `__MATH_INLINE_${mathIndex}__`
        mathExpressions.push({ placeholder, content: match })
        mathIndex++
        return placeholder
      })
      normalized = normalized.replace(/\n/g, '<br>')
      mathExpressions.forEach(({ placeholder, content }) => {
        normalized = normalized.replace(placeholder, content)
      })
      normalized = normalized.replace(/\s*\$+\s*$/, '')
    }

    return normalized
  }

  const normalizedFront = useMemo(() => normalizeLaTeX(front, false), [front])
  const normalizedBack = useMemo(() => normalizeLaTeX(back, true), [back])
  // Split back into formula (first complete $...$ or $$...$$) and steps text. Use proper matching so we
  // don't split on }$ inside \frac{...} or \text{...}; only split when the rest looks like "Step 2" etc.
  const { backFormula, backSteps } = useMemo(() => {
    const s = normalizedBack
    const endOfFirstMath = findEndOfFirstMathBlock(s)
    if (endOfFirstMath === -1) return { backFormula: s, backSteps: null }
    const after = s.slice(endOfFirstMath)
    // Only split when the remainder is essentially "Step 2: ..." (no extra content/formulas between)
    if (!/^(\s|<br>)*Step\s*\d/i.test(after)) return { backFormula: s, backSteps: null }
    return { backFormula: s.slice(0, endOfFirstMath), backSteps: after }
  }, [normalizedBack])

  return (
    <div
      onClick={handleFlip}
      style={{
        perspective: '1000px',
        width: '100%',
        maxWidth: '500px',
        height: '300px',
        margin: '0 auto',
        cursor: 'pointer'
      }}
    >
      <div
        style={{
          position: 'relative',
          width: '100%',
          height: '100%',
          transformStyle: 'preserve-3d',
          transition: 'transform 0.6s',
          transform: isFlipped ? 'rotateY(180deg)' : 'rotateY(0deg)'
        }}
      >
        {/* Front of card */}
        <div
          style={{
            position: 'absolute',
            width: '100%',
            height: '100%',
            backfaceVisibility: 'hidden',
            background: 'var(--bg-primary)',
            borderRadius: 'var(--radius-md)',
            padding: '2rem',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            alignItems: 'center',
            boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
            border: '2px solid var(--primary-color)',
            color: 'var(--text-primary)'
          }}
        >
          <div style={{ 
            position: 'absolute', 
            top: '1rem', 
            right: '1rem', 
            fontSize: '0.875rem',
            opacity: 0.8
          }}>
            {cardNumber} / {totalCards}
          </div>
          <div style={{ 
            fontSize: '1.5rem', 
            fontWeight: 'bold', 
            marginBottom: '1rem',
            textAlign: 'center'
          }}>
            <MathText text={normalizedFront} inline={false} />
          </div>
          <div style={{ 
            fontSize: '0.875rem', 
            opacity: 0.9,
            marginTop: '1rem'
          }}>
            Click to flip
          </div>
        </div>

        {/* Back of card */}
        <div
          style={{
            position: 'absolute',
            width: '100%',
            height: '100%',
            backfaceVisibility: 'hidden',
            transform: 'rotateY(180deg)',
            background: 'var(--bg-primary)',
            borderRadius: 'var(--radius-md)',
            padding: '2rem',
            paddingTop: '2.5rem',
            paddingBottom: '1rem',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'flex-start',
            alignItems: 'stretch',
            boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
            border: '2px solid var(--border-color)',
            overflow: 'hidden'
          }}
        >
          <div style={{ 
            position: 'absolute', 
            top: '1rem', 
            right: '1rem', 
            fontSize: '0.875rem',
            color: 'var(--text-muted)'
          }}>
            {cardNumber} / {totalCards}
          </div>
          <div style={{ 
            fontSize: '1rem', 
            lineHeight: 1.6,
            color: 'var(--text-primary)',
            whiteSpace: 'pre-wrap',
            flex: '1 1 auto',
            minHeight: 0,
            overflowY: 'auto'
          }}>
            {backSteps != null ? (
              <>
                <MathText text={backFormula} inline={false} />
                {backSteps && (
                  <div
                    style={{ marginTop: '0.75rem' }}
                    dangerouslySetInnerHTML={{ __html: backSteps }}
                  />
                )}
              </>
            ) : (
              <MathText text={normalizedBack} inline={false} />
            )}
          </div>
          <div style={{ 
            fontSize: '0.875rem', 
            color: 'var(--text-muted)',
            marginTop: '0.75rem',
            textAlign: 'center',
            flexShrink: 0,
            paddingTop: '0.5rem',
            borderTop: '1px solid var(--border-color)'
          }}>
            Click to flip back
          </div>
        </div>
      </div>
    </div>
  )
}
