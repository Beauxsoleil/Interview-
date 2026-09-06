"""Structured applicant-profile extraction via the Gemini API.

We extract INTO a schema (structured JSON) rather than having the model
free-write a profile. Fields the transcript doesn't cover are returned as
"not mentioned" rather than guessed. The readable summary card is rendered by
the frontend from this JSON.
"""
from __future__ import annotations

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


def extract_profile(
    transcript_text: str, applicant_role: str
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
    except Exception as e:
        raise ProfileExtractionError(f"Gemini API call failed: {e}") from e

    profile = response.parsed
    if profile is None:
        raise ProfileExtractionError("Model did not return a parseable profile.")
    if not isinstance(profile, ApplicantProfile):
        profile = ApplicantProfile.model_validate(profile)

    return profile, settings.profile_model
