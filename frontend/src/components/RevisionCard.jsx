import { useState, useMemo } from 'react'
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

  // Normalize LaTeX escaping - fix double/triple backslashes and missing backslashes
  // Also converts newlines to <br> for proper HTML rendering
  const normalizeLaTeX = (text, isBack = false) => {
    if (!text || typeof text !== 'string') return text
    
    // First, handle cases where backslashes were lost during JSON parsing
    // If we see patterns like "ext{" or "ext " that should be "\text{", fix them
    // But be careful not to break valid text
    
    // Fix missing backslashes before LaTeX commands
    // Pattern: "ext{" should be "\text{" (when not already escaped)
    // Also handle cases where backslash was lost: "text{" -> "\text{"
    let normalized = text.replace(/([^\\])ext\{/g, '$1\\text{')
    normalized = normalized.replace(/^ext\{/g, '\\text{')
    normalized = normalized.replace(/([^\\])text\{/g, '$1\\text{')
    normalized = normalized.replace(/^text\{/g, '\\text{')
    
    // Fix "rac{" -> "\frac{" (when \frac lost its backslash and became form feed + "rac")
    // Also handle direct "rac{" pattern
    normalized = normalized.replace(/([^\\])rac\{/g, '$1\\frac{')
    normalized = normalized.replace(/^rac\{/g, '\\frac{')
    
    // Fix form feed character (0x0C) - this happens when Python interprets \f as form feed
    // Pattern: form feed followed by "rac" -> "\frac"
    normalized = normalized.replace(/\u000Crac/g, '\\frac')
    
    // Also fix form feed followed by any LaTeX-like command pattern (lowercase commands)
    normalized = normalized.replace(/\u000C([a-z]+)/g, '\\$1')
    
    // Fix form feed before backslash (like "\u000C\frac" -> "\frac")
    normalized = normalized.replace(/\u000C\\/g, '\\')
    
    // Remove standalone form feed characters (not part of a command)
    normalized = normalized.replace(/\u000C(?!\w)/g, '')
    
    // Don't replace \frac - it's already correct. Only fix "rac" without backslash
    
    // Fix broken LaTeX patterns where \text lost its backslash
    // Pattern: "10.0extm" -> "10.0 \text{m}"
    // Pattern: "10.0 extm" -> "10.0 \text{m}"
    normalized = normalized.replace(/(\d+\.?\d*)\s*ext([a-zA-Z])/g, '$1 \\text{$2}')
    normalized = normalized.replace(/(\d+\.?\d*)\s*ext\{([^}]+)\}/g, '$1 \\text{$2}')
    
    // Fix patterns like "extms−1" or "extms^{-1}" -> "\text{ms}^{-1}"
    normalized = normalized.replace(/ext([a-zA-Z]+)([−\-])(\d+)/g, '\\text{$1}^{$3}')
    normalized = normalized.replace(/ext\{([^}]+)\}([−\-])(\d+)/g, '\\text{$1}^{$3}')
    
    // Fix patterns in math mode: $h = 10.0 ext m$ -> $h = 10.0 \text{ m}$
    // Also handle cases where backslash was completely lost: $h = 10.0extm$ -> $h = 10.0 \text{m}$
    normalized = normalized.replace(/\$([^$]*?)(\d+\.?\d*)\s*ext\s*([a-zA-Z])([^$]*?)\$/g, '$$1$2 \\text{$3}$4$')
    normalized = normalized.replace(/\$([^$]*?)(\d+\.?\d*)\s*ext([a-zA-Z]+)([^$]*?)\$/g, '$$1$2 \\text{$3}$4$')
    
    // Fix specific pattern: "h=10.0extm" -> "h=10.0 \text{m}" (even outside math mode)
    normalized = normalized.replace(/([a-zA-Z])\s*=\s*(\d+\.?\d*)\s*ext([a-zA-Z]+)/g, '$1 = $2 \\text{$3}')
    
    // Fix pattern: "vx=20.0extms" -> "v_x=20.0 \text{ms}"
    normalized = normalized.replace(/([a-zA-Z])([xyz])\s*=\s*(\d+\.?\d*)\s*ext([a-zA-Z]+)/g, '$1_$2 = $3 \\text{$4}')
    
    // Now fix over-escaping (iteratively replace \\\\ with \\ until no more changes)
    let previous = ''
    while (normalized !== previous) {
      previous = normalized
      // Replace 4+ backslashes with 2 backslashes (for LaTeX commands)
      normalized = normalized.replace(/\\\\\\+/g, '\\\\')
    }
    
    // Fix subscript patterns like "vx" where it should be "v_x" (but be conservative)
    // Only fix if it's clearly a physics variable pattern (vx, vy, ax, ay, etc.)
    const physicsVars = ['vx', 'vy', 'vz', 'ax', 'ay', 'az', 'ux', 'uy', 'uz']
    physicsVars.forEach(varName => {
      const pattern = new RegExp(`([^_\\$])${varName[0]}${varName[1]}([^a-zA-Z_])`, 'g')
      normalized = normalized.replace(pattern, `$1${varName[0]}_${varName[1]}$2`)
    })
    
    // Fix patterns like "h=10.0" where units are missing backslash
    // Look for patterns like "=10.0extm" or "=10.0 extm"
    normalized = normalized.replace(/=\s*(\d+\.?\d*)\s*ext([a-zA-Z])/g, '= $1 \\text{$2}')
    
    // For back content, convert newlines to <br> tags for proper HTML rendering
    // But preserve newlines in LaTeX math blocks (between $...$ or $$...$$)
    if (isBack) {
      // Split by math delimiters to preserve newlines inside math
      const parts = normalized.split(/(\$\$[\s\S]*?\$\$|\$[^$\n]+?\$)/)
      const processedParts = parts.map((part, idx) => {
        // If this part is a math expression, keep it as is
        if (part.match(/^\$\$[\s\S]*?\$\$$/) || part.match(/^\$[^$\n]+?\$$/)) {
          return part
        }
        // Otherwise, convert newlines to <br>
        return part.replace(/\n/g, '<br>')
      })
      normalized = processedParts.join('')
    }
    
    return normalized
  }

  const normalizedFront = useMemo(() => normalizeLaTeX(front, false), [front])
  const normalizedBack = useMemo(() => normalizeLaTeX(back, true), [back])

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
            color: 'var(--text-primary)',
            whiteSpace: 'pre-wrap' // Preserve newlines and line breaks
          }}>
            <MathText text={normalizedBack} inline={false} />
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
