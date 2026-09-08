from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.combined_interviews import (
    create_combined_interview,
    mark_combined_parent_stale,
    rebuild_combined_interview,
)
from app.database import Base
from app.models import Applicant, Interview, Profile, SyncDraft, Transcript, utcnow
from app.routers import interviews as interview_routes


class CombinedInterviewTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        applicant = Applicant(name="Multi Part Applicant")
        self.db.add(applicant)
        self.db.flush()
        self.source_ids = [
            self._source(
                applicant.id,
                "part-one.m4a",
                10,
                [
                    {"speaker": "S1", "start": 0, "end": 2, "text": "First answer"},
                    {"speaker": "S2", "start": 2, "end": 4, "text": "Next question"},
                ],
                "S1",
                {"S1": "Candidate", "S2": "Interviewer"},
            ),
            self._source(
                applicant.id,
                "part-two.m4a",
                20,
                [{"speaker": "A", "start": 1, "end": 3, "text": "Second answer"}],
                "A",
                {"A": "Applicant"},
            ),
        ]
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _source(self, applicant_id, filename, duration, segments, applicant_speaker, labels):
        interview = Interview(
            applicant_id=applicant_id,
            audio_filename=filename,
            audio_path=f"/tmp/{filename}",
            audio_duration_seconds=duration,
            interview_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.db.add(interview)
        self.db.flush()
        self.db.add(
            Transcript(
                interview_id=interview.id,
                text="source",
                segments_json=json.dumps(segments),
                speaker_labels_json=json.dumps(labels),
                applicant_speaker=applicant_speaker,
                revision=1,
                reviewed_at=utcnow(),
            )
        )
        return interview.id

    def _combine(self):
        return create_combined_interview(
            self.db, self.source_ids, "Complete interview"
        )

    def test_combine_preserves_sources_and_adds_timing_provenance(self):
        combined = self._combine()
        self.db.refresh(combined)
        segments = json.loads(combined.transcript.segments_json)

        self.assertTrue(combined.is_combined)
        self.assertEqual(combined.audio_duration_seconds, 30)
        self.assertEqual([part.id for part in combined.source_parts], self.source_ids)
        self.assertEqual([part.part_number for part in combined.source_parts], [1, 2])
        self.assertEqual(segments[0]["speaker"], "Applicant")
        self.assertEqual(segments[-1]["start"], 11)
        self.assertEqual(segments[-1]["source_start"], 1)
        self.assertEqual(segments[-1]["source_interview_id"], self.source_ids[1])
        self.assertEqual(segments[-1]["part_number"], 2)
        self.assertIsNone(combined.transcript.reviewed_at)
        self.assertIsNotNone(self.db.get(Interview, self.source_ids[0]).transcript)

    def test_normal_list_hides_attached_sources(self):
        combined = self._combine()
        rows = interview_routes.list_interviews(db=self.db)
        self.assertEqual([row.id for row in rows], [combined.id])
        self.assertEqual(rows[0].part_count, 2)

    def test_deleting_combined_restores_sources_and_blocks_part_deletion(self):
        combined = self._combine()
        with self.assertRaises(HTTPException) as caught:
            interview_routes.delete_interview(self.source_ids[0], self.db)
        self.assertEqual(caught.exception.status_code, 409)

        interview_routes.delete_interview(combined.id, self.db)

        self.assertIsNone(self.db.get(Interview, combined.id))
        for source_id in self.source_ids:
            source = self.db.get(Interview, source_id)
            self.assertIsNotNone(source)
            self.assertIsNone(source.combined_parent_id)
            self.assertIsNone(source.part_number)

    def test_source_change_invalidates_derivatives_until_rebuild(self):
        combined = self._combine()
        combined.transcript.reviewed_at = utcnow()
        self.db.add(
            Profile(
                interview_id=combined.id,
                data_json="{}",
                source_transcript_revision=combined.transcript.revision,
            )
        )
        self.db.add(
            SyncDraft(
                interview_id=combined.id,
                data_json="{}",
                model="test",
                source_transcript_revision=combined.transcript.revision,
            )
        )
        self.db.commit()
        old_revision = combined.transcript.revision

        source = self.db.get(Interview, self.source_ids[0])
        mark_combined_parent_stale(self.db, source)
        self.db.commit()
        self.db.refresh(combined)

        self.assertTrue(combined.combined_needs_rebuild)
        self.assertIsNone(combined.transcript.reviewed_at)
        self.assertIsNone(combined.profile)
        self.assertIsNone(self.db.query(SyncDraft).filter_by(interview_id=combined.id).first())
        with self.assertRaises(HTTPException) as caught:
            interview_routes.review_transcript(combined.id, self.db)
        self.assertEqual(caught.exception.status_code, 409)

        rebuild_combined_interview(self.db, combined)
        self.assertFalse(combined.combined_needs_rebuild)
        self.assertEqual(combined.transcript.revision, old_revision + 1)
        self.assertIsNone(combined.transcript.reviewed_at)


if __name__ == "__main__":
    unittest.main()
