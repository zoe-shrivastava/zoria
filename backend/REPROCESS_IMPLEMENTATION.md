# Document Reprocessing Implementation ✅

## Summary

Reprocessing functionality has been implemented with UI button support. Documents stuck in `uploaded`, `failed`, or `parsed` status can now be reprocessed with optional cleanup of existing data.

## What Was Implemented

### 1. Backend Changes

#### DocumentProcessor (`workers/document_processor.py`)
- ✅ Added `cleanup_document_data()` method
  - Deletes chunks, questions, visuals for the document
  - Preserves concepts if linked to other documents
  - Transactional cleanup
  
- ✅ Enhanced `process_document()` method
  - Added `cleanup_first` parameter
  - Optionally cleans existing data before processing

#### DocumentService (`services/document_service.py`)
- ✅ Added `reprocess_document()` method
  - Handles Phase 1 (parsing) if needed
  - Optionally cleans existing data
  - Triggers Phase 2 (background processing)
  - Parameters:
    - `cleanup_existing`: Delete existing chunks/questions/visuals first
    - `skip_phase1`: Skip parsing if markdown/concepts already exist

#### API Endpoint (`api/v1/documents.py`)
- ✅ Added `POST /api/v1/documents/{document_id}/reprocess`
  - Request body: `{ cleanup_existing: bool, skip_phase1: bool }`
  - Access control enforced
  - Returns processing status

#### Schema Updates (`schemas/document.py`)
- ✅ Added `status` field to `DocumentResponse`
- ✅ Added `processing_started_at` and `processing_completed_at` fields

### 2. Frontend Changes

#### API Service (`frontend/src/services/api.js`)
- ✅ Added `documents.reprocess()` method
  - Calls reprocess endpoint
  - Handles cleanup and phase skipping options

#### DocumentList Component (`frontend/src/components/DocumentList.jsx`)
- ✅ Added "Reprocess" button
  - Shows for documents with status: `uploaded`, `failed`, or `parsed`
  - Disabled while processing
  - Shows "Processing..." text during operation
  
- ✅ Added status badge
  - Color-coded status indicators
  - Shows current document status
  
- ✅ Added `handleReprocess()` function
  - Confirmation dialog
  - Smart phase detection (needs Phase 1 or not)
  - Loading state management

## Usage

### From UI
1. Navigate to document list
2. Documents with status `uploaded`, `failed`, or `parsed` show "Reprocess" button
3. Click "Reprocess"
4. Confirm the action
5. Document status updates to `processing`
6. Background processing runs
7. Status updates to `ready` when complete

### From API
```bash
POST /api/v1/documents/{document_id}/reprocess
Content-Type: application/json

{
  "cleanup_existing": true,
  "skip_phase1": false
}
```

### From Python
```python
from services.document_service import DocumentService

service = DocumentService()
result = await service.reprocess_document(
    document_id="...",
    cleanup_existing=True,
    skip_phase1=False
)
```

## Cleanup Behavior

When `cleanup_existing=True`:
- ✅ Deletes all chunks for the document
- ✅ Deletes all questions linked to document's concepts
- ✅ Deletes all visuals linked to document's concepts
- ✅ Deletes question-skill relationships
- ✅ Deletes concept-document links
- ✅ Deletes concepts ONLY if they're not linked to other documents
- ✅ Preserves document record and file

**Safe**: Concepts used by multiple documents are preserved.

## Status Flow

```
uploaded → [Reprocess] → parsed → processing → ready
failed   → [Reprocess] → parsed → processing → ready
parsed   → [Reprocess] → processing → ready
```

## UI Features

- **Status Badge**: Color-coded status indicator
  - `uploaded`: Yellow
  - `parsed`: Light blue
  - `processing`: Green
  - `ready`: Green
  - `failed`: Red

- **Reprocess Button**: 
  - Only shows for reprocessable statuses
  - Disabled during processing
  - Shows loading state

- **Smart Detection**: 
  - Automatically detects if Phase 1 is needed
  - Shows appropriate confirmation message

## Files Modified

### Backend
- `workers/document_processor.py` - Cleanup method + cleanup_first parameter
- `services/document_service.py` - Reprocess method
- `api/v1/documents.py` - Reprocess endpoint
- `schemas/document.py` - Status fields
- `core/background_tasks.py` - Cleanup support

### Frontend
- `services/api.js` - Reprocess API method
- `components/DocumentList.jsx` - UI button + status badge

## Testing

To test reprocessing:

1. **Find a document in `uploaded` status**:
   ```sql
   SELECT id, filename, status FROM documents WHERE status = 'uploaded';
   ```

2. **Click "Reprocess" button in UI** or call API

3. **Verify cleanup** (if cleanup_existing=true):
   ```sql
   SELECT COUNT(*) FROM content_chunks WHERE document_id = '...';
   SELECT COUNT(*) FROM questions WHERE concept_id IN (
     SELECT id FROM concepts WHERE document_id = '...'
   );
   ```

4. **Verify reprocessing**:
   - Status should change: `uploaded` → `parsed` → `processing` → `ready`
   - New chunks/questions should be created
   - Document should be searchable when `ready`

## Notes

- Cleanup is **safe**: Won't delete concepts used by other documents
- Reprocessing is **idempotent**: Can be run multiple times
- Background processing is **non-blocking**: API returns immediately
- Status is **tracked**: Full lifecycle visibility
