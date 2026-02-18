/**
 * API service for Zoria backend
 * Updated to match Zoria API structure: /api/v1/*
 */

const getApiBase = () => {
  // Check for explicit environment variable (highest priority)
  const envApiBase = import.meta.env.VITE_API_BASE
  console.log('🔍 Environment check:', {
    VITE_API_BASE: import.meta.env.VITE_API_BASE,
    PROD: import.meta.env.PROD,
    MODE: import.meta.env.MODE
  })

  if (envApiBase) {
    console.log('✅ Using VITE_API_BASE:', envApiBase)
    return envApiBase
  }

  // In production, use the API domain
  if (import.meta.env.PROD) {
    console.log('✅ Using production URL')
    return 'https://zoria-api.krishnabihari.com'
  }

  // Development mode - default to localhost
  console.log('✅ Using localhost URL')
  return 'http://localhost:8001'
}

export const isAuthError = (error) => {
  if (!error) return false
  const message = error.message?.toLowerCase() || ''
  return (
    error.status === 401 ||
    (message.includes('unauthorized') ||
      message.includes('token') ||
      message.includes('session'))
  )
}

async function apiRequest(endpoint, options = {}) {
  const apiBase = getApiBase()
  const url = `${apiBase}${endpoint}`
  const token = localStorage.getItem('token') || sessionStorage.getItem('token')

  console.log('🌐 API Request:', {
    apiBase,
    endpoint,
    url,
    method: options.method || 'GET',
    hasToken: !!token,
    protocol: url.startsWith('https') ? 'HTTPS ✅' : 'HTTP ⚠️'
  })

  const headers = {
    ...options.headers,
  }

  // Don't set Content-Type for FormData - browser will set it with boundary
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    })

    console.log('✅ API Response:', {
      url,
      status: response.status,
      ok: response.ok
    })

    // Handle 204 No Content (DELETE operations) - no body to parse
    if (response.status === 204) {
      return null
    }

    if (!response.ok) {
      if (response.status === 401) {
        const isLoginEndpoint = endpoint.includes('/auth/login')

        if (!isLoginEndpoint && token) {
          localStorage.removeItem('token')
          sessionStorage.removeItem('token')

          if (!window._sessionExpiredDispatched) {
            window._sessionExpiredDispatched = true
            window.dispatchEvent(new CustomEvent('session-expired'))
            setTimeout(() => {
              window._sessionExpiredDispatched = false
            }, 2000)
          }

          const error = await response.json().catch(() => ({ message: 'Session expired' }))
          const sessionError = new Error(error.message || 'Session expired')
          sessionError._isSessionExpired = true
          throw sessionError
        }
      }

      const error = await response.json().catch(() => ({
        message: `HTTP ${response.status}: ${response.statusText}`
      }))
      throw new Error(error.message || error.detail || 'Request failed')
    }

    // Parse response body
    const contentType = response.headers.get('content-type')
    if (contentType && contentType.includes('application/json')) {
      const text = await response.text()
      if (!text || text.trim() === '') {
        return null
      }
      try {
        return JSON.parse(text)
      } catch (e) {
        // If JSON parsing fails, return the text
        return text
      }
    }

    const text = await response.text()
    return text || null
  } catch (error) {
    console.error('❌ API Error:', {
      url,
      error: error.message,
      errorType: error.name,
      stack: error.stack
    })

    if (error._isSessionExpired) {
      throw error
    }
    // Provide more detailed error messages
    if (error.name === 'TypeError' && error.message.includes('fetch')) {
      const apiBase = getApiBase()
      throw new Error(`Failed to connect to backend. Please check if the server is running at ${apiBase || 'http://localhost:8001'}`)
    }
    throw new Error(error.message || 'Network error')
  }
}

/**
 * Authentication API
 */
export const auth = {
  login: (email, password, mfaCode = null) =>
    apiRequest('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({
        email,
        password,
        ...(mfaCode && { mfa_code: mfaCode })
      }),
    }),

  completeMfaSetup: (parentId, password, mfaCode) =>
    apiRequest('/api/v1/auth/mfa/complete-setup', {
      method: 'POST',
      body: JSON.stringify({
        parent_id: parentId,
        password,
        mfa_code: mfaCode
      }),
    }),

  childLogin: (childId, pin) =>
    apiRequest('/api/v1/auth/child/login', {
      method: 'POST',
      body: JSON.stringify({ child_id: childId, pin }),
    }),

  getMe: () =>
    apiRequest('/api/v1/auth/me', { method: 'GET' }),
}

/**
 * Admin API
 */
