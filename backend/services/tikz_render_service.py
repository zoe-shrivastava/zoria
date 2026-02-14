"""Service for rendering TikZ diagrams to SVG/images."""

import logging
import aiohttp
import base64
import subprocess
import tempfile
import asyncio
import re
from pathlib import Path
from typing import Optional, Dict, Any
from io import BytesIO

logger = logging.getLogger(__name__)


class TikZRenderService:
    """Service for rendering TikZ code to SVG or PNG images."""
    
    def __init__(self):
        """Initialize the TikZ rendering service."""
        # QuickLaTeX API endpoint (free, but has rate limits)
        # Note: QuickLaTeX has limited TikZ support - it's optimized for math formulas
        self.quicklatex_url = "https://quicklatex.com/latex3.f"
        # Check if local LaTeX tools are available
        self.has_local_latex = self._check_local_latex()
    
    def _check_local_latex(self) -> bool:
        """Check if pdflatex and pdf2svg/dvisvgm are available."""
        try:
            # Check for pdflatex
            result = subprocess.run(
                ['pdflatex', '--version'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5
            )
            has_pdflatex = result.returncode == 0
            
            # Check for pdf2svg or dvisvgm
            has_pdf2svg = False
            has_dvisvgm = False
            try:
                result = subprocess.run(
                    ['pdf2svg', '--version'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=5
                )
                has_pdf2svg = result.returncode == 0
            except FileNotFoundError:
                pass
            
            try:
                result = subprocess.run(
                    ['dvisvgm', '--version'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=5
                )
                has_dvisvgm = result.returncode == 0
            except FileNotFoundError:
                pass
            
            has_converter = has_pdf2svg or has_dvisvgm
            if has_pdflatex and has_converter:
                logger.info(f"Local LaTeX available: pdflatex={has_pdflatex}, pdf2svg={has_pdf2svg}, dvisvgm={has_dvisvgm}")
                return True
            else:
                logger.warning(f"Local LaTeX partially available: pdflatex={has_pdflatex}, pdf2svg={has_pdf2svg}, dvisvgm={has_dvisvgm}")
                return False
        except Exception as e:
            logger.warning(f"Could not check for local LaTeX: {e}")
            return False
    
    def _fix_tikz_clipping(self, tikz_code: str) -> str:
        """
        Fix TikZ code to ensure proper clipping to prevent graphs from
        extending beyond the axis boundaries.
        
        Handles two cases:
        1. pgfplots axis environments - adds clip=true and restrict y to domain
        2. plain TikZ pictures - adds \clip command to limit drawing area
        
        Args:
            tikz_code: TikZ code
            
        Returns:
            Fixed TikZ code
        """
        original_code = tikz_code
        
        # Case 1: pgfplots axis environment
        if '\\begin{axis}' in tikz_code:
            def add_clipping_options(match):
                axis_start = match.group(1)  # \begin{axis}
                options = match.group(2) if match.group(2) else ''  # [options] or None
                
                additions = []
                
                # Always add clip=true for visual clipping to axis boundaries
                if 'clip=' not in (options or ''):
                    additions.append('clip=true')
                
                # Add restrict y to domain to prevent vertical overflow
                # This is especially important for exponential/logarithmic functions
                if 'restrict y to domain=' not in (options or ''):
                    # Use a reasonable default range that covers most educational graphs
                    additions.append('restrict y to domain=-50:50')
                
                if additions:
                    if options:
                        options = options.rstrip(']') + ',' + ','.join(additions) + ']'
                    else:
                        options = '[' + ','.join(additions) + ']'
                    logger.debug(f"Added clipping options to axis: {', '.join(additions)}")
                
                return axis_start + options
            
            tikz_code = re.sub(r'(\\begin\{axis\})(\[[^\]]*\])?', add_clipping_options, tikz_code)
        
        # Case 2: plain TikZ picture (no pgfplots)
        elif '\\begin{tikzpicture}' in tikz_code:
            # Check if \clip is already present
            if '\\clip' not in tikz_code:
                # Try to extract grid boundaries from the code
                # Pattern: (x1,y1) grid (x2,y2) or (-6,-6) grid (6,6)
                # Match: \(([-\d.]+),([-\d.]+)\)\s+grid\s+\(([-\d.]+),([-\d.]+)\)
                grid_match = re.search(r'\(([-\d.]+),([-\d.]+)\)\s+grid\s+\(([-\d.]+),([-\d.]+)\)', tikz_code)
                
                if grid_match:
                    # Extract grid boundaries
                    x1 = float(grid_match.group(1))  # First x coordinate
                    y1 = float(grid_match.group(2))  # First y coordinate
                    x2 = float(grid_match.group(3))  # Second x coordinate
                    y2 = float(grid_match.group(4))  # Second y coordinate
                    
                    # Determine min/max for rectangle
                    clip_x1 = min(x1, x2) - 0.5
                    clip_y1 = min(y1, y2) - 0.5
                    clip_x2 = max(x1, x2) + 0.5
                    clip_y2 = max(y1, y2) + 0.5
                    
                    # Add \clip command right after \begin{tikzpicture}
                    clip_command = f'\\clip ({clip_x1},{clip_y1}) rectangle ({clip_x2},{clip_y2});'
                    tikz_code = tikz_code.replace('\\begin{tikzpicture}', 
                                                  f'\\begin{{tikzpicture}}\n{clip_command}')
                    logger.info(f"Added \\clip command based on grid: {clip_command}")
                else:
                    # No grid found, try to extract from axis drawing commands
                    # Look for draw commands with coordinates to infer bounds
                    # Pattern: \draw[...] (x1,y1) -- (x2,y2) or similar
                    axis_match = re.findall(r'\(([-\d.]+),([-\d.]+)\)', tikz_code)
                    if axis_match:
                        coords = [(float(x), float(y)) for x, y in axis_match]
                        if coords:
                            xs = [c[0] for c in coords]
                            ys = [c[1] for c in coords]
                            clip_x1 = min(xs) - 1
                            clip_y1 = min(ys) - 1
                            clip_x2 = max(xs) + 1
                            clip_y2 = max(ys) + 1
                            
                            clip_command = f'\\clip ({clip_x1},{clip_y1}) rectangle ({clip_x2},{clip_y2});'
                            tikz_code = tikz_code.replace('\\begin{tikzpicture}', 
                                                          f'\\begin{{tikzpicture}}\n{clip_command}')
                            logger.info(f"Added \\clip command based on coordinates: {clip_command}")
                    else:
                        # No grid or coordinates found, use default reasonable bounds
                        clip_command = '\\clip (-10,-10) rectangle (10,10);'
                        tikz_code = tikz_code.replace('\\begin{tikzpicture}', 
                                                      f'\\begin{{tikzpicture}}\n{clip_command}')
                        logger.info(f"Added default \\clip command: {clip_command}")
        
        # Log original and updated code for debugging
        logger.info("=== TikZ Clipping Fix Debug ===")
        logger.info(f"ORIGINAL LaTeX (full code):\n{original_code}")
        
        if tikz_code != original_code:
            logger.info("✓ CHANGES APPLIED")
            logger.info(f"UPDATED LaTeX (full code):\n{tikz_code}")
        else:
            logger.info("✗ NO CHANGES - TikZ code unchanged")
            if '\\begin{axis}' in original_code:
                logger.info("Found \\begin{axis} - options may already be present")
            elif '\\begin{tikzpicture}' in original_code:
                logger.info("Found \\begin{tikzpicture} - \\clip may already be present")
        
        return tikz_code
    
    async def render_tikz_to_svg(
        self,
        tikz_code: str,
        use_quicklatex: bool = True
    ) -> Dict[str, Any]:
        """
        Render TikZ code to SVG using an external service.
        
        Args:
            tikz_code: TikZ code (e.g., "\\begin{tikzpicture}...\\end{tikzpicture}")
            use_quicklatex: If True, use QuickLaTeX; otherwise use iTex2Img
        
        Returns:
            Dict with 'success', 'svg_data' (base64), 'image_url', or 'error'
        """
        try:
            # Clean and prepare TikZ code
            tikz_code = tikz_code.strip()
            
            # Fix clipping issues at LaTeX level
            tikz_code = self._fix_tikz_clipping(tikz_code)
            
            # Wrap TikZ code in a complete LaTeX document
            # Use standalone class for better TikZ rendering (crops to content)
            latex_document = f"""\\documentclass{{standalone}}
\\usepackage{{tikz}}
\\usepackage{{pgfplots}}
\\pgfplotsset{{compat=1.18}}
\\begin{{document}}
{tikz_code}
\\end{{document}}"""
            
            # Try local LaTeX first if available (best quality)
            if self.has_local_latex:
                logger.info("Using local LaTeX compiler for TikZ rendering")
                result = await self._render_with_local_latex(latex_document)
                # If local LaTeX fails, fall back to QuickLaTeX if enabled
                if not result.get("success") and use_quicklatex:
                    logger.warning("Local LaTeX failed, falling back to QuickLaTeX")
                    return await self._render_with_quicklatex(latex_document)
                return result
            elif use_quicklatex:
                logger.warning("Local LaTeX not available, using QuickLaTeX (has limited TikZ support)")
                return await self._render_with_quicklatex(latex_document)
            else:
                # No local LaTeX and QuickLaTeX disabled - return error
                return {
                    "success": False,
                    "error": "No TikZ rendering service available. Local LaTeX not installed and QuickLaTeX disabled. Please rebuild Docker container with LaTeX tools or enable QuickLaTeX."
                }
                
        except Exception as e:
            logger.error(f"Error rendering TikZ: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _render_with_quicklatex(self, latex_document: str) -> Dict[str, Any]:
        """
        Render LaTeX/TikZ using QuickLaTeX API.
        
        QuickLaTeX returns a PNG image. We'll convert it or use it directly.
        """
        try:
            async with aiohttp.ClientSession() as session:
                # QuickLaTeX uses form data
                form_data = aiohttp.FormData()
                form_data.add_field('formula', latex_document)
                form_data.add_field('fsize', '17px')
                form_data.add_field('fcolor', '000000')
                form_data.add_field('mode', '0')  # 0 = PNG, 1 = GIF
                form_data.add_field('out', '1')   # 1 = PNG
                form_data.add_field('remhost', 'quicklatex.com')
                
                async with session.post(
                    self.quicklatex_url,
                    data=form_data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"QuickLaTeX API error {response.status}: {error_text}")
                        return {
                            "success": False,
                            "error": f"QuickLaTeX API returned {response.status}"
                        }
                    
                    # QuickLaTeX returns a response with image URL
                    response_text = await response.text()
                    logger.info(f"QuickLaTeX response: {response_text[:200]}")
                    
                    # Parse response (format: "0\n<image_url> <width> <height> <dpi>" or error codes)
                    # Example: "0\nhttps://quicklatex.com/.../image.png 0 608 40"
                    lines = response_text.strip().split('\n')
                    if len(lines) >= 2 and lines[0].strip() == '0':
                        # Extract URL from second line (URL may be followed by numbers)
                        url_line = lines[1].strip()
                        # URL is everything before the first space (or the whole line if no space)
                        image_url = url_line.split()[0] if ' ' in url_line else url_line
                        logger.info(f"QuickLaTeX image URL: {image_url}")
                        
                        # Fetch the image
                        async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=30)) as img_response:
                            if img_response.status == 200:
                                image_data = await img_response.read()
                                # Convert PNG to base64
                                image_b64 = base64.b64encode(image_data).decode('utf-8')
                                logger.info(f"Successfully fetched image, size: {len(image_data)} bytes")
                                return {
                                    "success": True,
                                    "image_url": image_url,
                                    "image_data": image_b64,
                                    "format": "png",
                                    "mime_type": "image/png"
                                }
                            else:
                                logger.error(f"Failed to fetch image from {image_url}: status {img_response.status}")
                                return {
                                    "success": False,
                                    "error": f"Failed to fetch image: HTTP {img_response.status}"
                                }
                    else:
                        # QuickLaTeX error codes: 1 = syntax error, 2 = server error, etc.
                        error_code = lines[0].strip() if lines else "unknown"
                        error_msg = lines[1].strip() if len(lines) > 1 else "Unknown error"
                        logger.error(f"QuickLaTeX error code {error_code}: {error_msg}")
                        return {
                            "success": False,
                            "error": f"QuickLaTeX error {error_code}: {error_msg}"
                        }
                    
        except aiohttp.ClientError as e:
            logger.error(f"Network error calling QuickLaTeX: {e}")
            return {
                "success": False,
                "error": f"Network error: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Error with QuickLaTeX: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    def _fix_svg_clipping(self, svg_content: str) -> str:
        """
        Fix SVG clipping issues where graph extends beyond axis grid.
        
        Simple, direct approach: Find clipPath rectangle paths and replace
        width/height to match viewBox dimensions.
        
        Args:
            svg_content: Raw SVG content as string
            
        Returns:
            Fixed SVG content
        """
        try:
            # Extract viewBox dimensions
            viewbox_match = re.search(r'viewBox=["\']([^"\']+)["\']', svg_content)
            if not viewbox_match:
                logger.warning("Could not extract viewBox from SVG")
                return svg_content
            
            viewbox_parts = viewbox_match.group(1).strip().split()
            if len(viewbox_parts) < 4:
                logger.warning(f"Invalid viewBox format: {viewbox_match.group(1)}")
                return svg_content
            
            viewbox_width = float(viewbox_parts[2])
            viewbox_height = float(viewbox_parts[3])
            
            logger.debug(f"SVG viewBox: {viewbox_width}x{viewbox_height}")
            
            # Simple, direct fix: Find clipPath with rectangle path and replace dimensions
            # Pattern: M 0 0 L <width> 0 L <width> <height> L 0 <height> Z
            # Match this pattern inside clipPath elements and replace width/height with viewBox dimensions
            
            def fix_clippath_rectangle(match):
                clip_start = match.group(1)
                clip_content = match.group(2)
                clip_end = match.group(3)
                
                # Find path with rectangle pattern: M 0 0 L w 0 L w h L 0 h Z
                # Match: M\s+0\s+0\s+L\s+(\d+\.?\d*)\s+0\s+L\s+\1\s+(\d+\.?\d*)\s+L\s+0\s+\2\s+Z
                rect_pattern = r'(M\s+0\s+0\s+L\s+)([\d.]+)(\s+0\s+L\s+)([\d.]+)(\s+)([\d.]+)(\s+L\s+0\s+)([\d.]+)(\s+Z)'
                
                def replace_dimensions(m):
                    m_part = m.group(1)
                    w1 = float(m.group(2))
                    l1 = m.group(3)
                    w2 = float(m.group(4))
                    space = m.group(5)
                    h1 = float(m.group(6))
                    l2 = m.group(7)
                    h2 = float(m.group(8))
                    z_part = m.group(9)
                    
                    # Verify it's a rectangle (w1==w2, h1==h2)
                    if abs(w1 - w2) < 0.1 and abs(h1 - h2) < 0.1:
                        width = w1
                        height = h1
                        
                        # Only fix if dimensions don't match viewBox
                        if abs(width - viewbox_width) > 0.1 or abs(height - viewbox_height) > 0.1:
                            logger.info(f"Fixing clipPath: {width}x{height} -> {viewbox_width}x{viewbox_height}")
                            return f'{m_part}{viewbox_width}{l1}{viewbox_width}{space}{viewbox_height}{l2}{viewbox_height}{z_part}'
                    
                    return m.group(0)
                
                # Fix the path inside this clipPath
                fixed_content = re.sub(rect_pattern, replace_dimensions, clip_content)
                
                if fixed_content != clip_content:
                    return clip_start + fixed_content + clip_end
                
                return match.group(0)
            
            # Apply to all clipPath elements
            clippath_pattern = r'(<clipPath[^>]*>)(.*?)(</clipPath>)'
            svg_content = re.sub(clippath_pattern, fix_clippath_rectangle, svg_content, flags=re.DOTALL)
            
            return svg_content
            
        except Exception as e:
            logger.warning(f"Error fixing SVG clipping: {e}. Returning original SVG.", exc_info=True)
            return svg_content
    
    async def _render_with_local_latex(self, latex_document: str) -> Dict[str, Any]:
        """
        Render TikZ using local pdflatex and pdf2svg/dvisvgm.
        
        This provides the best quality rendering for TikZ diagrams.
        """
        try:
            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._render_with_local_latex_sync,
                latex_document
            )
            return result
        except Exception as e:
            logger.error(f"Error with local LaTeX rendering: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    def _render_with_local_latex_sync(self, latex_document: str) -> Dict[str, Any]:
        """Synchronous version of local LaTeX rendering."""
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Write LaTeX file
                tex_file = Path(temp_dir) / 'tikz_render.tex'
                tex_file.write_text(latex_document, encoding='utf-8')
                
                # Compile LaTeX to PDF
                # Note: pdflatex outputs version info and package loading messages to stderr/stdout even on success
                # So we check if PDF exists rather than relying solely on returncode
                result = subprocess.run(
                    ['pdflatex', '-interaction=nonstopmode', '-output-directory', temp_dir, str(tex_file)],
                    cwd=temp_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,  # Combine stderr into stdout
                    timeout=30
                )
                
                pdf_file = Path(temp_dir) / 'tikz_render.pdf'
                
                # Check if PDF was generated (primary check)
                if not pdf_file.exists():
                    # PDF not generated - check for actual errors
                    if result.returncode != 0:
                        output_text = result.stdout.decode('utf-8', errors='replace') if result.stdout else ''
                        # Look for actual error messages (not just version info)
                        error_lines = [line for line in output_text.split('\n') 
                                      if 'error' in line.lower() or '!' in line or 'fatal' in line.lower()]
                        error_msg = '\n'.join(error_lines[-10:]) if error_lines else output_text[-500:]
                        logger.error(f"pdflatex failed (returncode={result.returncode}): {error_msg[:500]}")
                        return {
                            "success": False,
                            "error": f"LaTeX compilation failed: {error_msg[:200]}"
                        }
                    else:
                        # Returncode 0 but no PDF - might be a different issue
                        logger.error("pdflatex returned success but PDF file was not generated")
                        return {
                            "success": False,
                            "error": "PDF file was not generated despite successful compilation"
                        }
                
                # PDF exists - check returncode for warnings (but don't fail if PDF exists)
                if result.returncode != 0:
                    output_text = result.stdout.decode('utf-8', errors='replace') if result.stdout else ''
                    logger.warning(f"pdflatex returned non-zero exit code ({result.returncode}) but PDF was generated. Proceeding with conversion. Output: {output_text[-500:]}")
                    # Continue processing - PDF exists, so we can still convert it
                
                # Convert PDF to SVG
                svg_file = Path(temp_dir) / 'tikz_render.svg'
                
                # Try pdf2svg first, then dvisvgm
                if subprocess.run(['which', 'pdf2svg'], stdout=subprocess.PIPE).returncode == 0:
                    result = subprocess.run(
                        ['pdf2svg', str(pdf_file), str(svg_file)],
                        cwd=temp_dir,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=30
                    )
                elif subprocess.run(['which', 'dvisvgm'], stdout=subprocess.PIPE).returncode == 0:
                    # First convert PDF to DVI, then to SVG
                    dvi_file = Path(temp_dir) / 'tikz_render.dvi'
                    result = subprocess.run(
                        ['pdftodvi', str(pdf_file), str(dvi_file)],
                        cwd=temp_dir,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=30
                    )
                    if result.returncode == 0:
                        result = subprocess.run(
                            ['dvisvgm', '--no-fonts', '--output=%f', str(dvi_file)],
                            cwd=temp_dir,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            timeout=30
                        )
                else:
                    return {
                        "success": False,
                        "error": "Neither pdf2svg nor dvisvgm is available"
                    }
                
                if result.returncode != 0 or not svg_file.exists():
                    error_msg = result.stderr.decode('utf-8', errors='replace') if result.stderr else 'Unknown error'
                    logger.error(f"SVG conversion failed: {error_msg[:500]}")
                    return {
                        "success": False,
                        "error": f"SVG conversion failed: {error_msg[:200]}"
                    }
                
                # Read SVG and encode as base64
                svg_data = svg_file.read_text(encoding='utf-8')
                
                # Fix clipping issues where graph extends beyond axis grid
                svg_data = self._fix_svg_clipping(svg_data)
                
                svg_b64 = base64.b64encode(svg_data.encode('utf-8')).decode('utf-8')
                
                logger.info(f"Successfully rendered TikZ to SVG, size: {len(svg_data)} bytes")
                return {
                    "success": True,
                    "svg_data": svg_b64,
                    "format": "svg",
                    "mime_type": "image/svg+xml"
                }
                
            except subprocess.TimeoutExpired:
                logger.error("LaTeX rendering timed out")
                return {
                    "success": False,
                    "error": "Rendering timed out"
                }
            except Exception as e:
                logger.error(f"Error in local LaTeX rendering: {e}", exc_info=True)
                return {
                    "success": False,
                    "error": str(e)
                }
