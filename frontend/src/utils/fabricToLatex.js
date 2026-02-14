/**
 * Utility functions to convert Fabric.js canvas JSON to LaTeX/TikZ code
 */

/**
 * Convert canvas coordinates to graph coordinates
 * Canvas: origin at top-left (0,0), Y increases downward
 * Graph: origin at center, Y increases upward
 * 
 * @param {number} canvasX - X coordinate in canvas space
 * @param {number} canvasY - Y coordinate in canvas space
 * @param {number} width - Canvas width
 * @param {number} height - Canvas height
 * @param {number} scale - Pixels per graph unit (default: grid size)
 * @returns {[number, number]} - [graphX, graphY]
 */
function canvasToGraphCoords(canvasX, canvasY, width, height, scale = 20) {
  const centerX = width / 2;
  const centerY = height / 2;
  const graphX = (canvasX - centerX) / scale;
  const graphY = (centerY - canvasY) / scale; // Flip Y axis
  return [graphX, graphY];
}

/**
 * Parse SVG path commands to TikZ coordinates
 * Handles: M (move), L (line), Q (quadratic), C (cubic), Z (close)
 * 
 * @param {Array} path - Fabric.js path array (e.g., [["M", x, y], ["L", x, y], ...])
 * @param {number} offsetX - X offset from object's left position
 * @param {number} offsetY - Y offset from object's top position
 * @param {number} width - Canvas width
 * @param {number} height - Canvas height
 * @param {number} scale - Pixels per graph unit
 * @returns {Array} - Array of [x, y] coordinate pairs
 */
function parsePathToCoords(path, offsetX, offsetY, width, height, scale = 20) {
  const coords = [];
  let currentX = offsetX;
  let currentY = offsetY;
  
  for (const command of path) {
    if (!Array.isArray(command) || command.length === 0) continue;
    
    const cmd = command[0].toUpperCase();
    
    switch (cmd) {
      case 'M': // Move to
        if (command.length >= 3) {
          currentX = command[1] + offsetX;
          currentY = command[2] + offsetY;
          const [gx, gy] = canvasToGraphCoords(currentX, currentY, width, height, scale);
          coords.push([gx, gy]);
        }
        break;
        
      case 'L': // Line to
        if (command.length >= 3) {
          currentX = command[1] + offsetX;
          currentY = command[2] + offsetY;
          const [gx, gy] = canvasToGraphCoords(currentX, currentY, width, height, scale);
          coords.push([gx, gy]);
        }
        break;
        
      case 'Q': // Quadratic bezier
        if (command.length >= 5) {
          // For simplicity, convert to line segments
          // Could be improved to use TikZ's .. controls syntax
          const [gx1, gy1] = canvasToGraphCoords(
            command[1] + offsetX, 
            command[2] + offsetY, 
            width, height, scale
          );
          const [gx2, gy2] = canvasToGraphCoords(
            command[3] + offsetX, 
            command[4] + offsetY, 
            width, height, scale
          );
          // Add control point and end point
          coords.push([gx1, gy1]);
          coords.push([gx2, gy2]);
          currentX = command[3] + offsetX;
          currentY = command[4] + offsetY;
        }
        break;
        
      case 'C': // Cubic bezier
        if (command.length >= 7) {
          // For simplicity, convert to line segments
          // Could be improved to use TikZ's .. controls syntax
          const [gx1, gy1] = canvasToGraphCoords(
            command[1] + offsetX, 
            command[2] + offsetY, 
            width, height, scale
          );
          const [gx2, gy2] = canvasToGraphCoords(
            command[3] + offsetX, 
            command[4] + offsetY, 
            width, height, scale
          );
          const [gx3, gy3] = canvasToGraphCoords(
            command[5] + offsetX, 
            command[6] + offsetY, 
            width, height, scale
          );
          coords.push([gx1, gy1]);
          coords.push([gx2, gy2]);
          coords.push([gx3, gy3]);
          currentX = command[5] + offsetX;
          currentY = command[6] + offsetY;
        }
        break;
        
      case 'Z': // Close path
        // Close the path by returning to first point
        if (coords.length > 0) {
          coords.push([...coords[0]]);
        }
        break;
        
      default:
        // Unknown command, skip
        break;
    }
  }
  
  return coords;
}

/**
 * Format a number for LaTeX (remove unnecessary decimals)
 * 
 * @param {number} num - Number to format
 * @returns {string} - Formatted number string
 */
function formatNumber(num) {
  // Round to 2 decimal places, remove trailing zeros
  const rounded = Math.round(num * 100) / 100;
  if (Math.abs(rounded - Math.round(rounded)) < 0.01) {
    return Math.round(rounded).toString();
  }
  return rounded.toFixed(2).replace(/\.?0+$/, '');
}

/**
 * Convert Fabric.js JSON to LaTeX/TikZ code
 * 
 * @param {Object|string} fabricData - Fabric.js canvas JSON (object or string)
 * @param {Object} options - Conversion options
 * @param {number} options.width - Canvas width (default: 600)
 * @param {number} options.height - Canvas height (default: 400)
 * @param {number} options.scale - Pixels per graph unit (default: 20)
 * @param {boolean} options.usePgfplots - Use pgfplots axis environment (default: true for graphs)
 * @param {string} options.lineColor - Line color (default: 'black')
 * @param {number} options.lineWidth - Line width in pt (default: 1.5)
 * @returns {string} - LaTeX/TikZ code
 */
