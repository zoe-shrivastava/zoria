import { useState, useMemo } from 'react'
import MathText from './MathText'

/**
 * Split card text by math delimiters. Backend sends already-normalized LaTeX;
 * no LaTeX repair or alteration on the frontend—only split and render.
 * Returns [{ type: 'text'|'math', content: string, display?: boolean }, ...]
 */
function splitByMath(str) {
  if (!str || typeof str !== 'string') return [{ type: 'text', content: str || '' }]
  const segments = []
  let i = 0
  while (i < str.length) {
    // Display: $$...$$
    if (str.slice(i, i + 2) === '$$') {
      const end = str.indexOf('$$', i + 2)
      if (end === -1) {
        segments.push({ type: 'text', content: str.slice(i) })
        break
      }
      segments.push({ type: 'math', content: str.slice(i, end + 2), display: true })
      i = end + 2
      continue
    }
    // Display: \[...\]
    if (str.slice(i, i + 2) === '\\[') {
      const end = str.indexOf('\\]', i + 2)
      if (end === -1) {
        segments.push({ type: 'text', content: str.slice(i) })
        break
      }
      segments.push({ type: 'math', content: str.slice(i, end + 2), display: true })
      i = end + 2
      continue
    }
    // Inline: $...$
    if (str[i] === '$') {
      let depth = 0
      let j = i + 1
      while (j < str.length) {
        if (str[j] === '\\') {
          j += 2
          continue
        }
        if (str[j] === '{') depth++
        else if (str[j] === '}') depth--
        else if (str[j] === '$' && depth === 0) break
        j++
      }
      if (j < str.length) {
        segments.push({ type: 'math', content: str.slice(i, j + 1), display: false })
        i = j + 1
        continue
      }
    }
    // No math start; take until next $ or end
    const next = str.indexOf('$', i)
    const end = next === -1 ? str.length : next
    if (end > i) {
      segments.push({ type: 'text', content: str.slice(i, end) })
    }
    i = end === i ? i + 1 : end
  }
  return segments.length ? segments : [{ type: 'text', content: '' }]
}

/**
 * Renders card content by splitting on math delimiters. No Markdown parsing,
 * no LaTeX repair—backend is the single source of truth for LaTeX.
 */
function CardContent({ text, style = {} }) {
  const segments = useMemo(() => splitByMath(text), [text])
  return (
    <span style={{ whiteSpace: 'pre-wrap', ...style }}>
      {segments.map((seg, idx) =>
        seg.type === 'text' ? (
          <span key={idx}>{seg.content}</span>
        ) : (
          <MathText key={idx} text={seg.content} inline={!seg.display} />
        )
      )}
    </span>
  )
}

/**
 * RevisionCard - A flashcard-style component for studying.
 * Front/back are rendered by splitting on $...$ and $$...$$; LaTeX is
 * normalized only in the backend—do not repair or alter it here.
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
          <div
            style={{
              position: 'absolute',
              top: '1rem',
              right: '1rem',
              fontSize: '0.875rem',
              opacity: 0.8
            }}
          >
            {cardNumber} / {totalCards}
          </div>
          <div
            style={{
              fontSize: '1.5rem',
              fontWeight: 'bold',
              marginBottom: '1rem',
              textAlign: 'center',
              width: '100%'
            }}
          >
            <CardContent text={front || ''} />
          </div>
          <div
            style={{
              fontSize: '0.875rem',
              opacity: 0.9,
              marginTop: '1rem'
            }}
          >
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
          <div
            style={{
              position: 'absolute',
              top: '1rem',
              right: '1rem',
              fontSize: '0.875rem',
              color: 'var(--text-muted)'
            }}
          >
            {cardNumber} / {totalCards}
          </div>
          <div
            style={{
              fontSize: '1rem',
              lineHeight: 1.6,
              color: 'var(--text-primary)',
              flex: '1 1 auto',
              minHeight: 0,
              overflowY: 'auto'
            }}
          >
            <CardContent text={back || ''} />
          </div>
          <div
            style={{
              fontSize: '0.875rem',
              color: 'var(--text-muted)',
              marginTop: '0.75rem',
              textAlign: 'center',
              flexShrink: 0,
              paddingTop: '0.5rem',
              borderTop: '1px solid var(--border-color)'
            }}
          >
            Click to flip back
          </div>
        </div>
      </div>
    </div>
  )
}
