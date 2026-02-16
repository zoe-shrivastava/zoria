import { useState, useEffect, useRef } from 'react'
import { tests } from '../services/api'
import LoadingSpinner from './LoadingSpinner'
import StudyGuide from './StudyGuide'
import LearningDrawer from './LearningDrawer'
import AICoach from './AICoach'
import { showNotification } from '../utils/notifications'
import { useLearningContext } from './LearningWorkspace'

export default function EvaluationReport({ childId, daysBack = 30, showAllGuides = false, user = null, isWorkspaceMode = false, preferredLanguage = null }) {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedGuideId, setSelectedGuideId] = useState(null)
  const [allGuides, setAllGuides] = useState(null)
  const [loadingGuides, setLoadingGuides] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerContext, setDrawerContext] = useState(null)
  const [coachOpen, setCoachOpen] = useState(false)
  const [coachGuideId, setCoachGuideId] = useState(null)
  const [coachContext, setCoachContext] = useState(null)
  const reportContainerRef = useRef(null)
  const [containerHeight, setContainerHeight] = useState(null)
  const [expandedSubjects, setExpandedSubjects] = useState({}) // Track which subjects are expanded
  const [showMetadata, setShowMetadata] = useState(false) // Toggle for metadata info
  const recommendationsCarouselRef = useRef(null)
  
  // Use workspace context - always call hook, but handle gracefully if not in workspace
  let workspaceContext = null
  if (isWorkspaceMode) {
    try {
      workspaceContext = useLearningContext()
    } catch (e) {
      console.warn('Not in workspace mode or context not available:', e)
      workspaceContext = null
    }
  }

  // Helper to open guide (works in both modes)
  const handleOpenGuide = (guideId, contextPayload) => {
    console.log('🔵 handleOpenGuide called:', { guideId, contextPayload, isWorkspaceMode, hasContext: !!workspaceContext })
    if (isWorkspaceMode && workspaceContext) {
      console.log('🔵 Using workspace context to open guide')
      workspaceContext.openGuide(guideId, contextPayload)
    } else {
      console.log('🔵 Using local state to open drawer')
      setDrawerContext({ guideId, payload: contextPayload })
      setDrawerOpen(true)
    }
  }

  // Helper to regenerate study guide
  const handleRegenerateGuide = async (guideId, e) => {
    e.preventDefault()
    e.stopPropagation()
    
    try {
      showNotification('Regenerating study guide...', 'info')
      const result = await tests.regenerateStudyGuide(guideId, preferredLanguage)
      showNotification('Study guide regenerated successfully', 'success')
      // Reload the report to get updated study guides
      await loadReport()
      // Also reload all guides if showAllGuides is true
      if (showAllGuides) {
        await loadAllGuides()
      }
    } catch (err) {
      console.error('Failed to regenerate study guide:', err)
      showNotification(err.message || 'Failed to regenerate study guide', 'error')
    }
  }

  useEffect(() => {
    loadReport()
    if (showAllGuides) {
      loadAllGuides()
    }
  }, [childId, daysBack, showAllGuides, preferredLanguage])

  // Debug drawer state changes
  useEffect(() => {
    console.log('Drawer state changed:', { drawerOpen, drawerContext })
  }, [drawerOpen, drawerContext])

  // Debug: Log guideMap when report is available
  // MUST be before any early returns to follow Rules of Hooks
  useEffect(() => {
    if (report?.study_guide_links) {
      console.log('Study guide links:', report.study_guide_links)
      const guideMap = {}
      report.study_guide_links.forEach(link => {
        guideMap[link.concept] = link.guide_id
      })
      console.log('Guide map:', guideMap)
    }
  }, [report])

  // Measure container height for drawer
  useEffect(() => {
    const updateHeight = () => {
      if (reportContainerRef.current) {
        const rect = reportContainerRef.current.getBoundingClientRect()
        setContainerHeight(rect.height)
      }
    }

    updateHeight()
    window.addEventListener('resize', updateHeight)
    
    // Also update when report changes
    if (report) {
      // Small delay to ensure DOM is updated
      setTimeout(updateHeight, 100)
    }

    return () => window.removeEventListener('resize', updateHeight)
  }, [report])
  
  const loadAllGuides = async () => {
    if (!childId) return
    try {
      setLoadingGuides(true)
      const data = await tests.listStudyGuides(childId)
      setAllGuides(data.guides || [])
    } catch (err) {
      console.error('Failed to load study guides:', err)
    } finally {
      setLoadingGuides(false)
    }
  }

  const loadReport = async () => {
    if (!childId) {
      setError('Child ID is required')
      setLoading(false)
      return
    }
    try {
      setLoading(true)
      setError(null)
      console.log('Loading evaluation report for child:', childId, 'daysBack:', daysBack)
      const data = await tests.getEvaluationReport(childId, daysBack, true, preferredLanguage)
      console.log('Evaluation report loaded:', data)
      setReport(data)
    } catch (err) {
      console.error('Error loading evaluation report:', err)
      const errorMessage = err.message || 'Failed to load report'
      setError(errorMessage)
      showNotification(errorMessage, 'error')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center' }}>
        <LoadingSpinner />
        <p style={{ marginTop: '1rem', color: 'var(--text-color)' }}>Generating evaluation report...</p>
      </div>
    )
  }
  
  if (error) {
    return (
      <div className="error" style={{ padding: '2rem', textAlign: 'center' }}>
        <h3 style={{ color: 'var(--error-color)', marginBottom: '1rem' }}>Error Loading Report</h3>
        <p>{error}</p>
        <button 
          onClick={loadReport} 
          className="btn-primary"
          style={{ marginTop: '1rem' }}
        >
          Retry
        </button>
      </div>
    )
  }
  
  if (!report || report.error) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center' }}>
        <h3 style={{ marginBottom: '1rem' }}>No Report Available</h3>
        <p>{report?.error || 'No evaluation data available for this period.'}</p>
        <p style={{ marginTop: '0.5rem', color: 'var(--text-color)' }}>
          Tests analyzed: {report?.tests_analyzed || 0}
        </p>
        {(!report?.tests_analyzed || report.tests_analyzed === 0) && (
          <p style={{ marginTop: '1rem', color: 'var(--text-color)' }}>
            Complete at least one test to generate an evaluation report.
          </p>
        )}
      </div>
    )
  }

  const { overall_performance, subject_performance, strengths, areas_of_focus, recommendations, error_patterns, study_guide_links } = report

  // Helper function to format subject/concept names consistently
  // Handles formats like "biology_General" -> "Biology" or "physics" -> "Physics"
  const formatSubjectName = (name) => {
    if (!name) return 'General'
    // If it contains underscore, take the first part (subject) and capitalize properly
    if (name.includes('_')) {
      const subject = name.split('_')[0]
      // Capitalize first letter, rest lowercase
      return subject.charAt(0).toUpperCase() + subject.slice(1).toLowerCase()
    }
    // If it's already a single word, capitalize first letter
    return name.charAt(0).toUpperCase() + name.slice(1).toLowerCase()
  }

  // Create a map of concept to guide_id for quick lookup
  const guideMap = {}
  if (study_guide_links) {
    study_guide_links.forEach(link => {
      guideMap[link.concept] = link.guide_id
    })
    console.log('📋 Guide Map created:', guideMap)
    console.log('📋 Study guide links:', study_guide_links)
  } else {
    console.log('⚠️ No study_guide_links in report')
  }

  return (
    <div 
      ref={reportContainerRef} 
      style={{ 
        padding: '2rem', 
        maxWidth: isWorkspaceMode ? '100%' : '1200px', 
        margin: isWorkspaceMode ? 0 : '0 auto',
        display: 'flex',
        flexDirection: 'column',
        height: isWorkspaceMode ? '100%' : '100vh',
        overflow: 'hidden'
      }}
    >
      {/* Top 2/3: Evaluation Report Content */}
      <div style={{ 
        flex: '2',
        overflowY: 'auto', 
        paddingRight: '1rem',
        marginBottom: 0
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2 style={{ margin: 0 }}>Evaluation Report</h2>
          {!isWorkspaceMode && (
            <button
              onClick={() => {
                // Open Zoria with the first available guide or general context
                const firstGuide = study_guide_links && study_guide_links.length > 0 
                  ? study_guide_links[0].guide_id 
                  : null
                setCoachOpen(true)
                if (firstGuide) {
                  setCoachGuideId(firstGuide)
                  setCoachContext({
                    activeTopic: study_guide_links[0].concept,
                    relatedError: null,
                    navigationState: 'GUIDE'
                  })
                } else {
                  // Open Zoria without a specific guide - can still answer general questions
                  setCoachGuideId(null)
                  setCoachContext({
                    activeTopic: 'General Learning',
                    relatedError: null,
                    navigationState: 'GUIDE'
                  })
                }
              }}
              className="btn-primary"
              style={{ 
                padding: '0.75rem 1.5rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem'
              }}
            >
              Chat with Zoria
            </button>
          )}
        </div>

      {/* Performance Snapshot - Radial Progress Ring */}
      <div style={{
        background: 'var(--bg-secondary)',
        padding: '2rem',
        borderRadius: 'var(--radius-md)',
        marginBottom: '2rem',
        border: '1px solid var(--border-color)',
        display: 'flex',
        alignItems: 'center',
        gap: '2rem',
        position: 'relative'
      }}>
        {/* Radial Progress Ring */}
        <div style={{ position: 'relative', flexShrink: 0 }}>
          <svg width="120" height="120" style={{ transform: 'rotate(-90deg)' }}>
            {/* Background circle */}
            <circle
              cx="60"
              cy="60"
              r="50"
              fill="none"
              stroke="var(--border-color)"
              strokeWidth="8"
            />
            {/* Progress circle */}
            <circle
              cx="60"
              cy="60"
              r="50"
              fill="none"
              stroke={overall_performance.accuracy_percentage >= 70 ? 'var(--success-color)' : 
                      overall_performance.accuracy_percentage < 60 ? 'var(--error-color)' : 
                      'var(--primary-color)'}
              strokeWidth="8"
              strokeLinecap="round"
              strokeDasharray={`${2 * Math.PI * 50}`}
              strokeDashoffset={`${2 * Math.PI * 50 * (1 - overall_performance.accuracy_percentage / 100)}`}
              style={{ transition: 'stroke-dashoffset 0.5s ease' }}
            />
          </svg>
          <div style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            textAlign: 'center'
          }}>
            <div style={{
              fontSize: '1.75rem',
              fontWeight: 'bold',
              color: 'var(--primary-color)'
            }}>
              {overall_performance.accuracy_percentage}%
            </div>
            <div style={{
              fontSize: '0.75rem',
              color: 'var(--text-color)'
            }}>
              Accuracy
            </div>
          </div>
        </div>

        {/* Summary Text */}
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: '1.1rem', fontWeight: '600', marginBottom: '0.5rem' }}>
            Performance Snapshot
          </div>
          <div style={{ fontSize: '0.95rem', color: 'var(--text-color)', marginBottom: '0.25rem' }}>
            {overall_performance.correct_count}/{overall_performance.total_questions} Questions Correct
          </div>
          <div style={{ fontSize: '0.95rem', color: 'var(--text-color)' }}>
            Avg Score: {overall_performance.score_percentage}%
          </div>
        </div>

        {/* Info Icon for Metadata */}
        <button
          onClick={() => setShowMetadata(!showMetadata)}
          style={{
            background: 'transparent',
            border: 'none',
            cursor: 'pointer',
            padding: '0.5rem',
            borderRadius: '50%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-color)',
            fontSize: '1.25rem',
            transition: 'background 0.2s'
          }}
          onMouseEnter={(e) => e.currentTarget.style.background = 'var(--bg-primary)'}
          onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
          title="Report Information"
        >
          Info
        </button>

        {/* Metadata Tooltip/Collapsible */}
        {showMetadata && (
          <div style={{
            position: 'absolute',
            top: '100%',
            right: 0,
            marginTop: '0.5rem',
            background: 'var(--bg-primary)',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-md)',
            padding: '1rem',
            boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
            zIndex: 100,
            minWidth: '250px'
          }}>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-color)', lineHeight: 1.6 }}>
              <div><strong>Generated:</strong> {(() => {
                let dateStr = report.generated_at
                if (!dateStr.includes('Z') && !dateStr.match(/[+-]\d{2}:\d{2}$/)) {
                  dateStr = dateStr.endsWith('Z') ? dateStr : dateStr + 'Z'
                }
                const date = new Date(dateStr)
                return date.toLocaleString(undefined, {
                  year: 'numeric',
                  month: 'short',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit'
                })
              })()}</div>
              <div style={{ marginTop: '0.5rem' }}><strong>Period:</strong> Last {report.period_days} days</div>
              <div style={{ marginTop: '0.5rem' }}><strong>Tests Analyzed:</strong> {report.tests_analyzed}</div>
            </div>
          </div>
        )}
      </div>

      {/* Subject-Level Performance - Collapsible Cards */}
      {subject_performance && subject_performance.length > 0 && (
        <div style={{ marginBottom: '2rem' }}>
          <h3 style={{ marginBottom: '1rem' }}>Subject Performance</h3>
          <div style={{ display: 'grid', gap: '0.75rem' }}>
            {subject_performance.map((subject, idx) => {
              const isExpanded = expandedSubjects[idx]
              const totalErrors = subject.common_errors?.reduce((sum, err) => sum + err.count, 0) || 0
              const hasHighErrors = totalErrors > 5
              
              return (
                <div 
                  key={idx} 
                  style={{
                    background: subject.avg_performance >= 70 ? 'var(--success-color-light)' : 
                               subject.avg_performance < 60 ? 'var(--error-color-light)' : 
                               'var(--bg-secondary)',
                    borderRadius: 'var(--radius-md)',
                    border: `1px solid ${subject.avg_performance >= 70 ? 'var(--success-color)' : 
                                            subject.avg_performance < 60 ? 'var(--error-color)' : 
                                            'var(--border-color)'}`,
                    overflow: 'hidden',
                    transition: 'all 0.3s ease'
                  }}
                >
                  {/* Header - Always Visible */}
                  <div 
                    onClick={() => setExpandedSubjects(prev => ({ ...prev, [idx]: !prev[idx] }))}
                    style={{
                      padding: '1rem',
                      cursor: 'pointer',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      userSelect: 'none'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flex: 1 }}>
                      <div>
                        <div style={{ 
                          fontSize: '1.1rem', 
                          fontWeight: '600',
                          marginBottom: '0.25rem'
                        }}>
                          {formatSubjectName(subject.subject) || 'Unknown Subject'}
                        </div>
                        <div style={{ fontSize: '0.875rem', color: 'var(--text-color)' }}>
                          {subject.total_questions} questions • {subject.concepts_count} concepts
                        </div>
                      </div>
                      {hasHighErrors && (
                        <span style={{
                          padding: '0.25rem 0.75rem',
                          background: 'var(--error-color)',
                          color: 'white',
                          borderRadius: 'var(--radius-full)',
                          fontSize: '0.75rem',
                          fontWeight: '600'
                        }}>
                          {totalErrors} Errors
                        </span>
                      )}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ 
                          fontSize: '1.5rem', 
                          fontWeight: 'bold', 
                          color: subject.avg_performance >= 70 ? 'var(--success-color)' : 
                                 subject.avg_performance < 60 ? 'var(--error-color)' : 
                                 'var(--text-color)' 
                        }}>
                          {subject.avg_performance}%
                        </div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-color)' }}>
                          Avg Performance
                        </div>
                      </div>
                      <div style={{
                        fontSize: '0.875rem',
                        color: 'var(--text-color)',
                        fontWeight: '600',
                        transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
                        transition: 'transform 0.3s ease'
                      }}>
                        ▼
                      </div>
                    </div>
                  </div>

                  {/* Expandable Content */}
                  {isExpanded && (
                    <div style={{
                      padding: '0 1rem 1rem 1rem',
                      borderTop: '1px solid var(--border-color)',
                      marginTop: '0.5rem',
                      paddingTop: '1rem',
                      animation: 'slideDown 0.3s ease'
                    }}>
                      <div style={{ 
                        display: 'grid', 
                        gridTemplateColumns: 'repeat(3, 1fr)', 
                        gap: '1rem', 
                        marginBottom: '1rem',
                        fontSize: '0.875rem' 
                      }}>
                        <div>
                          <div style={{ color: 'var(--text-color)', marginBottom: '0.25rem' }}>Accuracy</div>
                          <div style={{ fontWeight: '600', fontSize: '1rem' }}>{subject.accuracy}%</div>
                        </div>
                        <div>
                          <div style={{ color: 'var(--text-color)', marginBottom: '0.25rem' }}>Score</div>
                          <div style={{ fontWeight: '600', fontSize: '1rem' }}>{subject.score_percentage}%</div>
                        </div>
                        <div>
                          <div style={{ color: 'var(--text-color)', marginBottom: '0.25rem' }}>Correct</div>
                          <div style={{ fontWeight: '600', fontSize: '1rem' }}>
                            {subject.correct_count}/{subject.total_questions}
                          </div>
                        </div>
                      </div>
                      {subject.common_errors && subject.common_errors.length > 0 && (
                        <div>
                          <strong style={{ fontSize: '0.875rem' }}>Common Errors:</strong>
                          <div style={{ 
                            marginTop: '0.5rem', 
                            display: 'flex', 
                            flexWrap: 'wrap', 
                            gap: '0.5rem' 
                          }}>
                            {subject.common_errors.map((err, i) => (
                              <span key={i} style={{
                                padding: '0.375rem 0.75rem',
                                background: 'var(--bg-primary)',
                                borderRadius: 'var(--radius-sm)',
                                fontSize: '0.8rem',
                                border: '1px solid var(--border-color)'
                              }}>
                                {err.type} ({err.count})
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          <style>{`
            @keyframes slideDown {
              from {
                opacity: 0;
                max-height: 0;
              }
              to {
                opacity: 1;
                max-height: 500px;
              }
            }
          `}</style>
        </div>
      )}

      {/* Strengths */}
      {strengths && strengths.length > 0 && (
        <div style={{ marginBottom: '2rem' }}>
          <h3 style={{ color: 'var(--success-color)', marginBottom: '1rem' }}>
            Strengths
          </h3>
          <div style={{ display: 'grid', gap: '1rem' }}>
            {strengths.map((strength, idx) => (
              <div key={idx} style={{
                background: 'var(--success-color-light)',
                padding: '1rem',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--success-color)'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <strong>{formatSubjectName(strength.concept)}</strong>
                    <div style={{ marginTop: '0.5rem', fontSize: '0.9rem' }}>
                      Accuracy: {strength.accuracy}% • Score: {strength.score_percentage}%
                      {' • '}
                      {strength.questions_count} questions
                    </div>
                  </div>
                  <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: 'var(--success-color)' }}>
                    {strength.score_percentage}%
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Areas of Focus - Task-Oriented Cards */}
      {areas_of_focus && areas_of_focus.length > 0 && (
        <div style={{ marginBottom: '2rem' }}>
          <h3 style={{ color: 'var(--error-color)', marginBottom: '1rem' }}>
            Areas of Focus
          </h3>
          <div style={{ display: 'grid', gap: '1rem' }}>
            {areas_of_focus.map((area, idx) => {
              const hasGuide = guideMap[area.concept]
              
              return (
                <div 
                  key={idx} 
                  style={{
                    background: 'var(--bg-secondary)',
                    padding: '1.5rem',
                    borderRadius: 'var(--radius-md)',
                    border: '2px solid var(--error-color)',
                    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)'
                  }}
                >
                  {/* Header with Concept Name and Score */}
                  <div style={{ marginBottom: '1rem' }}>
                    <div style={{ 
                      fontSize: '1.25rem', 
                      fontWeight: '600',
                      marginBottom: '0.5rem',
                      color: 'var(--error-color)'
                    }}>
                      {formatSubjectName(area.concept)}
                    </div>
                    <div style={{ fontSize: '0.875rem', color: 'var(--text-color)' }}>
                      {area.questions_count} questions • Accuracy: {area.accuracy}%
                    </div>
                  </div>

                  {/* Progress Bar */}
                  <div style={{ marginBottom: '1rem' }}>
                    <div style={{ 
                      display: 'flex', 
                      justifyContent: 'space-between', 
                      alignItems: 'center',
                      marginBottom: '0.5rem'
                    }}>
                      <span style={{ fontSize: '0.875rem', fontWeight: '600' }}>Progress</span>
                      <span style={{ fontSize: '0.875rem', color: 'var(--text-color)' }}>
                        {area.score_percentage}%
                      </span>
                    </div>
                    <div style={{
                      width: '100%',
                      height: '12px',
                      background: 'var(--bg-primary)',
                      borderRadius: 'var(--radius-full)',
                      overflow: 'hidden',
                      border: '1px solid var(--border-color)'
                    }}>
                      <div style={{
                        width: `${area.score_percentage}%`,
                        height: '100%',
                        background: area.score_percentage >= 70 ? 'var(--success-color)' :
                                    area.score_percentage < 60 ? 'var(--error-color)' :
                                    'var(--primary-color)',
                        transition: 'width 0.5s ease',
                        borderRadius: 'var(--radius-full)'
                      }} />
                    </div>
                  </div>

                  {/* Quick Error Summary */}
                  {area.common_errors && area.common_errors.length > 0 && (
                    <div style={{ 
                      marginBottom: '1rem',
                      padding: '0.75rem',
                      background: 'var(--error-color-light)',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: '0.875rem'
                    }}>
                      <strong style={{ color: 'var(--error-color)' }}>Common Issues:</strong>
                      <div style={{ 
                        marginTop: '0.5rem',
                        display: 'flex',
                        flexWrap: 'wrap',
                        gap: '0.5rem'
                      }}>
                        {area.common_errors.slice(0, 3).map((err, i) => (
                          <span key={i} style={{
                            padding: '0.25rem 0.5rem',
                            background: 'var(--bg-primary)',
                            borderRadius: 'var(--radius-sm)',
                            fontSize: '0.8rem',
                            border: '1px solid var(--error-color)'
                          }}>
                            {err.type} ({err.count})
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Master This Concept Button */}
                  {hasGuide ? (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.preventDefault()
                        e.stopPropagation()
                        
                        const guideId = guideMap[area.concept]
                        const primaryError = area.common_errors?.[0]
                        const errorDetails = area.common_errors || []
                        
                        const contextPayload = {
                          activeTopic: area.concept,
                          relatedError: {
                            errorType: primaryError?.type || 'Conceptual',
                            errorDetails: errorDetails.map(err => ({
                              type: err.type,
                              count: err.count,
                              description: err.description || `${err.type} error occurred ${err.count} times`
                            })),
                            misconceptions: area.misconceptions || []
                          },
                          navigationState: 'GUIDE',
                          focusArea: area.focus_area || area.concept
                        }
                        
                        handleOpenGuide(guideId, contextPayload)
                      }}
                      style={{
                        width: '100%',
                        padding: '1rem',
                        background: 'var(--primary-color-light)',
                        color: 'var(--text-color)',
                        border: '2px solid var(--primary-color)',
                        borderRadius: 'var(--radius-md)',
                        cursor: 'pointer',
                        fontSize: '1rem',
                        fontWeight: '600',
                        transition: 'all 0.2s',
                        boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)'
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = 'var(--primary-color)'
                        e.currentTarget.style.color = 'var(--text-color)'
                        e.currentTarget.style.borderColor = 'var(--primary-color)'
                        e.currentTarget.style.transform = 'translateY(-2px)'
                        e.currentTarget.style.boxShadow = '0 4px 8px rgba(0, 0, 0, 0.15)'
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = 'var(--primary-color-light)'
                        e.currentTarget.style.color = 'var(--text-color)'
                        e.currentTarget.style.borderColor = 'var(--primary-color)'
                        e.currentTarget.style.transform = 'translateY(0)'
                        e.currentTarget.style.boxShadow = '0 2px 4px rgba(0, 0, 0, 0.1)'
                      }}
                    >
                      Master The Concept
                    </button>
                  ) : (
                    <div style={{
                      width: '100%',
                      padding: '1rem',
                      background: 'var(--bg-primary)',
                      border: '2px dashed var(--border-color)',
                      borderRadius: 'var(--radius-md)',
                      textAlign: 'center',
                      fontSize: '0.875rem',
                      color: 'var(--text-color)',
                      fontStyle: 'italic'
                    }}>
                      Study guide coming soon...
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Recommendations - Horizontal Carousel */}
      {recommendations && recommendations.length > 0 && (
        <div style={{ marginBottom: '2rem' }}>
          <h3 style={{ marginBottom: '1rem' }}>Recommendations</h3>
          <div 
            ref={recommendationsCarouselRef}
            style={{
              display: 'flex',
              gap: '1rem',
              overflowX: 'auto',
              paddingBottom: '0.5rem',
              scrollSnapType: 'x mandatory',
              scrollbarWidth: 'thin',
              WebkitOverflowScrolling: 'touch'
            }}
            onWheel={(e) => {
              if (e.deltaY !== 0) {
                e.preventDefault()
                recommendationsCarouselRef.current?.scrollBy({
                  left: e.deltaY,
                  behavior: 'smooth'
                })
              }
            }}
          >
            {recommendations.map((rec, idx) => {
              // Determine card color based on recommendation type
              let borderColor = 'var(--primary-color)'
              let bgColor = 'var(--primary-color-light)'
              
              const recLower = rec.toLowerCase()
              if (recLower.includes('focus') || recLower.includes('improve') || recLower.includes('work on')) {
                borderColor = 'var(--error-color)'
                bgColor = 'var(--error-color-light)'
              } else if (recLower.includes('keep') || recLower.includes('continue') || recLower.includes('good')) {
                borderColor = 'var(--success-color)'
                bgColor = 'var(--success-color-light)'
              } else if (recLower.includes('fix') || recLower.includes('error') || recLower.includes('mistake')) {
                borderColor = '#fbbf24' // Yellow/amber
                bgColor = '#fef3c7'
              }
              
              return (
                <div
                  key={idx}
                  style={{
                    minWidth: '280px',
                    maxWidth: '320px',
                    padding: '1.5rem',
                    background: bgColor,
                    borderRadius: 'var(--radius-md)',
                    border: `2px solid ${borderColor}`,
                    scrollSnapAlign: 'start',
                    flexShrink: 0,
                    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)'
                  }}
                >
                  <div style={{
                    fontSize: '1rem',
                    lineHeight: 1.6,
                    color: 'var(--text-color)'
                  }}>
                    {rec}
                  </div>
                </div>
              )
            })}
          </div>
          {/* Scroll Indicator */}
          {recommendations.length > 1 && (
            <div style={{
              display: 'flex',
              justifyContent: 'center',
              gap: '0.5rem',
              marginTop: '0.75rem'
            }}>
              {recommendations.map((_, idx) => (
                <div
                  key={idx}
                  style={{
                    width: '8px',
                    height: '8px',
                    borderRadius: '50%',
                    background: 'var(--border-color)',
                    cursor: 'pointer',
                    transition: 'background 0.2s'
                  }}
                  onClick={() => {
                    const cardWidth = 300 // Approximate card width + gap
                    recommendationsCarouselRef.current?.scrollTo({
                      left: idx * cardWidth,
                      behavior: 'smooth'
                    })
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.background = 'var(--primary-color)'}
                  onMouseLeave={(e) => e.currentTarget.style.background = 'var(--border-color)'}
                />
              ))}
            </div>
          )}
        </div>
      )}
        </div>

      {/* Bottom 1/3: Study Guides Section - Card Grid */}
      <div style={{ 
        flex: '1', 
        borderTop: '2px solid var(--border-color)',
        paddingTop: '1.5rem',
        marginTop: '1.5rem',
        overflowY: 'auto',
        minHeight: 0 // Allow flexbox to shrink
      }}>
        <div style={{ 
          marginBottom: '1rem' 
        }}>
          <h3 style={{ margin: 0 }}>Study Guides</h3>
        </div>
        
        {loadingGuides ? (
          <LoadingSpinner />
        ) : study_guide_links && study_guide_links.length > 0 ? (
          <div style={{ 
            display: 'grid', 
            gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
            gap: '1rem',
            maxWidth: '100%'
          }}>
            {study_guide_links.map((link) => {
              const guide = allGuides?.find(g => g.id === link.guide_id) || {
                id: link.guide_id,
                concept_name: link.concept,
                focus_area: link.concept,
                generated_at: null
              }
              
              const subjectName = formatSubjectName(link.concept)
              
              return (
                <div
                  key={link.guide_id}
                  onClick={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                    
                    const contextPayload = {
                      activeTopic: link.concept,
                      relatedError: null,
                      navigationState: 'GUIDE',
                      focusArea: link.concept
                    }
                    handleOpenGuide(link.guide_id, contextPayload)
                  }}
                  style={{
                    background: 'var(--bg-secondary)',
                    padding: '1rem',
                    borderRadius: 'var(--radius-md)',
                    border: '2px solid var(--border-color)',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                    display: 'flex',
                    flexDirection: 'column',
                    aspectRatio: '1',
                    minHeight: 0,
                    justifyContent: 'space-between',
                    position: 'relative'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = 'var(--primary-color)'
                    e.currentTarget.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.1)'
                    e.currentTarget.style.transform = 'translateY(-2px)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = 'var(--border-color)'
                    e.currentTarget.style.boxShadow = 'none'
                    e.currentTarget.style.transform = 'translateY(0)'
                  }}
                >
                  {/* Refresh Icon Button - Top Right */}
                  <button
                    onClick={(e) => {
                      e.preventDefault()
                      e.stopPropagation()
                      handleRegenerateGuide(link.guide_id, e)
                    }}
                    style={{
                      position: 'absolute',
                      top: '0.5rem',
                      right: '0.5rem',
                      background: 'var(--bg-primary)',
                      border: '1px solid var(--border-color)',
                      borderRadius: '50%',
                      width: '28px',
                      height: '28px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      cursor: 'pointer',
                      fontSize: '1rem',
                      padding: 0,
                      zIndex: 10,
                      transition: 'all 0.2s'
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = 'var(--primary-color-light)'
                      e.currentTarget.style.borderColor = 'var(--primary-color)'
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = 'var(--bg-primary)'
                      e.currentTarget.style.borderColor = 'var(--border-color)'
                    }}
                    title="Regenerate study guide"
                  >
                    🔄
                  </button>

                  <div>
                    <div style={{ 
                      fontWeight: '600', 
                      fontSize: '1rem',
                      marginBottom: '0.5rem',
                      color: 'var(--primary-color)',
                      paddingRight: '2rem'
                    }}>
                      {subjectName}
                    </div>
                    {guide.focus_area && guide.focus_area !== link.concept && (
                      <div style={{ 
                        fontSize: '0.75rem', 
                        color: 'var(--text-color)', 
                        marginBottom: '0.5rem' 
                      }}>
                        {guide.focus_area}
                      </div>
                    )}
                    {guide.generated_at && (() => {
                      let dateStr = guide.generated_at
                      if (!dateStr.includes('Z') && !dateStr.match(/[+-]\d{2}:\d{2}$/)) {
                        dateStr = dateStr.endsWith('Z') ? dateStr : dateStr + 'Z'
                      }
                      const date = new Date(dateStr)
                      return (
                        <div style={{ 
                          fontSize: '0.7rem', 
                          color: 'var(--text-muted)',
                          marginTop: '0.5rem'
                        }}>
                          {date.toLocaleString(undefined, {
                            month: 'short',
                            day: 'numeric',
                            year: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit'
                          })}
                        </div>
                      )
                    })()}
                  </div>
                  <div style={{
                    marginTop: '0.75rem',
                    padding: '0.5rem',
                    background: 'var(--primary-color-light)',
                    borderRadius: 'var(--radius-sm)',
                    textAlign: 'center',
                    fontSize: '0.875rem',
                    fontWeight: '600',
                    color: 'var(--primary-color)'
                  }}>
                    View Guide
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div style={{ 
            padding: '2rem', 
            textAlign: 'center', 
            color: 'var(--text-color)' 
          }}>
            <p>No study guides available yet.</p>
            <p style={{ fontSize: '0.875rem', marginTop: '0.5rem' }}>
              Study guides are generated automatically when you view your evaluation report.
            </p>
          </div>
        )}
      </div>

      {/* Learning Drawer - Only render if not in workspace mode */}
      {!isWorkspaceMode && drawerOpen && drawerContext && (
        <LearningDrawer
          isOpen={drawerOpen}
          onClose={() => {
            console.log('Closing drawer')
            setDrawerOpen(false)
            setDrawerContext(null)
          }}
          guideId={drawerContext.guideId}
          contextPayload={drawerContext.payload}
          containerHeight={containerHeight}
          onOpenCoach={(guideId, context) => {
            setCoachOpen(true)
            setCoachGuideId(guideId)
            setCoachContext(context)
          }}
          preferredLanguage={preferredLanguage}
        />
      )}

      {/* Zoria - Only render if not in workspace mode */}
      {!isWorkspaceMode && coachOpen && (
        <AICoach
          isOpen={coachOpen}
          onToggle={() => {
            setCoachOpen(false)
            setCoachGuideId(null)
            setCoachContext(null)
          }}
          guideId={coachGuideId}
          contextPayload={coachContext}
          activeTab="GUIDE"
          onNavigateTab={() => {}}
          userName={user?.name || user?.email || 'You'}
        />
      )}

      {/* Legacy Study Guide Modal (for backward compatibility - DISABLED, use drawer instead) */}
      {false && selectedGuideId && !drawerOpen && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.5)',
          zIndex: 1000,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '2rem'
        }}>
          <div style={{
            background: 'white',
            borderRadius: 'var(--radius-md)',
            maxWidth: '90%',
            maxHeight: '90%',
            overflow: 'auto',
            width: '100%',
            boxShadow: '0 4px 6px rgba(0,0,0,0.1)'
          }}>
            <StudyGuide 
              guideId={selectedGuideId} 
              onClose={() => setSelectedGuideId(null)}
              preferredLanguage={preferredLanguage}
            />
          </div>
        </div>
      )}
    </div>
  )
}
