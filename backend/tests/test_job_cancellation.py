from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import jobs
from app.database import Base
from app.models import Applicant, Interview, Job, JobState
from app.routers import interviews as interview_routes


class JobCancellationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.temp = tempfile.TemporaryDirectory()
        self.audio = Path(self.temp.name) / "active.mp3"
        self.audio.write_bytes(b"test audio placeholder")

        applicant = Applicant(name="Cancellation Test")
        self.db.add(applicant)
        self.db.flush()
        interview = Interview(applicant_id=applicant.id, audio_path=str(self.audio))
        self.db.add(interview)
        self.db.flush()
        job = Job(
            interview_id=interview.id,
            kind="transcribe",
            state=JobState.RUNNING.value,
        )
        self.db.add(job)
        self.db.commit()
        self.interview_id = interview.id
        self.job_id = job.id

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.temp.cleanup()

    def test_delete_requests_cancel_before_removing_audio(self):
        interview_routes.delete_interview(self.interview_id, self.db)

        interview = self.db.get(Interview, self.interview_id)
        job = self.db.get(Job, self.job_id)
        self.assertTrue(interview.delete_requested)
        self.assertEqual(job.state, JobState.CANCELLED.value)
        self.assertTrue(self.audio.exists())

    def test_worker_finalization_deletes_record_and_audio(self):
        interview_routes.delete_interview(self.interview_id, self.db)
        jobs._finalize_cancelled_job(self.db, self.job_id)

        self.assertIsNone(self.db.get(Interview, self.interview_id))
        self.assertFalse(self.audio.exists())

    def test_cancelled_job_rejects_worker_progress_update(self):
        interview_routes.delete_interview(self.interview_id, self.db)
        job = self.db.get(Job, self.job_id)
        with self.assertRaises(jobs.JobCancelled):
            jobs._update_job(self.db, job, progress=75, stage="transcription")

    def test_profile_extraction_is_queued_for_background_processing(self):
        session_factory = sessionmaker(bind=self.engine)
        fake_executor = Mock()
        with (
            patch.object(jobs, "SessionLocal", session_factory),
            patch.object(jobs, "_executor", fake_executor),
        ):
            job_id = jobs.enqueue_profile_extraction(self.interview_id)

        queued = self.db.get(Job, job_id)
        self.db.refresh(queued)
        self.assertEqual(queued.kind, "profile")
        self.assertEqual(queued.state, JobState.QUEUED.value)
        fake_executor.submit.assert_called_once_with(jobs._run_profile_job, job_id)


if __name__ == "__main__":
    unittest.main()
