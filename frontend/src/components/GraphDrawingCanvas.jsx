import { useRef, useEffect, useState, useCallback } from 'react'
import { fabric } from 'fabric'
import { fabricToLatex, fabricToLatexDocument, copyToClipboard } from '../utils/fabricToLatex'

/**
 * GraphDrawingCanvas - A canvas component for drawing graphs/diagrams
 * 
 * Features:
 * - Grid background
 * - Coordinate axes
 * - Free-form drawing with mouse/touch
 * - Clear button
 * - Export drawing data as JSON
 */
export default function GraphDrawingCanvas({ 
  onDrawingChange, 
  readOnly = false,
  initialDrawingData = null,
  width = 600,
  height = 400
}) {
  const canvasRef = useRef(null)
  const [fabricCanvas, setFabricCanvas] = useState(null)
  const [isDrawing, setIsDrawing] = useState(false)
  const [drawingMode, setDrawingMode] = useState('free') // 'free' or 'point-to-point'
  const saveTimeoutRef = useRef(null) // Ref to persist debounce timeout across renders
  const onDrawingChangeRef = useRef(onDrawingChange) // Ref to avoid recreating canvas when callback changes
  
  // Update the ref when callback changes
  useEffect(() => {
    onDrawingChangeRef.current = onDrawingChange
  }, [onDrawingChange])

  // Initialize canvas
  useEffect(() => {
    if (!canvasRef.current) return

    const canvas = new fabric.Canvas(canvasRef.current, {
      width: width,
      height: height,
      backgroundColor: '#ffffff',
      isDrawingMode: !readOnly && drawingMode === 'free', // Only enable free drawing in free mode
      freeDrawingBrush: {
        width: 2,
        color: '#000000',
      },
    })
    
    // Draw grid and axes
    drawGrid(canvas)
    drawAxes(canvas)

    // Lock grid and axes so they can't be moved
    canvas.getObjects().forEach((obj) => {
      if (obj.selectable !== undefined) {
        obj.selectable = false
        obj.evented = false
      }
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
          // Re-draw grid and axes on top
          drawGrid(canvas)
          drawAxes(canvas)
        })
      } catch (error) {
        console.error('Failed to load initial drawing:', error)
      }
    }

    // Helper to get only user-drawn objects (exclude grid/axes)
    const getUserDrawingData = () => {
      const allObjects = canvas.getObjects()
      // Simplified filter: exclude only objects explicitly marked for exclusion
      // Grid/axes have: excludeFromExport: true
      // User drawings have: excludeFromExport: false or undefined
      const userObjects = allObjects.filter((obj) => {
        // Exclude only if explicitly marked as excluded (grid/axes)
        return obj.excludeFromExport !== true
      })
      
      console.log('getUserDrawingData:', {
        totalObjects: allObjects.length,
        userObjects: userObjects.length,
        userObjectTypes: userObjects.map(obj => obj.type),
        sampleObjects: userObjects.slice(0, 3).map(obj => ({ 
          type: obj.type, 
          selectable: obj.selectable, 
          evented: obj.evented, 
          excludeFromExport: obj.excludeFromExport 
        }))
      })
      
      // Create a proper canvas JSON structure with only user objects
      // This structure is compatible with loadFromJSON
      const canvasData = {
        version: fabric.version,
        objects: userObjects.map(obj => obj.toObject(['selectable', 'evented', 'excludeFromExport']))
      }
      return canvasData
    }
    
    // Debounce helper to prevent excessive save calls
    // Use ref to persist across re-renders
    const debouncedSave = (data) => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current)
      }
      saveTimeoutRef.current = setTimeout(() => {
        console.log('Debounced save - sending data:', {
          objectsCount: data.objects?.length || 0,
          dataPreview: JSON.stringify(data).substring(0, 200)
        })
        onDrawingChangeRef.current?.(data)
        saveTimeoutRef.current = null
      }, 500) // 500ms debounce - increased to ensure all changes are captured
    }
    
    // Also save immediately on certain events (like object removal) to ensure changes persist
    const immediateSave = (data) => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current)
        saveTimeoutRef.current = null
      }
      console.log('Immediate save - sending data:', {
        objectsCount: data.objects?.length || 0
      })
      onDrawingChangeRef.current?.(data)
    }

    // Primary handler for path:created - fires when user finishes drawing a path
    const handlePathCreated = (e) => {
      console.log('path:created event received:', e)
      if (!readOnly && e.path) {
        const path = e.path
        console.log('Path created:', {
          pathType: path.type,
          pathInCanvas: canvas.getObjects().includes(path),
          totalObjectsBefore: canvas.getObjects().length
        })
        
        // Configure path for export
        path.set({
          selectable: true,
          evented: true,
          excludeFromExport: false
        })
        
        console.log('Path configured:', {
          selectable: path.selectable,
          evented: path.evented,
          excludeFromExport: path.excludeFromExport,
          totalObjectsAfter: canvas.getObjects().length
        })
        
        // Use retry mechanism to ensure path is added to canvas
        const checkAndSave = (attempt = 1) => {
          const allObjects = canvas.getObjects()
          const pathInCanvas = allObjects.includes(path)
          const userPaths = allObjects.filter(obj => 
            obj.type === 'path' && obj.excludeFromExport !== true
          )
          
          console.log(`Check attempt ${attempt}:`, {
            pathInCanvas,
            totalObjects: allObjects.length,
            userPathsCount: userPaths.length
          })
          
          if (pathInCanvas || userPaths.length > 0) {
            // Path is in canvas, get all user drawings
            const data = getUserDrawingData()
            console.log('path:created - sending data:', {
              objectsCount: data.objects?.length || 0
            })
            debouncedSave(data)
          } else if (attempt < 5) {
            // Retry if path not found yet (up to 5 attempts)
            setTimeout(() => checkAndSave(attempt + 1), 50)
          } else {
            console.warn('Path not found in canvas after multiple attempts, saving anyway')
            // Still try to save what we have
            const data = getUserDrawingData()
            debouncedSave(data)
          }
        }
        
        // Start checking after a short delay
        setTimeout(() => checkAndSave(), 50)
      }
    }

    // Handler for object:added - only process paths, ignore grid/axes
    const handleObjectAdded = (e) => {
      if (!readOnly && e.target) {
        const obj = e.target
        
        // Skip grid/axes (they have excludeFromExport: true)
        if (obj.excludeFromExport === true) {
          return // Ignore grid/axes
        }
        
        // Only process paths (user drawings)
        if (obj.type === 'path') {
          console.log('object:added - path detected:', {
            objectType: obj.type,
            totalObjects: canvas.getObjects().length,
            pathSelectable: obj.selectable,
            pathEvented: obj.evented,
            pathExcludeFromExport: obj.excludeFromExport,
            pathInCanvas: canvas.getObjects().includes(obj)
          })
          
          // Ensure path is configured
          obj.set({
            selectable: true,
            evented: true,
            excludeFromExport: false
          })
          
          // Save after delay with retry
          const checkAndSave = (attempt = 1) => {
            const allObjects = canvas.getObjects()
            const pathInCanvas = allObjects.includes(obj)
            
            if (pathInCanvas || attempt >= 3) {
              const data = getUserDrawingData()
              console.log('object:added - sending data:', {
                objectsCount: data.objects?.length || 0,
                attempt
              })
              debouncedSave(data)
            } else {
              setTimeout(() => checkAndSave(attempt + 1), 50)
            }
          }
          
          setTimeout(() => checkAndSave(), 50)
        }
      }
    }

    const handleObjectModified = () => {
      if (!readOnly) {
        const data = getUserDrawingData()
        debouncedSave(data)
      }
    }

    const handleObjectRemoved = () => {
      if (!readOnly) {
        const data = getUserDrawingData()
        immediateSave(data) // Save immediately when objects are removed
      }
    }

    // Register event handlers - path:created is primary for free drawing
    canvas.on('path:created', handlePathCreated)
    canvas.on('object:added', handleObjectAdded) // Backup for other object types
    canvas.on('object:modified', handleObjectModified)
    canvas.on('object:removed', handleObjectRemoved)
    
    // Log that handlers are registered
    console.log('Event handlers registered:', {
      hasPathCreated: canvas.__eventListeners?.path?.created?.length > 0,
      hasObjectAdded: canvas.__eventListeners?.object?.added?.length > 0,
      isDrawingMode: canvas.isDrawingMode,
      drawingMode: drawingMode
    })
    
      // Point-to-point mode: handle mouse clicks
      const handleMouseDown = (e) => {
        if (readOnly || drawingMode !== 'point-to-point') return
        
        // Don't handle clicks on existing objects (let them be selected/moved)
        if (e.target && e.target !== canvas) return
        
        const pointer = canvas.getPointer(e.e)
        const point = { x: pointer.x, y: pointer.y }
        
        // Create a small circle to mark the point
        const circle = new fabric.Circle({
          left: point.x,
          top: point.y,
          radius: 3,
          fill: '#000000',
          selectable: true, // Allow selection for editing
          evented: true, // Allow interaction
          excludeFromExport: false, // Include in export
          originX: 'center',
          originY: 'center'
        })
        canvas.add(circle)
        console.log('Point-to-point: Added circle at', point.x, point.y)
        
        // If we have a previous point, draw a line
        const currentPoints = canvas.getObjects().filter(obj => 
          obj.type === 'circle' && obj.excludeFromExport !== true && obj.radius === 3
        )
        console.log('Point-to-point: Current points count', currentPoints.length)
        
        if (currentPoints.length > 1) {
          const prevCircle = currentPoints[currentPoints.length - 2]
          const line = new fabric.Line([prevCircle.left, prevCircle.top, point.x, point.y], {
            stroke: '#000000',
            strokeWidth: 2,
            selectable: true,
            evented: true,
            excludeFromExport: false // Include in export
          })
          canvas.add(line)
          canvas.sendToBack(line) // Keep lines behind points
          console.log('Point-to-point: Added line from', prevCircle.left, prevCircle.top, 'to', point.x, point.y)
        }
        
        // Force immediate save after adding point/line
        setTimeout(() => {
          const data = getUserDrawingData()
          console.log('point-to-point - mouse:down - saving data:', {
            objectsCount: data.objects?.length || 0,
            objectTypes: data.objects?.map(obj => obj.type) || []
          })
          immediateSave(data) // Use immediate save for point-to-point mode
        }, 100) // Small delay to ensure objects are added
      }
    
    canvas.on('mouse:down', handleMouseDown)
    
    // Force save when mouse is released (drawing stops)
    const handleMouseUp = () => {
      if (!readOnly) {
        // Force immediate save when drawing stops (for both modes)
        setTimeout(() => {
          const data = getUserDrawingData()
          console.log('mouse:up - forcing final save:', {
            objectsCount: data.objects?.length || 0,
            drawingMode: drawingMode,
            objectTypes: data.objects?.map(obj => obj.type) || []
          })
          immediateSave(data)
        }, 100) // Small delay to ensure objects are fully added
      }
    }
    canvas.on('mouse:up', handleMouseUp)
    
    // Verify canvas state
    console.log('Canvas initialized:', {
      isDrawingMode: canvas.isDrawingMode,
      drawingMode: drawingMode,
      readOnly: readOnly,
      width: width,
      height: height,
      hasContext: !!canvas.getContext(),
      totalObjects: canvas.getObjects().length
    })
    
    // Double-check drawing mode is set correctly
    if (!readOnly && drawingMode === 'free' && !canvas.isDrawingMode) {
      console.warn('Canvas should be in drawing mode but is not! Fixing...')
      canvas.isDrawingMode = true
    }

    // Handle window resize
    const handleResize = () => {
      // Optional: adjust canvas size on resize
    }
    window.addEventListener('resize', handleResize)

    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current)
      }
      canvas.off('object:added', handleObjectAdded)
      canvas.off('path:created', handlePathCreated)
      canvas.off('object:modified', handleObjectModified)
      canvas.off('object:removed', handleObjectRemoved)
      canvas.off('mouse:down', handleMouseDown)
      canvas.off('mouse:up', handleMouseUp)
      window.removeEventListener('resize', handleResize)
      canvas.dispose()
    }
  }, [width, height, readOnly, drawingMode]) // Removed onDrawingChange to prevent unnecessary recreations

  // Update drawing mode when readOnly or drawingMode changes
  useEffect(() => {
    if (fabricCanvas && fabricCanvas.getContext()) {
      try {
        // Only enable free drawing mode if not readOnly and in free mode
        fabricCanvas.isDrawingMode = !readOnly && drawingMode === 'free'
        fabricCanvas.renderAll()
      } catch (error) {
        console.error('Error updating drawing mode:', error)
      }
    }
  }, [fabricCanvas, readOnly, drawingMode])

  // Reload drawing data when initialDrawingData changes (but only if canvas is already initialized)
  useEffect(() => {
    if (!fabricCanvas) return
    
    console.log('GraphDrawingCanvas: initialDrawingData changed', {
      hasData: !!initialDrawingData,
      dataType: typeof initialDrawingData,
      dataPreview: initialDrawingData 
        ? (typeof initialDrawingData === 'string' 
            ? initialDrawingData.substring(0, 100) 
            : JSON.stringify(initialDrawingData).substring(0, 100))
        : 'null'
    })
    
    // If no initial data, clear user drawings but keep grid/axes
    if (!initialDrawingData) {
      try {
        const allObjects = fabricCanvas.getObjects()
        const userObjects = allObjects.filter((obj) => {
          return obj.selectable !== false || obj.evented !== false
        })
        userObjects.forEach((obj) => {
          fabricCanvas.remove(obj)
        })
        if (fabricCanvas.getContext()) {
          fabricCanvas.renderAll()
        }
      } catch (error) {
        console.error('Error clearing canvas:', error)
      }
      return
    }

    try {
      const data = typeof initialDrawingData === 'string' 
        ? JSON.parse(initialDrawingData) 
        : initialDrawingData
      
      console.log('GraphDrawingCanvas: Parsed data', {
        hasObjects: !!(data && data.objects),
        objectsLength: data?.objects?.length || 0,
        dataKeys: data ? Object.keys(data) : []
      })
      
      // Only reload if we have actual drawing data (objects array)
      if (data && data.objects && Array.isArray(data.objects) && data.objects.length > 0) {
        console.log('GraphDrawingCanvas: Loading drawing with', data.objects.length, 'objects')
        // Clear existing user drawings (keep grid/axes)
        const allObjects = fabricCanvas.getObjects()
        const userObjects = allObjects.filter((obj) => {
          return obj.selectable !== false || obj.evented !== false
        })
        userObjects.forEach((obj) => {
          fabricCanvas.remove(obj)
        })
        
        // Load the drawing data
        if (fabricCanvas.getContext()) {
          fabricCanvas.loadFromJSON(data, () => {
            console.log('GraphDrawingCanvas: Drawing loaded successfully')
            if (fabricCanvas.getContext()) {
              fabricCanvas.renderAll()
              // Re-draw grid and axes on top
              drawGrid(fabricCanvas)
              drawAxes(fabricCanvas)
            }
          })
        }
      } else {
        console.log('GraphDrawingCanvas: No valid drawing data to load', data)
      }
    } catch (error) {
      console.error('GraphDrawingCanvas: Failed to load initial drawing:', error, initialDrawingData)
    }
  }, [fabricCanvas, initialDrawingData])

  const drawGrid = (canvas) => {
    const gridSize = 20
    const halfWidth = width / 2
    const halfHeight = height / 2

    // Vertical grid lines (x coordinates in canvas space: 0 to width)
    for (let x = 0; x <= width; x += gridSize) {
      const line = new fabric.Line([x, 0, x, height], {
        stroke: '#e0e0e0',
        strokeWidth: 1,
        selectable: false,
        evented: false,
        excludeFromExport: true,
      })
      canvas.add(line)
      canvas.sendToBack(line)
    }

    // Horizontal grid lines (y coordinates in canvas space: 0 to height)
    for (let y = 0; y <= height; y += gridSize) {
      const line = new fabric.Line([0, y, width, y], {
        stroke: '#e0e0e0',
        strokeWidth: 1,
        selectable: false,
        evented: false,
        excludeFromExport: true,
      })
      canvas.add(line)
      canvas.sendToBack(line)
    }
  }

  const drawAxes = (canvas) => {
    const halfWidth = width / 2
    const halfHeight = height / 2

    // X-axis (horizontal line at center Y)
    const xAxis = new fabric.Line([0, halfHeight, width, halfHeight], {
      stroke: '#000000',
      strokeWidth: 2,
      selectable: false,
      evented: false,
      excludeFromExport: true,
    })
    canvas.add(xAxis)
    canvas.bringToFront(xAxis)

    // Y-axis (vertical line at center X)
    const yAxis = new fabric.Line([halfWidth, 0, halfWidth, height], {
      stroke: '#000000',
      strokeWidth: 2,
      selectable: false,
      evented: false,
      excludeFromExport: true,
    })
    canvas.add(yAxis)
    canvas.bringToFront(yAxis)

    // Add axis labels
    const xLabel = new fabric.Text('x', {
      left: width - 20,
      top: halfHeight + 5,
      fontSize: 14,
      fill: '#000000',
      selectable: false,
      evented: false,
      excludeFromExport: true,
    })
    canvas.add(xLabel)

    const yLabel = new fabric.Text('y', {
      left: halfWidth + 5,
      top: 5,
      fontSize: 14,
      fill: '#000000',
      selectable: false,
      evented: false,
      excludeFromExport: true,
    })
    canvas.add(yLabel)

    // Add origin label
    const originLabel = new fabric.Text('O', {
      left: halfWidth + 5,
      top: halfHeight + 5,
      fontSize: 12,
      fill: '#000000',
      selectable: false,
      evented: false,
      excludeFromExport: true,
    })
    canvas.add(originLabel)
  }

  const clearCanvas = useCallback(() => {
    if (fabricCanvas && !readOnly && fabricCanvas.getContext()) {
      try {
        // Remove all objects except grid and axes
        const objectsToRemove = fabricCanvas.getObjects().filter((obj) => {
          // Keep grid lines and axes (they have excludeFromExport: true)
          return obj.excludeFromExport !== true
        })
        
        objectsToRemove.forEach((obj) => {
          fabricCanvas.remove(obj)
        })
        
        if (fabricCanvas.getContext()) {
          fabricCanvas.renderAll()
        }
        
        // Notify parent of change - send empty drawing data
        const canvasData = {
          version: fabric.version,
          objects: []
        }
        console.log('clearCanvas - sending empty data')
        onDrawingChangeRef.current?.(canvasData)
      } catch (error) {
        console.error('Error clearing canvas:', error)
      }
    }
  }, [fabricCanvas, readOnly])

  // Export to LaTeX
  const exportToLatex = useCallback(async () => {
    if (!fabricCanvas) return
    
    try {
      // Get user drawing data (excludes grid/axes)
      const allObjects = fabricCanvas.getObjects()
      const userObjects = allObjects.filter((obj) => {
        return obj.excludeFromExport !== true
      })
      
      const canvasData = {
        version: fabric.version,
        objects: userObjects.map(obj => obj.toObject(['selectable', 'evented', 'excludeFromExport']))
      }
      
      // Convert to LaTeX
      const latexCode = fabricToLatex(canvasData, {
        width,
        height,
        scale: 20, // Grid size
        usePgfplots: true,
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
      // Get user drawing data (excludes grid/axes)
      const allObjects = fabricCanvas.getObjects()
      const userObjects = allObjects.filter((obj) => {
        return obj.excludeFromExport !== true
      })
      
      const canvasData = {
        version: fabric.version,
        objects: userObjects.map(obj => obj.toObject(['selectable', 'evented', 'excludeFromExport']))
      }
      
      // Convert to complete LaTeX document
      const latexDoc = fabricToLatexDocument(canvasData, {
        width,
        height,
        scale: 20, // Grid size
        usePgfplots: true,
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
            <div style={{ display: 'flex', gap: '0.25rem', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '0.25rem' }}>
              <button
                onClick={() => {
                  setDrawingMode('free')
                }}
                style={{
                  fontSize: '0.875rem',
                  padding: '0.5rem 1rem',
                  border: 'none',
                  borderRadius: 'var(--radius-sm)',
                  background: drawingMode === 'free' ? 'var(--primary-color)' : 'transparent',
                  color: drawingMode === 'free' ? 'white' : 'var(--text-color)',
                  cursor: 'pointer'
                }}
              >
                Free Draw
              </button>
              <button
                onClick={() => {
                  setDrawingMode('point-to-point')
                }}
                style={{
                  fontSize: '0.875rem',
                  padding: '0.5rem 1rem',
                  border: 'none',
                  borderRadius: 'var(--radius-sm)',
                  background: drawingMode === 'point-to-point' ? 'var(--primary-color)' : 'transparent',
                  color: drawingMode === 'point-to-point' ? 'white' : 'var(--text-color)',
                  cursor: 'pointer'
                }}
              >
                Point-to-Point
              </button>
            </div>
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
            {drawingMode === 'free' 
              ? 'Click and drag to draw on the graph'
              : 'Click to place points - lines will connect automatically'}
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
