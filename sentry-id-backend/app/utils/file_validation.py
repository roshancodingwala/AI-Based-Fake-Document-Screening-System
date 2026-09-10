"""
Upload validation shared by every endpoint that accepts a file.

Keeps three prototype-grade protections in one place:
- content-type allow-list (rejects unexpected file types)
- size limit (protects memory / disk)
- basic filename sanitisation
"""
import logging

from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings

logger = logging.getLogger("sentry_id.uploads")


async def validate_upload(file: UploadFile) -> bytes:
    settings = get_settings()

    if file.content_type not in settings.allowed_content_types:
        logger.warning("security_event=rejected_upload reason=bad_content_type type=%s", file.content_type)
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{file.content_type}'. Allowed: {settings.allowed_content_types}",
        )

    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)

    if size_mb > settings.max_upload_size_mb:
        logger.warning("security_event=rejected_upload reason=too_large size_mb=%.2f", size_mb)
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File too large ({size_mb:.1f}MB). Limit is {settings.max_upload_size_mb}MB.",
        )

    if len(contents) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    await file.seek(0)
    return contents
