from pydantic import BaseModel


class TimestampSettings(BaseModel):
    """Admin-configurable display settings for timestamps in the UI."""

    # Document list: upload / processing timestamps
    show_document_timestamps: bool = True

    # Test list: creation timestamps
    show_test_timestamps: bool = True

    # Study guides & evaluation report: generated_at timestamps
    show_study_guide_timestamps: bool = True

