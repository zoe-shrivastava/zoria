"""TikZ rendering API endpoints."""

import logging
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from typing import Optional

from services.tikz_render_service import TikZRenderService
from core.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


class TikZRenderRequest(BaseModel):
    """Request model for TikZ rendering."""
    tikz_code: str
    format: Optional[str] = "svg"  # "svg" or "png"
    use_quicklatex: Optional[bool] = False  # Default to False - QuickLaTeX has limited TikZ support


class TikZRenderResponse(BaseModel):
    """Response model for TikZ rendering."""
    success: bool
    image_data: Optional[str] = None  # Base64 encoded image
    image_url: Optional[str] = None  # Direct URL to image (if available)
    format: Optional[str] = None  # "svg" or "png"
    mime_type: Optional[str] = None
    error: Optional[str] = None


@router.post("/render", response_model=TikZRenderResponse)
async def render_tikz(
    request: TikZRenderRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Render TikZ code to SVG or PNG image.
    
    POST /api/v1/tikz/render
    
    Requires authentication. Accepts TikZ code and returns a base64-encoded image.
    """
    tikz_service = TikZRenderService()
    
    try:
        logger.info(f"Rendering TikZ diagram (code length: {len(request.tikz_code)}, use_quicklatex: {request.use_quicklatex})")
        
        # Render TikZ code
        result = await tikz_service.render_tikz_to_svg(
            tikz_code=request.tikz_code,
            use_quicklatex=request.use_quicklatex
        )
        
        logger.info(f"TikZ rendering result: success={result.get('success')}, error={result.get('error')}")
        
        if not result.get("success"):
            error_msg = result.get("error", "Failed to render TikZ diagram")
            logger.error(f"TikZ rendering failed: {error_msg}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )
        
        # Return response
        response_data = {
            "success": True,
            "format": result.get("format", "png"),
            "mime_type": result.get("mime_type", "image/png")
        }
        
        # Include image data or URL
        if "image_data" in result:
            response_data["image_data"] = result["image_data"]
            logger.info(f"Image data length: {len(result['image_data'])}")
        if "image_url" in result:
            response_data["image_url"] = result["image_url"]
        if "svg_data" in result:
            response_data["image_data"] = result["svg_data"]
            response_data["format"] = "svg"
            response_data["mime_type"] = "image/svg+xml"
            logger.info(f"SVG data length: {len(result['svg_data'])}")
        
        # Validate that we have image data
        if "image_data" not in response_data:
            logger.error("No image data in response")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Rendering succeeded but no image data returned"
            )
        
        return TikZRenderResponse(**response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error rendering TikZ: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to render TikZ diagram: {str(e)}"
        )
