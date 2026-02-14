import { useRef, useEffect, useState, useCallback } from 'react'
import { fabric } from 'fabric'
import { fabricToLatex, fabricToLatexDocument, copyToClipboard } from '../utils/fabricToLatex'

/**
 * DiagramDrawingCanvas - A blank canvas component for drawing diagrams
 * 
 * Features:
 * - Blank white canvas (no grid/axes)
 * - Free-form drawing with mouse/touch
 * - Clear button
 * - Export drawing data as JSON
 */
export default function DiagramDrawingCanvas({ 
  onDrawingChange, 
  readOnly = false,
  initialDrawingData = null,
  width = 600,
  height = 400
}) {
  const canvasRef = useRef(null)
  const [fabricCanvas, setFabricCanvas] = useState(null)

  // Initialize canvas
  useEffect(() => {
    if (!canvasRef.current) return

    const canvas = new fabric.Canvas(canvasRef.current, {
      width: width,
      height: height,
      backgroundColor: '#ffffff',
      isDrawingMode: !readOnly,
      freeDrawingBrush: {
        width: 2,
        color: '#000000',
      },
    })

    setFabricCanvas(canvas)

    // Load initial drawing if provided
    if (initialDrawingData) {
      try {
        const data = typeof initialDrawingData === 'string' 
          ? JSON.parse(initialDrawingData) 
          : initialDrawingData
        canvas.loadFromJSON(data, () => {
          canvas.renderAll()
        })
      } catch (error) {
        console.error('Failed to load initial drawing:', error)
      }
    }

    // Listen for drawing changes
    const handlePathCreated = () => {
      if (!readOnly) {
        const data = canvas.toJSON()
        onDrawingChange?.(data)
      }
    }

    const handleObjectModified = () => {
      if (!readOnly) {
        const data = canvas.toJSON()
        onDrawingChange?.(data)
      }
    }

    const handleObjectRemoved = () => {
      if (!readOnly) {
        const data = canvas.toJSON()
        onDrawingChange?.(data)
      }
    }

    canvas.on('path:created', handlePathCreated)
    canvas.on('object:modified', handleObjectModified)
    canvas.on('object:removed', handleObjectRemoved)

    return () => {
      canvas.off('path:created', handlePathCreated)
      canvas.off('object:modified', handleObjectModified)
      canvas.off('object:removed', handleObjectRemoved)
      canvas.dispose()
    }
  }, [width, height, readOnly, onDrawingChange])

  // Update drawing mode when readOnly changes
  useEffect(() => {
    if (fabricCanvas) {
      fabricCanvas.isDrawingMode = !readOnly
      fabricCanvas.renderAll()
    }
  }, [fabricCanvas, readOnly])

  // Reload drawing data when initialDrawingData changes (but only if canvas is already initialized)
  useEffect(() => {
    if (!fabricCanvas) return
    
    // If no initial data, clear canvas
    if (!initialDrawingData) {
      fabricCanvas.clear()
      fabricCanvas.backgroundColor = '#ffffff'
      fabricCanvas.renderAll()
      return
    }

    try {
      const data = typeof initialDrawingData === 'string' 
        ? JSON.parse(initialDrawingData) 
        : initialDrawingData
      
      // Only reload if we have actual drawing data (objects array)
      if (data && data.objects && Array.isArray(data.objects) && data.objects.length > 0) {
        // Clear existing drawings
        fabricCanvas.clear()
        fabricCanvas.backgroundColor = '#ffffff'
        
        // Load the drawing data
        fabricCanvas.loadFromJSON(data, () => {
          fabricCanvas.renderAll()
        })
      }
    } catch (error) {
      console.error('Failed to load initial drawing:', error, initialDrawingData)
    }
  }, [fabricCanvas, initialDrawingData])

  const clearCanvas = useCallback(() => {
    if (fabricCanvas && !readOnly) {
      fabricCanvas.clear()
      fabricCanvas.backgroundColor = '#ffffff'
      fabricCanvas.renderAll()
      
      // Notify parent of change
      const data = fabricCanvas.toJSON()
      onDrawingChange?.(data)
    }
  }, [fabricCanvas, readOnly, onDrawingChange])

  // Export to LaTeX
  const exportToLatex = useCallback(async () => {
    if (!fabricCanvas) return
    
    try {
      // Get all drawing data
      const canvasData = fabricCanvas.toJSON()
      
      // Convert to LaTeX (without pgfplots for diagrams)
      const latexCode = fabricToLatex(canvasData, {
        width,
        height,
        scale: 20,
        usePgfplots: false, // Plain TikZ for diagrams
        lineColor: 'black',
        lineWidth: 1.5
      })
      
      // Copy to clipboard
      const success = await copyToClipboard(latexCode)
      if (success) {
        alert('LaTeX code copied to clipboard!')
      } else {
        // Fallback: show in prompt
        prompt('LaTeX code (copy manually):', latexCode)
      }
    } catch (error) {
      console.error('Error exporting to LaTeX:', error)
      alert('Error exporting to LaTeX: ' + error.message)
    }
  }, [fabricCanvas, width, height])

  // Export to LaTeX document
  const exportToLatexDocument = useCallback(async () => {
    if (!fabricCanvas) return
    
    try {
      // Get all drawing data
      const canvasData = fabricCanvas.toJSON()
      
      // Convert to complete LaTeX document
      const latexDoc = fabricToLatexDocument(canvasData, {
        width,
        height,
        scale: 20,
        usePgfplots: false, // Plain TikZ for diagrams
        lineColor: 'black',
        lineWidth: 1.5
      })
      
      // Copy to clipboard
      const success = await copyToClipboard(latexDoc)
      if (success) {
        alert('Complete LaTeX document copied to clipboard!')
      } else {
        // Fallback: show in prompt
        prompt('LaTeX document (copy manually):', latexDoc)
      }
    } catch (error) {
      console.error('Error exporting LaTeX document:', error)
      alert('Error exporting LaTeX document: ' + error.message)
    }
  }, [fabricCanvas, width, height])

  return (
    <div style={{ 
      display: 'flex', 
      flexDirection: 'column', 
      alignItems: 'center',
      gap: '1rem',
      marginTop: '1rem',
      marginBottom: '1rem'
    }}>
      <div style={{
        border: '1px solid var(--border-color)',
        borderRadius: 'var(--radius-md)',
        padding: '0.5rem',
        background: '#ffffff',
        boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
      }}>
        <canvas ref={canvasRef} />
      </div>
      {!readOnly && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', alignItems: 'center' }}>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap', justifyContent: 'center' }}>
            <button
              onClick={clearCanvas}
              className="btn-secondary"
              style={{ fontSize: '0.875rem', padding: '0.5rem 1rem' }}
            >
              Clear Drawing
            </button>
            <button
              onClick={exportToLatex}
              className="btn-secondary"
              style={{ fontSize: '0.875rem', padding: '0.5rem 1rem' }}
              title="Export drawing as LaTeX/TikZ code"
            >
              Export to LaTeX
            </button>
            <button
              onClick={exportToLatexDocument}
              className="btn-secondary"
              style={{ fontSize: '0.875rem', padding: '0.5rem 1rem' }}
              title="Export as complete LaTeX document"
            >
              Export LaTeX Doc
            </button>
          </div>
          <div style={{ 
            fontSize: '0.875rem', 
            color: 'var(--text-muted)',
            display: 'flex',
            alignItems: 'center',
            padding: '0.5rem'
          }}>
            Click and drag to draw
          </div>
        </div>
      )}
      {readOnly && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', alignItems: 'center' }}>
          <div style={{ 
            fontSize: '0.875rem', 
            color: 'var(--text-muted)',
            fontStyle: 'italic'
          }}>
            View only - drawing disabled
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              onClick={exportToLatex}
              className="btn-secondary"
              style={{ fontSize: '0.875rem', padding: '0.5rem 1rem' }}
              title="Export drawing as LaTeX/TikZ code"
            >
              Export to LaTeX
            </button>
            <button
              onClick={exportToLatexDocument}
              className="btn-secondary"
              style={{ fontSize: '0.875rem', padding: '0.5rem 1rem' }}
              title="Export as complete LaTeX document"
            >
              Export LaTeX Doc
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
