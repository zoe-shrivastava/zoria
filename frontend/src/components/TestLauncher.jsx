import { useState, useEffect } from 'react'
import { tests } from '../services/api'
import { showNotification } from '../utils/notifications'
import LoadingSpinner from './LoadingSpinner'

export default function TestLauncher({ childId, onTestGenerated, userRole, preferredLanguage = null }) {
  const [subjectsData, setSubjectsData] = useState([])
  const [selectedSubject, setSelectedSubject] = useState('')
  const [selectedTopics, setSelectedTopics] = useState([])
  const [includePrerequisites, setIncludePrerequisites] = useState(false)
  const [difficulty, setDifficulty] = useState('')
  const [numQuestions, setNumQuestions] = useState(10)
  const [timeLimit, setTimeLimit] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingSubjects, setLoadingSubjects] = useState(true)

  useEffect(() => {
    if (childId) {
      loadSubjectsTopics()
    }
  }, [childId])

  const loadSubjectsTopics = async () => {
    try {
      setLoadingSubjects(true)
      const data = await tests.getSubjectsTopics(childId)
      if (data && data.subjects) {
        setSubjectsData(data.subjects)
        if (data.subjects.length === 0 && data.message) {
          showNotification(data.message, 'info')
        }
      } else {
        setSubjectsData([])
        const message = data?.message || 'No subjects/topics found. Upload and process documents first.'
        showNotification(message, 'info')
      }
    } catch (error) {
      console.error('Error loading subjects/topics:', error)
      showNotification(error.message || 'Failed to load subjects/topics', 'error')
      setSubjectsData([])
    } finally {
      setLoadingSubjects(false)
    }
  }

  const getSelectedSubjectData = () => {
    return subjectsData.find(s => s.subject === selectedSubject)
  }

  const handleSubjectChange = (e) => {
    setSelectedSubject(e.target.value)
    setSelectedTopics([]) // Reset topics when subject changes
  }

  const handleTopicToggle = (topicName) => {
    setSelectedTopics(prev => {
      if (prev.includes(topicName)) {
        return prev.filter(t => t !== topicName)
      } else {
        return [...prev, topicName]
      }
    })
  }

  const handleGenerate = async () => {
    if (!selectedSubject) {
      showNotification('Please select a subject', 'warning')
      return
    }

    if (selectedTopics.length === 0) {
      showNotification('Please select at least one topic', 'warning')
      return
    }

    try {
      setLoading(true)
      
      // Get the selected subject data to extract subject_id
      const selectedSubjectData = getSelectedSubjectData()
      const subjectId = selectedSubjectData?.subject_id || selectedSubject
      
      const testData = {
        subject: subjectId,  // Use subject_id if available, fallback to display name
        topics: selectedTopics,
        child_id: childId,
        include_prerequisites: includePrerequisites,
        num_questions: numQuestions,
      }

      if (difficulty) {
        testData.difficulty = difficulty
      }

      if (timeLimit) {
        testData.time_limit_minutes = parseInt(timeLimit)
      }

      if (preferredLanguage) {
        testData.language = preferredLanguage
      }

      const test = await tests.generate(testData)
      showNotification('Test generated successfully!', 'success')
      if (onTestGenerated) {
        onTestGenerated(test)
      }
    } catch (error) {
      showNotification(error.message || 'Failed to generate test', 'error')
    } finally {
      setLoading(false)
    }
  }

  const selectedSubjectData = getSelectedSubjectData()
  const allTopics = selectedSubjectData ? (selectedSubjectData.topics || []) : []

  return (
    <div className="test-launcher" style={{ padding: '1.5rem' }}>
      <h2 style={{ marginBottom: '1.5rem' }}>Generate Test</h2>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        {/* Subject Selection */}
        <div>
          <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>
            Select Subject
          </label>
          {loadingSubjects ? (
            <LoadingSpinner />
          ) : (
            <select
              value={selectedSubject}
              onChange={handleSubjectChange}
              style={{
                width: '100%',
                padding: '0.75rem',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-md)',
                fontSize: '1rem',
              }}
            >
              <option value="">-- Select a subject --</option>
              {subjectsData.map((subjectData) => (
                <option key={subjectData.subject} value={subjectData.subject}>
                  {subjectData.subject} ({subjectData.topics?.length || 0} topics)
                </option>
              ))}
            </select>
          )}
          {!loadingSubjects && subjectsData.length === 0 && (
            <p style={{ marginTop: '0.5rem', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
              No subjects available. Upload and process documents to see subjects and topics.
            </p>
          )}
        </div>

        {/* Topic Selection (Multiple) */}
        {selectedSubject && (
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>
              Select Topics (one or more)
            </label>
            <div style={{
              border: '1px solid var(--border-color)',
              borderRadius: 'var(--radius-md)',
              padding: '0.75rem',
              maxHeight: '300px',
              overflowY: 'auto',
              background: 'var(--bg-secondary)',
            }}>
              {allTopics.length === 0 ? (
                <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
                  No topics available for this subject. Make sure documents have been processed and contain concepts.
                </p>
              ) : (
                allTopics.map((topic) => (
                  <label
                    key={topic}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.75rem',
                      padding: '0.5rem',
                      cursor: 'pointer',
                      borderRadius: 'var(--radius-sm)',
                      transition: 'background 0.2s',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = 'var(--bg-tertiary)'
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = 'transparent'
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={selectedTopics.includes(topic)}
                      onChange={() => handleTopicToggle(topic)}
                      style={{
                        width: '18px',
                        height: '18px',
                        cursor: 'pointer',
                      }}
                    />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: '500' }}>{topic}</div>
                    </div>
                  </label>
                ))
              )}
            </div>
            {selectedTopics.length > 0 && (
              <div style={{ marginTop: '0.5rem', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                {selectedTopics.length} topic{selectedTopics.length !== 1 ? 's' : ''} selected
              </div>
            )}
          </div>
        )}

        {/* Options */}
        {selectedTopics.length > 0 && (
          <>
            <div>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={includePrerequisites}
                  onChange={(e) => setIncludePrerequisites(e.target.checked)}
                />
                <span>Include prerequisite concepts</span>
              </label>
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>
                Difficulty (Optional)
              </label>
              <select
                value={difficulty}
                onChange={(e) => setDifficulty(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '1rem',
                }}
              >
                <option value="">Any difficulty</option>
                <option value="easy">Easy</option>
                <option value="medium">Medium</option>
                <option value="hard">Hard</option>
              </select>
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>
                Number of Questions
              </label>
              <input
                type="number"
                min="1"
                max="50"
                value={numQuestions}
                onChange={(e) => setNumQuestions(parseInt(e.target.value) || 10)}
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '1rem',
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>
                Time Limit (minutes, optional)
              </label>
              <input
                type="number"
                min="1"
                value={timeLimit}
                onChange={(e) => setTimeLimit(e.target.value)}
                placeholder="No time limit"
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '1rem',
                }}
              />
            </div>

            <button
              onClick={handleGenerate}
              disabled={loading}
              className="btn-primary"
              style={{ width: '100%', marginTop: '1rem' }}
            >
              {loading ? 'Generating...' : 'Generate Test'}
            </button>
          </>
        )}
      </div>
    </div>
  )
}
