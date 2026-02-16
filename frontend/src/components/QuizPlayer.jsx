import { useState, useEffect } from 'react'
import { tests } from '../services/api'
import { showNotification } from '../utils/notifications'
import LoadingSpinner from './LoadingSpinner'
import MathText from './MathText'
import GraphDrawingCanvas from './GraphDrawingCanvas'
import DiagramDrawingCanvas from './DiagramDrawingCanvas'
import MatchingQuestionWidget from './MatchingQuestionWidget'
import FillInBlankWidget from './FillInBlankWidget'

export default function QuizPlayer({ testId, onComplete, readOnly = false, isAdmin = false, onViewReport }) {
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
  
  // Behavioral tracking state per question
  const [behavioralData, setBehavioralData] = useState({}) // { questionId: { edit_count, hints_accessed, latency_ms, idle_time_ms, confidence_score, question_start_time, last_activity_time } }
  const [confidenceScores, setConfidenceScores] = useState({}) // { questionId: 1-5 }

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

  // Initialize canvas visibility and behavioral tracking when question changes
  // This must be before any early returns to follow React hooks rules
  useEffect(() => {
    if (test && test.questions && test.questions.length > 0) {
      const questions = test.questions || []
      const currentQuestion = questions[currentQuestionIndex]
      if (currentQuestion && currentQuestion.question_id) {
        const questionId = currentQuestion.question_id
        const needsGraph = currentQuestion.metadata?.needs_graph === true
        const needsDiagram = currentQuestion.metadata?.needs_diagram === true
        
        setCanvasVisibility(prev => ({
          ...prev,
          [questionId]: {
            showGraph: needsGraph || (prev[questionId]?.showGraph ?? false),
            showDiagram: needsDiagram || (prev[questionId]?.showDiagram ?? false)
          }
        }))
        
        // Initialize behavioral tracking for this question if not already started
        // Only initialize if test is active and not read-only
        if (!readOnly && started && !behavioralData[questionId]) {
          const now = Date.now()
          setBehavioralData(prev => ({
            ...prev,
            [questionId]: {
              edit_count: 0,
              hints_accessed: 0,
              latency_ms: null, // Will be set when first answer is provided
              idle_time_ms: 0,
              question_start_time: now,
              last_activity_time: now,
              confidence_score: null
            }
          }))
        } else if (!readOnly && started && behavioralData[questionId]) {
          // Update last activity time when switching to this question
          setBehavioralData(prev => ({
            ...prev,
            [questionId]: {
              ...prev[questionId],
              last_activity_time: Date.now()
            }
          }))
        }
      }
    }
  }, [test, currentQuestionIndex, readOnly, started])
  
  // Track idle time (time spent not typing/editing)
  useEffect(() => {
    if (readOnly || !started) return
    
    const questions = test?.questions || []
    const currentQuestion = questions[currentQuestionIndex]
    if (!currentQuestion) return
    
    const questionId = currentQuestion.question_id
    
    let lastCheckTime = Date.now()
    
    const idleCheckInterval = setInterval(() => {
      setBehavioralData(prev => {
        const behavioral = prev[questionId]
        if (!behavioral) return prev
        
        const now = Date.now()
        const lastActivity = behavioral.last_activity_time || behavioral.question_start_time
        const timeSinceLastActivity = now - lastActivity
        
        // Update idle time if user hasn't been active for more than 1 second
        if (timeSinceLastActivity > 1000) {
          const elapsed = now - lastCheckTime
          return {
            ...prev,
            [questionId]: {
              ...behavioral,
              idle_time_ms: (behavioral.idle_time_ms || 0) + elapsed
            }
          }
        }
        return prev
      })
      lastCheckTime = Date.now()
    }, 1000) // Check every second
    
    return () => clearInterval(idleCheckInterval)
  }, [test, currentQuestionIndex, readOnly, started])

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
    const previousAnswer = answers[questionId]
    const isNewAnswer = previousAnswer !== answer
    const newAnswers = { ...answers, [questionId]: answer }
    setAnswers(newAnswers)

    // Update behavioral tracking
    if (!readOnly && started) {
      const now = Date.now()
      const behavioral = behavioralData[questionId] || {}
      const questionStartTime = behavioral.question_start_time || now
      
      // Track edit count (increment if answer changed)
      if (isNewAnswer && previousAnswer !== undefined) {
        setBehavioralData(prev => ({
          ...prev,
          [questionId]: {
            ...(prev[questionId] || {}),
            edit_count: (prev[questionId]?.edit_count || 0) + 1,
            last_activity_time: now
          }
        }))
      }
      
      // Track latency (time from question load to first answer)
      if (previousAnswer === undefined && answer) {
        const latency = now - questionStartTime
        setBehavioralData(prev => ({
          ...prev,
          [questionId]: {
            ...(prev[questionId] || {}),
            latency_ms: latency,
            last_activity_time: now
          }
        }))
      } else {
        // Update last activity time
        setBehavioralData(prev => ({
          ...prev,
          [questionId]: {
            ...(prev[questionId] || {}),
            last_activity_time: now
          }
        }))
      }
    }

    // Auto-save answer with behavioral data
    if (!readOnly && started) {
      try {
        // Ensure answer is a string (required by API)
        const answerString = typeof answer === 'string' ? answer : JSON.stringify(answer)
        
        // Prepare behavioral data for this question
        const behavioral = behavioralData[questionId] || {}
        const confidence = confidenceScores[questionId] || behavioral.confidence_score
        
        const behavioralPayload = {
          latency_ms: behavioral.latency_ms || null,
          idle_time_ms: behavioral.idle_time_ms || 0,
          edit_count: behavioral.edit_count || 0,
          hints_accessed: behavioral.hints_accessed || 0,
          confidence_score: confidence || null
        }
        
        console.log('Saving answer with behavioral data:', {
          questionId,
          answerType: typeof answer,
          answerStringLength: answerString.length,
          behavioralData: behavioralPayload
        })
        
        await tests.answer(testId, questionId, answerString, null, behavioralPayload)
        console.log('Answer saved successfully:', { 
          questionId, 
          answerLength: answerString.length,
          behavioralData: behavioralPayload
        })
      } catch (error) {
        console.error('Failed to save answer:', error)
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

  const questionType = currentQuestion.type || 'short_answer'
  const isMCQ = questionType === 'multiple_choice'
  const isMatching = questionType === 'matching'
  const isFillInBlank = questionType === 'fill_in_the_blank'
  const isProblemSolving = questionType === 'problem_solving'
  const isShortAnswer = questionType === 'short_answer'
  const isConceptual = questionType === 'conceptual_question'
  
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
    const wasHidden = !showHints[questionId]
    setShowHints(prev => ({
      ...prev,
      [questionId]: !prev[questionId]
    }))
    
    // Track hint access (only count when showing hint, not hiding)
    if (wasHidden) {
      setBehavioralData(prev => ({
        ...prev,
        [questionId]: {
          ...(prev[questionId] || {}),
          hints_accessed: (prev[questionId]?.hints_accessed || 0) + 1
        }
      }))
    }
  }
  
  // Update confidence score
  const handleConfidenceChange = (questionId, score) => {
    setConfidenceScores(prev => ({
      ...prev,
      [questionId]: score
    }))
    setBehavioralData(prev => ({
      ...prev,
      [questionId]: {
        ...(prev[questionId] || {}),
        confidence_score: score
      }
    }))
  }

  // Get hint for current question
  // Check multiple possible locations: metadata.hint, metadata.blueprint.hint, or direct hint field
  // Also check if metadata.hint is the fallback message and prefer blueprint.hint if available
  let hint = null
  const fallbackHints = [
    "Review the key concepts related to this question.",
    "Consider each option carefully and identify the key concept being tested.",
    "Think about the key formula or concept needed to solve this problem.",
    "Break down the problem into steps and identify what information you need."
  ]
  
  if (currentQuestion.metadata) {
    // First check metadata.hint directly (stored when question was created)
    const metadataHint = currentQuestion.metadata.hint
    const isFallbackHint = metadataHint && fallbackHints.includes(metadataHint.trim())
    
    // Check metadata.blueprint.hint (blueprint is the full question blueprint)
    let blueprintHint = null
    if (currentQuestion.metadata.blueprint) {
      if (typeof currentQuestion.metadata.blueprint === 'object') {
        // Check blueprint.hint directly - this is where it should be according to the schema
        blueprintHint = currentQuestion.metadata.blueprint.hint
      } else if (typeof currentQuestion.metadata.blueprint === 'string') {
        try {
          const blueprint = JSON.parse(currentQuestion.metadata.blueprint)
          blueprintHint = blueprint.hint
        } catch (e) {
          // Ignore parse errors
        }
      }
    }
    
    // Prefer blueprint hint if metadata hint is a fallback, otherwise use metadata hint
    if (isFallbackHint && blueprintHint && blueprintHint.trim() && !fallbackHints.includes(blueprintHint.trim())) {
      hint = blueprintHint
    } else if (metadataHint && metadataHint.trim()) {
      hint = metadataHint
    } else if (blueprintHint && blueprintHint.trim()) {
      hint = blueprintHint
    }
  }
  
  // Fallback to direct hint field
  if (!hint) {
    hint = currentQuestion.hint
  }
  
  // Debug logging - show full structure to help diagnose hint location
  if (!hint) {
    console.log('No hint found for question - full structure:', {
      questionId,
      hasMetadata: !!currentQuestion.metadata,
      metadataType: typeof currentQuestion.metadata,
      metadataKeys: currentQuestion.metadata ? Object.keys(currentQuestion.metadata) : [],
      metadataHint: currentQuestion.metadata?.hint,
      hasBlueprint: !!currentQuestion.metadata?.blueprint,
      blueprintType: typeof currentQuestion.metadata?.blueprint,
      blueprintKeys: (typeof currentQuestion.metadata?.blueprint === 'object' && currentQuestion.metadata?.blueprint) ? Object.keys(currentQuestion.metadata.blueprint) : [],
      blueprintHint: (typeof currentQuestion.metadata?.blueprint === 'object' && currentQuestion.metadata?.blueprint) ? currentQuestion.metadata.blueprint.hint : undefined,
      directHint: currentQuestion.hint,
      fullMetadata: currentQuestion.metadata ? JSON.stringify(currentQuestion.metadata).substring(0, 1000) : null
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

  // Helper function to render a single question (for reuse in all-questions view)
  const renderQuestion = (question, questionIndex, showAllQuestions = false) => {
    const qId = question.question_id
    const qAnswer = answers[qId]
    const qAnswerComponents = parseAnswer(qAnswer)
    const qHasAnswer = qAnswer !== undefined && qAnswer !== null && qAnswer !== ''
    const qType = question.type || 'short_answer'
    const qIsMCQ = qType === 'multiple_choice'
    const qIsMatching = qType === 'matching'
    const qIsFillInBlank = qType === 'fill_in_the_blank'
    const qIsProblemSolving = qType === 'problem_solving'
    const qIsConceptual = qType === 'conceptual_question'
    const qOptions = question.metadata?.options || []
    
    // Get hint for this question
    let qHint = null
    const fallbackHints = [
      "Review the key concepts related to this question.",
      "Consider each option carefully and identify the key concept being tested.",
      "Think about the key formula or concept needed to solve this problem.",
      "Break down the problem into steps and identify what information you need."
    ]
    
    if (question.metadata) {
      const metadataHint = question.metadata.hint
      const isFallbackHint = metadataHint && fallbackHints.includes(metadataHint.trim())
      
      let blueprintHint = null
      if (question.metadata.blueprint) {
        if (typeof question.metadata.blueprint === 'object') {
          blueprintHint = question.metadata.blueprint.hint
        } else if (typeof question.metadata.blueprint === 'string') {
          try {
            const blueprint = JSON.parse(question.metadata.blueprint)
            blueprintHint = blueprint.hint
          } catch (e) {
            // Ignore parse errors
          }
        }
      }
      
      if (isFallbackHint && blueprintHint && blueprintHint.trim() && !fallbackHints.includes(blueprintHint.trim())) {
        qHint = blueprintHint
      } else if (metadataHint && metadataHint.trim()) {
        qHint = metadataHint
      } else if (blueprintHint && blueprintHint.trim()) {
        qHint = blueprintHint
      }
    }
    
    if (!qHint) {
      qHint = question.hint
    }
    
    // Determine correct answer (MCQ)
    let qCorrectIndex = null
    let qCorrectText = null
    let qCorrectLabel = null
    if (qIsMCQ && question.metadata?.correct_answer) {
      const letter = String(question.metadata.correct_answer).trim().toUpperCase()
      if (['A', 'B', 'C', 'D'].includes(letter)) {
        const idx = letter.charCodeAt(0) - 'A'.charCodeAt(0)
        if (idx >= 0 && idx < qOptions.length) {
          qCorrectIndex = idx
          qCorrectText = qOptions[idx]
          qCorrectLabel = letter
        }
      }
    }
    
    const qShouldShowCorrect =
      isCompleted &&
      qIsMCQ &&
      qCorrectText &&
      (!qHasAnswer || question.is_correct === false)
    
    // Extract expected answer and detailed feedback
    let qExpectedAnswer = null
    if (question.metadata) {
      qExpectedAnswer = question.metadata.expected_answer
      if (!qExpectedAnswer && question.metadata.blueprint) {
        if (typeof question.metadata.blueprint === 'object') {
          qExpectedAnswer = question.metadata.blueprint.expected_answer
        } else if (typeof question.metadata.blueprint === 'string') {
          try {
            const blueprint = JSON.parse(question.metadata.blueprint)
            qExpectedAnswer = blueprint.expected_answer
          } catch (e) {
            // Ignore parse errors
          }
        }
      }
    }
    
    // Normalize expected answer
    let qNormalizedExpectedAnswer = qExpectedAnswer
    if (qExpectedAnswer) {
      if (typeof qNormalizedExpectedAnswer === 'string') {
        if (qNormalizedExpectedAnswer.trim().startsWith('[')) {
          try {
            const parsed = JSON.parse(qNormalizedExpectedAnswer)
            if (Array.isArray(parsed)) {
              qNormalizedExpectedAnswer = parsed
            }
          } catch (e) {
            const pythonListMatch = qNormalizedExpectedAnswer.match(/^\[(['"])(.*?)\1\]$/)
            if (pythonListMatch) {
              qNormalizedExpectedAnswer = pythonListMatch[2]
            } else {
              const bracketMatch = qNormalizedExpectedAnswer.match(/^\[(.*)\]$/)
              if (bracketMatch) {
                let content = bracketMatch[1].trim()
                if ((content.startsWith("'") && content.endsWith("'")) || 
                    (content.startsWith('"') && content.endsWith('"'))) {
                  content = content.slice(1, -1)
                }
                content = content.replace(/\\'/g, "'").replace(/\\"/g, '"')
                qNormalizedExpectedAnswer = content
              }
            }
          }
        }
      }
      
      if (Array.isArray(qNormalizedExpectedAnswer)) {
        qNormalizedExpectedAnswer = qNormalizedExpectedAnswer.length === 1 
          ? qNormalizedExpectedAnswer[0] 
          : qNormalizedExpectedAnswer.join(' ')
      }
      
      if (typeof qNormalizedExpectedAnswer !== 'string') {
        qNormalizedExpectedAnswer = String(qNormalizedExpectedAnswer)
      }
      
      while (qNormalizedExpectedAnswer.includes('\\\\')) {
        qNormalizedExpectedAnswer = qNormalizedExpectedAnswer.replace(/\\\\/g, '\\')
      }
    }
    
    const qDetailedFeedback = question.detailed_feedback
    const qIsIncorrect = question.is_correct === false
    // Check if answer is partially correct (has score but less than max)
    const qIsPartiallyCorrect = question.score != null && question.max_score != null && 
                                 question.score < question.max_score && question.score > 0
    // Show feedback for incorrect (score = 0 or is_correct = false) or partially correct answers
    const qShouldShowFeedback = qDetailedFeedback && (qIsIncorrect || qIsPartiallyCorrect || 
                                 (question.score != null && question.score === 0))
    
    // Format detailed feedback - handle JSON objects/strings
    let qFormattedFeedback = qDetailedFeedback
    if (qDetailedFeedback && typeof qDetailedFeedback === 'string') {
      try {
        // Try to parse as JSON
        const parsed = JSON.parse(qDetailedFeedback)
        if (typeof parsed === 'object' && parsed !== null) {
          // Format the JSON object into readable text
          const parts = []
          if (parsed.process_evaluation) {
            parts.push(parsed.process_evaluation)
          }
          if (parsed.semantic_equivalence) {
            parts.push(parsed.semantic_equivalence)
          }
          if (parsed.multi_part_answer_analysis) {
            if (typeof parsed.multi_part_answer_analysis === 'object') {
              const analysisParts = []
              if (parsed.multi_part_answer_analysis.units) {
                analysisParts.push(parsed.multi_part_answer_analysis.units)
              }
              // Add any other analysis fields
              Object.keys(parsed.multi_part_answer_analysis).forEach(key => {
                if (key !== 'units' && parsed.multi_part_answer_analysis[key]) {
                  analysisParts.push(parsed.multi_part_answer_analysis[key])
                }
              })
              if (analysisParts.length > 0) {
                parts.push(analysisParts.join(' '))
              }
            } else {
              parts.push(parsed.multi_part_answer_analysis)
            }
          }
          // If we couldn't format it nicely, use the original JSON string
          qFormattedFeedback = parts.length > 0 ? parts.join('\n\n') : qDetailedFeedback
        }
      } catch (e) {
        // Not JSON, use as-is
        qFormattedFeedback = qDetailedFeedback
      }
    } else if (qDetailedFeedback && typeof qDetailedFeedback === 'object') {
      // Already an object, format it
      const parts = []
      if (qDetailedFeedback.process_evaluation) {
        parts.push(qDetailedFeedback.process_evaluation)
      }
      if (qDetailedFeedback.semantic_equivalence) {
        parts.push(qDetailedFeedback.semantic_equivalence)
      }
      if (qDetailedFeedback.multi_part_answer_analysis) {
        if (typeof qDetailedFeedback.multi_part_answer_analysis === 'object') {
          const analysisParts = []
          if (qDetailedFeedback.multi_part_answer_analysis.units) {
            analysisParts.push(qDetailedFeedback.multi_part_answer_analysis.units)
          }
          // Add any other analysis fields
          Object.keys(qDetailedFeedback.multi_part_answer_analysis).forEach(key => {
            if (key !== 'units' && qDetailedFeedback.multi_part_answer_analysis[key]) {
              analysisParts.push(qDetailedFeedback.multi_part_answer_analysis[key])
            }
          })
          if (analysisParts.length > 0) {
            parts.push(analysisParts.join(' '))
          }
        } else {
          parts.push(qDetailedFeedback.multi_part_answer_analysis)
        }
      }
      qFormattedFeedback = parts.length > 0 ? parts.join('\n\n') : JSON.stringify(qDetailedFeedback, null, 2)
    }
    
    // Debug logging for detailed feedback
    if (isCompleted && !qIsMCQ) {
      console.log('Question feedback debug:', {
        questionId: question.question_id,
        hasDetailedFeedback: !!qDetailedFeedback,
        detailedFeedback: qDetailedFeedback,
        isIncorrect: qIsIncorrect,
        isPartiallyCorrect: qIsPartiallyCorrect,
        score: question.score,
        maxScore: question.max_score,
        shouldShowFeedback: qShouldShowFeedback,
        isCorrect: question.is_correct
      })
    }
    
    // Extract solution steps
    let qSolutionSteps = null
    if (question.metadata) {
      qSolutionSteps = question.metadata.solution_steps
      if (!qSolutionSteps && question.metadata.blueprint) {
        if (typeof question.metadata.blueprint === 'object') {
          qSolutionSteps = question.metadata.blueprint.solution_steps
        } else if (typeof question.metadata.blueprint === 'string') {
          try {
            const blueprint = JSON.parse(question.metadata.blueprint)
            qSolutionSteps = blueprint.solution_steps
          } catch (e) {
            // Ignore parse errors
          }
        }
      }
    }
    
    return (
      <div key={qId} style={{
        background: '#fafbfc',
        border: '1px solid var(--border-color)',
        borderRadius: 'var(--radius-md)',
        padding: '1.5rem',
        marginBottom: showAllQuestions ? '2rem' : '1.5rem',
      }}>
        <div style={{ marginBottom: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            Question {questionIndex + 1} {question.section_title ? `• ${question.section_title}` : ''}
            {question.difficulty && ` • ${question.difficulty}`}
          </div>
        </div>
        
        <div style={{ fontSize: '1.125rem', marginBottom: '1.5rem', lineHeight: '1.6' }}>
          <MathText text={question.text} />
          {question.metadata?.diagram_code && (() => {
            const normalizeTikzCode = (code) => {
              if (!code) return ''
              return code.replace(/\\\\/g, '\\').replace(/\s+/g, ' ').trim()
            }
            const metadataDiagram = normalizeTikzCode(question.metadata.diagram_code)
            const questionText = question.text || ''
            const hasDiagramInText = 
              questionText.includes('Diagram (LaTeX)') ||
              questionText.includes('\\begin{tikzpicture}') ||
              questionText.includes('<script type="text/tikz">') ||
              questionText.includes("Diagram (LaTeX):")
            const normalizedQuestionText = normalizeTikzCode(questionText)
            const diagramInText = normalizedQuestionText.includes(metadataDiagram) && metadataDiagram.length > 20
            
            if (!hasDiagramInText && !diagramInText) {
              return (
                <div style={{ marginTop: '1rem', marginBottom: '1rem' }}>
                  <MathText text={`Diagram (LaTeX): ${question.metadata.diagram_code}`} />
                </div>
              )
            }
            return null
          })()}
        </div>
        
        {/* Answer Display (read-only for completed tests) */}
        {isCompleted && (
          <div style={{
            marginBottom: '1rem',
            padding: '1rem',
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-md)',
          }}>
            <div style={{ fontSize: '0.875rem', fontWeight: '600', marginBottom: '0.5rem', color: 'var(--text-muted)' }}>
              Your Answer:
            </div>
            {qHasAnswer ? (
              qIsMCQ ? (
                <div>
                  {qOptions.map((opt, idx) => (
                    <div key={idx} style={{
                      padding: '0.5rem',
                      background: qAnswer === String(idx) ? 'var(--primary-color-light)' : 'transparent',
                      borderRadius: 'var(--radius-sm)',
                      marginBottom: '0.25rem',
                    }}>
                      {String.fromCharCode('A'.charCodeAt(0) + idx)}) <MathText text={opt} inline />
                      {qAnswer === String(idx) && <span style={{ marginLeft: '0.5rem', color: 'var(--primary-color)' }}>✓ Selected</span>}
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                  {qAnswerComponents.text || '(No text answer)'}
                  {qAnswerComponents.graph && <div style={{ marginTop: '0.5rem', fontSize: '0.875rem', color: 'var(--text-muted)' }}>[Graph drawing included]</div>}
                  {qAnswerComponents.diagram && <div style={{ marginTop: '0.5rem', fontSize: '0.875rem', color: 'var(--text-muted)' }}>[Diagram drawing included]</div>}
                </div>
              )
            ) : (
              <div style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>No answer provided</div>
            )}
          </div>
        )}
        
        {/* Show score if completed */}
        {isCompleted && question.score !== null && (
          <div style={{
            marginTop: '1rem',
            padding: '0.75rem',
            background: question.is_correct ? 'var(--success-color-light)' : 'var(--error-color-light)',
            borderRadius: 'var(--radius-md)',
            color: question.is_correct ? 'var(--success-color)' : 'var(--error-color)',
          }}>
            {question.is_correct ? '✓ Correct' : '✗ Incorrect'} 
            {question.score !== undefined && ` (${question.score}/${question.max_score} points)`}
          </div>
        )}
        
        {/* Show correct answer for MCQ */}
        {qShouldShowCorrect && (
          <div style={{
            marginTop: '0.75rem',
            padding: '0.75rem',
            background: 'var(--bg-secondary)',
            borderRadius: 'var(--radius-md)',
            border: '1px dashed var(--border-color)',
            fontSize: '0.95rem',
            lineHeight: 1.5,
          }}>
            {!qHasAnswer ? (
              <div style={{ marginBottom: '0.25rem' }}>You did not answer this question.</div>
            ) : (
              <div style={{ marginBottom: '0.25rem' }}>Your answer was incorrect.</div>
            )}
            <div style={{ marginBottom: '0.5rem' }}>
              <strong>Correct answer:</strong>{' '}
              {qCorrectLabel ? `${qCorrectLabel}) ` : ''}
              <MathText text={qCorrectText} inline />
            </div>
          </div>
        )}
        
        {/* Show expected answer and detailed feedback for non-MCQ */}
        {isCompleted && !qIsMCQ && (qNormalizedExpectedAnswer || qShouldShowFeedback) && (
          <div>
            {qNormalizedExpectedAnswer && (
              <div style={{
                marginTop: '0.75rem',
                padding: '0.75rem',
                background: 'var(--bg-secondary)',
                borderRadius: 'var(--radius-md)',
                border: '1px dashed var(--border-color)',
                fontSize: '0.95rem',
                lineHeight: 1.5,
              }}>
                <div>
                  <strong>Expected answer:</strong>{' '}
                  <MathText text={qNormalizedExpectedAnswer} inline />
                </div>
              </div>
            )}
            
            {qShouldShowFeedback && (
              <div style={{
                marginTop: '0.75rem',
                padding: '1rem',
                background: 'var(--error-color-light)',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--error-color)',
                borderLeft: '4px solid var(--error-color)',
                fontSize: '0.95rem',
                lineHeight: 1.6,
              }}>
                <div style={{
                  fontSize: '0.875rem',
                  fontWeight: '600',
                  color: 'var(--error-color)',
                  marginBottom: '0.75rem'
                }}>
                  Detailed Explanation
                </div>
                <div style={{ color: 'var(--text-color)', whiteSpace: 'pre-wrap' }}>
                  <MathText text={qFormattedFeedback} />
                </div>
              </div>
            )}
          </div>
        )}
        
        {/* Show solution steps */}
        {isCompleted && qSolutionSteps && Array.isArray(qSolutionSteps) && qSolutionSteps.length > 0 && (
          <div style={{
            marginTop: '1rem',
            padding: '1rem',
            background: 'var(--primary-color-light)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--primary-color)',
            borderLeft: '4px solid var(--primary-color)',
          }}>
            <div style={{
              fontSize: '0.875rem',
              fontWeight: '600',
              color: 'var(--primary-color)',
              marginBottom: '0.75rem'
            }}>
              Solution Steps
            </div>
            <ol style={{
              margin: 0,
              paddingLeft: '1.5rem',
              listStyleType: 'decimal',
            }}>
              {qSolutionSteps.map((step, idx) => {
                const normalizedStep = typeof step === 'string' 
                  ? step.replace(/\\\\/g, '\\') 
                  : step
                return (
                  <li key={idx} style={{
                    marginBottom: '0.75rem',
                    fontSize: '0.95rem',
                    lineHeight: 1.6,
                  }}>
                    <MathText text={normalizedStep} />
                  </li>
                )
              })}
            </ol>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="quiz-player" style={{ padding: '1.5rem', position: 'relative' }}>
      {/* Evaluation Overlay - Show when submitting/evaluating */}
      {submitting && (
        <div style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(255, 255, 255, 0.95)',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 1000,
          borderRadius: 'var(--radius-md)',
        }}>
          <LoadingSpinner size="large" text="Evaluating..." />
        </div>
      )}

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
        {!isCompleted && (
          <div style={{ textAlign: 'right' }}>
            <div>Question {currentQuestionIndex + 1} of {questions.length}</div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
              {answeredCount} answered
            </div>
          </div>
        )}
      </div>

      {/* Progress Bar - Only show for active tests */}
      {!isCompleted && (
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
      )}

      {/* Show all questions if completed, otherwise show single question */}
      {isCompleted ? (
        <div>
          {questions.map((q, idx) => renderQuestion(q, idx, true))}
        </div>
      ) : (
        /* Single Question View */
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
          {!readOnly && !isCompleted && hint && (
            <button
              type="button"
              onClick={toggleHint}
              disabled={submitting || isGraphRendering}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.5rem 1rem',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-md)',
                background: showHints[questionId] ? 'var(--primary-color-light)' : 'transparent',
                color: showHints[questionId] ? 'var(--primary-color)' : 'var(--text-color)',
                cursor: submitting || isGraphRendering ? 'not-allowed' : 'pointer',
                fontSize: '0.875rem',
                fontWeight: showHints[questionId] ? '600' : '400',
                opacity: submitting || isGraphRendering ? 0.6 : 1,
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"></circle>
                <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path>
                <line x1="12" y1="17" x2="12.01" y2="17"></line>
              </svg>
              {showHints[questionId] ? 'Hide Hint' : 'Show Hint'}
            </button>
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
                Hint
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
                  disabled={submitting || readOnly || isCompleted || isGraphRendering}
                  style={{ marginRight: '0.75rem' }}
                />
                <span>
                  <MathText text={option} inline />
                </span>
              </label>
            ))}
          </div>
        ) : isMatching ? (
          <MatchingQuestionWidget
            question={currentQuestion}
            answer={answerComponents.text}
            onChange={(value) => handleAnswerComponentChange(questionId, 'text', value)}
            disabled={submitting || readOnly || isCompleted || isGraphRendering}
          />
        ) : isFillInBlank ? (
          <FillInBlankWidget
            question={currentQuestion}
            answer={answerComponents.text}
            onChange={(value) => handleAnswerComponentChange(questionId, 'text', value)}
            disabled={submitting || readOnly || isCompleted || isGraphRendering}
          />
        ) : (
          <div>
            {/* Note for text-based questions - customize by type */}
            {!isGraphRendering && (
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
                {isProblemSolving ? 'Show all of your steps' : 
                 isConceptual ? 'Explain your reasoning' :
                 'Type your answer'}
              </div>
            )}
            
            {/* Text Input - For short_answer, problem_solving, conceptual_question */}
            <textarea
              value={answerComponents.text}
              onChange={(e) => handleAnswerComponentChange(questionId, 'text', e.target.value)}
              disabled={submitting || readOnly || isCompleted || isGraphRendering}
              placeholder={
                isGraphRendering 
                  ? 'Please wait for diagrams to finish rendering...' 
                  : isProblemSolving 
                    ? 'Show your work and calculations...'
                    : isConceptual
                      ? 'Explain your reasoning...'
                      : 'Type your answer here...'
              }
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
                    disabled={submitting || readOnly || isCompleted || isGraphRendering}
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
                    disabled={submitting || readOnly || isCompleted || isGraphRendering}
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
                    This question requires you to draw a graph
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
                    This question requires you to draw a diagram
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

        {/* Confidence Score Input (for active tests only) */}
        {!readOnly && !isCompleted && started && (
          <div style={{
            marginTop: '1.5rem',
            padding: '1rem',
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-md)',
          }}>
            <div style={{
              fontSize: '0.875rem',
              fontWeight: '600',
              marginBottom: '0.75rem',
              color: 'var(--text-color)'
            }}>
              How confident are you in your answer?
            </div>
            <div style={{
              display: 'flex',
              gap: '0.5rem',
              alignItems: 'center',
              flexWrap: 'wrap'
            }}>
              {[1, 2, 3, 4, 5].map(score => {
                const isSelected = (confidenceScores[questionId] || behavioralData[questionId]?.confidence_score) === score
                return (
                  <button
                    key={score}
                    type="button"
                    onClick={() => handleConfidenceChange(questionId, score)}
                    style={{
                      padding: '0.5rem 1rem',
                      border: `2px solid ${isSelected ? 'var(--primary-color)' : 'var(--border-color)'}`,
                      borderRadius: 'var(--radius-md)',
                      background: isSelected ? 'var(--primary-color-light)' : 'transparent',
                      color: isSelected ? 'var(--primary-color)' : 'var(--text-color)',
                      cursor: 'pointer',
                      fontSize: '0.875rem',
                      fontWeight: isSelected ? '600' : '400',
                      transition: 'all 0.2s',
                      minWidth: '60px'
                    }}
                    onMouseEnter={(e) => {
                      if (!isSelected) {
                        e.target.style.borderColor = 'var(--primary-color)'
                        e.target.style.background = 'var(--primary-color-light)'
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!isSelected) {
                        e.target.style.borderColor = 'var(--border-color)'
                        e.target.style.background = 'transparent'
                      }
                    }}
                  >
                    {score === 1 && 'Not at all'}
                    {score === 2 && 'Slightly'}
                    {score === 3 && 'Somewhat'}
                    {score === 4 && 'Very'}
                    {score === 5 && 'Extremely'}
                  </button>
                )
              })}
            </div>
            <div style={{
              fontSize: '0.75rem',
              color: 'var(--text-muted)',
              marginTop: '0.5rem',
              fontStyle: 'italic'
            }}>
              Select your confidence level (1 = not confident, 5 = very confident)
            </div>
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
            <div style={{ marginBottom: '0.5rem' }}>
              <strong>Correct answer:</strong>{' '}
              {correctLabel ? `${correctLabel}) ` : ''}
              <MathText text={correctText} inline />
            </div>
          </div>
        )}

        {/* Show expected answer and detailed feedback for non-MCQ completed tests */}
        {isCompleted && !isMCQ && (() => {
          // Extract expected_answer from metadata or blueprint
          let expectedAnswer = null
          if (currentQuestion.metadata) {
            expectedAnswer = currentQuestion.metadata.expected_answer
            if (!expectedAnswer && currentQuestion.metadata.blueprint) {
              if (typeof currentQuestion.metadata.blueprint === 'object') {
                expectedAnswer = currentQuestion.metadata.blueprint.expected_answer
              } else if (typeof currentQuestion.metadata.blueprint === 'string') {
                try {
                  const blueprint = JSON.parse(currentQuestion.metadata.blueprint)
                  expectedAnswer = blueprint.expected_answer
                } catch (e) {
                  // Ignore parse errors
                }
              }
            }
          }
          
          // Extract detailed_feedback from response metadata
          const detailedFeedback = currentQuestion.detailed_feedback
          const isIncorrect = currentQuestion.is_correct === false
          // Check if answer is partially correct (has score but less than max)
          const isPartiallyCorrect = currentQuestion.score != null && currentQuestion.max_score != null && 
                                     currentQuestion.score < currentQuestion.max_score && currentQuestion.score > 0
          // Show feedback for incorrect or partially correct answers
          const shouldShowFeedback = detailedFeedback && (isIncorrect || isPartiallyCorrect)
          
          if (expectedAnswer || shouldShowFeedback) {
            // Handle array format (convert to string) and normalize backslashes
            let normalizedExpectedAnswer = expectedAnswer
            
            // Debug: log the raw value
            console.log('Expected answer raw:', expectedAnswer, 'Type:', typeof expectedAnswer, 'IsArray:', Array.isArray(expectedAnswer))
            
            // If it's a string that looks like a Python list (e.g., "['value']" or '["value"]'), extract the content
            if (typeof normalizedExpectedAnswer === 'string') {
              // Try to parse as JSON array first
              if (normalizedExpectedAnswer.trim().startsWith('[')) {
                try {
                  const parsed = JSON.parse(normalizedExpectedAnswer)
                  if (Array.isArray(parsed)) {
                    normalizedExpectedAnswer = parsed
                    console.log('Parsed as JSON array:', parsed)
                  }
                } catch (e) {
                  // If JSON parsing fails, try to extract from Python-style string representation
                  // Match patterns like: ['value'] or ["value"] or ['value1', 'value2']
                  const pythonListMatch = normalizedExpectedAnswer.match(/^\[(['"])(.*?)\1\]$/)
                  if (pythonListMatch) {
                    // Single item in quotes - extract the content
                    normalizedExpectedAnswer = pythonListMatch[2]
                    console.log('Extracted from Python-style list:', normalizedExpectedAnswer)
                  } else {
                    // Try to extract content between brackets more flexibly
                    // Handle cases like: ['value'] or ["value"] with escaped quotes
                    const bracketMatch = normalizedExpectedAnswer.match(/^\[(.*)\]$/)
                    if (bracketMatch) {
                      let content = bracketMatch[1].trim()
                      // Remove surrounding quotes if present (handle both ' and ")
                      if ((content.startsWith("'") && content.endsWith("'")) || 
                          (content.startsWith('"') && content.endsWith('"'))) {
                        content = content.slice(1, -1)
                      }
                      // Unescape any escaped quotes
                      content = content.replace(/\\'/g, "'").replace(/\\"/g, '"')
                      normalizedExpectedAnswer = content
                      console.log('Extracted from brackets:', normalizedExpectedAnswer)
                    }
                  }
                }
              }
            }
            
            if (Array.isArray(normalizedExpectedAnswer)) {
              // If it's an array, join elements with space, or take first element if single item
              normalizedExpectedAnswer = normalizedExpectedAnswer.length === 1 
                ? normalizedExpectedAnswer[0] 
                : normalizedExpectedAnswer.join(' ')
              console.log('Extracted from array:', normalizedExpectedAnswer)
            }
            
            // Convert to string if not already
            if (typeof normalizedExpectedAnswer !== 'string') {
              normalizedExpectedAnswer = String(normalizedExpectedAnswer)
            }
            
            // Normalize double backslashes to single backslashes for LaTeX rendering
            // This handles JSON-escaped backslashes
            // Replace \\ (two backslashes) with \ (one backslash) for LaTeX
            // Do this multiple times to handle cases like \\\\ (four backslashes) -> \\ (two) -> \ (one)
            let beforeNormalize = normalizedExpectedAnswer
            while (normalizedExpectedAnswer.includes('\\\\')) {
              normalizedExpectedAnswer = normalizedExpectedAnswer.replace(/\\\\/g, '\\')
            }
            console.log('Expected answer - Before normalize:', beforeNormalize, 'After normalize:', normalizedExpectedAnswer)
            
            // Extract detailed_feedback from response metadata
            const detailedFeedback = currentQuestion.detailed_feedback
            const isIncorrect = currentQuestion.is_correct === false
            // Check if answer is partially correct (has score but less than max)
            const isPartiallyCorrect = currentQuestion.score != null && currentQuestion.max_score != null && 
                                       currentQuestion.score < currentQuestion.max_score && currentQuestion.score > 0
            // Show feedback for incorrect (score = 0 or is_correct = false) or partially correct answers
            const shouldShowFeedback = detailedFeedback && (isIncorrect || isPartiallyCorrect || 
                                       (currentQuestion.score != null && currentQuestion.score === 0))
            
            // Format detailed feedback - handle JSON objects/strings
            let formattedFeedback = detailedFeedback
            if (detailedFeedback && typeof detailedFeedback === 'string') {
              try {
                // Try to parse as JSON
                const parsed = JSON.parse(detailedFeedback)
                if (typeof parsed === 'object' && parsed !== null) {
                  // Format the JSON object into readable text
                  const parts = []
                  if (parsed.process_evaluation) {
                    parts.push(parsed.process_evaluation)
                  }
                  if (parsed.semantic_equivalence) {
                    parts.push(parsed.semantic_equivalence)
                  }
                  if (parsed.multi_part_answer_analysis) {
                    if (typeof parsed.multi_part_answer_analysis === 'object') {
                      const analysisParts = []
                      if (parsed.multi_part_answer_analysis.units) {
                        analysisParts.push(parsed.multi_part_answer_analysis.units)
                      }
                      // Add any other analysis fields
                      Object.keys(parsed.multi_part_answer_analysis).forEach(key => {
                        if (key !== 'units' && parsed.multi_part_answer_analysis[key]) {
                          analysisParts.push(parsed.multi_part_answer_analysis[key])
                        }
                      })
                      if (analysisParts.length > 0) {
                        parts.push(analysisParts.join(' '))
                      }
                    } else {
                      parts.push(parsed.multi_part_answer_analysis)
                    }
                  }
                  // If we couldn't format it nicely, use the original JSON string
                  formattedFeedback = parts.length > 0 ? parts.join('\n\n') : detailedFeedback
                }
              } catch (e) {
                // Not JSON, use as-is
                formattedFeedback = detailedFeedback
              }
            } else if (detailedFeedback && typeof detailedFeedback === 'object') {
              // Already an object, format it
              const parts = []
              if (detailedFeedback.process_evaluation) {
                parts.push(detailedFeedback.process_evaluation)
              }
              if (detailedFeedback.semantic_equivalence) {
                parts.push(detailedFeedback.semantic_equivalence)
              }
              if (detailedFeedback.multi_part_answer_analysis) {
                if (typeof detailedFeedback.multi_part_answer_analysis === 'object') {
                  const analysisParts = []
                  if (detailedFeedback.multi_part_answer_analysis.units) {
                    analysisParts.push(detailedFeedback.multi_part_answer_analysis.units)
                  }
                  // Add any other analysis fields
                  Object.keys(detailedFeedback.multi_part_answer_analysis).forEach(key => {
                    if (key !== 'units' && detailedFeedback.multi_part_answer_analysis[key]) {
                      analysisParts.push(detailedFeedback.multi_part_answer_analysis[key])
                    }
                  })
                  if (analysisParts.length > 0) {
                    parts.push(analysisParts.join(' '))
                  }
                } else {
                  parts.push(detailedFeedback.multi_part_answer_analysis)
                }
              }
              formattedFeedback = parts.length > 0 ? parts.join('\n\n') : JSON.stringify(detailedFeedback, null, 2)
            }
            
            // Debug logging for detailed feedback
            console.log('Single question view feedback debug:', {
              questionId: currentQuestion.question_id,
              hasDetailedFeedback: !!detailedFeedback,
              detailedFeedback: detailedFeedback,
              isIncorrect: isIncorrect,
              isPartiallyCorrect: isPartiallyCorrect,
              score: currentQuestion.score,
              maxScore: currentQuestion.max_score,
              shouldShowFeedback: shouldShowFeedback,
              isCorrect: currentQuestion.is_correct
            })
            
            return (
              <div>
                {expectedAnswer && (
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
                    <div>
                      <strong>Expected answer:</strong>{' '}
                      <MathText text={normalizedExpectedAnswer} inline />
                    </div>
                  </div>
                )}
                
                {/* Show detailed feedback for incorrect or partially correct answers */}
                {shouldShowFeedback && (
                  <div
                    style={{
                      marginTop: '0.75rem',
                      padding: '1rem',
                      background: 'var(--error-color-light)',
                      borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--error-color)',
                      borderLeft: '4px solid var(--error-color)',
                      fontSize: '0.95rem',
                      lineHeight: 1.6,
                    }}
                  >
                    <div style={{
                      fontSize: '0.875rem',
                      fontWeight: '600',
                      color: 'var(--error-color)',
                      marginBottom: '0.75rem'
                    }}>
                      Detailed Explanation
                    </div>
                    <div style={{ color: 'var(--text-color)', whiteSpace: 'pre-wrap' }}>
                      <MathText text={formattedFeedback} />
                    </div>
                  </div>
                )}
              </div>
            )
          }
          return null
        })()}

        {/* Show solution steps for completed tests */}
        {isCompleted && (() => {
          // Extract solution_steps from metadata or blueprint
          let solutionSteps = null
          if (currentQuestion.metadata) {
            // Check metadata.solution_steps first
            solutionSteps = currentQuestion.metadata.solution_steps
            
            // If not found, check metadata.blueprint.solution_steps
            if (!solutionSteps && currentQuestion.metadata.blueprint) {
              if (typeof currentQuestion.metadata.blueprint === 'object') {
                solutionSteps = currentQuestion.metadata.blueprint.solution_steps
              } else if (typeof currentQuestion.metadata.blueprint === 'string') {
                try {
                  const blueprint = JSON.parse(currentQuestion.metadata.blueprint)
                  solutionSteps = blueprint.solution_steps
                } catch (e) {
                  // Ignore parse errors
                }
              }
            }
          }
          
          // Only show if we have solution steps
          if (solutionSteps && Array.isArray(solutionSteps) && solutionSteps.length > 0) {
            return (
              <div
                style={{
                  marginTop: '1rem',
                  padding: '1rem',
                  background: 'var(--primary-color-light)',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--primary-color)',
                  borderLeft: '4px solid var(--primary-color)',
                }}
              >
                <div style={{
                  fontSize: '0.875rem',
                  fontWeight: '600',
                  color: 'var(--primary-color)',
                  marginBottom: '0.75rem'
                }}>
                  Solution Steps
                </div>
                <ol style={{
                  margin: 0,
                  paddingLeft: '1.5rem',
                  listStyleType: 'decimal',
                }}>
                  {solutionSteps.map((step, idx) => {
                    // Normalize double backslashes to single backslashes for LaTeX rendering
                    // JSON stores \\ (2 backslashes) which represents \ (1 backslash) in the parsed string
                    // But LaTeX needs single backslashes, so we convert \\ to \
                    const normalizedStep = typeof step === 'string' 
                      ? step.replace(/\\\\/g, '\\') 
                      : step
                    
                    return (
                      <li key={idx} style={{
                        marginBottom: '0.75rem',
                        fontSize: '0.95rem',
                        lineHeight: 1.6,
                      }}>
                        <MathText text={normalizedStep} />
                      </li>
                    )
                  })}
                </ol>
              </div>
            )
          }
          return null
        })()}
      </div>
      )}

      {/* Navigation - Only show for active tests */}
      {!isCompleted && (
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem' }}>
        <button
          onClick={() => setCurrentQuestionIndex(Math.max(0, currentQuestionIndex - 1))}
          disabled={submitting || currentQuestionIndex === 0 || isGraphRendering}
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
              disabled={submitting || isGraphRendering}
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
            disabled={submitting || isGraphRendering}
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
      )}

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
              {test.total_score != null && test.max_score != null && test.max_score > 0
                ? `Percentage: ${((test.total_score / test.max_score) * 100).toFixed(1)}%`
                : null}
            </div>
            {test.updated_at && (
              <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
                Last evaluated: {(() => {
                  // Ensure UTC timestamps are properly parsed
                  let dateStr = test.updated_at
                  if (!dateStr.includes('Z') && !dateStr.match(/[+-]\d{2}:\d{2}$/)) {
                    // Add 'Z' to indicate UTC if not present
                    dateStr = dateStr.endsWith('Z') ? dateStr : dateStr + 'Z'
                  }
                  const date = new Date(dateStr)
                  return date.toLocaleString(undefined, {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                    timeZoneName: 'short'
                  })
                })()}
              </div>
            )}
          </div>
          <div style={{ display: 'flex', gap: '0.75rem', marginLeft: 'auto' }}>
            {test.child_id && onViewReport && (
              <button
                onClick={() => onViewReport(test.child_id)}
                className="btn-primary"
                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                  <polyline points="14 2 14 8 20 8"></polyline>
                  <line x1="16" y1="13" x2="8" y2="13"></line>
                  <line x1="16" y1="17" x2="8" y2="17"></line>
                  <polyline points="10 9 9 9 8 9"></polyline>
                </svg>
                View Evaluation Report
              </button>
            )}
            {isAdmin && (
              <button
                onClick={handleDownload}
                className="btn-secondary"
              >
                Download Test (TXT)
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
