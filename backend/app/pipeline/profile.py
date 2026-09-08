"""Structured applicant-profile extraction via the Gemini API.

We extract INTO a schema (structured JSON) rather than having the model
free-write a profile. Fields the transcript doesn't cover are returned as
"not mentioned" rather than guessed. The readable summary card is rendered by
the frontend from this JSON.
"""
from __future__ import annotations

import random
import re
import time
from collections.abc import Callable

from ..config import settings
from ..schemas import ApplicantProfile

SYSTEM_PROMPT = """\
You extract a structured profile of the APPLICANT from an interview transcript.

Rules:
- Only extract information about the applicant (the speaker identified below).
  Ignore facts that are only about the interviewer.
- Extract ONLY what the transcript states or clearly implies. If a field is not
  covered, set its value to exactly "not mentioned". Never guess or infer beyond
  the evidence.
- For each field, include a short supporting quote or paraphrase as evidence,
  or null when the field is "not mentioned".
- free_text_notes: a concise summary of the applicant's stated goals,
  motivations, and any other relevant flags. Empty string if nothing notable.
"""


class ProfileExtractionError(RuntimeError):
    pass


class ProfileServiceUnavailable(ProfileExtractionError):
    """A temporary provider failure that is safe for the caller to retry."""

    def __init__(self, status_code: int | None, attempts: int):
        self.status_code = status_code
        self.attempts = attempts
        super().__init__(
            f"Gemini remained temporarily unavailable after {attempts} attempts."
        )


def _status_code(error: Exception) -> int | None:
    raw_status = getattr(error, "status_code", None) or getattr(error, "code", None)
    try:
        return int(raw_status)
    except (TypeError, ValueError):
        match = re.search(r"\b(429|500|502|503|504)\b", str(error))
        return int(match.group(1)) if match else None


def _is_transient(error: Exception) -> tuple[bool, int | None]:
    status = _status_code(error)
    text = str(error).upper()
    transient = status in {429, 500, 502, 503, 504} or any(
        marker in text
        for marker in ("RESOURCE_EXHAUSTED", "UNAVAILABLE", "DEADLINE_EXCEEDED")
    )
    return transient, status


def extract_profile(
    transcript_text: str,
    applicant_role: str,
    *,
    max_attempts: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = random.random,
    on_retry: Callable[[int, int, float, int | None], None] | None = None,
) -> tuple[ApplicantProfile, str]:
    """Return (profile, model_id). Raises ProfileExtractionError on failure."""
    if not settings.gemini_api_key:
        raise ProfileExtractionError(
            "GEMINI_API_KEY is not configured; profile extraction is disabled."
        )

    try:
        from google import genai
        from google.genai import types
    except ImportError as e:  # pragma: no cover
        raise ProfileExtractionError("Google Gen AI SDK is not installed.") from e

    client = genai.Client(api_key=settings.gemini_api_key)

    user_content = (
        f"The applicant is: {applicant_role}\n\n"
        f"Transcript:\n{transcript_text}"
    )

    attempts = max_attempts or settings.profile_retry_attempts
    if attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    for attempt in range(1, attempts + 1):
        try:
            response = client.models.generate_content(
                model=settings.profile_model,
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=ApplicantProfile,
                ),
            )
            break
        except Exception as error:
            transient, status = _is_transient(error)
            if not transient:
                raise ProfileExtractionError(
                    f"Gemini API call failed: {error}"
                ) from error
            if attempt == attempts:
                raise ProfileServiceUnavailable(status, attempts) from error
            base_delay = min(
                settings.profile_retry_max_seconds,
                settings.profile_retry_base_seconds * (2 ** (attempt - 1)),
            )
            delay = base_delay + (jitter() * min(2.0, base_delay * 0.2))
            if on_retry:
                on_retry(attempt, attempts, delay, status)
            sleep(delay)

    profile = response.parsed
    if profile is None:
        raise ProfileExtractionError("Model did not return a parseable profile.")
    if not isinstance(profile, ApplicantProfile):
        profile = ApplicantProfile.model_validate(profile)

    return profile, settings.profile_model
