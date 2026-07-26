"""Structured applicant-profile extraction via the Claude API.

We extract INTO a schema (structured JSON) rather than having the model
free-write a profile. Fields the transcript doesn't cover are returned as
"not mentioned" rather than guessed. The readable summary card is rendered by
the frontend from this JSON.
"""
from __future__ import annotations

from ..config import settings
from ..schemas import ApplicantProfile

# Per-field guidance is carried in the system prompt rather than in the Pydantic
# field descriptions. Pydantic emits those as a sibling of `$ref` (because each
# field is a ProfileField object), and that sibling is dropped when the schema
# is dereferenced — so the model would never see them. The descriptions stay on
# the model for documentation; this prompt is what actually reaches Claude.
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
- Keep each value under 20 words. Answer each field independently; do not carry
  information from one field into another.

Fields:
- age: the applicant's age in years, digits only (e.g. "26").
- physical_health: injuries, conditions, surgeries, limitations, fitness.
- prior_service_history: prior military or uniformed service — branch, years,
  role, and discharge type.
- legal_history: legal status and history — arrests, charges, convictions,
  citations, and current standing such as pending charges, probation, or parole.
- education_level: highest level of education completed, plus field of study if
  stated.
- marital_status: single, married, divorced, separated, or widowed.
- number_of_dependents: number of dependents or children.
- tattoos_brandings_piercings: tattoos, brandings, or piercings, including body
  location.
- free_text_notes: a concise summary of the applicant's stated goals,
  motivations, and any other relevant flags. Empty string if nothing notable.
"""


class ProfileExtractionError(RuntimeError):
    pass


def extract_profile(
    transcript_text: str, applicant_role: str
) -> tuple[ApplicantProfile, str]:
    """Return (profile, model_id). Raises ProfileExtractionError on failure."""
    if not settings.anthropic_api_key:
        raise ProfileExtractionError(
            "ANTHROPIC_API_KEY is not configured; profile extraction is disabled."
        )

    try:
        import anthropic
    except ImportError as e:  # pragma: no cover
        raise ProfileExtractionError("anthropic SDK is not installed.") from e

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    user_content = (
        f"The applicant is: {applicant_role}\n\n"
        f"Transcript:\n{transcript_text}"
    )

    try:
        response = client.messages.parse(
            model=settings.profile_model,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
            output_format=ApplicantProfile,
        )
    except Exception as e:
        raise ProfileExtractionError(f"Claude API call failed: {e}") from e

    if response.stop_reason == "refusal":
        raise ProfileExtractionError("Model refused to process the transcript.")

    profile = response.parsed_output
    if profile is None:
        raise ProfileExtractionError("Model did not return a parseable profile.")

    return profile, settings.profile_model
