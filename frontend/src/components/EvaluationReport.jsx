import { useState, useEffect } from 'react'
import { tests } from '../services/api'
import LoadingSpinner from './LoadingSpinner'
import StudyGuide from './StudyGuide'
import { showNotification } from '../utils/notifications'

export default function EvaluationReport({ childId, daysBack = 30, showAllGuides = false }) {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedGuideId, setSelectedGuideId] = useState(null)
  const [allGuides, setAllGuides] = useState(null)
  const [loadingGuides, setLoadingGuides] = useState(false)

  useEffect(() => {
    loadReport()
    if (showAllGuides) {
      loadAllGuides()
    }
  }, [childId, daysBack, showAllGuides])
  
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
      const data = await tests.getEvaluationReport(childId, daysBack, true)
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
        <p style={{ marginTop: '1rem', color: 'var(--text-muted)' }}>Generating evaluation report...</p>
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
        <p style={{ marginTop: '0.5rem', color: 'var(--text-muted)' }}>
          Tests analyzed: {report?.tests_analyzed || 0}
        </p>
        {(!report?.tests_analyzed || report.tests_analyzed === 0) && (
          <p style={{ marginTop: '1rem', color: 'var(--text-muted)' }}>
            Complete at least one test to generate an evaluation report.
          </p>
        )}
      </div>
    )
  }

  const { overall_performance, subject_performance, strengths, areas_of_focus, recommendations, error_patterns, study_guide_links } = report

  // Create a map of concept to guide_id for quick lookup
  const guideMap = {}
  if (study_guide_links) {
    study_guide_links.forEach(link => {
      guideMap[link.concept] = link.guide_id
    })
  }

  return (
    <div style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
      <h2>Evaluation Report</h2>
      <div style={{ marginBottom: '1rem', color: 'var(--text-muted)' }}>
        Generated: {(() => {
          // Ensure UTC timestamps are properly parsed
          let dateStr = report.generated_at
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
        {' • '}
        Period: Last {report.period_days} days
        {' • '}
        Tests analyzed: {report.tests_analyzed}
      </div>

      {/* Overall Performance */}
      <div style={{
        background: 'var(--bg-secondary)',
        padding: '1.5rem',
        borderRadius: 'var(--radius-md)',
        marginBottom: '2rem',
        border: '1px solid var(--border-color)'
      }}>
        <h3 style={{ marginBottom: '1rem' }}>Overall Performance</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginTop: '1rem' }}>
          <div>
            <div style={{ fontSize: '2rem', fontWeight: 'bold', color: 'var(--primary-color)' }}>
              {overall_performance.accuracy_percentage}%
            </div>
            <div style={{ color: 'var(--text-muted)' }}>Accuracy</div>
          </div>
          <div>
            <div style={{ fontSize: '2rem', fontWeight: 'bold', color: 'var(--primary-color)' }}>
              {overall_performance.score_percentage}%
            </div>
            <div style={{ color: 'var(--text-muted)' }}>Score</div>
          </div>
          <div>
            <div style={{ fontSize: '2rem', fontWeight: 'bold' }}>
              {overall_performance.correct_count}/{overall_performance.total_questions}
            </div>
            <div style={{ color: 'var(--text-muted)' }}>Questions Correct</div>
          </div>
        </div>
      </div>

      {/* Subject-Level Performance */}
      {subject_performance && subject_performance.length > 0 && (
        <div style={{ marginBottom: '2rem' }}>
          <h3 style={{ marginBottom: '1rem' }}>Subject Performance</h3>
          <div style={{ display: 'grid', gap: '1rem' }}>
            {subject_performance.map((subject, idx) => (
              <div key={idx} style={{
                background: subject.avg_performance >= 70 ? 'var(--success-color-light)' : 
                           subject.avg_performance < 60 ? 'var(--error-color-light)' : 
                           'var(--bg-secondary)',
                padding: '1rem',
                borderRadius: 'var(--radius-md)',
                border: `1px solid ${subject.avg_performance >= 70 ? 'var(--success-color)' : 
                                        subject.avg_performance < 60 ? 'var(--error-color)' : 
                                        'var(--border-color)'}`
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                  <div>
                    <strong style={{ fontSize: '1.1rem' }}>{subject.subject || 'Unknown Subject'}</strong>
                    <div style={{ marginTop: '0.25rem', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                      {subject.total_questions} questions • {subject.concepts_count} concepts
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '1.5rem', fontWeight: 'bold', 
                                 color: subject.avg_performance >= 70 ? 'var(--success-color)' : 
                                        subject.avg_performance < 60 ? 'var(--error-color)' : 
                                        'var(--text-color)' }}>
                      {subject.avg_performance}%
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      Avg Performance
                    </div>
                  </div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginTop: '0.75rem', fontSize: '0.875rem' }}>
                  <div>
                    <div style={{ color: 'var(--text-muted)' }}>Accuracy</div>
                    <div style={{ fontWeight: '600' }}>{subject.accuracy}%</div>
                  </div>
                  <div>
                    <div style={{ color: 'var(--text-muted)' }}>Score</div>
                    <div style={{ fontWeight: '600' }}>{subject.score_percentage}%</div>
                  </div>
                  <div>
                    <div style={{ color: 'var(--text-muted)' }}>Correct</div>
                    <div style={{ fontWeight: '600' }}>{subject.correct_count}/{subject.total_questions}</div>
                  </div>
                </div>
                {subject.common_errors && subject.common_errors.length > 0 && (
                  <div style={{ marginTop: '0.75rem', fontSize: '0.875rem' }}>
                    <strong>Common Errors:</strong>
                    <div style={{ marginTop: '0.25rem', display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                      {subject.common_errors.map((err, i) => (
                        <span key={i} style={{
                          padding: '0.25rem 0.5rem',
                          background: 'var(--bg-primary)',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: '0.8rem'
                        }}>
                          {err.type} ({err.count})
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
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
                    <strong>{strength.concept}</strong>
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

      {/* Areas of Focus */}
      {areas_of_focus && areas_of_focus.length > 0 && (
        <div style={{ marginBottom: '2rem' }}>
          <h3 style={{ color: 'var(--error-color)', marginBottom: '1rem' }}>
            Areas of Focus
          </h3>
          <div style={{ display: 'grid', gap: '1rem' }}>
            {areas_of_focus.map((area, idx) => (
              <div key={idx} style={{
                background: 'var(--error-color-light)',
                padding: '1rem',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--error-color)'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                  <div>
                    <strong>{area.concept}</strong>
                    <div style={{ marginTop: '0.5rem', fontSize: '0.9rem' }}>
                      Accuracy: {area.accuracy}% • Score: {area.score_percentage}%
                      {' • '}
                      {area.questions_count} questions
                    </div>
                  </div>
                  <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: 'var(--error-color)' }}>
                    {area.score_percentage}%
                  </div>
                </div>
                
                {area.common_errors && area.common_errors.length > 0 && (
                  <div style={{ marginTop: '0.75rem', fontSize: '0.9rem' }}>
                    <strong>Common Errors:</strong>
                    <ul style={{ marginTop: '0.25rem', paddingLeft: '1.5rem' }}>
                      {area.common_errors.map((err, i) => (
                        <li key={i}>
                          {err.type} ({err.count} times)
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {area.misconceptions && area.misconceptions.length > 0 && (
                  <div style={{ marginTop: '0.75rem', fontSize: '0.9rem' }}>
                    <strong>Misconceptions:</strong>
                    <ul style={{ marginTop: '0.25rem', paddingLeft: '1.5rem' }}>
                      {area.misconceptions.slice(0, 3).map((misc, i) => (
                        <li key={i}>{misc}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Study Guide Link */}
                {guideMap[area.concept] && (
                  <button
                    onClick={() => setSelectedGuideId(guideMap[area.concept])}
                    style={{
                      marginTop: '0.75rem',
                      padding: '0.5rem 1rem',
                      background: 'var(--primary-color)',
                      color: 'white',
                      border: 'none',
                      borderRadius: 'var(--radius-md)',
                      cursor: 'pointer',
                      fontSize: '0.9rem'
                    }}
                  >
                    View Study Guide
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recommendations */}
      {recommendations && recommendations.length > 0 && (
        <div style={{
          background: 'var(--primary-color-light)',
          padding: '1.5rem',
          borderRadius: 'var(--radius-md)',
          border: '1px solid var(--primary-color)',
          marginBottom: '2rem'
        }}>
          <h3 style={{ marginBottom: '1rem' }}>Recommendations</h3>
          <ul style={{ margin: 0, paddingLeft: '1.5rem' }}>
            {recommendations.map((rec, idx) => (
              <li key={idx} style={{ marginBottom: '0.5rem', lineHeight: 1.6 }}>{rec}</li>
            ))}
          </ul>
        </div>
      )}

      {/* All Study Guides Section */}
      {showAllGuides && (
        <div style={{ marginTop: '3rem' }}>
          <h3 style={{ marginBottom: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>All Study Guides</span>
            <button
              onClick={loadAllGuides}
              className="btn-secondary"
              style={{ fontSize: '0.875rem' }}
              disabled={loadingGuides}
            >
              {loadingGuides ? 'Loading...' : 'Refresh'}
            </button>
          </h3>
          {loadingGuides ? (
            <LoadingSpinner />
          ) : allGuides && allGuides.length > 0 ? (
            <div style={{ display: 'grid', gap: '1rem' }}>
              {allGuides.map((guide) => (
                <div
                  key={guide.id}
                  style={{
                    background: 'var(--bg-secondary)',
                    padding: '1rem',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--border-color)',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center'
                  }}
                >
                  <div>
                    <strong>{guide.concept_name}</strong>
                    {guide.focus_area && (
                      <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                        Focus: {guide.focus_area}
                      </div>
                    )}
                    {guide.generated_at && (() => {
                      // Ensure UTC timestamps are properly parsed
                      let dateStr = guide.generated_at
                      if (!dateStr.includes('Z') && !dateStr.match(/[+-]\d{2}:\d{2}$/)) {
                        // Add 'Z' to indicate UTC if not present
                        dateStr = dateStr.endsWith('Z') ? dateStr : dateStr + 'Z'
                      }
                      const date = new Date(dateStr)
                      return (
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                          Generated: {date.toLocaleString(undefined, {
                            year: 'numeric',
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                            timeZoneName: 'short'
                          })}
                        </div>
                      )
                    })()}
                  </div>
                  <button
                    onClick={() => setSelectedGuideId(guide.id)}
                    className="btn-primary"
                    style={{ fontSize: '0.875rem' }}
                  >
                    View Guide
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
              <p>No study guides available yet.</p>
              <p style={{ fontSize: '0.875rem', marginTop: '0.5rem' }}>
                Study guides are generated automatically when you view your evaluation report.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Study Guide Modal */}
      {selectedGuideId && (
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
            />
          </div>
        </div>
      )}
    </div>
  )
}
