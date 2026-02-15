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
    
    // CRITICAL: Protect display math blocks ($$...$$) first to prevent breaking them
    const displayMathBlocks = []
    let protectedText = text
    let mathIndex = 0
    
    // Extract and protect display math blocks
    protectedText = protectedText.replace(/\$\$[\s\S]*?\$\$/g, (match) => {
      const placeholder = `__DISPLAY_MATH_${mathIndex}__`
      displayMathBlocks.push({ placeholder, content: match })
      mathIndex++
      return placeholder
    })
    
    // CRITICAL: Fix \frac\frac (double fraction) FIRST - convert to single \frac
    // This must happen before any other processing
    let normalized = protectedText.replace(/\\frac\\frac/g, '\\frac')
    
    // CRITICAL: Fix \f\frac -> \frac (when \f is left before \frac)
    // This happens when \frac lost its \f part, leaving \f, then \frac was added
    normalized = normalized.replace(/\\f\\frac/g, '\\frac')
    
    // CRITICAL: Fix \fracrac patterns FIRST (before form feed handling)
    // This handles cases where \frac lost \f, became rac{, and we incorrectly added \frac
    normalized = normalized.replace(/\\fracrac\{/g, '\\frac{')
    normalized = normalized.replace(/\\fracrac/g, '\\frac')
    
    // CRITICAL: Fix form feed characters - these are \f in Python strings that became \u000C
    // The pattern \f\f suggests \frac where the 'rac' parts were lost
    
    // Pattern: \f\f followed by {anything}{anything} -> \frac{anything}{anything}
    // This handles \frac{v-u}{t} that became \f\f{v-u}{t}
    normalized = normalized.replace(/\\f\\f\{([^}]+)\}\{([^}]+)\}/g, '\\frac{$1}{$2}')
    
    // Pattern: \f\f followed by {digit}{digit} -> \frac{digit}{digit}
    // This handles \frac{1}{2} that became \f\f{1}{2}
    normalized = normalized.replace(/\\f\\f\{(\d+)\}\{(\d+)\}/g, '\\frac{$1}{$2}')
    
    // Pattern: \f\f followed by {digit or { -> \frac{ (most common: \frac{1} or \frac{2})
    normalized = normalized.replace(/\\f\\f\{(\d+)\}/g, '\\frac{$1}')
    
    // Pattern: \f\f in math context (like E=\f\f) -> \frac
    // This handles cases where \frac{1}{2} became \f\f{1}{2}
    normalized = normalized.replace(/([=\[\(])\\f\\f([\d\{])/g, '$1\\frac{$2')
    normalized = normalized.replace(/\\f\\f([\d\{])/g, '\\frac{$1')
    
    // CRITICAL: Fix \t (tab) characters that appear in \text{...}
    // When \text{ becomes \t + ext{ or \t + \text{, we need to fix it
    // Handle both escape sequence \t and literal tab character (0x09)
    
    // Pattern: \t followed by ext{ -> \text{ (without backslash before ext)
    normalized = normalized.replace(/\\t(ext\{)/g, '\\text{')
    normalized = normalized.replace(/\\t\s*ext\{/g, '\\text{')
    normalized = normalized.replace(/\t(ext\{)/g, '\\text{')
    normalized = normalized.replace(/\t\s*ext\{/g, '\\text{')
    
    // Pattern: \t followed by \text{ -> \text{ (with backslash before text)
    // This handles cases where \text{ became \t\text{
    normalized = normalized.replace(/\\t\\text\{/g, '\\text{')
    normalized = normalized.replace(/\\t\s*\\text\{/g, '\\text{')
    normalized = normalized.replace(/\t\\text\{/g, '\\text{')
    normalized = normalized.replace(/\t\s*\\text\{/g, '\\text{')
    
    // More aggressive: remove \t anywhere it appears before text commands
    normalized = normalized.replace(/\\t\s*\\text/g, '\\text')
    normalized = normalized.replace(/\t\s*\\text/g, '\\text')
    
    // Pattern: \t in math context where it should be part of \text
    // Handle cases like: $u = 0 \t\text{ m/s}$ -> $u = 0 \text{ m/s}$
    normalized = normalized.replace(/(\d+)\s*\\t\s*ext\{([^}]+)\}/g, '$1 \\text{$2}')
    normalized = normalized.replace(/(\d+)\s*\t\s*ext\{([^}]+)\}/g, '$1 \\text{$2}')
    normalized = normalized.replace(/(\d+)\s*\\t\s*\\text\{([^}]+)\}/g, '$1 \\text{$2}')
    normalized = normalized.replace(/(\d+)\s*\t\s*\\text\{([^}]+)\}/g, '$1 \\text{$2}')
    
    // More aggressive: fix \t\text{ anywhere in math mode
    normalized = normalized.replace(/\$([^$]*?)\\t\s*ext\{([^}]+)\}([^$]*?)\$/g, '$$1\\text{$2}$3$')
    normalized = normalized.replace(/\$([^$]*?)\t\s*ext\{([^}]+)\}([^$]*?)\$/g, '$$1\\text{$2}$3$')
    normalized = normalized.replace(/\$([^$]*?)\\t\s*\\text\{([^}]+)\}([^$]*?)\$/g, '$$1\\text{$2}$3$')
    normalized = normalized.replace(/\$([^$]*?)\t\s*\\text\{([^}]+)\}([^$]*?)\$/g, '$$1\\text{$2}$3$')
    
    // Also handle display math $$...$$
    // Note: In replacement strings, $$ = literal $, so $$$1 = $$ + $1 (backreference)
    normalized = normalized.replace(/\$\$([\s\S]*?)\\t\s*ext\{([^}]+)\}([\s\S]*?)\$\$/g, '$$$1\\text{$2}$3$$')
    normalized = normalized.replace(/\$\$([\s\S]*?)\t\s*ext\{([^}]+)\}([\s\S]*?)\$\$/g, '$$$1\\text{$2}$3$$')
    normalized = normalized.replace(/\$\$([\s\S]*?)\\t\s*\\text\{([^}]+)\}([\s\S]*?)\$\$/g, '$$$1\\text{$2}$3$$')
    normalized = normalized.replace(/\$\$([\s\S]*?)\t\s*\\text\{([^}]+)\}([\s\S]*?)\$\$/g, '$$$1\\text{$2}$3$$')
    
    // Note: \frac\frac fix is already done at the beginning
    
    // Pattern: \f\f (standalone, anywhere) -> \frac
    // This is a catch-all for \f\f patterns that don't match above
    normalized = normalized.replace(/\\f\\f/g, '\\frac')
    
    // Pattern: \f followed by {digit or { -> \frac{ (single \f case)
    normalized = normalized.replace(/\\f\{(\d+)\}/g, '\\frac{$1}')
    normalized = normalized.replace(/\\f([\d\{])/g, '\\frac{$1}')
    
    // Pattern: \f (standalone in math context) -> \frac
    // Only replace if it's clearly in a math expression
    normalized = normalized.replace(/([=\[\(,\s])\\f([\d\{])/g, '$1\\frac{$2')
    
    // Pattern: form feed character (Unicode \u000C) followed by "rac" -> "\frac"
    normalized = normalized.replace(/\u000Crac/g, '\\frac')
    
    // Pattern: multiple form feeds (like \u000C\u000C) - likely \frac (NOT \frac\frac)
    normalized = normalized.replace(/\u000C\u000C/g, '\\frac')
    normalized = normalized.replace(/\u000C\u000C\{(\d+)\}/g, '\\frac{$1}')
    
    // Pattern: form feed followed by "rac{" -> "\frac{"
    normalized = normalized.replace(/\u000Crac\{/g, '\\frac{')
    
    // Pattern: form feed followed by any lowercase LaTeX command -> "\command"
    normalized = normalized.replace(/\u000C([a-z]+)/g, '\\$1')
    
    // Pattern: form feed before backslash (like "\u000C\frac" -> "\frac")
    normalized = normalized.replace(/\u000C\\/g, '\\')
    
    // Pattern: standalone form feed in math context (likely \frac) -> \frac
    normalized = normalized.replace(/([=\(\[\{,\s])\u000C([\d\{])/g, '$1\\frac{$2')
    
    // Remove remaining standalone form feed characters (not part of a command)
    normalized = normalized.replace(/\u000C(?!\w)/g, '')
    
    // Now normalize over-escaped backslashes (similar to MathText component)
    // This handles double-escaping that can occur in JSON serialization
    // Replace 4+ consecutive backslashes with 2 backslashes
    normalized = normalized.replace(/(\\\\){2,}/g, '\\\\')
    
    // Fix missing backslashes before LaTeX commands
    // Pattern: "ext{" should be "\text{" (when not already escaped)
    // Also handle cases where backslash was lost: "text{" -> "\text{"
    normalized = normalized.replace(/([^\\])ext\{/g, '$1\\text{')
    normalized = normalized.replace(/^ext\{/g, '\\text{')
    normalized = normalized.replace(/([^\\])text\{/g, '$1\\text{')
    normalized = normalized.replace(/^text\{/g, '\\text{')
    
    // Fix "rac{" -> "\frac{" (when \frac lost its backslash and became form feed + "rac")
    // CRITICAL: Fix \fracrac{ FIRST before fixing rac{ patterns
    // This handles cases where \frac lost \f, became rac{, and we incorrectly added \frac
    normalized = normalized.replace(/\\fracrac\{/g, '\\frac{')
    normalized = normalized.replace(/\\fracrac/g, '\\frac')
    
    // Then fix standalone rac{ patterns (but not if it's part of \fracrac)
    // Pattern: rac{ at start of string or after non-backslash, non-f character
    normalized = normalized.replace(/([^\\f])rac\{/g, '$1\\frac{')
    normalized = normalized.replace(/^rac\{/g, '\\frac{')
    
    // Also handle rac{ that might appear after spaces or other characters
    normalized = normalized.replace(/\s+rac\{/g, ' \\frac{')
    
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
    
    // Restore display math blocks that were protected at the beginning
    // But first normalize them for \t and \frac\frac issues
    displayMathBlocks.forEach(({ placeholder, content }) => {
      let normalizedContent = content
      // Fix \frac\frac in display math
      normalizedContent = normalizedContent.replace(/\\frac\\frac/g, '\\frac')
      // Fix \t issues in display math
      normalizedContent = normalizedContent.replace(/\\t(ext\{)/g, '\\text{')
      normalizedContent = normalizedContent.replace(/\\t\s*ext\{/g, '\\text{')
      normalizedContent = normalizedContent.replace(/\t(ext\{)/g, '\\text{')
      normalizedContent = normalizedContent.replace(/\t\s*ext\{/g, '\\text{')
      normalizedContent = normalizedContent.replace(/\\t\\text\{/g, '\\text{')
      normalizedContent = normalizedContent.replace(/\\t\s*\\text\{/g, '\\text{')
      normalizedContent = normalizedContent.replace(/\t\\text\{/g, '\\text{')
      normalizedContent = normalizedContent.replace(/\t\s*\\text\{/g, '\\text{')
      normalized = normalized.replace(placeholder, normalizedContent)
    })
    
    // For back content, convert newlines to <br> tags for proper HTML rendering
    // But preserve newlines in LaTeX math blocks (between $...$ or $$...$$)
    if (isBack) {
      // First, extract and protect all math expressions (including the restored display math)
      const mathExpressions = []
      let mathIndex = 0
      
      // Extract display math ($$...$$) - these can contain newlines
      normalized = normalized.replace(/\$\$[\s\S]*?\$\$/g, (match) => {
        const placeholder = `__MATH_DISPLAY_${mathIndex}__`
        mathExpressions.push({ placeholder, content: match })
        mathIndex++
        return placeholder
      })
      
      // Extract inline math ($...$) - these should not contain newlines
      normalized = normalized.replace(/\$[^$\n]+?\$/g, (match) => {
        const placeholder = `__MATH_INLINE_${mathIndex}__`
        mathExpressions.push({ placeholder, content: match })
        mathIndex++
        return placeholder
      })
      
      // Now convert newlines to <br> in the non-math parts
      normalized = normalized.replace(/\n/g, '<br>')
      
      // Restore math expressions
      mathExpressions.forEach(({ placeholder, content }) => {
        normalized = normalized.replace(placeholder, content)
      })
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
