import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import { tests } from '../services/api'
import { showNotification } from '../utils/notifications'
import MathText from './MathText'
import StudyGuide from './StudyGuide'
import RevisionCardsView from './RevisionCardsView'

export default function AICoach({
  isOpen,
  onToggle,
  guideId,
  contextPayload,
  activeTab,
  onNavigateTab,
  userName = 'You',
  isWorkspaceMode = false,
  disableChat = false,
  preferredLanguage = null,
}) {
  const [messages, setMessages] = useState([])
  const [inputMessage, setInputMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const messagesEndRef = useRef(null)
  const chatContainerRef = useRef(null)

  // Initialize with contextual hook if context provided
  useEffect(() => {
    if (isOpen && messages.length === 0 && contextPayload?.relatedError) {
      const contextualHook = buildContextualHook(contextPayload)
      if (contextualHook) {
        setMessages([{
          role: 'assistant',
          content: contextualHook,
          isSystem: true
        }])
      }
    }
  }, [isOpen, contextPayload])

  // Reset messages when guideId changes or drawer closes
  useEffect(() => {
    if (!isOpen) {
      setMessages([])
      setInputMessage('')
    }
  }, [isOpen, guideId])

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const buildContextualHook = (context) => {
    if (!context?.relatedError) return null
    
    const { activeTopic, relatedError } = context
    const errorType = relatedError.errorType
    
    // Build contextual opening message
    if (errorType === 'Arithmetic') {
      return `I see you had some trouble with ${activeTopic}, particularly with calculations. Let's work through this together. What specific part would you like to focus on?`
    } else if (errorType === 'Conceptual') {
      return `I notice there were some conceptual challenges with ${activeTopic}. Understanding the core ideas is important. What would you like to explore first?`
    } else if (errorType === 'Procedural') {
      return `It looks like the step-by-step process for ${activeTopic} was tricky. Let's break it down together. Which step would you like to start with?`
    }
    
    return `I see you're working on ${activeTopic}. How can I help you understand this better?`
  }

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || isLoading) return

    const userMessage = inputMessage.trim()
    setInputMessage('')
    
    // Add user message
    const newUserMessage = { role: 'user', content: userMessage }
    setMessages(prev => [...prev, newUserMessage])
    setIsLoading(true)

    try {
      if (!guideId) {
        setIsLoading(false)
        return
      }

      const response = await tests.chatWithCoach({
        guide_id: guideId,
        message: userMessage,
        conversation_history: messages.filter(m => !m.isSystem).map(m => ({
          role: m.role,
          content: m.content
        })),
        context: contextPayload,
        ...(preferredLanguage && { language: preferredLanguage })
      })

      if (response.success) {
        const assistantMessage = { 
          role: 'assistant', 
          content: response.response,
          actions: response.actions // For deep linking
        }
        setMessages(prev => [...prev, assistantMessage])
        
        // Handle deep linking if coach suggests navigation
        if (response.actions?.navigateToTab) {
          onNavigateTab?.(response.actions.navigateToTab)
        }
      } else {
        showNotification(response.message || 'Failed to get response', 'error')
        setMessages(prev => prev.slice(0, -1)) // Remove user message on error
      }
    } catch (error) {
      showNotification(error.message || 'Failed to send message', 'error')
      setMessages(prev => prev.slice(0, -1))
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendMessage()
    }
  }

  // Helper to extract text from React children for LaTeX rendering
  const extractText = (node) => {
    if (typeof node === 'string') return node
    if (typeof node === 'number') return String(node)
    if (Array.isArray(node)) return node.map(extractText).join('')
    if (node?.props?.children) return extractText(node.props.children)
    return ''
  }

  // Normalize LaTeX escaping - convert double backslashes to single for proper rendering
  const normalizeLaTeX = (text) => {
    if (!text || typeof text !== 'string') return text
    // Convert double backslashes before LaTeX commands to single backslashes
    // e.g., \\text{KE} -> \text{KE}, \\frac{1}{2} -> \frac{1}{2}
    // But preserve \\[ and \\] for display math delimiters
    // Pattern: Replace \\ followed by a letter (LaTeX command) with single \
    let normalized = text
    // First, protect display math delimiters
    normalized = normalized.replace(/\\\\\[/g, '__PROTECT_OPEN__')
    normalized = normalized.replace(/\\\\\]/g, '__PROTECT_CLOSE__')
    // Replace double backslashes before letters with single backslash
    normalized = normalized.replace(/\\\\([a-zA-Z])/g, '\\$1')
    // Restore protected delimiters
    normalized = normalized.replace(/__PROTECT_OPEN__/g, '\\\\[')
    normalized = normalized.replace(/__PROTECT_CLOSE__/g, '\\\\]')
    return normalized
  }

  // Shared markdown components for LaTeX rendering
  const markdownComponents = {
    // Paragraphs with LaTeX
    // eslint-disable-next-line react/prop-types
    p: ({ children }) => {
      const text = normalizeLaTeX(extractText(children))
      return (
        <p style={{ margin: '0.5rem 0', marginTop: 0 }}>
          <MathText text={text} inline={false} />
        </p>
      )
    },
    // Headings with LaTeX
    // eslint-disable-next-line react/prop-types
    h1: ({ children }) => {
      const text = normalizeLaTeX(extractText(children))
      return (
        <h1 style={{ 
          fontSize: '1.25rem', 
          margin: '0.75rem 0 0.5rem 0',
          fontWeight: '700'
        }}>
          <MathText text={text} inline={false} />
        </h1>
      )
    },
    // eslint-disable-next-line react/prop-types
    h2: ({ children }) => {
      const text = normalizeLaTeX(extractText(children))
      return (
        <h2 style={{ 
          fontSize: '1.125rem', 
          margin: '0.75rem 0 0.5rem 0',
          fontWeight: '600'
        }}>
          <MathText text={text} inline={false} />
        </h2>
      )
    },
    // eslint-disable-next-line react/prop-types
    h3: ({ children }) => {
      const text = normalizeLaTeX(extractText(children))
      return (
        <h3 style={{ 
          fontSize: '1rem', 
          margin: '0.5rem 0',
          fontWeight: '600'
        }}>
          <MathText text={text} inline={false} />
        </h3>
      )
    },
    // Lists with LaTeX
    // eslint-disable-next-line react/prop-types
    ul: ({ children }) => (
      <ul style={{ margin: '0.5rem 0', paddingLeft: '1.5rem' }}>
        {children}
      </ul>
    ),
    // eslint-disable-next-line react/prop-types
    ol: ({ children }) => (
      <ol style={{ margin: '0.5rem 0', paddingLeft: '1.5rem' }}>
        {children}
      </ol>
    ),
    // eslint-disable-next-line react/prop-types
    li: ({ children }) => {
      const text = normalizeLaTeX(extractText(children))
      return (
        <li style={{ marginBottom: '0.25rem' }}>
          <MathText text={text} inline={false} />
        </li>
      )
    },
    // Code blocks
    // eslint-disable-next-line react/prop-types
    code: ({ children, className }) => {
      const code = String(children || '')
      const isUser = false // You can pass this as a prop if needed
      if (className?.startsWith('language-')) {
        return (
          <pre style={{ 
            background: isUser ? 'rgba(0,0,0,0.2)' : 'var(--bg-primary)', 
            padding: '0.5rem', 
            borderRadius: 'var(--radius-sm)',
            overflowX: 'auto',
            margin: '0.5rem 0',
            fontSize: '0.875rem'
          }}>
            <code style={{ background: 'none', padding: 0, fontFamily: 'monospace' }}>
              {code}
            </code>
          </pre>
        )
      }
      return (
        <code style={{ 
          background: isUser ? 'rgba(0,0,0,0.2)' : 'var(--bg-primary)', 
          padding: '0.2rem 0.4rem', 
          borderRadius: 'var(--radius-sm)',
          fontFamily: 'monospace',
          fontSize: '0.9em'
        }}>
          {code}
        </code>
      )
    },
    // Links - handle navigation links specially
    // eslint-disable-next-line react/prop-types
    a: ({ href, children }) => {
      const linkText = extractText(children)
      const isNavLink = href === 'cards' || href === 'guide' || 
                       linkText.toLowerCase().includes('card') ||
                       linkText.toLowerCase().includes('guide')
      
      if (isNavLink) {
        const targetTab = href === 'cards' || linkText.toLowerCase().includes('card') 
          ? 'CARDS' 
          : 'GUIDE'
        return (
          <button
            onClick={() => onNavigateTab?.(targetTab)}
            style={{
              background: 'transparent',
              border: '1px solid currentColor',
              borderRadius: 'var(--radius-sm)',
              padding: '0.25rem 0.5rem',
              color: 'inherit',
              cursor: 'pointer',
              textDecoration: 'underline',
              margin: '0 0.25rem',
              fontFamily: 'inherit',
              fontSize: 'inherit'
            }}
          >
            {linkText}
          </button>
        )
      }
      return (
        <a 
          href={href} 
          style={{ 
            color: 'inherit', 
            textDecoration: 'underline' 
          }} 
          target="_blank" 
          rel="noopener noreferrer"
        >
          {linkText}
        </a>
      )
    },
    // Strong/Bold with LaTeX
    // eslint-disable-next-line react/prop-types
    strong: ({ children }) => {
      const text = normalizeLaTeX(extractText(children))
      return (
        <strong style={{ fontWeight: '600' }}>
          <MathText text={text} inline={true} />
        </strong>
      )
    },
    // Emphasis/Italic with LaTeX
    // eslint-disable-next-line react/prop-types
    em: ({ children }) => {
      const text = normalizeLaTeX(extractText(children))
      return (
        <em style={{ fontStyle: 'italic' }}>
          <MathText text={text} inline={true} />
        </em>
      )
    },
    // Blockquotes with LaTeX
    // eslint-disable-next-line react/prop-types
    blockquote: ({ children }) => {
      const text = normalizeLaTeX(extractText(children))
      const isUser = false
      return (
        <blockquote style={{
          margin: '0.5rem 0',
          padding: '0.5rem 1rem',
          borderLeft: '3px solid currentColor',
          background: isUser ? 'rgba(0,0,0,0.1)' : 'var(--bg-primary)',
          borderRadius: '0 var(--radius-sm) var(--radius-sm) 0',
          fontStyle: 'italic'
        }}>
          <MathText text={text} inline={false} />
        </blockquote>
      )
    },
    // Horizontal rule
    hr: () => (
      <hr style={{
        border: 'none',
        borderTop: `1px solid var(--border-color)`,
        margin: '0.75rem 0'
      }} />
    )
  }

  const isMobile = window.innerWidth < 768

  // Determine current tab (use prop if provided, otherwise default to CHAT)
  const currentTab = disableChat && (activeTab === 'CHAT' || !activeTab) ? 'GUIDE' : (activeTab || 'CHAT')
  
  // In workspace mode, always render with tabs
  if (isWorkspaceMode) {
    return (
      <div
        ref={chatContainerRef}
        style={{
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
          overflow: 'hidden',
          background: 'var(--bg-primary)'
        }}
      >
        {/* Header with Tabs */}
        <div style={{
          borderBottom: '1px solid var(--border-color)',
          background: 'var(--bg-secondary)'
        }}>
          <div style={{
            padding: '1rem 1.5rem',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <img
                src="/zoria-coach-icon.png?v=4"
                alt="Zoria"
                style={{
                  height: 48,
                  width: 'auto',
                  flexShrink: 0
                }}
              />
              <div>
                <div style={{ fontWeight: '600', fontSize: '1.125rem' }}>Zoria</div>
                <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>
                  Your AI learning assistant
                </div>
              </div>
            </div>
          </div>
          
          {/* Tab Navigation */}
          <div style={{
            display: 'flex',
            borderTop: '1px solid var(--border-color)',
            background: 'var(--bg-primary)'
          }}>
            {!disableChat && (
              <button
                onClick={() => onNavigateTab?.('CHAT')}
                style={{
                  flex: 1,
                  padding: '0.75rem 1rem',
                  border: 'none',
                  borderBottom: currentTab === 'CHAT' ? '3px solid var(--primary-color)' : '3px solid transparent',
                  background: currentTab === 'CHAT' ? 'var(--bg-secondary)' : 'transparent',
                  color: currentTab === 'CHAT' ? 'var(--primary-color)' : 'var(--text-muted)',
                  cursor: 'pointer',
                  fontWeight: currentTab === 'CHAT' ? '600' : '400',
                  transition: 'all 0.2s'
                }}
              >
                Chat
              </button>
            )}
            {guideId && (
              <>
                <button
                  onClick={() => onNavigateTab?.('GUIDE')}
                  style={{
                    flex: 1,
                    padding: '0.75rem 1rem',
                    border: 'none',
                    borderBottom: currentTab === 'GUIDE' ? '3px solid var(--primary-color)' : '3px solid transparent',
                    background: currentTab === 'GUIDE' ? 'var(--bg-secondary)' : 'transparent',
                    color: currentTab === 'GUIDE' ? 'var(--primary-color)' : 'var(--text-muted)',
                    cursor: 'pointer',
                    fontWeight: currentTab === 'GUIDE' ? '600' : '400',
                    transition: 'all 0.2s'
                  }}
                >
                  Guide
                </button>
                <button
                  onClick={() => onNavigateTab?.('CARDS')}
                  style={{
                    flex: 1,
                    padding: '0.75rem 1rem',
                    border: 'none',
                    borderBottom: currentTab === 'CARDS' ? '3px solid var(--primary-color)' : '3px solid transparent',
                    background: currentTab === 'CARDS' ? 'var(--bg-secondary)' : 'transparent',
                    color: currentTab === 'CARDS' ? 'var(--primary-color)' : 'var(--text-muted)',
                    cursor: 'pointer',
                    fontWeight: currentTab === 'CARDS' ? '600' : '400',
                    transition: 'all 0.2s'
                  }}
                >
                  Cards
                </button>
              </>
            )}
          </div>
        </div>

        {/* Content Area - Tab-based rendering */}
        <div style={{
          flex: 1,
          overflow: 'hidden',
          position: 'relative'
        }}>
          {currentTab === 'CHAT' && (
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              height: '100%',
              overflow: 'hidden'
            }}>
              {/* Messages */}
              <div style={{
                flex: 1,
                overflowY: 'auto',
                padding: '1rem',
                display: 'flex',
                flexDirection: 'column',
                gap: '1rem'
              }}>
                {!guideId && messages.length === 0 && (
                  <div style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    padding: '2rem',
                    textAlign: 'center',
                    color: 'var(--text-muted)',
                    fontSize: '0.95rem'
                  }}>
                    <p style={{ margin: 0 }}>Select a study guide from the report to start a conversation with the coach.</p>
                  </div>
                )}
                {messages.map((msg, idx) => {
                  const isUser = msg.role === 'user'
                  
                  return (
                    <div
                      key={idx}
                      style={{
                        alignSelf: isUser ? 'flex-end' : 'flex-start',
                        maxWidth: '80%',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '0.25rem'
                      }}
                    >
                      {/* User name label + student icon */}
                      {isUser && (
                        <div style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.5rem',
                          alignSelf: 'flex-end',
                          paddingRight: '0.5rem'
                        }}>
                          <img
                            src="/student-icon.png"
                            alt="Student"
                            style={{
                              height: 36,
                              width: 'auto'
                            }}
                          />
                          <span style={{
                            fontSize: '1rem',
                            fontWeight: '600',
                            color: 'var(--primary-color)'
                          }}>
                            {userName}
                          </span>
                        </div>
                      )}
                      {/* Zoria label + avatar */}
                      {!isUser && (
                        <div style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.5rem',
                          alignSelf: 'flex-start',
                          paddingLeft: '0.5rem'
                        }}>
                          <img
                            src="/zoria-coach-icon.png?v=4"
                            alt="Zoria"
                            style={{
                              height: 36,
                              width: 'auto'
                            }}
                          />
                          <span style={{
                            fontSize: '1rem',
                            fontWeight: '600',
                            color: 'var(--text-muted)'
                          }}>
                            Zoria
                          </span>
                        </div>
                      )}
                      <div
                        style={{
                          padding: '0.75rem 1rem',
                          borderRadius: 'var(--radius-md)',
                          background: isUser 
                            ? 'var(--primary-color)' 
                            : 'var(--bg-secondary)',
                          color: isUser ? 'white' : 'var(--text-color)',
                          border: !isUser 
                            ? '1px solid var(--border-color)' 
                            : 'none',
                          lineHeight: 1.6
                        }}
                      >
                        {isUser ? (
                          <div style={{ color: '#3b82f6' }}>
                            <MathText text={normalizeLaTeX(msg.content)} inline={false} />
                          </div>
                        ) : (
                          <ReactMarkdown components={markdownComponents}>
                            {normalizeLaTeX(msg.content)}
                          </ReactMarkdown>
                        )}
                      </div>
                    </div>
                  )
                })}
                {isLoading && (
                  <div style={{
                    alignSelf: 'flex-start',
                    padding: '0.75rem 1rem',
                    color: 'var(--text-muted)',
                    fontStyle: 'italic'
                  }}>
                    Thinking...
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Input - only enabled when a study guide is selected */}
              <div style={{
                padding: '1rem',
                borderTop: '1px solid var(--border-color)',
                background: 'var(--bg-secondary)'
              }}>
                {!guideId ? (
                  <p style={{
                    margin: 0,
                    padding: '0.75rem',
                    color: 'var(--text-muted)',
                    fontSize: '0.9rem',
                    textAlign: 'center'
                  }}>
                    Select a study guide from the report to start a conversation with the coach.
                  </p>
                ) : (
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <textarea
                      value={inputMessage}
                      onChange={(e) => setInputMessage(e.target.value)}
                      onKeyPress={handleKeyPress}
                      placeholder="Ask a question..."
                      style={{
                        flex: 1,
                        padding: '0.75rem',
                        border: '1px solid var(--border-color)',
                        borderRadius: 'var(--radius-md)',
                        resize: 'none',
                        minHeight: '60px',
                        maxHeight: '120px',
                        fontFamily: 'inherit'
                      }}
                      disabled={isLoading}
                    />
                    <button
                      onClick={handleSendMessage}
                      disabled={!inputMessage.trim() || isLoading}
                      className="btn-primary"
                      style={{ padding: '0.75rem 1.5rem', alignSelf: 'flex-end' }}
                    >
                      Send
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}
          
          {currentTab === 'GUIDE' && guideId && (
            <div style={{ height: '100%', overflowY: 'auto' }}>
              <StudyGuide 
                guideId={guideId}
                contextPayload={contextPayload}
                onNavigateToCards={() => onNavigateTab?.('CARDS')}
                preferredLanguage={preferredLanguage}
              />
            </div>
          )}
          
          {currentTab === 'CARDS' && guideId && (
            <div style={{ height: '100%', overflowY: 'auto' }}>
              <RevisionCardsView
                guideId={guideId}
                contextPayload={contextPayload}
                onAskCoach={() => onNavigateTab?.('CHAT')}
              />
            </div>
          )}
          
          {!guideId && currentTab !== 'CHAT' && (
            <div style={{
              padding: '2rem',
              textAlign: 'center',
              color: 'var(--text-muted)'
            }}>
              <p>Open a study guide from the report to view Guide or Cards.</p>
            </div>
          )}
        </div>
      </div>
    )
  }

  if (!isOpen) {
    // Collapsed state - floating button on right side
    return (
      <button
        onClick={onToggle}
        style={{
          position: 'fixed',
          bottom: '2rem',
          right: '2rem',
          width: '60px',
          height: '60px',
          borderRadius: '50%',
          background: 'var(--primary-color)',
          color: 'white',
          border: 'none',
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
          cursor: 'pointer',
          fontSize: '1.5rem',
          zIndex: 1002,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}
        title="Open Zoria"
      >
        💬
      </button>
    )
  }

  // Expanded state - right drawer
  return (
    <>
      {/* Backdrop */}
      <div
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.5)',
          zIndex: 1001,
          animation: 'fadeIn 0.2s ease-in'
        }}
        onClick={onToggle}
      />
      
      {/* Right Drawer */}
      <div
        ref={chatContainerRef}
        style={{
          position: 'fixed',
          top: 0,
          right: 0,
          width: isMobile ? '100%' : '40%',
          maxWidth: '600px',
          height: '100vh',
          maxHeight: '100vh',
          background: 'var(--bg-primary)',
          boxShadow: '-4px 0 12px rgba(0, 0, 0, 0.15)',
          display: 'flex',
          flexDirection: 'column',
          zIndex: 1002,
          animation: 'slideInRight 0.3s ease-out'
        }}
      >
      {/* Header */}
      <div style={{
        padding: '1rem 1.5rem',
        borderBottom: '1px solid var(--border-color)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        background: 'var(--bg-secondary)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <img
            src="/zoria-coach-icon.png?v=4"
            alt="Zoria"
            style={{
              height: 48,
              width: 'auto',
              flexShrink: 0
            }}
          />
          <div>
            <div style={{ fontWeight: '600', fontSize: '1.125rem' }}>Zoria</div>
            <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>
              Your AI learning assistant
            </div>
          </div>
        </div>
        <button
          onClick={onToggle}
          className="btn-secondary"
          style={{ padding: '0.5rem' }}
        >
          ✕ Close
        </button>
      </div>

      {/* Messages */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '1rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem'
      }}>
        {messages.map((msg, idx) => {
          const isUser = msg.role === 'user'
          
          return (
            <div
              key={idx}
              style={{
                alignSelf: isUser ? 'flex-end' : 'flex-start',
                maxWidth: '80%',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.25rem'
              }}
            >
              {/* User name label + student icon */}
              {isUser && (
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  alignSelf: 'flex-end',
                  paddingRight: '0.5rem'
                }}>
                  <img
                    src="/student-icon.png"
                    alt="Student"
                    style={{
                      height: 36,
                      width: 'auto'
                    }}
                  />
                  <span style={{
                    fontSize: '1rem',
                    fontWeight: '600',
                    color: 'var(--primary-color)'
                  }}>
                    {userName}
                  </span>
                </div>
              )}
              {/* Zoria label + avatar */}
              {!isUser && (
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  alignSelf: 'flex-start',
                  paddingLeft: '0.5rem'
                }}>
                  <img
                    src="/zoria-coach-icon.png?v=4"
                    alt="Zoria"
                    style={{
                      height: 36,
                      width: 'auto'
                    }}
                  />
                  <span style={{
                    fontSize: '1rem',
                    fontWeight: '600',
                    color: 'var(--text-muted)'
                  }}>
                    Zoria
                  </span>
                </div>
              )}
              <div
                style={{
                  padding: '0.75rem 1rem',
                  borderRadius: 'var(--radius-md)',
                  background: isUser 
                    ? 'var(--primary-color)' 
                    : 'var(--bg-secondary)',
                  color: isUser ? 'white' : 'var(--text-color)',
                  border: !isUser 
                    ? '1px solid var(--border-color)' 
                    : 'none',
                  lineHeight: 1.6
                }}
              >
                {isUser ? (
                  // User messages: simple text with LaTeX support - blue text
                  <div style={{ color: '#3b82f6' }}>
                    <MathText text={normalizeLaTeX(msg.content)} inline={false} />
                  </div>
                ) : (
                // Assistant messages: full markdown with LaTeX support
                <ReactMarkdown components={markdownComponents}>
                  {normalizeLaTeX(msg.content)}
                </ReactMarkdown>
                )}
              </div>
            </div>
          )
        })}
        {isLoading && (
          <div style={{
            alignSelf: 'flex-start',
            padding: '0.75rem 1rem',
            color: 'var(--text-muted)',
            fontStyle: 'italic'
          }}>
            Thinking...
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div style={{
        padding: '1rem',
        borderTop: '1px solid var(--border-color)',
        background: 'var(--bg-secondary)'
      }}>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <textarea
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask a question..."
            style={{
              flex: 1,
              padding: '0.75rem',
              border: '1px solid var(--border-color)',
              borderRadius: 'var(--radius-md)',
              resize: 'none',
              minHeight: '60px',
              maxHeight: '120px',
              fontFamily: 'inherit'
            }}
            disabled={isLoading}
          />
          <button
            onClick={handleSendMessage}
            disabled={!inputMessage.trim() || isLoading}
            className="btn-primary"
            style={{ padding: '0.75rem 1.5rem', alignSelf: 'flex-end' }}
          >
            Send
          </button>
        </div>
      </div>
      
      <style>{`
        @keyframes slideInRight {
          from {
            transform: translateX(100%);
          }
          to {
            transform: translateX(0);
          }
        }
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @media (max-width: 768px) {
          .ai-coach-drawer {
            width: 100% !important;
            max-width: 100% !important;
          }
        }
      `}</style>
    </div>
    </>
  )
}
