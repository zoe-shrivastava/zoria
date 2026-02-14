import { useState, useEffect } from 'react'
import { tests } from '../services/api'
import { showNotification } from '../utils/notifications'
import LoadingSpinner from './LoadingSpinner'
import MathText from './MathText'
import GraphDrawingCanvas from './GraphDrawingCanvas'
import DiagramDrawingCanvas from './DiagramDrawingCanvas'

export default function QuizPlayer({ testId, onComplete, readOnly = false }) {
  const [test, setTest] = useState(null)
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0)
  const [answers, setAnswers] = useState({})
  const [timeRemaining, setTimeRemaining] = useState(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [started, setStarted] = useState(false)
  // State for showing/hiding canvases per question
  const [canvasVisibility, setCanvasVisibility] = useState({}) // { questionId: { showGraph: bool, showDiagram: bool } }
  // State for showing hints per question
  const [showHints, setShowHints] = useState({}) // { questionId: bool }
  // State to track if graphs/diagrams are currently rendering
  const [isGraphRendering, setIsGraphRendering] = useState(false)

  useEffect(() => {
    loadTest()
  }, [testId])

  useEffect(() => {
    if (test && test.time_limit_minutes && started && !readOnly) {
      const totalSeconds = test.time_limit_minutes * 60
      setTimeRemaining(totalSeconds)

      const interval = setInterval(() => {
        setTimeRemaining((prev) => {
          if (prev <= 1) {
            clearInterval(interval)
            handleSubmit()
            return 0
          }
          return prev - 1
        })
      }, 1000)

      return () => clearInterval(interval)
    }
  }, [test, started, readOnly])

  // Monitor for graph/diagram rendering status
  useEffect(() => {
    const checkRenderingStatus = () => {
      // Check for loading indicators in the DOM
      const loadingElements = document.querySelectorAll('.tikz-loading')
      const hasLoading = loadingElements.length > 0
      
      // Also check for containers with _isRendering flag
      const tikzContainers = document.querySelectorAll('.tikz-diagram')
      let hasRenderingFlag = false
      tikzContainers.forEach(container => {
        if (container._isRendering) {
          hasRenderingFlag = true
        }
      })
      
      const isRendering = hasLoading || hasRenderingFlag
      setIsGraphRendering(isRendering)
    }

    // Check immediately
    checkRenderingStatus()

    // Set up interval to check periodically
    const interval = setInterval(checkRenderingStatus, 500) // Check every 500ms

    // Also use MutationObserver for more immediate updates
    const observer = new MutationObserver(() => {
      checkRenderingStatus()
    })

    // Observe the document body for changes
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['class']
    })

    return () => {
      clearInterval(interval)
      observer.disconnect()
    }
  }, [currentQuestionIndex]) // Re-run when question changes

  const loadTest = async () => {
    try {
      setLoading(true)
      const testData = await tests.get(testId)
      setTest(testData)
      
      // Load existing answers
      const existingAnswers = {}
      if (testData.questions) {
        testData.questions.forEach((q) => {
          if (q.answer) {
            existingAnswers[q.question_id] = q.answer
            // Debug: Log loaded answers
            console.log('Loaded answer for question:', {
              questionId: q.question_id,
              answerType: typeof q.answer,
              answerLength: q.answer?.length,
              answerPreview: typeof q.answer === 'string' 
                ? q.answer.substring(0, 100) 
                : JSON.stringify(q.answer).substring(0, 100)
            })
          }
        })
      }
      setAnswers(existingAnswers)
      console.log('All loaded answers:', existingAnswers)

      // Check if test is already started
      if (testData.status === 'active' || testData.status === 'completed') {
        setStarted(true)
      }
    } catch (error) {
      showNotification(error.message || 'Failed to load test', 'error')
    } finally {
      setLoading(false)
    }
  }

  // Helper to parse answer (could be string or JSON object)
  const parseAnswer = (answer) => {
    if (!answer) return { text: '', graph: null, diagram: null }
    
    // First, try to parse as JSON if it's a string
    let parsed = answer
    if (typeof answer === 'string') {
      try {
        parsed = JSON.parse(answer)
      } catch (e) {
        // Not valid JSON, treat as plain text
        return { text: answer, graph: null, diagram: null }
      }
    }
    
    // If parsed is an object, check what type it is
    if (typeof parsed === 'object' && parsed !== null) {
      // Check if it's a combined answer format (has text/graph/diagram keys)
      if ('text' in parsed || 'graph' in parsed || 'diagram' in parsed) {
        // It's a combined answer format
        let graph = parsed.graph || null
        let diagram = parsed.diagram || null
        
        // If graph is a string that looks like JSON, try to parse it
        if (graph && typeof graph === 'string' && graph.trim().startsWith('{')) {
          try {
            graph = JSON.parse(graph)
          } catch (e) {
            // Keep as string if parsing fails
          }
        }
        
        // If diagram is a string that looks like JSON, try to parse it
        if (diagram && typeof diagram === 'string' && diagram.trim().startsWith('{')) {
          try {
            diagram = JSON.parse(diagram)
          } catch (e) {
            // Keep as string if parsing fails
          }
        }
        
        return {
          text: parsed.text || '',
          graph: graph,
          diagram: diagram
        }
      }
      
      // Check if it's a canvas drawing (has version and objects array)
      if (parsed.objects && Array.isArray(parsed.objects) && (parsed.version || parsed.type === 'path' || parsed.objects.some(obj => obj.type === 'path'))) {
        // It's a canvas drawing - determine if it's graph or diagram based on context
        // For now, assume it's a graph (we can enhance this later)
        return { text: '', graph: parsed, diagram: null }
      }
    }
    
    // Otherwise, treat as text
    return { text: typeof answer === 'string' ? answer : JSON.stringify(answer), graph: null, diagram: null }
  }

  // Helper to combine answer components into JSON string
  const combineAnswer = (text, graph, diagram) => {
    const combined = {
      text: text || '',
      graph: graph || null,
      diagram: diagram || null
    }
    // Only include non-empty fields
    const filtered = Object.fromEntries(
      Object.entries(combined).filter(([_, v]) => v !== null && v !== '')
    )
    
    // Always stringify to ensure consistent format
    // If only one field, still stringify it (but as a single value)
    if (Object.keys(filtered).length === 1) {
      const singleValue = Object.values(filtered)[0]
      // If it's already a string (like a JSON string), return it as-is
      // Otherwise, stringify it
      if (typeof singleValue === 'string') {
        return singleValue
      }
      return JSON.stringify(singleValue)
    }
    // Multiple fields - stringify the combined object
    return JSON.stringify(filtered)
  }

  // Update answer component (text, graph, or diagram)
  const handleAnswerComponentChange = async (questionId, component, value) => {
    const currentAnswer = answers[questionId] || ''
    const parsed = parseAnswer(currentAnswer)
    
    let newCombined
    if (component === 'text') {
      newCombined = combineAnswer(value, parsed.graph, parsed.diagram)
    } else if (component === 'graph') {
      newCombined = combineAnswer(parsed.text, value, parsed.diagram)
    } else if (component === 'diagram') {
      newCombined = combineAnswer(parsed.text, parsed.graph, value)
    } else {
      return
    }
    
    await handleAnswerChange(questionId, newCombined)
  }

  const handleStart = async () => {
    try {
      setLoading(true)
      const startedTest = await tests.start(testId)
      setTest(startedTest)
      setStarted(true)
      showNotification('Test started!', 'success')
    } catch (error) {
      showNotification(error.message || 'Failed to start test', 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleAnswerChange = async (questionId, answer) => {
    const newAnswers = { ...answers, [questionId]: answer }
    setAnswers(newAnswers)

    // Auto-save answer
    if (!readOnly && started) {
      try {
        // Ensure answer is a string (required by API)
        const answerString = typeof answer === 'string' ? answer : JSON.stringify(answer)
        console.log('Saving answer:', {
          questionId,
          answerType: typeof answer,
          answerStringLength: answerString.length,
          answerPreview: answerString.substring(0, 200)
        })
        await tests.answer(testId, questionId, answerString)
        console.log('✅ Answer saved successfully:', { 
          questionId, 
          answerLength: answerString.length,
          answerPreview: answerString.substring(0, 200)
        })
      } catch (error) {
        console.error('❌ Failed to save answer:', error)
        showNotification('Failed to save answer. Please try again.', 'error')
      }
    }
  }

  const handleSubmit = async () => {
    if (!window.confirm('Are you sure you want to submit this test? You cannot change answers after submitting.')) {
      return
    }

    try {
      setSubmitting(true)
      const result = await tests.submit(testId)
      showNotification(
        `Test submitted! Score: ${result.percentage.toFixed(1)}% (${result.correct_count}/${result.graded_count})`,
        'success'
      )
      if (onComplete) {
        onComplete(result)
      }
      // Reload test to show scores
      await loadTest()
    } catch (error) {
      showNotification(error.message || 'Failed to submit test', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  const handleDownload = () => {
    if (!test || !test.questions) return

    const lines = []
    lines.push(`Test: ${test.title}`)
    lines.push(`Status: ${test.status}`)
    if (test.completed_at) {
      // If date string doesn't have timezone info (no 'Z' or +/-), treat it as UTC
      let dateStr = test.completed_at
      if (!dateStr.includes('Z') && !dateStr.match(/[+-]\d{2}:\d{2}$/)) {
        // Add 'Z' to indicate UTC if not present
        dateStr = dateStr.endsWith('Z') ? dateStr : dateStr + 'Z'
      }
      const date = new Date(dateStr)
      // Use browser's local timezone - toLocaleString() automatically converts UTC to local timezone
      lines.push(`Completed at: ${date.toLocaleString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        timeZoneName: 'short'
      })}`)
    }
    if (test.total_score != null && test.max_score != null) {
      lines.push(`Score: ${test.total_score}/${test.max_score}`)
    }
    lines.push('')

    test.questions.forEach((q, idx) => {
      const qNum = idx + 1
      const options = q.metadata?.options || []
      const correctLetter = (q.metadata?.correct_answer || '').toString().trim().toUpperCase()
      const studentAnswer = q.answer

      lines.push(`Question ${qNum}:`)
      lines.push(q.text || '')
      lines.push('')
      if (options.length) {
        options.forEach((opt, i) => {
          const label = String.fromCharCode('A'.charCodeAt(0) + i)
          lines.push(`  ${label}) ${opt}`)
        })
      }
      lines.push(`Student answer: ${studentAnswer != null ? studentAnswer : '(no answer)'}`)
      if (correctLetter) {
        lines.push(`Correct answer: ${correctLetter}`)
      }
      if (q.is_correct != null) {
        lines.push(`Result: ${q.is_correct ? 'Correct' : 'Incorrect'}`)
      }
      if (q.score != null && q.max_score != null) {
        lines.push(`Score: ${q.score}/${q.max_score}`)
      }
      if (q.metadata?.explanation) {
        lines.push('Explanation:')
        lines.push(q.metadata.explanation)
      }
      lines.push('')
    })

    const content = lines.join('\n')
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `test-${test.id || testId}.txt`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  if (loading) {
    return <LoadingSpinner />
  }

  if (!test) {
    return <div>Test not found</div>
  }

  if (!started && !readOnly) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center' }}>
        <h2>{test.title}</h2>
        <p style={{ margin: '1rem 0', color: 'var(--text-muted)' }}>
          {test.questions?.length || 0} questions
          {test.time_limit_minutes && ` • ${test.time_limit_minutes} minutes`}
        </p>
        <button onClick={handleStart} className="btn-primary" style={{ marginTop: '1rem' }}>
          Start Test
        </button>
      </div>
    )
  }

  const questions = test.questions || []
  const currentQuestion = questions[currentQuestionIndex]
  const answeredCount = Object.keys(answers).filter((id) => answers[id]).length

  if (!currentQuestion) {
    return <div>No questions found</div>
  }

  const isMCQ = currentQuestion.type === 'multiple_choice'
  const options = currentQuestion.metadata?.options || []
  const isCompleted = test.status === 'completed'
  const questionId = currentQuestion.question_id
  const studentAnswer = answers[questionId]
  const hasStudentAnswer = studentAnswer !== undefined && studentAnswer !== null && studentAnswer !== ''
  
  // Parse current answer into components
  const answerComponents = parseAnswer(studentAnswer)
  
  // Debug: Log answer components to help diagnose loading issues
  console.log('Answer components for current question:', {
    questionId,
    studentAnswerType: typeof studentAnswer,
    studentAnswerPreview: studentAnswer 
      ? (typeof studentAnswer === 'string' 
          ? studentAnswer.substring(0, 150) 
          : JSON.stringify(studentAnswer).substring(0, 150))
      : 'null',
    hasText: !!answerComponents.text,
    hasGraph: !!answerComponents.graph,
    hasDiagram: !!answerComponents.diagram,
    graphType: typeof answerComponents.graph,
    graphPreview: answerComponents.graph 
      ? (typeof answerComponents.graph === 'string' 
          ? answerComponents.graph.substring(0, 100) 
          : JSON.stringify(answerComponents.graph).substring(0, 100))
      : 'null'
  })
  
  // Get needs flags from question metadata
  const needsGraph = currentQuestion.metadata?.needs_graph === true
  const needsDiagram = currentQuestion.metadata?.needs_diagram === true
  
  // Get canvas visibility for current question - auto-show if needed
  const currentCanvasVisibility = canvasVisibility[questionId] || { 
    showGraph: needsGraph || false,
    showDiagram: needsDiagram || false
  }
  
  // Initialize canvas visibility based on needs flags when question changes
  useEffect(() => {
    if (currentQuestion && questionId) {
      const needsGraph = currentQuestion.metadata?.needs_graph === true
      const needsDiagram = currentQuestion.metadata?.needs_diagram === true
      
      setCanvasVisibility(prev => ({
        ...prev,
        [questionId]: {
          showGraph: needsGraph || (prev[questionId]?.showGraph ?? false),
          showDiagram: needsDiagram || (prev[questionId]?.showDiagram ?? false)
        }
      }))
    }
  }, [questionId, currentQuestion])
  
  // Toggle canvas visibility
  const toggleCanvas = (canvasType) => {
    setCanvasVisibility(prev => ({
      ...prev,
      [questionId]: {
        ...prev[questionId],
        [canvasType]: !prev[questionId]?.[canvasType]
      }
    }))
  }

  // Toggle hint visibility
  const toggleHint = () => {
    setShowHints(prev => ({
      ...prev,
      [questionId]: !prev[questionId]
    }))
  }

  // Get hint for current question
  // Check multiple possible locations: metadata.hint, metadata.blueprint.hint, or direct hint field
  let hint = null
  if (currentQuestion.metadata) {
    // First check metadata.hint directly (stored when question was created)
    hint = currentQuestion.metadata.hint
    
    // If not found, check metadata.blueprint.hint (blueprint is the full question blueprint)
    if (!hint && currentQuestion.metadata.blueprint) {
      if (typeof currentQuestion.metadata.blueprint === 'object') {
        // Check blueprint.hint directly - this is where it should be according to the schema
        hint = currentQuestion.metadata.blueprint.hint
      } else if (typeof currentQuestion.metadata.blueprint === 'string') {
        try {
          const blueprint = JSON.parse(currentQuestion.metadata.blueprint)
          hint = blueprint.hint
        } catch (e) {
          // Ignore parse errors
        }
      }
    }
  }
  
  // Fallback to direct hint field
  if (!hint) {
    hint = currentQuestion.hint
  }
  
  // Debug logging - show full blueprint structure if hint not found
  if (!hint && currentQuestion.metadata?.blueprint) {
    const blueprint = currentQuestion.metadata.blueprint
    console.log('No hint found for question - checking blueprint structure:', {
      questionId,
      metadataKeys: currentQuestion.metadata ? Object.keys(currentQuestion.metadata) : [],
      metadataHint: currentQuestion.metadata?.hint,
      blueprintType: typeof blueprint,
      blueprintKeys: typeof blueprint === 'object' ? Object.keys(blueprint) : [],
      blueprintHint: typeof blueprint === 'object' ? blueprint.hint : undefined,
      blueprintSample: typeof blueprint === 'object' ? JSON.stringify(blueprint).substring(0, 500) : blueprint?.substring(0, 500)
    })
  }

  // Determine correct answer (MCQ) from metadata
  let correctIndex = null
  let correctText = null
  let correctLabel = null
  if (isMCQ && currentQuestion.metadata?.correct_answer) {
    const letter = String(currentQuestion.metadata.correct_answer).trim().toUpperCase()
    if (['A', 'B', 'C', 'D'].includes(letter)) {
      const idx = letter.charCodeAt(0) - 'A'.charCodeAt(0)
      if (idx >= 0 && idx < options.length) {
        correctIndex = idx
        correctText = options[idx]
        correctLabel = letter
      }
    }
  }

  const shouldShowCorrect =
    isCompleted &&
    isMCQ &&
    correctText &&
    (!hasStudentAnswer || currentQuestion.is_correct === false)

  return (
    <div className="quiz-player" style={{ padding: '1.5rem' }}>
      {/* Header */}
      <div style={{ marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2>{test.title}</h2>
          {timeRemaining !== null && (
            <div style={{ marginTop: '0.5rem', fontSize: '1.25rem', fontWeight: '600' }}>
              Time: {formatTime(timeRemaining)}
            </div>
          )}
        </div>
        <div style={{ textAlign: 'right' }}>
          <div>Question {currentQuestionIndex + 1} of {questions.length}</div>
          <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            {answeredCount} answered
          </div>
        </div>
      </div>

      {/* Progress Bar */}
      <div style={{ marginBottom: '1.5rem' }}>
        <div style={{
          width: '100%',
          height: '8px',
          backgroundColor: 'var(--bg-tertiary)',
          borderRadius: '4px',
          overflow: 'hidden',
        }}>
          <div style={{
            width: `${((currentQuestionIndex + 1) / questions.length) * 100}%`,
            height: '100%',
            backgroundColor: 'var(--primary-color)',
            transition: 'width 0.3s',
          }} />
        </div>
      </div>

      {/* Question */}
      <div style={{
        background: '#fafbfc',
        border: '1px solid var(--border-color)',
        borderRadius: 'var(--radius-md)',
        padding: '1.5rem',
        marginBottom: '1.5rem',
      }}>
        <div style={{ marginBottom: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            {currentQuestion.section_title || 'Question'}
            {currentQuestion.difficulty && ` • ${currentQuestion.difficulty}`}
          </div>
          {!readOnly && !isCompleted && (
            hint ? (
              <button
                type="button"
                onClick={toggleHint}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  padding: '0.5rem 1rem',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-md)',
                  background: showHints[questionId] ? 'var(--primary-color-light)' : 'transparent',
                  color: showHints[questionId] ? 'var(--primary-color)' : 'var(--text-color)',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                  fontWeight: showHints[questionId] ? '600' : '400',
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10"></circle>
                  <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path>
                  <line x1="12" y1="17" x2="12.01" y2="17"></line>
                </svg>
                {showHints[questionId] ? 'Hide Hint' : 'Show Hint'}
              </button>
            ) : (
              <div style={{
                fontSize: '0.75rem',
                color: 'var(--text-muted)',
                fontStyle: 'italic',
                padding: '0.5rem 1rem'
              }}>
                No hint available
              </div>
            )
          )}
        </div>
        <div style={{ fontSize: '1.125rem', marginBottom: '1.5rem', lineHeight: '1.6' }}>
          <MathText text={currentQuestion.text} />
          {/* Show hint if toggled */}
          {hint && showHints[questionId] && (
            <div style={{
              marginTop: '1rem',
              padding: '1rem',
              background: 'var(--primary-color-light)',
              border: '1px solid var(--primary-color)',
              borderRadius: 'var(--radius-md)',
              borderLeft: '4px solid var(--primary-color)',
            }}>
              <div style={{ 
                fontSize: '0.875rem', 
                fontWeight: '600', 
                color: 'var(--primary-color)',
                marginBottom: '0.5rem'
              }}>
                💡 Hint
              </div>
              <div style={{ fontSize: '0.95rem', lineHeight: '1.6' }}>
                <MathText text={hint} />
              </div>
            </div>
          )}
          {/* Render diagram if present in metadata and not already in question text */}
          {(() => {
            if (!currentQuestion.metadata?.diagram_code) return null
            
            // Normalize the diagram code for comparison (remove whitespace, normalize backslashes)
            const normalizeTikzCode = (code) => {
              if (!code) return ''
              return code
                .replace(/\\\\/g, '\\')  // Normalize double backslashes
                .replace(/\s+/g, ' ')     // Normalize whitespace
                .trim()
            }
            
            const metadataDiagram = normalizeTikzCode(currentQuestion.metadata.diagram_code)
            const questionText = currentQuestion.text || ''
            
            // Check if diagram is already in question text
            // Check for various patterns: "Diagram (LaTeX):", direct tikzpicture, or script tags
            const hasDiagramInText = 
              questionText.includes('Diagram (LaTeX)') ||
              questionText.includes('\\begin{tikzpicture}') ||
              questionText.includes('<script type="text/tikz">') ||
              questionText.includes("Diagram (LaTeX):")
            
            // Also check if the normalized diagram code appears in the question text
            const normalizedQuestionText = normalizeTikzCode(questionText)
            const diagramInText = normalizedQuestionText.includes(metadataDiagram) && metadataDiagram.length > 20
            
            // Only render if diagram is not already in question text
            if (!hasDiagramInText && !diagramInText) {
              return (
                <div style={{ marginTop: '1rem', marginBottom: '1rem' }}>
                  <MathText text={`Diagram (LaTeX): ${currentQuestion.metadata.diagram_code}`} />
                </div>
              )
            }
            return null
          })()}
        </div>

        {/* Rendering Indicator */}
        {isGraphRendering && (
          <div style={{
            padding: '0.75rem 1rem',
            marginBottom: '1rem',
            background: 'var(--primary-color-light)',
            border: '1px solid var(--primary-color)',
            borderRadius: 'var(--radius-md)',
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            fontSize: '0.9rem',
            color: 'var(--text-color)'
          }}>
            <div style={{
              width: '20px',
              height: '20px',
              border: '3px solid var(--primary-color)',
              borderTop: '3px solid transparent',
              borderRadius: '50%',
              animation: 'spin 1s linear infinite'
            }} />
            <span>Rendering diagrams... Please wait before submitting or changing answers.</span>
            <style>{`
              @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
              }
            `}</style>
          </div>
        )}

        {/* Answer Input */}
        {isMCQ ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {options.map((option, idx) => (
              <label
                key={idx}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  padding: '0.75rem',
                  border: `2px solid ${
                    answers[currentQuestion.question_id] === String(idx)
                      ? 'var(--primary-color)'
                      : 'var(--border-color)'
                  }`,
                  borderRadius: 'var(--radius-md)',
                  cursor: readOnly ? 'default' : 'pointer',
                  background: answers[currentQuestion.question_id] === String(idx)
                    ? 'var(--primary-color-light)'
                    : 'transparent',
                }}
              >
                <input
                  type="radio"
                  name={`question-${currentQuestion.question_id}`}
                  value={idx}
                  checked={answers[currentQuestion.question_id] === String(idx)}
                  onChange={(e) => handleAnswerChange(currentQuestion.question_id, e.target.value)}
                  disabled={readOnly || isCompleted || isGraphRendering}
                  style={{ marginRight: '0.75rem' }}
                />
                <span>
                  <MathText text={option} inline />
                </span>
              </label>
            ))}
          </div>
        ) : (
          <div>
            {/* Note for non-MCQ questions */}
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
              📝 Show all of your steps
            </div>
            
            {/* Text Input - Always shown for non-MCQ */}
            <textarea
              value={answerComponents.text}
              onChange={(e) => handleAnswerComponentChange(questionId, 'text', e.target.value)}
              disabled={readOnly || isCompleted || isGraphRendering}
              placeholder={isGraphRendering ? 'Please wait for diagrams to finish rendering...' : 'Type your answer here...'}
              style={{
                width: '100%',
                minHeight: '120px',
                padding: '0.75rem',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-md)',
                fontSize: '1rem',
                fontFamily: 'inherit',
                resize: 'vertical',
                marginBottom: '1rem',
              }}
            />
            
            {/* Toggle Buttons for Graph and Diagram - Only show if needed or already visible */}
            {(needsGraph || needsDiagram || currentCanvasVisibility.showGraph || currentCanvasVisibility.showDiagram) && (
              <div style={{ 
                display: 'flex', 
                gap: '0.75rem', 
                marginBottom: '1rem',
                flexWrap: 'wrap'
              }}>
                {(needsGraph || currentCanvasVisibility.showGraph) && (
                  <button
                    type="button"
                    onClick={() => toggleCanvas('showGraph')}
                    disabled={readOnly || isCompleted || isGraphRendering}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      padding: '0.5rem 1rem',
                      border: `2px solid ${currentCanvasVisibility.showGraph ? 'var(--primary-color)' : 'var(--border-color)'}`,
                      borderRadius: 'var(--radius-md)',
                      background: currentCanvasVisibility.showGraph ? 'var(--primary-color-light)' : 'transparent',
                      cursor: readOnly || isCompleted ? 'default' : 'pointer',
                      fontSize: '0.875rem',
                    }}
                    title={needsGraph ? "This question requires a graph" : "Toggle graph drawing canvas"}
                  >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="22 6 18 6 15 10 12 4 9 10 6 6 2 6"></polyline>
                      <path d="M22 18v-7H2v7"></path>
                      <line x1="12" y1="4" x2="12" y2="18"></line>
                    </svg>
                    {currentCanvasVisibility.showGraph ? 'Hide Graph' : 'Show Graph'}
                    {needsGraph && <span style={{ marginLeft: '0.25rem', fontSize: '0.75rem', color: 'var(--primary-color)', fontWeight: '600' }}>(Required)</span>}
                  </button>
                )}
                
                {(needsDiagram || currentCanvasVisibility.showDiagram) && (
                  <button
                    type="button"
                    onClick={() => toggleCanvas('showDiagram')}
                    disabled={readOnly || isCompleted || isGraphRendering}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      padding: '0.5rem 1rem',
                      border: `2px solid ${currentCanvasVisibility.showDiagram ? 'var(--primary-color)' : 'var(--border-color)'}`,
                      borderRadius: 'var(--radius-md)',
                      background: currentCanvasVisibility.showDiagram ? 'var(--primary-color-light)' : 'transparent',
                      cursor: readOnly || isCompleted ? 'default' : 'pointer',
                      fontSize: '0.875rem',
                    }}
                    title={needsDiagram ? "This question requires a diagram" : "Toggle diagram drawing canvas"}
                  >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                      <line x1="9" y1="9" x2="15" y2="15"></line>
                      <line x1="15" y1="9" x2="9" y2="15"></line>
                    </svg>
                    {currentCanvasVisibility.showDiagram ? 'Hide Diagram' : 'Show Diagram'}
                    {needsDiagram && <span style={{ marginLeft: '0.25rem', fontSize: '0.75rem', color: 'var(--primary-color)', fontWeight: '600' }}>(Required)</span>}
                  </button>
                )}
              </div>
            )}
            
            {/* Graph Canvas - Auto-show if needed, or conditionally shown */}
            {(needsGraph || currentCanvasVisibility.showGraph) && (
              <div style={{ marginBottom: '1rem' }}>
                {needsGraph && (
                  <div style={{ 
                    marginBottom: '0.5rem', 
                    fontSize: '0.875rem', 
                    color: 'var(--primary-color)',
                    fontWeight: '500'
                  }}>
                    ⚠️ This question requires you to draw a graph
                  </div>
                )}
                <div style={{ 
                  marginBottom: '0.5rem', 
                  fontSize: '0.875rem', 
                  color: 'var(--text-muted)',
                  fontStyle: 'italic'
                }}>
                  Draw your graph below:
                </div>
                <GraphDrawingCanvas
                  onDrawingChange={(drawingData) => {
                    try {
                      // Ensure drawingData is properly serialized
                      const drawingJson = typeof drawingData === 'string' 
                        ? drawingData 
                        : JSON.stringify(drawingData)
                      handleAnswerComponentChange(questionId, 'graph', drawingJson)
                    } catch (error) {
                      console.error('Error saving graph drawing:', error)
                      showNotification('Failed to save graph drawing', 'error')
                    }
                  }}
                  readOnly={readOnly || isCompleted || isGraphRendering}
                  initialDrawingData={answerComponents.graph}
                  width={600}
                  height={400}
                />
              </div>
            )}
            
            {/* Diagram Canvas - Auto-show if needed, or conditionally shown */}
            {(needsDiagram || currentCanvasVisibility.showDiagram) && (
              <div style={{ marginBottom: '1rem' }}>
                {needsDiagram && (
                  <div style={{ 
                    marginBottom: '0.5rem', 
                    fontSize: '0.875rem', 
                    color: 'var(--primary-color)',
                    fontWeight: '500'
                  }}>
                    ⚠️ This question requires you to draw a diagram
                  </div>
                )}
                <div style={{ 
                  marginBottom: '0.5rem', 
                  fontSize: '0.875rem', 
                  color: 'var(--text-muted)',
                  fontStyle: 'italic'
                }}>
                  Draw your diagram below:
                </div>
                <DiagramDrawingCanvas
                  onDrawingChange={(drawingData) => {
                    try {
                      // Ensure drawingData is properly serialized
                      const drawingJson = typeof drawingData === 'string' 
                        ? drawingData 
                        : JSON.stringify(drawingData)
                      handleAnswerComponentChange(questionId, 'diagram', drawingJson)
                    } catch (error) {
                      console.error('Error saving diagram drawing:', error)
                      showNotification('Failed to save diagram drawing', 'error')
                    }
                  }}
                  readOnly={readOnly || isCompleted || isGraphRendering}
                  initialDrawingData={answerComponents.diagram}
                  width={600}
                  height={400}
                />
              </div>
            )}
          </div>
        )}

        {/* Show score if completed */}
        {isCompleted && currentQuestion.score !== null && (
          <div style={{
            marginTop: '1rem',
            padding: '0.75rem',
            background: currentQuestion.is_correct ? 'var(--success-color-light)' : 'var(--error-color-light)',
            borderRadius: 'var(--radius-md)',
            color: currentQuestion.is_correct ? 'var(--success-color)' : 'var(--error-color)',
          }}>
            {currentQuestion.is_correct ? '✓ Correct' : '✗ Incorrect'} 
            {currentQuestion.score !== undefined && ` (${currentQuestion.score}/${currentQuestion.max_score} points)`}
          </div>
        )}

        {/* Show correct answer for completed tests when student answer is missing or incorrect */}
        {shouldShowCorrect && (
          <div
            style={{
              marginTop: '0.75rem',
              padding: '0.75rem',
              background: 'var(--bg-secondary)',
              borderRadius: 'var(--radius-md)',
              border: '1px dashed var(--border-color)',
              fontSize: '0.95rem',
              lineHeight: 1.5,
            }}
          >
            {!hasStudentAnswer ? (
              <div style={{ marginBottom: '0.25rem' }}>You did not answer this question.</div>
            ) : (
              <div style={{ marginBottom: '0.25rem' }}>Your answer was incorrect.</div>
            )}
            <div>
              <strong>Correct answer:</strong>{' '}
              {correctLabel ? `${correctLabel}) ` : ''}
              <MathText text={correctText} inline />
            </div>
          </div>
        )}
      </div>

      {/* Navigation */}
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem' }}>
        <button
          onClick={() => setCurrentQuestionIndex(Math.max(0, currentQuestionIndex - 1))}
          disabled={currentQuestionIndex === 0 || isGraphRendering}
          className="btn-secondary"
          title={isGraphRendering ? 'Please wait for diagrams to finish rendering' : ''}
        >
          Previous
        </button>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {questions.map((_, idx) => (
            <button
              key={idx}
              onClick={() => setCurrentQuestionIndex(idx)}
              disabled={isGraphRendering}
              style={{
                width: '32px',
                height: '32px',
                padding: 0,
                borderRadius: '50%',
                border: `2px solid ${
                  answers[questions[idx].question_id]
                    ? 'var(--primary-color)'
                    : 'var(--border-color)'
                }`,
                background: currentQuestionIndex === idx
                  ? 'var(--primary-color)'
                  : answers[questions[idx].question_id]
                  ? 'var(--primary-color-light)'
                  : 'transparent',
                color: currentQuestionIndex === idx ? 'white' : 'inherit',
                cursor: 'pointer',
              }}
              title={isGraphRendering ? 'Please wait for diagrams to finish rendering' : `Question ${idx + 1}`}
            />
          ))}
        </div>
        {currentQuestionIndex < questions.length - 1 ? (
          <button
            onClick={() => setCurrentQuestionIndex(Math.min(questions.length - 1, currentQuestionIndex + 1))}
            disabled={isGraphRendering}
            className="btn-primary"
            title={isGraphRendering ? 'Please wait for diagrams to finish rendering' : ''}
          >
            Next
          </button>
        ) : (
          <button
            onClick={handleSubmit}
            disabled={submitting || readOnly || isCompleted || isGraphRendering}
            className="btn-primary"
            title={isGraphRendering ? 'Please wait for diagrams to finish rendering' : ''}
          >
            {submitting ? 'Submitting...' : isGraphRendering ? 'Rendering diagrams...' : 'Submit Test'}
          </button>
        )}
      </div>

      {/* Results Summary + Download */}
      {isCompleted && test.total_score !== null && (
        <div style={{
          marginTop: '2rem',
          padding: '1.5rem',
          background: 'var(--bg-tertiary)',
          border: '1px solid var(--border-color)',
          borderRadius: 'var(--radius-md)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '1rem',
          flexWrap: 'wrap',
        }}>
          <div style={{ textAlign: 'left' }}>
            <h3 style={{ marginBottom: '0.5rem' }}>Test Results</h3>
            <div style={{ fontSize: '1.3rem', fontWeight: '600', marginBottom: '0.25rem' }}>
              {test.total_score}/{test.max_score} points
            </div>
            <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>
              {test.total_score && test.max_score
                ? `Percentage: ${((test.total_score / test.max_score) * 100).toFixed(1)}%`
                : null}
            </div>
          </div>
          <button
            onClick={handleDownload}
            className="btn-secondary"
            style={{ marginLeft: 'auto' }}
          >
            Download Test (TXT)
          </button>
        </div>
      )}
    </div>
  )
}