export function fabricToLatex(fabricData, options = {}) {
  const {
    width = 600,
    height = 400,
    scale = 20,
    usePgfplots = true,
    lineColor = 'black',
    lineWidth = 1.5
  } = options;
  
  // Parse input if it's a string
  let data;
  if (typeof fabricData === 'string') {
    try {
      data = JSON.parse(fabricData);
    } catch (e) {
      throw new Error('Invalid JSON format');
    }
  } else {
    data = fabricData;
  }
  
  if (!data || !data.objects || !Array.isArray(data.objects)) {
    return '% No drawing data to convert';
  }
  
  const tikzCommands = [];
  const allCoords = [];
  
  // Process each object
  data.objects.forEach((obj, index) => {
    try {
      if (obj.type === 'path') {
        // Free-drawn path
        const path = obj.path || [];
        const offsetX = obj.left || 0;
        const offsetY = obj.top || 0;
        
        const coords = parsePathToCoords(path, offsetX, offsetY, width, height, scale);
        
        if (coords.length > 0) {
          allCoords.push(...coords);
          
          // Convert to TikZ coordinates string
          const coordString = coords.map(([x, y]) => 
            `(${formatNumber(x)},${formatNumber(y)})`
          ).join(' -- ');
          
          const color = obj.stroke || lineColor;
          const strokeWidth = obj.strokeWidth ? (obj.strokeWidth / scale) * lineWidth : lineWidth;
          
          tikzCommands.push(`    \\draw[${color}, line width=${strokeWidth.toFixed(2)}pt] ${coordString};`);
        }
      } else if (obj.type === 'line') {
        // Point-to-point line
        const x1 = obj.x1 || 0;
        const y1 = obj.y1 || 0;
        const x2 = obj.x2 || 0;
        const y2 = obj.y2 || 0;
        
        const [gx1, gy1] = canvasToGraphCoords(x1, y1, width, height, scale);
        const [gx2, gy2] = canvasToGraphCoords(x2, y2, width, height, scale);
        
        allCoords.push([gx1, gy1], [gx2, gy2]);
        
        const color = obj.stroke || lineColor;
        const strokeWidth = obj.strokeWidth ? (obj.strokeWidth / scale) * lineWidth : lineWidth;
        
        tikzCommands.push(
          `    \\draw[${color}, line width=${strokeWidth.toFixed(2)}pt] ` +
          `(${formatNumber(gx1)},${formatNumber(gy1)}) -- ` +
          `(${formatNumber(gx2)},${formatNumber(gy2)});`
        );
      } else if (obj.type === 'circle') {
        // Point marker
        const centerX = obj.left || 0;
        const centerY = obj.top || 0;
        const radius = (obj.radius || 3) / scale;
        
        const [gx, gy] = canvasToGraphCoords(centerX, centerY, width, height, scale);
        
        allCoords.push([gx, gy]);
        
        const color = obj.fill || obj.stroke || lineColor;
        
        tikzCommands.push(
          `    \\filldraw[${color}] (${formatNumber(gx)},${formatNumber(gy)}) ` +
          `circle (${formatNumber(radius)});`
        );
      }
      // Add more object types as needed (rect, polygon, etc.)
    } catch (error) {
      console.warn(`Error processing object ${index}:`, error);
    }
  });
  
  if (tikzCommands.length === 0) {
    return '% No valid drawing objects found';
  }
  
  // Calculate axis limits from all coordinates
  let xMin = -10, xMax = 10, yMin = -10, yMax = 10;
  if (allCoords.length > 0) {
    const xs = allCoords.map(([x]) => x);
    const ys = allCoords.map(([, y]) => y);
    xMin = Math.floor(Math.min(...xs)) - 1;
    xMax = Math.ceil(Math.max(...xs)) + 1;
    yMin = Math.floor(Math.min(...ys)) - 1;
    yMax = Math.ceil(Math.max(...ys)) + 1;
  }
  
  // Generate LaTeX code
  if (usePgfplots) {
    // Use pgfplots for graphs with axes
    return `\\begin{tikzpicture}
\\begin{axis}[
    axis lines = middle,
    grid = both,
    width = 10cm,
    height = 10cm,
    xmin = ${xMin}, xmax = ${xMax},
    ymin = ${yMin}, ymax = ${yMax},
    xtick distance = 1,
    ytick distance = 1,
    xlabel = {\\$x\\$},
    ylabel = {\\$y\\$},
    clip = true
]
${tikzCommands.join('\n')}
\\end{axis}
\\end{tikzpicture}`;
  } else {
    // Plain TikZ for diagrams without axes
    return `\\begin{tikzpicture}[scale=0.5]
${tikzCommands.join('\n')}
\\end{tikzpicture}`;
  }
}

/**
 * Generate a complete LaTeX document with the TikZ code
 * 
 * @param {Object|string} fabricData - Fabric.js canvas JSON
 * @param {Object} options - Conversion options (same as fabricToLatex)
 * @returns {string} - Complete LaTeX document
 */
export function fabricToLatexDocument(fabricData, options = {}) {
  const tikzCode = fabricToLatex(fabricData, options);
  
  return `\\documentclass{article}
\\usepackage[utf8]{inputenc}
\\usepackage{tikz}
\\usepackage{pgfplots}
\\pgfplotsset{compat=1.18}

\\begin{document}

${tikzCode}

\\end{document}`;
}

/**
 * Copy text to clipboard (browser API)
 * 
 * @param {string} text - Text to copy
 * @returns {Promise<boolean>} - Success status
 */
export async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (err) {
    // Fallback for older browsers
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.opacity = '0';
    document.body.appendChild(textArea);
    textArea.select();
    try {
      document.execCommand('copy');
      document.body.removeChild(textArea);
      return true;
    } catch (e) {
      document.body.removeChild(textArea);
      return false;
    }
  }
}
