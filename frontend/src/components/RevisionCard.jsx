import { useState } from 'react'
import MathText from './MathText'

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
            <MathText text={front} inline={false} />
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
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
            border: '2px solid var(--border-color)',
            overflowY: 'auto'
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
            color: 'var(--text-primary)'
          }}>
            <MathText text={back} inline={false} />
          </div>
          <div style={{ 
            fontSize: '0.875rem', 
            color: 'var(--text-muted)',
            marginTop: '1rem',
            textAlign: 'center'
          }}>
            Click to flip back
          </div>
        </div>
      </div>
    </div>
  )
}
