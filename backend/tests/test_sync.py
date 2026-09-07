from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base
from app.firestore_sync import ArchivedApplicantError, FirestoreGateway, firebase_configured
from app.models import Applicant, Interview, SyncDraft, SyncLog
from app.pipeline.sync_profile import GeminiRateLimitError, extract_sync_profile
from app.routers import sync as sync_routes
from app.sync_schemas import (
    FirestoreSyncExtraction,
    SyncConfirmRequest,
    SyncProposalRequest,
)


class FakeSnapshot:
    def __init__(self, doc_id: str, data: dict | None):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return None if self._data is None else dict(self._data)


class FakeDocument:
    def __init__(self, store: dict, doc_id: str):
        self.store = store
        self.id = doc_id

    def get(self, transaction=None):
        return FakeSnapshot(self.id, self.store.get(self.id))

    def collection(self, name: str):
        return FakeCollection(self.store.setdefault(f"{self.id}/{name}", {}), name)


class FakeCollection:
    def __init__(self, store: dict, name: str = "applicants"):
        self.store = store
        self.name = name

    def stream(self):
        return [FakeSnapshot(doc_id, data) for doc_id, data in self.store.items()]

    def document(self, doc_id: str | None = None):
        return FakeDocument(self.store, doc_id or f"new-{len(self.store) + 1}")


class FakeTransaction:
    def set(self, ref: FakeDocument, data: dict):
        ref.store[ref.id] = dict(data)


class FakeClient:
    def __init__(self, applicants: dict):
        self._applicants = applicants

    def collection(self, name: str):
        assert name == "applicants"
        return FakeCollection(self._applicants)

    def transaction(self):
        return FakeTransaction()


class FakeFirestore:
    SERVER_TIMESTAMP = "SERVER_TIMESTAMP"

    @staticmethod
    def transactional(function):
        return function


