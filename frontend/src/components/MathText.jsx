import { useEffect, useRef } from 'react'
import { tikz as tikzApi } from '../services/api'

/**
 * MathText renders text that may contain LaTeX using KaTeX auto-render,
 * and TikZ diagrams using TikZJax.
 *
 * Assumes KaTeX, auto-render, and TikZJax are loaded globally via CDN in index.html
 * and exposed as window.renderMathInElement and window.tikzjax.
 * 
 * Note: TikZJax automatically processes all <script type="text/tikz"> elements
 * when they are added to the DOM, so we just need to ensure the scripts are
 * properly created and inserted.
 */
export default function MathText({ text, inline = false }) {
  const ref = useRef(null)

  useEffect(() => {
    if (!ref.current) return

    const el = ref.current
    let cancelled = false
    let attempts = 0
    const isRenderingRef = { current: false } // Use ref-like object to prevent double rendering
    
    // Clear processed diagrams when text changes to allow re-rendering
    if (el._processedTikzDiagrams) {
      el._processedTikzDiagrams.clear()
    }

    // Helper function to render TikZ via backend API
    const renderViaBackendAPI = async (script, container) => {
      // Check if already rendered or in progress
      // Check for both backend-rendered images and TikZJax-rendered SVG/canvas
      if (container.querySelector('.tikz-rendered') || 
          container.querySelector('svg, canvas') ||
          (container.querySelector('.tikz-loading') && container.querySelector('svg, canvas'))) {
        console.log('MathText: Skipping renderViaBackendAPI - already rendered')
        return
      }
      
      // Check if rendering is already in progress for this container
      if (container._isRendering) {
        console.log('MathText: Skipping renderViaBackendAPI - render already in progress')
        return
      }
      
      // Mark as rendering in progress
      container._isRendering = true
      console.log('MathText: Starting renderViaBackendAPI for container')
      
      // Ensure loading indicator is visible (it should already be there, but make sure)
      let loadingDiv = container.querySelector('.tikz-loading')
      if (!loadingDiv) {
        loadingDiv = document.createElement('div')
        loadingDiv.className = 'tikz-loading'
        loadingDiv.innerHTML = `
          <div style="padding: 1.5rem; text-align: center;">
            <div style="display: inline-block; width: 40px; height: 40px; border: 4px solid #f3f3f3; border-top: 4px solid #4a90e2; border-radius: 50%; animation: spin 1s linear infinite; margin-bottom: 0.5rem;"></div>
            <div style="color: #666; font-size: 0.9rem;">Rendering diagram...</div>
          </div>
          <style>
            @keyframes spin {
              0% { transform: rotate(0deg); }
              100% { transform: rotate(360deg); }
            }
          </style>
        `
        // Remove any existing rendered content but keep the script
        const existingContent = Array.from(container.children).filter(
          child => !child.classList.contains('tikz-loading') && child.tagName !== 'SCRIPT'
        )
        existingContent.forEach(child => child.remove())
        container.insertBefore(loadingDiv, script)
      }
      
      // Get TikZ code
      let code = script.getAttribute('data-tikz-code') || script.textContent || ''
      
      // If code still has double backslashes, unescape them
      if (code.includes('\\\\')) {
        code = code.replace(/\\\\/g, '\\')
      }
      
      try {
        // Call backend API to render TikZ
        // Backend will try local LaTeX first, then fall back to QuickLaTeX if needed
        // use_quicklatex=true allows fallback to QuickLaTeX if local LaTeX is unavailable
        const response = await tikzApi.render(code.trim(), 'svg', true)
        
        if (response.success && response.image_data) {
          // Remove loading indicator
          loadingDiv.remove()
          
          // Create image element with base64 data
          const img = document.createElement('img')
          const mimeType = response.mime_type || 'image/png'
          img.src = `data:${mimeType};base64,${response.image_data}`
          img.alt = 'TikZ Diagram'
          img.style.cssText = 'max-width: 100%; height: auto; margin: 1rem auto; display: block;'
          img.className = 'tikz-rendered'
          
          // Remove script element (no longer needed)
          script.remove()
          container.appendChild(img)
          
          // Clear rendering flag
          container._isRendering = false
          console.log('MathText: renderViaBackendAPI completed successfully')
        } else {
          throw new Error(response.error || 'Failed to render TikZ')
        }
      } catch (error) {
        console.error('Failed to render TikZ via API:', error)
        // Clear rendering flag on error
        container._isRendering = false
        
        // Remove loading indicator
        loadingDiv.remove()
        
        // Fallback: Show TikZ code in a styled box
        const displayCode = code.trim()
        const wrapper = document.createElement('div')
        wrapper.style.cssText = 'padding: 1rem; background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); border: 2px dashed #4a90e2; border-radius: 8px; text-align: center; min-height: 120px; display: flex; align-items: center; justify-content: center; flex-direction: column;'
        
        const title = document.createElement('div')
        title.textContent = '📊 Diagram'
        title.style.cssText = 'font-size: 1.2rem; margin-bottom: 0.5rem; color: #2c3e50;'
        
        const codeElement = document.createElement('pre')
        codeElement.textContent = displayCode.substring(0, 500) + (displayCode.length > 500 ? '...' : '')
        codeElement.style.cssText = 'margin: 0; font-family: monospace; font-size: 0.7rem; color: #7f8c8d; background: rgba(255,255,255,0.9); padding: 0.75rem; border-radius: 4px; max-width: 100%; overflow-x: auto; white-space: pre-wrap; text-align: left;'
        
        const footer = document.createElement('div')
        footer.textContent = 'TikZ rendering unavailable - diagram code shown above'
        footer.style.cssText = 'font-size: 0.7rem; color: #95a5a6; margin-top: 0.5rem;'
        
        wrapper.appendChild(title)
        wrapper.appendChild(codeElement)
        wrapper.appendChild(footer)
        
        // Remove script element
        script.remove()
        container.appendChild(wrapper)
      }
    }

    const doRender = () => {
      if (!el || cancelled || isRenderingRef.current) {
        if (isRenderingRef.current) {
          console.log('MathText: Skipping render - already rendering')
        }
        return
      }
      
      try {
        // Set rendering flag to prevent concurrent renders
        isRenderingRef.current = true
        console.log('MathText: Starting render for text:', text?.substring(0, 100))
        
        let processedText = text || ''
        const tikzDiagrams = []

      // Extract and process TikZ diagrams
      // Pattern 1: "Diagram (LaTeX): \begin{tikzpicture}...\end{tikzpicture}" or with escaped backslashes
      // Pattern 2: Direct script tags: <script type="text/tikz">...</script>
      // Note: Question text may have escaped backslashes (\\begin) which need to be unescaped
      // Also handles newlines before "Diagram (LaTeX):"
      const tikzPattern1 = /(?:Diagram\s*)?\(LaTeX\):\s*((?:\\\\)*\\begin\{tikzpicture\}[\s\S]*?(?:\\\\)*\\end\{tikzpicture\})/gi
      const tikzPattern2 = /<script\s+type=["']text\/tikz["']>([\s\S]*?)<\/script>/g
      
      // Track unique diagrams to avoid duplicates
      const seenDiagrams = new Set()
      const normalizeCode = (code) => code.replace(/\\\\/g, '\\').replace(/\s+/g, ' ').trim()
      
      // Extract TikZ code and replace with placeholders
      let tikzIndex = 0
      console.log('MathText: Checking for TikZ patterns in text (length:', processedText.length, ')')
      processedText = processedText.replace(tikzPattern1, (match, tikzCode) => {
        console.log('MathText: Found TikZ pattern 1 match:', match.substring(0, 100))
        // Unescape backslashes: \\begin -> \begin, \\draw -> \draw, etc.
        // Handle both single and double escaping
        let unescapedCode = tikzCode.trim()
          .replace(/\\\\\\/g, '\\') // Triple backslash -> single
          .replace(/\\\\/g, '\\')  // Double backslash -> single
        
        // Check for duplicates using normalized code
        const normalizedCode = normalizeCode(unescapedCode)
        const codeHash = normalizedCode.substring(0, 100)
        
        if (seenDiagrams.has(codeHash)) {
          // Duplicate found - return empty string to remove it
          return ''
        }
        
        seenDiagrams.add(codeHash)
        const placeholder = `__TIKZ_PLACEHOLDER_${tikzIndex}__`
        tikzDiagrams.push({ placeholder, tikzCode: unescapedCode })
        tikzIndex++
        return placeholder
      })
      
      processedText = processedText.replace(tikzPattern2, (match, tikzCode) => {
        console.log('MathText: Found TikZ pattern 2 match (script tag)')
        // Script tags should already have correct escaping, but unescape just in case
        let unescapedCode = tikzCode.trim()
          .replace(/\\\\\\/g, '\\') // Triple backslash -> single
          .replace(/\\\\/g, '\\')   // Double backslash -> single
        
        // Check for duplicates using normalized code
        const normalizedCode = normalizeCode(unescapedCode)
        const codeHash = normalizedCode.substring(0, 100)
        
        if (seenDiagrams.has(codeHash)) {
          // Duplicate found - return empty string to remove it
          return ''
        }
        
        seenDiagrams.add(codeHash)
        const placeholder = `__TIKZ_PLACEHOLDER_${tikzIndex}__`
        tikzDiagrams.push({ placeholder, tikzCode: unescapedCode })
        tikzIndex++
        return placeholder
      })
      
      console.log('MathText: Total TikZ diagrams extracted:', tikzDiagrams.length)

      // Normalize over-escaped backslashes in LaTeX expressions
      // Handles cases where backslashes were double-escaped during storage/transmission
      // e.g., \\\\text{m/s} -> \\text{m/s} (which will render correctly as \text{m/s})
      const normalizeLaTeXEscaping = (latexText) => {
        // Replace 4+ consecutive backslashes with 2 backslashes
        // This handles double-escaping that can occur in JSON serialization
        // Pattern: \\\\ (4 backslashes) or more -> \\ (2 backslashes)
        // Match 4 or more backslashes and replace with exactly 2
        return latexText.replace(/(\\\\){2,}/g, '\\\\')
      }
      
      // Extract display math patterns first ($$...$$, \[...\], \(...\))
      const displayPatterns = [
        /\$\$[\s\S]*?\$\$/g,  // Display math: $$...$$
        /\\\[[\s\S]*?\\\]/g,  // Display math: \[...\]
        /\\\([\s\S]*?\\\)/g,   // Inline math: \(...\)
      ]
      
      let protectedText = processedText
      const allDollarExpressions = []
      let dollarIndex = 0
      
      // First, extract display math (always LaTeX) and normalize
      displayPatterns.forEach(pattern => {
        protectedText = protectedText.replace(pattern, (match) => {
          // Normalize over-escaped backslashes in display math
          const normalized = normalizeLaTeXEscaping(match)
          const placeholder = `__LATEX_${dollarIndex}__`
          allDollarExpressions.push({ placeholder, original: normalized })
          dollarIndex++
          return placeholder
        })
      })
      
      // Then, extract all inline $...$ patterns and normalize
      const dollarPattern = /\$[^$\n]+?\$/g
      protectedText = protectedText.replace(dollarPattern, (match) => {
        // Normalize over-escaped backslashes for LaTeX expressions
        const normalized = normalizeLaTeXEscaping(match)
        const placeholder = `__DOLLAR_${dollarIndex}__`
        allDollarExpressions.push({ placeholder, original: normalized })
        dollarIndex++
        return placeholder
      })
      
      // Restore all expressions (LLM handles currency formatting correctly)
      let finalText = protectedText
      allDollarExpressions.forEach(({ placeholder, original }) => {
        finalText = finalText.replace(placeholder, original)
      })

      // Set raw HTML so KaTeX auto-render can see delimiters like $...$, $$...$$, \\(...\\), \\[...\\]
      el.innerHTML = finalText

      // Replace placeholders with actual script elements (must be done after innerHTML)
      if (tikzDiagrams.length > 0) {
        console.log(`MathText: Found ${tikzDiagrams.length} TikZ diagram(s) to process`)
        // Track processed diagrams to avoid duplicates
        if (!el._processedTikzDiagrams) {
          el._processedTikzDiagrams = new Set()
        }
        
        const normalizeCode = (code) => code.replace(/\\\\/g, '\\').replace(/\s+/g, ' ').trim()
        
        tikzDiagrams.forEach(({ placeholder, tikzCode }) => {
          // Normalize code for comparison
          const normalizedCode = normalizeCode(tikzCode)
          const codeHash = normalizedCode.substring(0, 100)
          
          // Check if we've already processed this diagram
          const isDuplicate = el._processedTikzDiagrams.has(codeHash)
          console.log(`MathText: Processing diagram placeholder ${placeholder}, duplicate: ${isDuplicate}, codeHash: ${codeHash.substring(0, 50)}...`)
          
          // Find text nodes containing the placeholder
          const walker = document.createTreeWalker(
            el,
            NodeFilter.SHOW_TEXT,
            null,
            false
          )
          
          let node
          while (node = walker.nextNode()) {
            if (node.textContent.includes(placeholder)) {
              const parent = node.parentNode
              const parts = node.textContent.split(placeholder)
              
              // Create fragment with text before, TikZ container (or nothing if duplicate), and text after
              const fragment = document.createDocumentFragment()
              
              if (parts[0]) {
                fragment.appendChild(document.createTextNode(parts[0]))
              }
              
              if (!isDuplicate) {
                // Mark as processed
                el._processedTikzDiagrams.add(codeHash)
                
                // Create TikZ container
                const tikzContainer = document.createElement('div')
                tikzContainer.className = 'tikz-diagram'
                tikzContainer.style.cssText = 'margin: 1rem 0; text-align: center; min-height: 100px; display: flex; flex-direction: column; align-items: center;'
                
                // Show loading indicator immediately
                const loadingDiv = document.createElement('div')
                loadingDiv.className = 'tikz-loading'
                loadingDiv.innerHTML = `
                  <div style="padding: 1.5rem; text-align: center;">
                    <div style="display: inline-block; width: 40px; height: 40px; border: 4px solid #f3f3f3; border-top: 4px solid #4a90e2; border-radius: 50%; animation: spin 1s linear infinite; margin-bottom: 0.5rem;"></div>
                    <div style="color: #666; font-size: 0.9rem;">Rendering diagram...</div>
                  </div>
                  <style>
                    @keyframes spin {
                      0% { transform: rotate(0deg); }
                      100% { transform: rotate(360deg); }
                    }
                  </style>
                `
                tikzContainer.appendChild(loadingDiv)
                
                // Create script element (must be created, not inserted as HTML)
                const script = document.createElement('script')
                script.type = 'text/tikz'
                // tikzCode is already unescaped, so use it directly
                script.textContent = tikzCode
                // Store the unescaped code in a data attribute for fallback use
                script.setAttribute('data-tikz-code', tikzCode)
                script.style.display = 'none' // Hide script element
                tikzContainer.appendChild(script)
                
                fragment.appendChild(tikzContainer)
              }
              // If duplicate, just skip adding the container (placeholder will be removed)
              
              if (parts[1]) {
                fragment.appendChild(document.createTextNode(parts[1]))
              }
              
              parent.replaceChild(fragment, node)
              break
            }
          }
        })
      }

      // Render TikZ diagrams first (before KaTeX)
      // Check if TikZ diagrams are present
      if (tikzDiagrams.length > 0) {
        // Wait for DOM to update, then process TikZ
        const processTikz = () => {
          if (typeof window === 'undefined') return
          
          // Check for TikZJax in various possible locations
          const tikzjax = window.tikzjax || window.TikZJax || window.tikzJax
          
          if (tikzjax) {
            try {
              // Find all script tags with type="text/tikz" in the element
              const tikzScripts = el.querySelectorAll('script[type="text/tikz"]')
              if (tikzScripts.length > 0) {
                console.log(`Found ${tikzScripts.length} TikZ script(s) to render`)
                
                // Set up observers to detect when TikZJax finishes rendering
                tikzScripts.forEach(script => {
                  const container = script.parentElement
                  if (container && container.classList.contains('tikz-diagram')) {
                    // Watch for SVG/canvas elements to appear (TikZJax renders to these)
                    const observer = new MutationObserver((mutations) => {
                      const hasRendered = container.querySelector('svg, canvas')
                      const loadingDiv = container.querySelector('.tikz-loading')
                      if (hasRendered && loadingDiv) {
                        loadingDiv.remove()
                        // Center-align SVG/canvas elements
                        const svg = container.querySelector('svg')
                        const canvas = container.querySelector('canvas')
                        if (svg) {
                          svg.style.cssText = 'max-width: 100%; height: auto; margin: 0 auto; display: block;'
                        }
                        if (canvas) {
                          canvas.style.cssText = 'max-width: 100%; height: auto; margin: 0 auto; display: block;'
                        }
                        observer.disconnect()
                      }
                    })
                    observer.observe(container, { childList: true, subtree: true })
                    
                    // Timeout fallback: if TikZJax doesn't render within 10 seconds, use backend API
                    setTimeout(() => {
                      const hasRendered = container.querySelector('svg, canvas')
                      const hasBackendRendered = container.querySelector('.tikz-rendered')
                      const loadingDiv = container.querySelector('.tikz-loading')
                      const isRendering = container._isRendering
                      // Only fallback if neither TikZJax nor backend has rendered, and not already rendering
                      if (!hasRendered && !hasBackendRendered && !isRendering && loadingDiv) {
                        console.warn('TikZJax timeout, falling back to backend API')
                        observer.disconnect()
                        // Fall through to backend API rendering
                        renderViaBackendAPI(script, container)
                      } else if (hasRendered) {
                        // TikZJax rendered successfully, disconnect observer
                        observer.disconnect()
                      } else if (isRendering) {
                        console.log('MathText: Backend API render already in progress, skipping timeout fallback')
                        observer.disconnect()
                      }
                    }, 10000)
                  }
                })
                
                // TikZJax should auto-process script tags, but we can try to trigger it
                // According to TikZJax docs, it processes all script[type="text/tikz"] automatically
                // But for dynamically added ones, we might need to trigger it
                
                // Try to dispatch a custom event or call processElements if available
                if (typeof tikzjax.processElements === 'function') {
                  tikzjax.processElements(el)
                  console.log('Called tikzjax.processElements')
                } else if (typeof tikzjax.process === 'function') {
                  tikzScripts.forEach(script => {
                    tikzjax.process(script)
                  })
                  console.log('Called tikzjax.process for each script')
                } else {
                  // TikZJax should auto-process - log for debugging
                  console.log('TikZJax found, waiting for auto-processing. Available methods:', Object.keys(tikzjax))
                  console.log('TikZ scripts found:', tikzScripts.length)
                  
                  // Force a re-render by cloning and replacing (triggers TikZJax to process)
                  const clone = el.cloneNode(true)
                  el.parentNode?.replaceChild(clone, el)
                  // Update ref to point to new element
                  if (ref.current) {
                    ref.current = clone
                  }
                }
              } else {
                console.warn('No TikZ scripts found in element after insertion')
              }
            } catch (e) {
              console.error('Failed to render TikZ', e, e.stack)
            }
          } else {
            // Check if script is still loading
            const tikzScriptTags = Array.from(document.querySelectorAll('script[src*="tikzjax"]'))
            const tikzScript = tikzScriptTags.find(s => s.src && s.src.includes('tikzjax'))
            
            if (tikzScript) {
              // Check if script has loaded
              const scriptLoaded = tikzScript.complete !== false && tikzScript.readyState !== 'loading'
              
              if (!scriptLoaded && attempts < 5) {
                // Script is still loading, wait a bit more
                attempts += 1
                setTimeout(processTikz, 500)
                return
              } else if (scriptLoaded && !window.tikzjax && !window.TikZJax && attempts < 8) {
                // Script loaded but TikZJax not immediately available - might need more time to initialize
                attempts += 1
                setTimeout(processTikz, 500)
                return
              } else if (scriptLoaded && !window.tikzjax && !window.TikZJax) {
                // Script loaded but TikZJax not available - TikZJax may auto-process scripts without exposing a global
                // Check if any SVG/canvas elements were created (indicating TikZJax processed the scripts)
                const processedElements = el.querySelectorAll('svg, canvas')
                if (processedElements.length > 0) {
                  console.log('TikZJax processed scripts (found', processedElements.length, 'rendered elements)')
                  return // Success - diagrams are rendered
                } else {
                  // No processed elements found - TikZJax isn't working
                  console.warn('TikZJax script loaded but not processing scripts. Showing fallback.')
                  attempts = 30 // Skip to fallback
                }
              }
            } else if (window.tikzjaxLoadError) {
              // Script failed to load
              console.warn('TikZJax script failed to load. Showing fallback.')
              attempts = 30
            } else if (attempts < 5) {
              // Script tag not found yet, might still be loading
              attempts += 1
              setTimeout(processTikz, 500)
              return
            } else {
              // No script tag found after retries
              console.warn('TikZJax script tag not found. Showing fallback.')
              attempts = 30
            }
            
            // After retries or if script failed, use backend API to render
            if (attempts >= 30 || window.tikzjaxLoadError) {
              // Use backend API to render TikZ diagrams
              const tikzScripts = el.querySelectorAll('script[type="text/tikz"]')
              tikzScripts.forEach(async (script) => {
                const container = script.parentElement
                if (container && container.classList.contains('tikz-diagram')) {
                  // Check if already rendered or rendering to prevent duplicate API calls
                  if (!container.querySelector('.tikz-rendered') && 
                      !container.querySelector('svg, canvas') &&
                      !container._isRendering) {
                    renderViaBackendAPI(script, container)
                  } else {
                    console.log('MathText: Skipping backend API call - already rendered or rendering')
                  }
                }
              })
              // Reset rendering flag after processing
              isRenderingRef.current = false
            } else {
              attempts += 1
              setTimeout(processTikz, 500)
            }
          }
        }
        
        // Use multiple delays to ensure DOM is fully updated
        requestAnimationFrame(() => {
          setTimeout(() => {
            requestAnimationFrame(() => {
              setTimeout(processTikz, 200)
            })
          }, 100)
        })
      } else {
        // No TikZ diagrams, reset rendering flag
        console.log('MathText: No TikZ diagrams found')
        isRenderingRef.current = false
      }

          // Render LaTeX math with KaTeX
      if (typeof window !== 'undefined' && window.renderMathInElement) {
        try {
          window.renderMathInElement(el, {
            delimiters: [
              { left: '$$', right: '$$', display: true },
              { left: '\\[', right: '\\]', display: true },
              { left: '$', right: '$', display: false },
              { left: '\\(', right: '\\)', display: false },
            ],
            throwOnError: false,
          })
        } catch (e) {
          console.error('Failed to render math', e)
        }
        // Reset rendering flag after KaTeX processing
        console.log('MathText: Render complete')
        isRenderingRef.current = false
      } else if (attempts < 5) {
        // KaTeX auto-render might not be ready yet; retry a few times
        attempts += 1
        setTimeout(doRender, 100)
      } else {
        // Reset rendering flag if KaTeX is not available
        console.log('MathText: KaTeX not available, resetting flag')
        isRenderingRef.current = false
      }
      } catch (error) {
        // Reset rendering flag on error
        isRenderingRef.current = false
        console.error('Error in MathText rendering:', error)
        // Show error message in the element
        if (el) {
          el.innerHTML = `<div style="padding: 1rem; color: var(--error); border: 1px solid var(--error); border-radius: 4px;">
            <strong>Error rendering content:</strong> ${error.message || 'Unknown error'}
          </div>`
        }
      }
    }

    doRender()

    return () => {
      cancelled = true
      isRenderingRef.current = false // Reset flag on cleanup
      
      // Clear rendering flags on all containers
      if (el) {
        const containers = el.querySelectorAll('.tikz-diagram')
        containers.forEach(container => {
          container._isRendering = false
        })
      }
    }
  }, [text])

  const Component = inline ? 'span' : 'div'

  return <Component ref={ref} />
}