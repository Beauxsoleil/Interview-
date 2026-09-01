from __future__ import annotations

import unittest
from unittest.mock import patch

from interview_pipeline_core import (
    PipelineConfig,
    real_backend_available,
    render_text,
    run_pipeline,
)


class PipelineConfigTests(unittest.TestCase):
    def test_rejects_unknown_backend(self) -> None:
        with self.assertRaisesRegex(ValueError, "pipeline_backend"):
            PipelineConfig(pipeline_backend="unknown")

    def test_rejects_invalid_speaker_hint(self) -> None:
        with self.assertRaisesRegex(ValueError, "default_num_speakers"):
            PipelineConfig(default_num_speakers=0)


class StubPipelineTests(unittest.TestCase):
    def test_optional_backend_detection_always_returns_boolean(self) -> None:
        self.assertIsInstance(real_backend_available(), bool)

    def test_forced_stub_returns_labeled_transcript(self) -> None:
        progress: list[tuple[int, str]] = []

        result = run_pipeline(
            "unused.m4a",
            on_progress=lambda percent, stage: progress.append((percent, stage)),
            config=PipelineConfig(pipeline_backend="stub"),
        )

        self.assertEqual(result["backend"], "stub")
        self.assertEqual(result["language"], "en")
        self.assertEqual(result["speakers"], ["Speaker 1", "Speaker 2"])
        self.assertTrue(result["turns"])
        self.assertIn("Speaker 1:", render_text(result["turns"]))
        self.assertEqual(progress[-1], (95, "finalizing"))

    @patch("interview_pipeline_core.runner.real_backend_available", return_value=False)
    def test_auto_falls_back_to_stub(self, _available) -> None:
        result = run_pipeline("unused.wav", config=PipelineConfig())

        self.assertEqual(result["backend"], "stub")


if __name__ == "__main__":
    unittest.main()