class FirestoreSyncTests(unittest.TestCase):
    def gateway(self, applicants: dict) -> FirestoreGateway:
        return FirestoreGateway(FakeClient(applicants), FakeFirestore)

    def test_search_is_case_insensitive_and_exact_first(self):
        gateway = self.gateway(
            {
                "1": {"name": "Alex Smith", "archived": False},
                "2": {"name": "Alexander Jones", "archived": True},
            }
        )
        matches = gateway.search_applicants("alex smith")
        self.assertEqual([match.id for match in matches], ["1"])

    def test_archived_applicant_requires_explicit_unarchive(self):
        gateway = self.gateway({"1": {"name": "Alex", "archived": True}})
        with self.assertRaises(ArchivedApplicantError):
            gateway.write_reviewed_sync(
                applicant_id="1",
                new_applicant_name=None,
                approved_values={},
                note="Reviewed note",
                interview_id=7,
                approved_by="Recruiter",
                unarchive=False,
            )

    def test_legacy_archive_folder_is_also_blocked_and_can_be_cleared(self):
        applicants = {
            "legacy": {
                "name": "Legacy",
                "archived": False,
                "archiveFolder": "previousFY",
                "archivedFiscalYear": 2025,
            }
        }
        gateway = self.gateway(applicants)
        self.assertTrue(gateway.get_applicant("legacy").archived)
        with self.assertRaises(ArchivedApplicantError):
            gateway.write_reviewed_sync(
                applicant_id="legacy",
                new_applicant_name=None,
                approved_values={},
                note="Reviewed note",
                interview_id=7,
                approved_by="Recruiter",
                unarchive=False,
            )
        _, _, unarchived = gateway.write_reviewed_sync(
            applicant_id="legacy",
            new_applicant_name=None,
            approved_values={},
            note="Reviewed note",
            interview_id=7,
            approved_by="Recruiter",
            unarchive=True,
        )
        self.assertTrue(unarchived)
        self.assertFalse(applicants["legacy"]["archived"])
        self.assertIsNone(applicants["legacy"]["archiveFolder"])
        self.assertIsNone(applicants["legacy"]["archivedAt"])

    def test_reviewed_write_preserves_unapproved_fields_and_adds_note(self):
        applicants = {
            "1": {
                "name": "Alex",
                "phone": "555-0100",
                "physicalHealth": "",
                "legalIssues": "",
                "archived": False,
            }
        }
        gateway = self.gateway(applicants)
        applicant_id, note_id, unarchived = gateway.write_reviewed_sync(
            applicant_id="1",
            new_applicant_name=None,
            approved_values={"physicalHealth": "Prior knee surgery"},
            note="Interested in service.",
            interview_id=7,
            approved_by="Recruiter",
            unarchive=False,
        )
        self.assertEqual(applicant_id, "1")
        self.assertTrue(note_id.startswith("new-"))
        self.assertFalse(unarchived)
        self.assertEqual(applicants["1"]["phone"], "555-0100")
        self.assertTrue(applicants["1"]["flagNeedsReview"])
        self.assertEqual(applicants["1/notes"][note_id]["interviewId"], 7)

    def test_new_applicant_gets_pibase_defaults(self):
        applicants = {}
        gateway = self.gateway(applicants)
        applicant_id, _, _ = gateway.write_reviewed_sync(
            applicant_id=None,
            new_applicant_name="Taylor",
            approved_values={"dependents": 2},
            note="Reviewed note",
            interview_id=9,
            approved_by="Recruiter",
            unarchive=False,
        )
        self.assertEqual(applicants[applicant_id]["statusStage"], "Initial Appointment")
        self.assertEqual(applicants[applicant_id]["precedence"], "normal")
        self.assertEqual(applicants[applicant_id]["dependents"], 2)

    def test_fixed_option_values_do_not_get_guessed(self):
        extraction = FirestoreSyncExtraction.model_validate(
            {
                "educationLevel": {"value": "Associates-ish", "evidence": "two years"},
                "maritalStatus": {"value": "Partnered", "evidence": "my partner"},
            }
        )
        self.assertEqual(extraction.educationLevel.value, "")
        self.assertEqual(extraction.maritalStatus.value, "")
        self.assertIsNone(sync_routes._field_value(extraction, "educationLevel"))

    def test_numeric_strings_are_normalized_for_firestore(self):
        extraction = FirestoreSyncExtraction.model_validate(
            {
                "age": {"value": "26", "evidence": "I am 26"},
                "dependents": {"value": "2", "evidence": "two children"},
            }
        )
        self.assertEqual(extraction.age.value, 26)
        self.assertEqual(extraction.dependents.value, 2)

    def test_unknown_approved_field_is_rejected(self):
        with self.assertRaises(ValueError):
            SyncConfirmRequest(
                create_new=True,
                approved_fields=["statusStage"],
                approved_by="Recruiter",
            )

    def test_health_configuration_check_validates_credential_shape_and_project(self):
        original_path = settings.google_application_credentials
        original_project = settings.firestore_project_id
        with tempfile.TemporaryDirectory() as directory:
            credential = Path(directory) / "credential.json"
            settings.google_application_credentials = credential
            settings.firestore_project_id = "pi-base-a3a09"
            credential.write_text("not json")
            self.assertFalse(firebase_configured())
            credential.write_text(
                json.dumps(
                    {
                        "type": "service_account",
                        "project_id": "wrong-project",
                        "client_email": "test@example.invalid",
                        "private_key": "test-only",
                    }
                )
            )
            self.assertFalse(firebase_configured())
            credential.write_text(
                json.dumps(
                    {
                        "type": "service_account",
                        "project_id": "pi-base-a3a09",
                        "client_email": "test@example.invalid",
                        "private_key": "test-only",
                    }
                )
            )
            self.assertTrue(firebase_configured())
        settings.google_application_credentials = original_path
        settings.firestore_project_id = original_project

    def test_proposal_and_confirm_write_a_local_audit_log(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        local_applicant = Applicant(name="Taylor")
        db.add(local_applicant)
        db.flush()
        interview = Interview(applicant_id=local_applicant.id)
        db.add(interview)
        db.flush()
        extraction = FirestoreSyncExtraction.model_validate(
            {
                "applicant_name": {"value": "Taylor", "evidence": "My name is Taylor"},
                "physicalHealth": {"value": "No concerns", "evidence": "healthy"},
                "free_text_notes": "Interested in joining.",
            }
        )
        db.add(
            SyncDraft(
                interview_id=interview.id,
                data_json=extraction.model_dump_json(),
                model="gemini-3.6-flash",
            )
        )
        db.commit()

        applicants = {"remote-1": {"name": "Taylor", "archived": False}}
        gateway = self.gateway(applicants)
        proposal = sync_routes.proposal(
            interview.id,
            SyncProposalRequest(applicant_id="remote-1"),
            db,
            gateway,
        )
        health_change = next(
            change for change in proposal.changes if change.field == "physicalHealth"
        )
        self.assertTrue(health_change.changed)

        result = sync_routes.confirm(
            interview.id,
            SyncConfirmRequest(
                applicant_id="remote-1",
                approved_fields=["physicalHealth"],
                approved_by="Recruiter",
            ),
            db,
            gateway,
        )
        self.assertEqual(result.fields_written, ["physicalHealth"])
        self.assertEqual(db.query(SyncLog).count(), 1)
        db.close()

    def test_gemini_rate_limit_is_retried_then_surfaced(self):
        class RateLimited(Exception):
            status_code = 429

        fake_client = Mock()
        fake_client.models.generate_content.side_effect = RateLimited("limited")
        sleeps: list[float] = []
        original_key = settings.gemini_api_key
        settings.gemini_api_key = "test-only"
        try:
            with patch("google.genai.Client", return_value=fake_client):
                with self.assertRaises(GeminiRateLimitError) as caught:
                    extract_sync_profile(
                        "Applicant: synthetic transcript",
                        "Applicant",
                        sleep=sleeps.append,
                        jitter=lambda: 0,
                    )
        finally:
            settings.gemini_api_key = original_key
        self.assertEqual(sleeps, [1, 2, 4])
        self.assertEqual(caught.exception.retry_after_seconds, 8)


if __name__ == "__main__":
    unittest.main()
