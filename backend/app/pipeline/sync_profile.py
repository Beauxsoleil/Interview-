"""Gemini extraction shaped directly for a reviewed PIBASE sync."""

from __future__ import annotations

import random
import time
from collections.abc import Callable

from ..config import settings
from ..sync_schemas import FirestoreSyncExtraction

SYSTEM_PROMPT = """\
Extract facts only about the applicant from this recruiter interview.
Never use facts that apply only to the interviewer. Never guess.
For every absent or unclear field, use exactly "not mentioned" and null evidence.
For every stated value, include a short supporting quote or paraphrase.

Use the Firestore-shaped field names in the response. educationLevel may only be
"HS Diploma", "GED", "Some College", "Degree", "", or "not mentioned".
maritalStatus may only be "Single", "Married", "Divorced", "Other", "", or
"not mentioned". Do not infer workflow/contact fields such as phone, email,
statusStage, precedence, waiver details, next actions, or dates.
free_text_notes is a concise factual summary suitable for a recruiter note.
"""


class SyncProfileError(RuntimeError):
    pass


class GeminiRateLimitError(SyncProfileError):
    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"Gemini rate limited the request; retry in {retry_after_seconds}s.")


def _is_rate_limit(error: Exception) -> bool:
    status = getattr(error, "status_code", None) or getattr(error, "code", None)
    return status == 429 or "429" in str(error) or "RESOURCE_EXHAUSTED" in str(error)


def extract_sync_profile(
    transcript_text: str,
    applicant_role: str,
    *,
    max_attempts: int = 4,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = random.random,
) -> tuple[FirestoreSyncExtraction, str]:
    if not settings.gemini_api_key:
        raise SyncProfileError("GEMINI_API_KEY is not configured.")

    try:
        from google import genai
        from google.genai import types
    except ImportError as error:  # pragma: no cover
        raise SyncProfileError("Google Gen AI SDK is not installed.") from error

    client = genai.Client(api_key=settings.gemini_api_key)
    content = f"The applicant is: {applicant_role}\n\nTranscript:\n{transcript_text}"

    for attempt in range(max_attempts):
        try:
            response = client.models.generate_content(
                model=settings.profile_model,
                contents=content,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=FirestoreSyncExtraction,
                ),
            )
            parsed = response.parsed
            if parsed is None:
                raise SyncProfileError("Gemini returned an empty or refused response.")
            if not isinstance(parsed, FirestoreSyncExtraction):
                parsed = FirestoreSyncExtraction.model_validate(parsed)
            return parsed, settings.profile_model
        except SyncProfileError:
            raise
        except Exception as error:
            if not _is_rate_limit(error):
                raise SyncProfileError(f"Gemini sync extraction failed: {error}") from error
            retry_after = min(60, round((2**attempt) + jitter()))
            if attempt == max_attempts - 1:
                raise GeminiRateLimitError(retry_after) from error
            sleep(retry_after)

    raise SyncProfileError("Gemini sync extraction failed.")

