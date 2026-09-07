from __future__ import annotations

import unittest

from interview_pipeline_core import PipelineConfig, run_pipeline, using_stub
from interview_pipeline_core.merge import DiarSegment, TextUnit, merge, render_text


class PipelineTests(unittest.TestCase):
    def test_stub_pipeline_runs_end_to_end(self) -> None:
        config = PipelineConfig(backend="stub")
        result = run_pipeline("unused.wav", config)

        self.assertEqual(result["backend"], "stub")
        self.assertEqual(result["language"], "en")
        self.assertEqual(result["speakers"], ["Speaker 1", "Speaker 2"])
        self.assertGreater(len(result["turns"]), 1)
        self.assertIn("Speaker 2:", render_text(result["turns"]))

    def test_merge_assigns_by_overlap(self) -> None:
        diarized = [
            DiarSegment("A", 0, 4),
            DiarSegment("B", 4, 8),
        ]
        units = [TextUnit(1, 2, "hello"), TextUnit(5, 6, "there")]

        self.assertEqual(
            [turn["speaker"] for turn in merge(diarized, units)], ["A", "B"]
        )

    def test_forced_stub_does_not_probe_ml_stack(self) -> None:
        self.assertTrue(using_stub(PipelineConfig(backend="stub")))

    def test_invalid_backend_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PipelineConfig(backend="invalid")


if __name__ == "__main__":
    unittest.main()

