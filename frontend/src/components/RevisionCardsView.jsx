import { useState, useEffect, useMemo } from 'react'
import { tests } from '../services/api'
import RevisionCard from './RevisionCard'
import LoadingSpinner from './LoadingSpinner'

export default function RevisionCardsView({ 
  guideId, 
  contextPayload,
  onAskCoach 
}) {
  const [guide, setGuide] = useState(null)
  const [loading, setLoading] = useState(true)
  const [currentCardIndex, setCurrentCardIndex] = useState(0)
  const [cardDifficulty, setCardDifficulty] = useState({}) // { cardIndex: 'easy' | 'medium' | 'hard' }

  useEffect(() => {
    loadGuide()
  }, [guideId])

  const loadGuide = async () => {
    try {
      setLoading(true)
      const data = await tests.getStudyGuide(guideId)
      setGuide(data)
    } catch (err) {
      console.error('Failed to load study guide:', err)
    } finally {
      setLoading(false)
    }
  }

  const revisionCards = useMemo(() => {
    if (!guide) return []
    if (guide.metadata?.revision_cards) {
      return guide.metadata.revision_cards.filter(
        card => card && card.front && card.back
      )
    }
    return []
  }, [guide])

  const currentCard = revisionCards[currentCardIndex]

  const handleCardDifficulty = (difficulty) => {
    setCardDifficulty(prev => ({
      ...prev,
      [currentCardIndex]: difficulty
    }))
  }

  // Reset card index when cards change
  useEffect(() => {
    if (revisionCards.length > 0 && currentCardIndex >= revisionCards.length) {
      setCurrentCardIndex(0)
    }
  }, [revisionCards.length, currentCardIndex])

  if (loading) return <LoadingSpinner />
  if (!guide || revisionCards.length === 0) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center' }}>
        <p>No revision cards available for this guide.</p>
      </div>
    )
  }

  return (
    <div style={{ padding: '2rem' }}>
      {/* Card Counter */}
      <div style={{
        textAlign: 'center',
        marginBottom: '1.5rem'
      }}>
        <span style={{ fontSize: '0.875rem', color: 'var(--text-color)' }}>
          Card {currentCardIndex + 1} of {revisionCards.length}
        </span>
      </div>

      {/* Card Display with Navigation Arrows */}
      {currentCard && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '1rem',
          position: 'relative'
        }}>
          {/* Left Arrow */}
          <button
            onClick={() => setCurrentCardIndex(prev => 
              prev > 0 ? prev - 1 : revisionCards.length - 1
            )}
            disabled={revisionCards.length <= 1}
            style={{
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '50%',
              width: '48px',
              height: '48px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: revisionCards.length <= 1 ? 'not-allowed' : 'pointer',
              fontSize: '1.5rem',
              color: revisionCards.length <= 1 ? 'var(--text-muted)' : 'var(--text-color)',
              transition: 'all 0.2s',
              flexShrink: 0,
              padding: 0
            }}
            onMouseEnter={(e) => {
              if (revisionCards.length > 1) {
                e.currentTarget.style.background = 'var(--primary-color-light)'
                e.currentTarget.style.borderColor = 'var(--primary-color)'
              }
            }}
            onMouseLeave={(e) => {
              if (revisionCards.length > 1) {
                e.currentTarget.style.background = 'var(--bg-secondary)'
                e.currentTarget.style.borderColor = 'var(--border-color)'
              }
            }}
            title="Previous card"
          >
            ←
          </button>

          {/* Card */}
          <div style={{ flex: 1 }}>
            <RevisionCard
              front={currentCard.front}
              back={currentCard.back}
              cardNumber={currentCardIndex + 1}
              totalCards={revisionCards.length}
            />
          </div>

          {/* Right Arrow */}
          <button
            onClick={() => setCurrentCardIndex(prev => 
              prev < revisionCards.length - 1 ? prev + 1 : 0
            )}
            disabled={revisionCards.length <= 1}
            style={{
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '50%',
              width: '48px',
              height: '48px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: revisionCards.length <= 1 ? 'not-allowed' : 'pointer',
              fontSize: '1.5rem',
              color: revisionCards.length <= 1 ? 'var(--text-muted)' : 'var(--text-color)',
              transition: 'all 0.2s',
              flexShrink: 0,
              padding: 0
            }}
            onMouseEnter={(e) => {
              if (revisionCards.length > 1) {
                e.currentTarget.style.background = 'var(--primary-color-light)'
                e.currentTarget.style.borderColor = 'var(--primary-color)'
              }
            }}
            onMouseLeave={(e) => {
              if (revisionCards.length > 1) {
                e.currentTarget.style.background = 'var(--bg-secondary)'
                e.currentTarget.style.borderColor = 'var(--border-color)'
              }
            }}
            title="Next card"
          >
            →
          </button>
        </div>
      )}

      {/* Difficulty Feedback */}
      <div style={{
        marginTop: '2rem',
        padding: '1rem',
        background: 'var(--bg-secondary)',
        borderRadius: 'var(--radius-md)',
        border: '1px solid var(--border-color)'
      }}>
        <div style={{ marginBottom: '0.75rem', fontWeight: '600' }}>
          How difficult was this card?
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {['easy', 'medium', 'hard'].map(difficulty => (
            <button
              key={difficulty}
              onClick={() => handleCardDifficulty(difficulty)}
              style={{
                flex: 1,
                padding: '0.5rem',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-sm)',
                background: cardDifficulty[currentCardIndex] === difficulty
                  ? 'var(--primary-color)'
                  : 'var(--bg-primary)',
                color: cardDifficulty[currentCardIndex] === difficulty
                  ? 'white'
                  : 'var(--text-color)',
                cursor: 'pointer',
                transition: 'all 0.2s'
              }}
            >
              {difficulty.charAt(0).toUpperCase() + difficulty.slice(1)}
            </button>
          ))}
        </div>
        {cardDifficulty[currentCardIndex] === 'hard' && (
          <button
            onClick={() => onAskCoach?.(currentCard)}
            className="btn-primary"
            style={{ marginTop: '1rem', width: '100%' }}
          >
            Ask Coach about this Card
          </button>
        )}
      </div>
    </div>
  )
}