export const admin = {
  check: async () => {
    try {
      const me = await auth.getMe()
      return { is_admin: me.role === 'admin' }
    } catch {
      return { is_admin: false }
    }
  },

  createParent: (email, password, role = 'parent') =>
    apiRequest('/api/v1/admin/parents', {
      method: 'POST',
      body: JSON.stringify({ email, password, role }),
    }),

  listParents: () =>
    apiRequest('/api/v1/admin/parents', { method: 'GET' }),

  deleteParent: (parentId) =>
    apiRequest(`/api/v1/admin/parents/${parentId}`, {
      method: 'DELETE',
    }),

  // Document management
  listDocuments: (params = {}) => {
    const queryParams = new URLSearchParams()
    if (params.child_id) queryParams.append('child_id', params.child_id)
    if (params.limit) queryParams.append('limit', params.limit)
    if (params.offset) queryParams.append('offset', params.offset)
    const query = queryParams.toString()
    return apiRequest(`/api/v1/admin/documents${query ? '?' + query : ''}`, { method: 'GET' })
  },

  getDocument: (documentId) =>
    apiRequest(`/api/v1/admin/documents/${documentId}`, { method: 'GET' }),

  reprocessDocument: (documentId, cleanupExisting = true, skipPhase1 = false) =>
    apiRequest(`/api/v1/admin/documents/${documentId}/reprocess`, {
      method: 'POST',
      body: JSON.stringify({ cleanup_existing: cleanupExisting, skip_phase1: skipPhase1 }),
    }),

  getKnowledgeGraph: (documentId) =>
    apiRequest(`/api/v1/admin/documents/${documentId}/knowledge-graph`, { method: 'GET' }),

  // Children management
  listChildren: () =>
    apiRequest('/api/v1/admin/children', { method: 'GET' }),

  // LLM Logs
  listLLMLogs: (params = {}) => {
    const queryParams = new URLSearchParams()
    if (params.limit) queryParams.append('limit', params.limit)
    if (params.offset) queryParams.append('offset', params.offset)
    if (params.model) queryParams.append('model', params.model)
    if (params.call_type) queryParams.append('call_type', params.call_type)
    if (params.provider) queryParams.append('provider', params.provider)
    if (params.success !== undefined) queryParams.append('success', params.success)
    if (params.start_date) queryParams.append('start_date', params.start_date)
    if (params.end_date) queryParams.append('end_date', params.end_date)
    const query = queryParams.toString()
    return apiRequest(`/api/v1/admin/llm-logs${query ? '?' + query : ''}`, { method: 'GET' })
  },

  getLLMUsageStats: (params = {}) => {
    const queryParams = new URLSearchParams()
    if (params.model) queryParams.append('model', params.model)
    if (params.call_type) queryParams.append('call_type', params.call_type)
    if (params.start_date) queryParams.append('start_date', params.start_date)
    if (params.end_date) queryParams.append('end_date', params.end_date)
    const query = queryParams.toString()
    return apiRequest(`/api/v1/admin/llm-logs/stats${query ? '?' + query : ''}`, { method: 'GET' })
  },
}

/**
 * Children API
 */
