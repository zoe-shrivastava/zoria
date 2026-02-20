import { useState, useEffect, useMemo } from 'react'
import Header from '../components/Header'
import DocumentUpload from '../components/DocumentUpload'
import DocumentList from '../components/DocumentList'
import CreateChild from '../components/CreateChild'
import EditChild from '../components/EditChild'
import TestLauncher from '../components/TestLauncher'
import TestList from '../components/TestList'
import TestListGrouped from '../components/TestListGrouped'
import QuizPlayer from '../components/QuizPlayer'
import EvaluationReport from '../components/EvaluationReport'
import LearningWorkspace from '../components/LearningWorkspace'
import { children, documents, child, isAuthError } from '../services/api'
import { showNotification } from '../utils/notifications'

// Language options for child portal (later can be driven by profile preferences)
const CHILD_LANGUAGE_OPTIONS = [
  { value: 'English', label: 'English' },
  { value: 'French', label: 'French' },
  { value: 'Hindi', label: 'Hindi' },
  { value: 'Spanish', label: 'Spanish' },
]

const CHILD_LANGUAGE_STORAGE_KEY = 'zoria_child_language'

export default function Dashboard({ user, onLogout, isAdmin, onNavigateToAdmin }) {
  const isParent = user?.role === 'parent'
  const isChild = user?.role === 'child'
  const [childList, setChildList] = useState([])
  const [selectedChild, setSelectedChild] = useState(null)
  const [childProfile, setChildProfile] = useState(null)
  const [childPreferredLanguage, setChildPreferredLanguage] = useState(() => {
    if (typeof window === 'undefined') return 'English'
    return window.localStorage.getItem(CHILD_LANGUAGE_STORAGE_KEY) || 'English'
  })
  const [loading, setLoading] = useState(true)
  const [showCreateChild, setShowCreateChild] = useState(false)
  const [editingChild, setEditingChild] = useState(null)
  const [deletingChild, setDeletingChild] = useState(null)
  const [activeTab, setActiveTab] = useState('overview')
  const [documentCount, setDocumentCount] = useState(0)
  const [testCount, setTestCount] = useState(0)
  const [selectedTest, setSelectedTest] = useState(null)
  const [testStatusFilter, setTestStatusFilter] = useState(null)
  const [documentListRefreshKey, setDocumentListRefreshKey] = useState(0)
  const [testListRefreshKey, setTestListRefreshKey] = useState(0)
  const [viewingReport, setViewingReport] = useState(false)
  const [reportChildId, setReportChildId] = useState(null)

  // Language options: parent view gets full list; child gets full list (selection is session-only, does not update profile)
  const childLanguageOptions = useMemo(() => {
    return CHILD_LANGUAGE_OPTIONS
  }, [])

  useEffect(() => {
    if (isParent || isAdmin) {
      loadChildren()
    } else if (isChild) {
      loadChildProfile()
    } else {
      setLoading(false)
    }
  }, [isParent, isChild, isAdmin])

  // Refetch child profile when switching to My Profile tab so parent-updated data is shown
  useEffect(() => {
    if (isChild && activeTab === 'profile' && childProfile?.id) {
      child.getProfile()
        .then((profile) => setChildProfile(profile))
        .catch(() => {})
    }
  }, [isChild, activeTab])

  useEffect(() => {
    if (activeTab === 'overview' || activeTab === 'documents') {
      if (isParent || isChild || isAdmin) {
        loadDocumentCount()
      }
    }
    if (activeTab === 'tests' && (isParent || isChild || isAdmin)) {
      loadTestCount()
    }
  }, [activeTab, selectedChild, isParent, isChild, isAdmin, childList.length])

  const loadChildProfile = async () => {
    try {
      setLoading(true)
      const profile = await child.getProfile()
      setChildProfile(profile)
      setSelectedChild(profile.id) // Set selected child to their own ID for documents
      // Default language from profile; child can change to English or back to profile language
      const profileLang = profile.preferred_language || ''
      const defaultLang = profileLang || (typeof window !== 'undefined' ? window.localStorage.getItem(CHILD_LANGUAGE_STORAGE_KEY) : null) || 'English'
      setChildPreferredLanguage(defaultLang)
      if (typeof window !== 'undefined' && defaultLang) {
        try { window.localStorage.setItem(CHILD_LANGUAGE_STORAGE_KEY, defaultLang) } catch (_) {}
      }
      // Load document count and test count
      if (profile.id) {
        const docData = await documents.list(profile.id)
        setDocumentCount(Array.isArray(docData) ? docData.length : (docData.total || 0))
        // Load test count with profile.id directly since state update is async
        loadTestCount(profile.id)
      }
    } catch (error) {
      if (!isAuthError(error)) {
        showNotification(error.message || 'Failed to load profile', 'error')
      }
    } finally {
      setLoading(false)
    }
  }

  const loadChildren = async () => {
    try {
      setLoading(true)
      let data
      if (isAdmin) {
        // Admin uses admin API to get all children
        const { admin } = await import('../services/api')
        data = await admin.listChildren()
      } else {
        // Parent uses parent API
        data = await children.list()
      }
      const childrenList = Array.isArray(data) ? data : []
      setChildList(childrenList)
      // Don't auto-select child for admins - they should see grouped view by default
      if (childrenList.length > 0 && !selectedChild && !isAdmin) {
        setSelectedChild(childrenList[0].id)
      }
    } catch (error) {
      if (!isAuthError(error)) {
        showNotification(error.message || 'Failed to load children', 'error')
      }
    } finally {
      setLoading(false)
    }
  }

  const loadDocumentCount = async () => {
    try {
      if (isAdmin) {
        // For admin, count all documents
        const { admin } = await import('../services/api')
        const docData = await admin.listDocuments({ limit: 1000 })
        const docArray = Array.isArray(docData) ? docData : (docData.documents || [])
        setDocumentCount(docArray.length)
      } else if (isChild) {
        // For child users, count their own documents
        const childId = childProfile?.id || user?.id
        if (childId) {
          const docData = await documents.list(childId)
          setDocumentCount(Array.isArray(docData) ? docData.length : (docData.total || 0))
        }
      } else if (isParent) {
        // For parents, count documents across ALL children
        let totalCount = 0
        for (const child of childList) {
          try {
            const docData = await documents.list(child.id)
            const count = Array.isArray(docData) ? docData.length : (docData.total || 0)
            totalCount += count
          } catch (err) {
            console.error(`Failed to load documents for child ${child.id}:`, err)
          }
        }
        setDocumentCount(totalCount)
      }
    } catch (error) {
      if (!isAuthError(error)) {
        console.error('Failed to load document count:', error)
      }
    }
  }

  const loadTestCount = async (childIdOverride = null) => {
    try {
      if (isChild) {
        // For child users, count their own tests
        const childId = childIdOverride || childProfile?.id || user?.id
        if (childId) {
          const { tests } = await import('../services/api')
          const testData = await tests.list(childId)
          const testsArray = Array.isArray(testData.tests) ? testData.tests : []
          setTestCount(testsArray.length)
        }
      } else if (isAdmin) {
        const { tests } = await import('../services/api')
        const grouped = await tests.listAllGrouped()
        const groups = grouped && typeof grouped === 'object' ? Object.values(grouped) : []
        const total = groups.reduce((sum, g) => sum + (Array.isArray(g?.tests) ? g.tests.length : (g?.total || 0)), 0)
        setTestCount(total)
      } else if (isParent && childList.length > 0) {
        const { tests } = await import('../services/api')
        let totalCount = 0
        for (const ch of childList) {
          try {
            const testData = await tests.list(ch.id)
            const arr = Array.isArray(testData.tests) ? testData.tests : []
            totalCount += arr.length
          } catch (err) {
            console.error(`Failed to load tests for child ${ch.id}:`, err)
          }
        }
        setTestCount(totalCount)
      }
    } catch (error) {
      if (!isAuthError(error)) {
        console.error('Failed to load test count:', error)
      }
    }
  }

  const handleChildCreated = () => {
    setShowCreateChild(false)
    loadChildren()
  }

  const handleChildUpdated = (updatedChild) => {
    if (updatedChild && updatedChild.id) {
      setChildList((prev) =>
        prev.map((c) => (c.id === updatedChild.id ? { ...c, ...updatedChild } : c))
      )
    }
    setEditingChild(null)
    loadChildren()
  }

  const handleDeleteChild = async (childId, childName) => {
    if (!window.confirm(`Are you sure you want to delete ${childName}? This action cannot be undone.`)) {
      return
    }
    
    try {
      await children.delete(childId)
      showNotification('Child profile deleted successfully', 'success')
      loadChildren()
      // Clear selected child if it was deleted
      if (selectedChild === childId) {
        setSelectedChild(null)
      }
    } catch (error) {
      showNotification(error.message || 'Failed to delete child profile', 'error')
    }
  }

  const handleUploadComplete = () => {
    loadDocumentCount()
    // Trigger DocumentList refresh by updating the key
    setDocumentListRefreshKey(prev => prev + 1)
  }

  const handleTestListRefresh = () => {
    if (isChild || isParent || isAdmin) {
      loadTestCount()
    }
    setTestListRefreshKey(prev => prev + 1)
  }

  // Admin dashboard with documents access
  if (isAdmin) {
    if (loading) {
      return (
        <div className="dashboard">
          <Header user={user} onLogout={onLogout} userProfile={user} />
          <div className="dashboard-content">
            <p className="loading-text">Loading...</p>
          </div>
        </div>
      )
    }

    const adminTabs = [
      { id: 'overview', label: 'Overview' },
      { id: 'children', label: 'Children', badge: childList.length || null },
      { id: 'documents', label: 'Documents', badge: documentCount || null },
      { id: 'tests', label: 'Tests' },
    ]
    
    return (
      <div className="dashboard">
        <Header 
          user={user} 
          onLogout={onLogout} 
          tabs={adminTabs}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          userProfile={user}
        />
        <div className="dashboard-content">
          <div style={{ marginBottom: '1rem', display: 'flex', gap: '0.5rem' }}>
            <button onClick={onNavigateToAdmin} className="btn-secondary">
              Admin Settings
            </button>
          </div>
          
          <div className="tab-content">
            {activeTab === 'overview' && (
              <div className="dashboard-section">
                <h2>Admin Dashboard</h2>
                <p style={{ color: 'var(--text-muted)', marginTop: '0.5rem' }}>
                  Welcome to Zoria Admin! Manage children, documents, and tests.
                </p>
                <div className="overview-grid" style={{ marginTop: '2rem' }}>
                  <div className="stat-card">
                    <div className="stat-value">{childList.length}</div>
                    <div className="stat-label">Children</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-value">{documentCount}</div>
                    <div className="stat-label">Documents</div>
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'children' && (
              <div className="dashboard-section">
                <h2>All Children</h2>
                {childList.length === 0 ? (
                  <div className="empty-state">
                    <p>No children found.</p>
                  </div>
                ) : (
                  <div className="child-list">
                    {childList.map((child) => (
                      <div
                        key={child.id}
                        className={`child-item ${selectedChild === child.id ? 'active' : ''}`}
                      >
                        <div 
                          className="child-item-content"
                          onClick={() => setSelectedChild(child.id)}
                        >
                          {child.avatar_url && (
                            <div className="child-avatar">
                              <img src={child.avatar_url} alt={child.name} />
                            </div>
                          )}
                          <div className="child-info">
                            <div className="child-name">{child.name}</div>
                            <div className="child-meta">
                              {child.grade && `Grade: ${child.grade}`}
                              {child.age && ` • Age: ${child.age}`}
                            </div>
                          </div>
                        </div>
                        <div className="child-id-section">
                          <div className="child-id-label">Child ID:</div>
                          <div className="child-id-value">{child.child_code || child.id}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
            
            {activeTab === 'documents' && (
              <div className="dashboard-section">
                <h2>All Documents</h2>
                <DocumentList childId={null} userRole="admin" />
              </div>
            )}

            {activeTab === 'tests' && (
              <div className="dashboard-section">
                {selectedTest ? (
                  <div>
                    <button
                      onClick={() => setSelectedTest(null)}
                      className="btn-secondary"
                      style={{ marginBottom: '1rem' }}
                    >
                      ← Back to Tests
                    </button>
                    <QuizPlayer
                      testId={selectedTest.id}
                      readOnly={true}
                      isAdmin={isAdmin}
                      onViewReport={(childId) => {
                        setSelectedChild(childId)
                        setActiveTab('reports')
                        setSelectedTest(null)
                      }}
                    />
                  </div>
                ) : (
                  <>
                    <h2>Tests</h2>
                    {isAdmin && !selectedChild && childList.length > 0 ? (
                      <>
                        <div style={{ 
                          marginBottom: '2rem', 
                          padding: '1rem', 
                          background: 'var(--bg-tertiary)', 
                          borderRadius: 'var(--radius-md)',
                          border: '1px solid var(--border-color)'
                        }}>
                          <p style={{ color: 'var(--text-muted)', margin: 0 }}>
                            <strong>Admin View:</strong> All tests grouped by child for easy management.
                          </p>
                        </div>
                        <div style={{ marginTop: '2rem' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                            <h3>All Tests by Child</h3>
                            <div style={{ display: 'flex', gap: '0.5rem' }}>
                              <button
                                onClick={() => setTestStatusFilter(null)}
                                className={testStatusFilter === null ? 'btn-primary' : 'btn-secondary'}
                                style={{ fontSize: '0.875rem' }}
                              >
                                All
                              </button>
                              <button
                                onClick={() => setTestStatusFilter('active')}
                                className={testStatusFilter === 'active' ? 'btn-primary' : 'btn-secondary'}
                                style={{ fontSize: '0.875rem' }}
                              >
                                Active
                              </button>
                              <button
                                onClick={() => setTestStatusFilter('completed')}
                                className={testStatusFilter === 'completed' ? 'btn-primary' : 'btn-secondary'}
                                style={{ fontSize: '0.875rem' }}
                              >
                                Completed
                              </button>
                            </div>
                          </div>
                          <TestListGrouped
                            statusFilter={testStatusFilter}
                            onTestSelect={(test) => setSelectedTest(test)}
                            isAdmin={isAdmin}
                            refreshKey={testListRefreshKey}
                            onTestDeleted={(testId) => {
                              if (selectedTest && selectedTest.id === testId) {
                                setSelectedTest(null)
                              }
                            }}
                          />
                        </div>
                      </>
                    ) : !selectedChild && childList.length > 0 && !isAdmin ? (
                      <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>
                        Please select a child to view or generate tests.
                      </p>
                    ) : selectedChild ? (
                      <>
                        {!isAdmin && !isParent && (
                          <div style={{ marginBottom: '2rem' }}>
                            <TestLauncher
                              childId={selectedChild}
                              userRole={user?.role}
                              onTestGenerated={(test) => {
                                setSelectedTest(test)
                                showNotification('Test generated!', 'success')
                              }}
                            />
                          </div>
                        )}
                        {isParent && (
                          <div style={{
                            marginBottom: '1rem',
                            padding: '1rem',
                            background: 'var(--bg-tertiary)',
                            borderRadius: 'var(--radius-md)',
                            border: '1px solid var(--border-color)'
                          }}>
                            <p style={{ color: 'var(--text-muted)', margin: 0 }}>
                              You can view all tests and evaluation reports (including cards). Only children can generate new tests or take tests.
                            </p>
                          </div>
                        )}
                        {isAdmin && (
                          <>
                            <div style={{ 
                              marginBottom: '1rem', 
                              padding: '1rem', 
                              background: 'var(--bg-tertiary)', 
                              borderRadius: 'var(--radius-md)',
                              border: '1px solid var(--border-color)'
                            }}>
                              <p style={{ color: 'var(--text-muted)', margin: 0 }}>
                                <strong>Admin Note:</strong> Admins can view and delete tests, but cannot generate new tests. 
                                Only children can generate and take tests.
                              </p>
                            </div>
                            <div style={{ marginBottom: '1rem' }}>
                              <button
                                onClick={() => setSelectedChild(null)}
                                className="btn-secondary"
                                style={{ fontSize: '0.875rem' }}
                              >
                                ← View All Tests (Grouped by Child)
                              </button>
                            </div>
                          </>
                        )}
                        <div style={{ marginTop: '2rem' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                            <h3>Test History</h3>
                            <div style={{ display: 'flex', gap: '0.5rem' }}>
                              <button
                                onClick={() => setTestStatusFilter(null)}
                                className={testStatusFilter === null ? 'btn-primary' : 'btn-secondary'}
                                style={{ fontSize: '0.875rem' }}
                              >
                                All
                              </button>
                              <button
                                onClick={() => setTestStatusFilter('active')}
                                className={testStatusFilter === 'active' ? 'btn-primary' : 'btn-secondary'}
                                style={{ fontSize: '0.875rem' }}
                              >
                                Active
                              </button>
                              <button
                                onClick={() => setTestStatusFilter('completed')}
                                className={testStatusFilter === 'completed' ? 'btn-primary' : 'btn-secondary'}
                                style={{ fontSize: '0.875rem' }}
                              >
                                Completed
                              </button>
                            </div>
                          </div>
                          <TestList
                            childId={selectedChild}
                            statusFilter={testStatusFilter}
                            onTestSelect={(test) => setSelectedTest(test)}
                            isAdmin={isAdmin}
                            userRole={user?.role}
                            refreshKey={testListRefreshKey}
                            onTestDeleted={(testId) => {
                              if (selectedTest && selectedTest.id === testId) {
                                setSelectedTest(null)
                              }
                            }}
                          />
                        </div>
                      </>
                    ) : childList.length === 0 ? (
                      <div className="empty-state">
                        <p>No children found. Tests can be generated once children are created.</p>
                      </div>
                    ) : (
                      <div className="empty-state">
                        <p>Select a child from the Children tab to view or generate tests.</p>
                      </div>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    )
  }

  // Child dashboard with profile and documents
  if (isChild) {
    // Child language dropdown is session-only: do NOT update profile (parent sets profile language).
    const handleChildLanguageChange = (value) => {
      setChildPreferredLanguage(value)
      try {
        window.localStorage.setItem(CHILD_LANGUAGE_STORAGE_KEY, value)
      } catch (_) {}
    }

    if (loading) {
      return (
        <div className="dashboard">
          <Header
            user={user}
            onLogout={onLogout}
            userProfile={user}
            tabs={[{ id: 'profile', label: 'My Profile' }, { id: 'documents', label: 'My Documents' }, { id: 'tests', label: 'Tests' }, { id: 'reports', label: 'Reports' }]}
            activeTab="profile"
            selectedLanguage={childPreferredLanguage}
            onLanguageChange={handleChildLanguageChange}
            languageOptions={childLanguageOptions}
          />
          <div className="dashboard-content">
            <p className="loading-text">Loading...</p>
          </div>
        </div>
      )
    }

    const childTabs = [
      { id: 'profile', label: 'My Profile' },
      { id: 'documents', label: 'My Documents', badge: documentCount || null },
      { id: 'tests', label: 'Tests', badge: testCount || null },
      { id: 'reports', label: 'Reports' },
    ]

    return (
      <div className="dashboard">
        <Header 
          user={user} 
          onLogout={onLogout}
          tabs={childTabs}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          userProfile={childProfile || user}
          selectedLanguage={childPreferredLanguage}
          onLanguageChange={handleChildLanguageChange}
          languageOptions={childLanguageOptions}
        />
        <div className="dashboard-content">

          <div className="tab-content">
            {activeTab === 'profile' && childProfile && (
              <div className="dashboard-section">
                <h2>My Profile</h2>
                <div className="child-profile-card" style={{
                  background: 'var(--bg-tertiary)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-md)',
                  padding: '1.5rem',
                  marginTop: '1rem'
                }}>
                  {childProfile.avatar_url && (
                    <div className="child-avatar" style={{ marginBottom: '1rem', width: '80px', height: '80px' }}>
                      <img src={childProfile.avatar_url} alt={childProfile.name} />
                    </div>
                  )}
                  <div className="profile-info">
                    <div style={{ marginBottom: '1rem' }}>
                      <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Name</div>
                      <div style={{ fontSize: '1.25rem', fontWeight: '600', color: 'var(--text-primary)' }}>
                        {childProfile.name}
                      </div>
                    </div>
                    {childProfile.child_code && (
                      <div style={{ marginBottom: '1rem' }}>
                        <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Child ID</div>
                        <div style={{ fontFamily: 'monospace', fontSize: '1rem', color: 'var(--text-primary)' }}>
                          {childProfile.child_code}
                        </div>
                      </div>
                    )}
                    {childProfile.grade && (
                      <div style={{ marginBottom: '1rem' }}>
                        <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Grade</div>
                        <div style={{ fontSize: '1rem', color: 'var(--text-primary)' }}>{childProfile.grade}</div>
                      </div>
                    )}
                    {childProfile.age && (
                      <div style={{ marginBottom: '1rem' }}>
                        <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Age</div>
                        <div style={{ fontSize: '1rem', color: 'var(--text-primary)' }}>{childProfile.age} years old</div>
                      </div>
                    )}
                    {(childProfile.preferred_language || childProfile.interaction_tone || childProfile.example_preferences || childProfile.interests || childProfile.sensitive_topics_to_avoid != null || childProfile.prefer_indirect_guidance) && (
                      <div style={{ marginTop: '1.25rem', paddingTop: '1rem', borderTop: '1px solid var(--border-color)' }}>
                        <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.5rem', fontWeight: '600' }}>Study preferences</div>
                        {childProfile.preferred_language && (
                          <div style={{ marginBottom: '0.5rem' }}>
                            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Language: </span>
                            <span style={{ fontSize: '0.95rem', color: 'var(--text-primary)' }}>{childProfile.preferred_language}</span>
                          </div>
                        )}
                        {childProfile.interaction_tone && (
                          <div style={{ marginBottom: '0.5rem' }}>
                            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Tone: </span>
                            <span style={{ fontSize: '0.95rem', color: 'var(--text-primary)' }}>{childProfile.interaction_tone}</span>
                          </div>
                        )}
                        {childProfile.example_preferences && (
                          <div style={{ marginBottom: '0.5rem' }}>
                            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Example style: </span>
                            <span style={{ fontSize: '0.95rem', color: 'var(--text-primary)' }}>{childProfile.example_preferences}</span>
                          </div>
                        )}
                        {childProfile.interests && (
                          <div style={{ marginBottom: '0.5rem' }}>
                            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Interests: </span>
                            <span style={{ fontSize: '0.95rem', color: 'var(--text-primary)' }}>{childProfile.interests}</span>
                          </div>
                        )}
                        {childProfile.sensitive_topics_to_avoid != null && childProfile.sensitive_topics_to_avoid !== '' && (
                          <div style={{ marginBottom: '0.5rem' }}>
                            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Topics to avoid: </span>
                            <span style={{ fontSize: '0.95rem', color: 'var(--text-primary)' }}>{childProfile.sensitive_topics_to_avoid}</span>
                          </div>
                        )}
                        {childProfile.prefer_indirect_guidance && (
                          <div style={{ marginBottom: '0.5rem' }}>
                            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Prefer indirect guidance for emotional topics</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'documents' && (
              <div className="dashboard-section">
                <h2>My Documents</h2>
                {childProfile && (
                  <>
                    <DocumentUpload
                      childId={childProfile.id}
                      childList={[]}
                      onUploadComplete={handleUploadComplete}
                    />
                    <div style={{ marginTop: '2rem' }}>
                      <DocumentList 
                        refreshKey={documentListRefreshKey}
                        childId={childProfile.id} 
                        isChild={true} 
                        userRole={user?.role} 
                      />
                    </div>
                  </>
                )}
              </div>
            )}

            {activeTab === 'reports' && (
              <div className="dashboard-section" style={{ padding: 0, height: '100vh', overflow: 'hidden' }}>
                {childProfile ? (
                  <LearningWorkspace
                  childId={childProfile.id}
                  daysBack={30}
                  showAllGuides={true}
                  user={user}
                  preferredLanguage={childPreferredLanguage}
                  onOpenTest={(testId) => {
                    setActiveTab('tests')
                    setSelectedTest({ id: testId })
                  }}
                />
                ) : (
                  <div className="empty-state">
                    <p>Loading profile...</p>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'tests' && (
              <div className="dashboard-section">
                {selectedTest ? (
                  <div>
                    <button
                      onClick={() => setSelectedTest(null)}
                      className="btn-secondary"
                      style={{ marginBottom: '1rem' }}
                    >
                      ← Back to Tests
                    </button>
                    <QuizPlayer
                      testId={selectedTest.id}
                      readOnly={selectedTest.status === 'completed'}
                      isAdmin={isAdmin}
                      onComplete={(result) => {
                        setSelectedTest(null)
                        showNotification(`Test completed! Score: ${result.percentage.toFixed(1)}%`, 'success')
                      }}
                      onViewReport={() => {
                        setActiveTab('reports')
                        setSelectedTest(null)
                      }}
                    />
                  </div>
                ) : (
                  <>
                    <h2>My Tests</h2>
                    {childProfile && (
                      <>
                        <div style={{ marginBottom: '2rem' }}>
                          <TestLauncher
                            childId={childProfile.id}
                            userRole={user?.role}
                            preferredLanguage={childPreferredLanguage}
                            onTestGenerated={(test) => {
                              // Don't auto-open test - just show notification
                              // Test will appear in list with "Processing" status
                              showNotification('Test generation started! It will appear in the list when ready.', 'success')
                              // Refresh test list after a short delay to show the new test
                              setTimeout(() => {
                                handleTestListRefresh()
                              }, 1000)
                            }}
                          />
                        </div>
                        <div style={{ marginTop: '2rem' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                            <h3>Test History</h3>
                            <div style={{ display: 'flex', gap: '0.5rem' }}>
                              <button
                                onClick={() => setTestStatusFilter(null)}
                                className={testStatusFilter === null ? 'btn-primary' : 'btn-secondary'}
                                style={{ fontSize: '0.875rem' }}
                              >
                                All
                              </button>
                              <button
                                onClick={() => setTestStatusFilter('active')}
                                className={testStatusFilter === 'active' ? 'btn-primary' : 'btn-secondary'}
                                style={{ fontSize: '0.875rem' }}
                              >
                                Active
                              </button>
                              <button
                                onClick={() => setTestStatusFilter('completed')}
                                className={testStatusFilter === 'completed' ? 'btn-primary' : 'btn-secondary'}
                                style={{ fontSize: '0.875rem' }}
                              >
                                Completed
                              </button>
                            </div>
                          </div>
                          <TestList
                            childId={childProfile.id}
                            statusFilter={testStatusFilter}
                            onTestSelect={(test) => setSelectedTest(test)}
                            isAdmin={isAdmin}
                            userRole={user?.role}
                            refreshKey={testListRefreshKey}
                            onTestDeleted={(testId) => {
                              if (selectedTest && selectedTest.id === testId) {
                                setSelectedTest(null)
                              }
                              handleTestListRefresh()
                            }}
                          />
                        </div>
                      </>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    )
  }

  // Parent dashboard with tabs
  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'children', label: 'Children', badge: childList.length || null },
    { id: 'documents', label: 'Documents', badge: documentCount || null },
    { id: 'tests', label: 'Tests', badge: testCount || null },
    { id: 'reports', label: 'Reports' },
  ]

  if (loading) {
    return (
      <div className="dashboard">
        <Header user={user} onLogout={onLogout} />
        <div className="dashboard-content">
          <p className="loading-text">Loading...</p>
        </div>
      </div>
    )
  }

  // Parent dashboard with tabs - ensure tabs are always shown
  return (
    <div className="dashboard">
      <Header
        user={user} 
        onLogout={onLogout}
        tabs={tabs}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        userProfile={user}
      />
      <div className="dashboard-content">

        {/* Shared child selector for Documents, Tests, and Reports */}
        {['documents', 'tests', 'reports'].includes(activeTab) && (isParent || isAdmin) && childList.length > 0 && (
          <div style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '0.5rem',
            alignItems: 'center',
            marginBottom: '1rem',
            padding: '0.75rem',
            background: 'var(--bg-secondary)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border-color)'
          }}>
            <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginRight: '0.25rem' }}>Select child:</span>
            {childList.map((child) => (
              <button
                key={child.id}
                type="button"
                onClick={() => setSelectedChild(child.id)}
                className={selectedChild === child.id ? 'btn-primary' : 'btn-secondary'}
                style={{ fontSize: '0.875rem', padding: '0.5rem 1rem' }}
              >
                {child.name}
              </button>
            ))}
          </div>
        )}

        <div className="tab-content">
          {activeTab === 'overview' && (
            <div className="dashboard-section">
              <h2>Overview</h2>
              <div className="overview-grid">
                <div className="stat-card">
                  {/* <div className="stat-icon">👶</div> */}
                  <div className="stat-value">{childList.length}</div>
                  <div className="stat-label">Children</div>
                </div>
                <div className="stat-card">
                  {/* <div className="stat-icon">📄</div> */}
                  <div className="stat-value">{documentCount}</div>
                  <div className="stat-label">Documents</div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'children' && (
            <div className="dashboard-section">
              <h2>Children</h2>
              {showCreateChild ? (
                <CreateChild
                  onChildCreated={handleChildCreated}
                  onCancel={() => setShowCreateChild(false)}
                />
              ) : editingChild ? (
                <EditChild
                  child={editingChild}
                  onChildUpdated={handleChildUpdated}
                  onCancel={() => setEditingChild(null)}
                />
              ) : (
                <>
                  <button
                    onClick={() => setShowCreateChild(true)}
                    className="btn-primary"
                    style={{ marginBottom: '1.5rem', width: 'auto' }}
                  >
                    + Create Child Profile
                  </button>
                  {childList.length === 0 ? (
                    <div className="empty-state">
                      <p>No children created yet.</p>
                      <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
                        Create a child profile to get started.
                      </p>
                    </div>
                  ) : (
                    <div className="child-list">
                      {childList.map((child) => (
                        <div
                          key={child.id}
                          className={`child-item ${selectedChild === child.id ? 'active' : ''}`}
                        >
                          <div 
                            className="child-item-content"
                            onClick={() => setSelectedChild(child.id)}
                          >
                            {child.avatar_url && (
                              <div className="child-avatar">
                                <img src={child.avatar_url} alt={child.name} />
                              </div>
                            )}
                            <div className="child-info">
                              <div className="child-name">{child.name}</div>
                              <div className="child-meta">
                                {child.grade && `Grade: ${child.grade}`}
                                {child.age && ` • Age: ${child.age}`}
                              </div>
                            </div>
                          </div>
                          <div className="child-id-section">
                            <div className="child-id-label">Child ID:</div>
                            <div className="child-id-value">{child.child_code || child.id}</div>
                            <button
                              type="button"
                              className="btn-copy-id"
                              onClick={(e) => {
                                e.stopPropagation()
                                const codeToCopy = child.child_code || child.id
                                navigator.clipboard.writeText(codeToCopy)
                                showNotification('Child ID copied to clipboard!', 'success')
                              }}
                              title="Copy Child ID"
                            >
                              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                              </svg>
                            </button>
                          </div>
                          <div className="child-actions">
                            <button
                              type="button"
                              className="btn-edit-child"
                              onClick={(e) => {
                                e.stopPropagation()
                                setEditingChild(child)
                              }}
                              title="Edit Child"
                            >
                              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                              </svg>
                            </button>
                            <button
                              type="button"
                              className="btn-delete-child"
                              onClick={(e) => {
                                e.stopPropagation()
                                handleDeleteChild(child.id, child.name)
                              }}
                              title="Delete Child"
                            >
                              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <polyline points="3 6 5 6 21 6"/>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                              </svg>
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {activeTab === 'documents' && (
            <div className="dashboard-section">
              <h2>Documents</h2>
              {!selectedChild && childList.length > 0 && (
                <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>
                  Please select a child above to upload or view documents.
                </p>
              )}
              {selectedChild ? (
                <>
                  <DocumentUpload
                    childId={selectedChild}
                    childList={childList}
                    onUploadComplete={handleUploadComplete}
                  />
                  <div style={{ marginTop: '2rem' }}>
                    <DocumentList 
                      refreshKey={documentListRefreshKey}
                      childId={selectedChild} 
                      userRole={user?.role} 
                    />
                  </div>
                </>
              ) : childList.length === 0 ? (
                <div className="empty-state">
                  <p>Create a child profile first to upload documents.</p>
                </div>
              ) : null}
            </div>
          )}

          {activeTab === 'reports' && (
            <div className="dashboard-section" style={{ padding: 0, height: '100vh', overflow: 'hidden' }}>
              {!selectedChild && childList.length > 0 && (
                <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>
                  Please select a child above to view their evaluation report and study guides.
                </p>
              )}
              {selectedChild ? (
                <>
                  {(isParent || isAdmin) && (
                    <p style={{ marginBottom: '0.5rem', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                      Viewing: <strong style={{ color: 'var(--text-primary)' }}>{childList.find(c => c.id === selectedChild)?.name || 'Child'}</strong>
                    </p>
                  )}
                  <LearningWorkspace
                    childId={selectedChild}
                    daysBack={30}
                    showAllGuides={true}
                    user={user}
                    preferredLanguage={null}
                    onOpenTest={(testId) => {
                      setActiveTab('tests')
                      setSelectedTest({ id: testId })
                    }}
                  />
                </>
              ) : childList.length === 0 ? (
                <div className="empty-state">
                  <p>Create a child profile first to view evaluation reports.</p>
                </div>
              ) : null}
            </div>
          )}

          {activeTab === 'tests' && (
            <div className="dashboard-section">
              {selectedTest ? (
                <div>
                  <button
                    onClick={() => setSelectedTest(null)}
                    className="btn-secondary"
                    style={{ marginBottom: '1rem' }}
                  >
                    ← Back to Tests
                  </button>
                  {(isParent || isAdmin) && (
                    <p style={{ marginBottom: '0.5rem', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                      Viewing test for: <strong style={{ color: 'var(--text-primary)' }}>{childList.find(c => c.id === selectedChild)?.name || 'Child'}</strong>
                    </p>
                  )}
                  <QuizPlayer
                    testId={selectedTest.id}
                    readOnly={true}
                    isAdmin={isAdmin}
                  />
                </div>
              ) : (
                <>
                  <h2>Tests</h2>
                  {!selectedChild && childList.length > 0 && (
                    <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>
                      Please select a child above to view their tests.
                    </p>
                  )}
                  {selectedChild ? (
                    <>
                      {(isParent || isAdmin) && (
                        <p style={{ marginBottom: '0.5rem', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                          Viewing: <strong style={{ color: 'var(--text-primary)' }}>{childList.find(c => c.id === selectedChild)?.name || 'Child'}</strong>
                        </p>
                      )}
                      {isParent && (
                        <div style={{
                          marginBottom: '1rem',
                          padding: '1rem',
                          background: 'var(--bg-tertiary)',
                          borderRadius: 'var(--radius-md)',
                          border: '1px solid var(--border-color)'
                        }}>
                          <p style={{ color: 'var(--text-muted)', margin: 0 }}>
                            You can view all tests and evaluation reports (including cards). Only children can generate new tests or take tests.
                          </p>
                        </div>
                      )}
                      {!isParent && (
                        <div style={{ marginBottom: '2rem' }}>
                          <TestLauncher
                            childId={selectedChild}
                            userRole={user?.role}
                            onTestGenerated={(test) => {
                              setSelectedTest(test)
                              showNotification('Test generated!', 'success')
                            }}
                          />
                        </div>
                      )}
                      <div style={{ marginTop: '2rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                          <h3>Test History</h3>
                          <div style={{ display: 'flex', gap: '0.5rem' }}>
                            <button
                              onClick={() => setTestStatusFilter(null)}
                              className={testStatusFilter === null ? 'btn-primary' : 'btn-secondary'}
                              style={{ fontSize: '0.875rem' }}
                            >
                              All
                            </button>
                            <button
                              onClick={() => setTestStatusFilter('active')}
                              className={testStatusFilter === 'active' ? 'btn-primary' : 'btn-secondary'}
                              style={{ fontSize: '0.875rem' }}
                            >
                              Active
                            </button>
                            <button
                              onClick={() => setTestStatusFilter('completed')}
                              className={testStatusFilter === 'completed' ? 'btn-primary' : 'btn-secondary'}
                              style={{ fontSize: '0.875rem' }}
                            >
                              Completed
                            </button>
                          </div>
                        </div>
                        <TestList
                          childId={selectedChild}
                          statusFilter={testStatusFilter}
                          onTestSelect={(test) => setSelectedTest(test)}
                          isAdmin={isAdmin}
                          onTestDeleted={(testId) => {
                            if (selectedTest && selectedTest.id === testId) {
                              setSelectedTest(null)
                            }
                          }}
                        />
                      </div>
                    </>
                  ) : childList.length === 0 ? (
                    <div className="empty-state">
                      <p>Create a child profile first to generate tests.</p>
                    </div>
                  ) : null}
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
