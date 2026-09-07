from __future__ import annotations

import unittest

from interview_pipeline_core import PipelineConfig, run_pipeline, using_stub
from interview_pipeline_core.merge import DiarSegment, TextUnit, merge, render_text
from interview_pipeline_core.transcription import (
    AudioWindow,
    _owned_units,
    audio_windows,
)


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

    def test_long_audio_windows_include_context_and_cover_timeline(self) -> None:
        self.assertEqual(
            audio_windows(905, 300, 8),
            [
                AudioWindow(0, 308, 0, 300),
                AudioWindow(292, 608, 300, 600),
                AudioWindow(592, 905, 600, 900),
                AudioWindow(892, 905, 900, 905),
            ],
        )

    def test_overlap_units_are_owned_by_only_one_window(self) -> None:
        first = AudioWindow(0, 308, 0, 300)
        second = AudioWindow(292, 608, 300, 600)
        first_units = _owned_units(
            [TextUnit(299.7, 300.1, "boundary")], first
        )
        second_units = _owned_units(
            [TextUnit(7.7, 8.1, "boundary")], second
        )

        self.assertEqual(len(first_units) + len(second_units), 1)

    def test_short_final_window_keeps_its_last_unit(self) -> None:
        final = AudioWindow(892, 905, 900, 905)
        units = _owned_units([TextUnit(12.5, 13.0, "done")], final)
        self.assertEqual(
            [(u.start, u.end, u.text) for u in units],
            [(904.5, 905.0, "done")],
        )

    def test_invalid_chunk_configuration_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PipelineConfig(
                transcription_chunk_seconds=10,
                transcription_overlap_seconds=5,
            )


if __name__ == "__main__":
    unittest.main()