export const children = {
  list: () =>
    apiRequest('/api/v1/parent/children', { method: 'GET' }),

  create: (data) =>
    apiRequest('/api/v1/parent/children', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  get: (childId) =>
    apiRequest(`/api/v1/parent/children/${childId}`, { method: 'GET' }),

  update: (childId, data) =>
    apiRequest(`/api/v1/parent/children/${childId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (childId) =>
    apiRequest(`/api/v1/parent/children/${childId}`, { method: 'DELETE' }),
}

/**
 * Documents API
 */
export const documents = {
  upload: async (file, childIds) => {
    const formData = new FormData()
    formData.append('file', file)

    // Support both single childId (backward compatibility) and array of childIds
    const childIdsArray = Array.isArray(childIds) ? childIds : (childIds ? [childIds] : [])

    if (childIdsArray.length > 0) {
      formData.append('child_ids', childIdsArray.join(','))
    }

    const token = localStorage.getItem('token') || sessionStorage.getItem('token')
    const apiBase = getApiBase()
    const url = `${apiBase}/api/v1/documents/upload`

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
      },
      body: formData,
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({
        message: `HTTP ${response.status}`
      }))
      throw new Error(error.message || error.detail || 'Upload failed')
    }

    return await response.json()
  },

  list: (childId, limit = 100, offset = 0) => {
    const params = new URLSearchParams()
    if (childId) params.append('child_id', childId)
    params.append('limit', limit)
    params.append('offset', offset)

    return apiRequest(`/api/v1/documents?${params}`, { method: 'GET' })
  },

  get: (documentId) =>
    apiRequest(`/api/v1/documents/${documentId}`, { method: 'GET' }),

  delete: (documentId) =>
    apiRequest(`/api/v1/documents/${documentId}`, { method: 'DELETE' }),

  reprocess: async (documentId, cleanupExisting = true, skipPhase1 = false) => {
    return apiRequest(`/api/v1/documents/${documentId}/reprocess`, {
      method: 'POST',
      body: JSON.stringify({
        cleanup_existing: cleanupExisting,
        skip_phase1: skipPhase1
      }),
    })
  },
}

/**
 * Tests API
 */
export const tests = {
  // Get all tests grouped by child (admin only)
  listAllGrouped: async (statusFilter = null) => {
    const params = statusFilter ? `?status=${statusFilter}` : ''
    return apiRequest(`/api/v1/tests/admin/all-grouped${params}`)
  },
  getSubjectsTopics: (childId) =>
    apiRequest(`/api/v1/tests/subjects-topics/${childId}`, { method: 'GET' }),

  generate: (data) =>
    apiRequest('/api/v1/tests/generate', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  get: (testId) =>
    apiRequest(`/api/v1/tests/${testId}`, { method: 'GET' }),

  list: (childId, status = null) => {
    const params = new URLSearchParams()
    if (status) params.append('status', status)
    const query = params.toString()
    return apiRequest(`/api/v1/tests/child/${childId}/list${query ? '?' + query : ''}`, { method: 'GET' })
  },

  start: (testId) =>
    apiRequest(`/api/v1/tests/${testId}/start`, {
      method: 'POST',
    }),

  answer: (testId, questionId, answer, timeSpentSeconds = null, behavioralData = null) =>
    apiRequest(`/api/v1/tests/${testId}/answer`, {
      method: 'POST',
      body: JSON.stringify({
        question_id: questionId,
        answer,
        time_spent_seconds: timeSpentSeconds,
        behavioral_data: behavioralData,
      }),
    }),

  submit: (testId) =>
    apiRequest(`/api/v1/tests/${testId}/submit`, {
      method: 'POST',
    }),

  delete: (testId) =>
    apiRequest(`/api/v1/tests/${testId}`, {
      method: 'DELETE',
    }),

  // Admin-only methods
  reevaluate: (testId) =>
    apiRequest(`/api/v1/admin/tests/${testId}/reevaluate`, {
      method: 'POST',
    }),

  reopen: (testId) =>
    apiRequest(`/api/v1/admin/tests/${testId}/reopen`, {
      method: 'POST',
    }),

  // Evaluation reports and study guides
  getEvaluationReport: (childId, daysBack = 30, generateGuides = true, language = null) => {
    const params = new URLSearchParams()
    params.append('days_back', daysBack)
    params.append('generate_guides', generateGuides)
    if (language) params.append('language', language)
    return apiRequest(`/api/v1/tests/child/${childId}/evaluation-report?${params.toString()}`, {
      method: 'GET',
    })
  },

  getStudyGuide: (guideId) =>
    apiRequest(`/api/v1/tests/study-guides/${guideId}`, {
      method: 'GET',
    }),

  regenerateStudyGuide: (guideId, language = null) => {
    const url = language
      ? `/api/v1/tests/study-guides/${guideId}/regenerate?language=${encodeURIComponent(language)}`
      : `/api/v1/tests/study-guides/${guideId}/regenerate`
    return apiRequest(url, {
      method: 'POST',
    })
  },

  listStudyGuides: (childId, conceptName = null) => {
    const params = conceptName ? `?concept_name=${encodeURIComponent(conceptName)}` : ''
    return apiRequest(`/api/v1/tests/child/${childId}/study-guides${params}`, {
      method: 'GET',
    })
  },

  chatWithCoach: (data) =>
    apiRequest('/api/v1/tests/study-guide/coach/chat', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
}

/**
 * Child API (for child users)
 */
export const child = {
  getProfile: () =>
    apiRequest('/api/v1/child/profile', { method: 'GET' }),
  updateProfile: (body) =>
    apiRequest('/api/v1/child/profile', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
}

/**
 * TikZ Rendering API
 */
export const tikz = {
  render: (tikzCode, format = 'svg', useQuickLaTeX = true) =>
    apiRequest('/api/v1/tikz/render', {
      method: 'POST',
      body: JSON.stringify({
        tikz_code: tikzCode,
        format,
        use_quicklatex: useQuickLaTeX,
      }),
    }),
}
