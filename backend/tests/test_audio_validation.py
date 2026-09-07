from __future__ import annotations

import json
import unittest

from app.audio_validation import AudioValidationError, parse_ffprobe_output


class AudioValidationTests(unittest.TestCase):
    def test_reads_audio_stream_and_duration(self):
        metadata = parse_ffprobe_output(json.dumps({
            "streams": [{"codec_type": "audio", "codec_name": "aac"}],
            "format": {"duration": "901.25"},
        }))
        self.assertEqual(metadata.codec, "aac")
        self.assertEqual(metadata.duration_seconds, 901.25)

    def test_rejects_video_without_audio(self):
        with self.assertRaises(AudioValidationError):
            parse_ffprobe_output(json.dumps({
                "streams": [{"codec_type": "video", "codec_name": "h264"}],
                "format": {"duration": "10"},
            }))

    def test_rejects_invalid_duration(self):
        with self.assertRaises(AudioValidationError):
            parse_ffprobe_output(json.dumps({
                "streams": [{"codec_type": "audio", "codec_name": "mp3"}],
                "format": {"duration": "nan"},
            }))


if __name__ == "__main__":
    unittest.main()
