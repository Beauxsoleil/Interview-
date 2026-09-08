from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from app.config import settings
from app.pipeline.profile import (
    ProfileExtractionError,
    ProfileServiceUnavailable,
    extract_profile,
)
from app.schemas import ApplicantProfile


class ProfileExtractionTests(unittest.TestCase):
    def setUp(self):
        self.original_key = settings.gemini_api_key
        self.original_base = settings.profile_retry_base_seconds
        self.original_max = settings.profile_retry_max_seconds
        settings.gemini_api_key = "test-only"
        settings.profile_retry_base_seconds = 5
        settings.profile_retry_max_seconds = 60

    def tearDown(self):
        settings.gemini_api_key = self.original_key
        settings.profile_retry_base_seconds = self.original_base
        settings.profile_retry_max_seconds = self.original_max

    def test_transient_503_retries_then_succeeds(self):
        class Unavailable(Exception):
            status_code = 503

        profile = ApplicantProfile()
        fake_client = Mock()
        fake_client.models.generate_content.side_effect = [
            Unavailable("high demand"),
            Unavailable("high demand"),
            Mock(parsed=profile),
        ]
        sleeps: list[float] = []
        retries: list[tuple[int, int, float, int | None]] = []

        with patch("google.genai.Client", return_value=fake_client):
            result, model = extract_profile(
                "Applicant: synthetic transcript",
                "Applicant",
                max_attempts=5,
                sleep=sleeps.append,
                jitter=lambda: 0,
                on_retry=lambda *args: retries.append(args),
            )

        self.assertIs(result, profile)
        self.assertEqual(model, settings.profile_model)
        self.assertEqual(sleeps, [5, 10])
        self.assertEqual(retries, [(1, 5, 5.0, 503), (2, 5, 10.0, 503)])

    def test_transient_503_exhaustion_has_typed_safe_error(self):
        class Unavailable(Exception):
            status_code = 503

        fake_client = Mock()
        fake_client.models.generate_content.side_effect = Unavailable("provider detail")
        with patch("google.genai.Client", return_value=fake_client):
            with self.assertRaises(ProfileServiceUnavailable) as caught:
                extract_profile(
                    "synthetic transcript",
                    "Applicant",
                    max_attempts=3,
                    sleep=lambda _delay: None,
                    jitter=lambda: 0,
                )

        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(caught.exception.attempts, 3)
        self.assertNotIn("provider detail", str(caught.exception))

    def test_non_transient_error_is_not_retried(self):
        class BadRequest(Exception):
            status_code = 400

        fake_client = Mock()
        fake_client.models.generate_content.side_effect = BadRequest("bad request")
        sleeps: list[float] = []
        with patch("google.genai.Client", return_value=fake_client):
            with self.assertRaises(ProfileExtractionError):
                extract_profile(
                    "synthetic transcript",
                    "Applicant",
                    max_attempts=5,
                    sleep=sleeps.append,
                )

        self.assertEqual(sleeps, [])


if __name__ == "__main__":
    unittest.main()
