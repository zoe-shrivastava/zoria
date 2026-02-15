import { useState, useMemo, useRef, useEffect } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import './KnowledgeGraphViewer.css'

export default function KnowledgeGraphViewer({ data, onClose, userRole = null }) {
  const [selectedConcept, setSelectedConcept] = useState(null)
  const [activeTab, setActiveTab] = useState('graph') // graph, concepts, relationships, questions, skills
  const [hoveredNode, setHoveredNode] = useState(null)
  const [graphDimensions, setGraphDimensions] = useState({ width: 1200, height: 800 })
  const graphContainerRef = useRef(null)
  const graphRef = useRef(null)

  if (!data) {
    return null
  }

  const { concepts, relationships, questions, skills, document_name } = data

  // Build concept map for easy lookup
  const conceptMap = {}
  concepts.forEach(c => {
    conceptMap[c.id] = c
  })

  // Transform data for graph visualization
  const graphData = useMemo(() => {
    // Ensure all concepts are included as nodes
    const nodes = concepts.map(concept => ({
      id: concept.id,
      name: concept.name,
      subtopic: concept.subtopic,
      difficulty: concept.difficulty,
      keywords: concept.keywords || [],
      ...concept
    }))

    // Include all relationships as links
    const links = relationships.map(rel => ({
      source: rel.from_concept_id,
      target: rel.to_concept_id,
      type: rel.relationship_type,
      strength: rel.strength || 0.5
    }))

    // Log for debugging
    console.log('Graph Data:', {
      nodes: nodes.length,
      links: links.length,
      concepts: concepts.length,
      relationships: relationships.length
    })

    return { nodes, links }
  }, [concepts, relationships])

  // Get relationships for a concept
  const getConceptRelationships = (conceptId) => {
    return relationships.filter(r => 
      r.from_concept_id === conceptId || r.to_concept_id === conceptId
    )
  }

  // Get questions for a concept
  const getConceptQuestions = (conceptId) => {
    return questions.filter(q => q.concept_id === conceptId)
  }

  // Update graph dimensions when container size changes
  useEffect(() => {
    const updateDimensions = () => {
      if (graphContainerRef.current) {
        const rect = graphContainerRef.current.getBoundingClientRect()
        setGraphDimensions({
          width: rect.width || 1200,
          height: rect.height || 800
        })
      }
    }

    updateDimensions()
    window.addEventListener('resize', updateDimensions)
    return () => window.removeEventListener('resize', updateDimensions)
  }, [activeTab])

  return (
    <div className="knowledge-graph-modal-overlay" onClick={onClose}>
      <div className="knowledge-graph-modal" onClick={(e) => e.stopPropagation()}>
        <div className="knowledge-graph-header">
          <div>
            <h2>Knowledge Graph</h2>
            <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.9rem', color: 'var(--text-muted, #6b7280)' }}>
              {document_name}
            </p>
          </div>
          <button className="knowledge-graph-close" onClick={onClose} title="Close">Close</button>
        </div>

        <div className="knowledge-graph-tabs">
          <button 
            className={activeTab === 'graph' ? 'active' : ''}
            onClick={() => setActiveTab('graph')}
          >
            Graph View
          </button>
          <button 
            className={activeTab === 'concepts' ? 'active' : ''}
            onClick={() => setActiveTab('concepts')}
          >
            Concepts ({concepts.length})
          </button>
          <button 
            className={activeTab === 'relationships' ? 'active' : ''}
            onClick={() => setActiveTab('relationships')}
          >
            Relationships ({relationships.length})
          </button>
          <button 
            className={activeTab === 'questions' ? 'active' : ''}
            onClick={() => setActiveTab('questions')}
          >
            Questions ({questions.length})
          </button>
          <button 
            className={activeTab === 'skills' ? 'active' : ''}
            onClick={() => setActiveTab('skills')}
          >
            Skills ({skills.length})
          </button>
        </div>

        <div className="knowledge-graph-content">
          {activeTab === 'graph' && (
            <div className="graph-view-container" ref={graphContainerRef}>
              <div className="graph-stats">
                <span>Nodes: {graphData.nodes.length} | Links: {graphData.links.length}</span>
              </div>
              <ForceGraph2D
                ref={graphRef}
                graphData={graphData}
                width={graphDimensions.width}
                height={graphDimensions.height}
                nodeLabel={node => {
                  const relCount = relationships.filter(r => 
                    r.from_concept_id === node.id || r.to_concept_id === node.id
                  ).length
                  const qCount = questions.filter(q => q.concept_id === node.id).length
                  return `
                    <div style="padding: 8px; background: white; border-radius: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.2); max-width: 300px;">
                      <strong style="font-size: 14px; color: #111827;">${node.name}</strong>
                      ${node.subtopic ? `<div style="font-size: 12px; color: #6b7280; margin-top: 4px;">${node.subtopic}</div>` : ''}
                      ${node.difficulty ? `<div style="font-size: 11px; color: #3b82f6; margin-top: 4px;">Difficulty: ${node.difficulty}</div>` : ''}
                      <div style="font-size: 11px; color: #6b7280; margin-top: 6px;">
                        Relationships: ${relCount} | Questions: ${qCount}
                      </div>
                    </div>
                  `
                }}
                nodeColor={node => {
                  if (hoveredNode === node.id) return '#3b82f6'
                  if (node.difficulty === 'easy') return '#10b981'
                  if (node.difficulty === 'medium') return '#f59e0b'
                  if (node.difficulty === 'hard') return '#ef4444'
                  return '#6366f1'
                }}
                nodeVal={node => {
                  const relCount = relationships.filter(r => 
                    r.from_concept_id === node.id || r.to_concept_id === node.id
                  ).length
                  // Ensure minimum size for visibility, even for isolated nodes
                  return Math.max(8, 5 + relCount * 2)
                }}
                nodeRelSize={8}
                linkLabel={link => {
                  const sourceConcept = concepts.find(c => c.id === link.source)
                  const targetConcept = concepts.find(c => c.id === link.target)
                  return `${sourceConcept?.name || link.source} → ${targetConcept?.name || link.target} (${link.type})`
                }}
                linkColor={link => {
                  const strength = link.strength || 0.5
                  if (strength > 0.7) return '#10b981'
                  if (strength > 0.4) return '#f59e0b'
                  return '#94a3b8'
                }}
                linkWidth={link => {
                  const strength = link.strength || 0.5
                  return Math.max(1, 1 + strength * 3)
                }}
                linkDirectionalArrowLength={6}
                linkDirectionalArrowRelPos={1}
                linkDirectionalParticles={2}
                linkDirectionalParticleSpeed={d => d.strength * 0.001}
                onNodeHover={node => setHoveredNode(node ? node.id : null)}
                onNodeClick={node => {
                  const concept = concepts.find(c => c.id === node.id)
                  if (concept) {
                    setSelectedConcept(selectedConcept?.id === concept.id ? null : concept)
                    setActiveTab('concepts')
                  }
                }}
                onNodeDragEnd={node => {
                  node.fx = node.x
                  node.fy = node.y
                }}
                d3Force="charge"
                d3ForceStrength={-500}
                d3ForceLinkDistance={200}
                d3ForceLinkStrength={0.5}
                d3ForceCenterX={0}
                d3ForceCenterY={0}
                cooldownTicks={200}
                onEngineStop={() => {
                  // Graph has stabilized
                }}
                enableZoomInteraction={true}
                enablePanInteraction={true}
                enableNodeDrag={true}
              />
              <div className="graph-legend">
                <div className="legend-item">
                  <div className="legend-color" style={{ background: '#10b981' }}></div>
                  <span>Easy</span>
                </div>
                <div className="legend-item">
                  <div className="legend-color" style={{ background: '#f59e0b' }}></div>
                  <span>Medium</span>
                </div>
                <div className="legend-item">
                  <div className="legend-color" style={{ background: '#ef4444' }}></div>
                  <span>Hard</span>
                </div>
                <div className="legend-item">
                  <div className="legend-color" style={{ background: '#6366f1' }}></div>
                  <span>Other</span>
                </div>
                <div className="legend-separator"></div>
                <div className="legend-item">
                  <div className="legend-info">Click nodes to view details</div>
                </div>
                <div className="legend-item">
                  <div className="legend-info">🖱️ Drag to explore</div>
                </div>
              </div>
            </div>
          )}
          {activeTab === 'concepts' && (
            <div className="concepts-grid">
              {concepts.map(concept => (
                <div 
                  key={concept.id} 
                  className={`concept-card ${selectedConcept?.id === concept.id ? 'selected' : ''}`}
                  onClick={() => setSelectedConcept(selectedConcept?.id === concept.id ? null : concept)}
                >
                  <div className="concept-header">
                    <h3>{concept.name}</h3>
                    {concept.difficulty && (
                      <span className={`difficulty-badge difficulty-${concept.difficulty}`}>
                        {concept.difficulty}
                      </span>
                    )}
                  </div>
                  {concept.subtopic && (
                    <p className="concept-subtopic">{concept.subtopic}</p>
                  )}
                  {concept.keywords && concept.keywords.length > 0 && (
                    <div className="concept-keywords">
                      {concept.keywords.map((kw, idx) => (
                        <span key={idx} className="keyword-tag">{kw}</span>
                      ))}
                    </div>
                  )}
                  {selectedConcept?.id === concept.id && (
                    <div className="concept-details">
                      {concept.prerequisites && concept.prerequisites.length > 0 && (
                        <div className="concept-section">
                          <strong>Prerequisites:</strong>
                          <ul>
                            {concept.prerequisites.map((prereq, idx) => (
                              <li key={idx}>{prereq}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {concept.grade && concept.grade.length > 0 && (
                        <div className="concept-section">
                          <strong>Grade Levels:</strong> {concept.grade.join(', ')}
                        </div>
                      )}
                      <div className="concept-stats">
                        <span>Relationships: {getConceptRelationships(concept.id).length}</span>
                        <span>Questions: {getConceptQuestions(concept.id).length}</span>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {activeTab === 'relationships' && (
            <div className="relationships-list">
              {relationships.length === 0 ? (
                <p className="empty-state">No relationships found</p>
              ) : (
                relationships.map(rel => (
                  <div key={rel.id} className="relationship-card">
                    <div className="relationship-nodes">
                      <div className="relationship-node">
                        <strong>{rel.from_concept_name}</strong>
                      </div>
                      <div className="relationship-arrow">
                        <span className={`relationship-type relationship-${rel.relationship_type}`}>
                          {rel.relationship_type.replace('_', ' ')}
                        </span>
                        {rel.strength && (
                          <span className="relationship-strength">
                            ({Math.round(rel.strength * 100)}%)
                          </span>
                        )}
                      </div>
                      <div className="relationship-node">
                        <strong>{rel.to_concept_name}</strong>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === 'questions' && (
            <div className="questions-list">
              {questions.length === 0 ? (
                <p className="empty-state">No questions found</p>
              ) : (
                questions.map(q => (
                  <div key={q.id} className="question-card">
                    <div className="question-header">
                      <span className="question-concept">{q.concept_name}</span>
                      {q.type && (
                        <span className="question-type">{q.type}</span>
                      )}
                      {q.difficulty && (
                        <span className={`difficulty-badge difficulty-${q.difficulty}`}>
                          {q.difficulty}
                        </span>
                      )}
                    </div>
                    <div className="question-text">{q.text}</div>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === 'skills' && (
            <div className="skills-list">
              {skills.length === 0 ? (
                <p className="empty-state">No skills found</p>
              ) : (
                skills.map(skill => (
                  <div key={skill.id} className="skill-card">
                    <div className="skill-header">
                      <h3>{skill.name}</h3>
                      {skill.cognitive_level && (
                        <span className="cognitive-level">{skill.cognitive_level}</span>
                      )}
                    </div>
                    {skill.description && (
                      <p className="skill-description">{skill.description}</p>
                    )}
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
