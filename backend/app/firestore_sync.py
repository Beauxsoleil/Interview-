"""Privileged, server-only access to the PIBASE Firestore project."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from .config import settings
from .sync_schemas import FirestoreApplicant


class FirestoreConfigurationError(RuntimeError):
    pass


class ArchivedApplicantError(RuntimeError):
    pass


class SyncConflictError(RuntimeError):
    pass


def firebase_configured() -> bool:
    path = settings.google_application_credentials
    if not path or not Path(path).is_file():
        return False
    try:
        metadata = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return bool(
        metadata.get("type") == "service_account"
        and metadata.get("project_id") == settings.firestore_project_id
        and metadata.get("client_email")
        and metadata.get("private_key")
    )


class FirestoreGateway:
    def __init__(self, client, firestore_module):
        self.client = client
        self.firestore = firestore_module

    @property
    def applicants(self):
        return self.client.collection("applicants")

    @staticmethod
    def _applicant(snapshot) -> FirestoreApplicant:
        data = snapshot.to_dict() or {}
        return FirestoreApplicant(
            id=snapshot.id,
            name=data.get("name", ""),
            phone=data.get("phone", ""),
            statusStage=data.get("statusStage", ""),
            archived=bool(data.get("archived", False) or data.get("archiveFolder")),
            data=data,
        )

    def search_applicants(self, query: str) -> list[FirestoreApplicant]:
        needle = query.strip().casefold()
        matches = [
            self._applicant(snapshot)
            for snapshot in self.applicants.stream()
            if not needle or needle in str((snapshot.to_dict() or {}).get("name", "")).casefold()
        ]
        return sorted(
            matches,
            key=lambda applicant: (
                applicant.name.casefold() != needle,
                applicant.name.casefold(),
            ),
        )[:20]

    def get_applicant(self, applicant_id: str) -> FirestoreApplicant | None:
        snapshot = self.applicants.document(applicant_id).get()
        return self._applicant(snapshot) if snapshot.exists else None

    def write_reviewed_sync(
        self,
        *,
        applicant_id: str | None,
        new_applicant_name: str | None,
        approved_values: dict,
        note: str,
        interview_id: int,
        approved_by: str,
        unarchive: bool,
        request_id: str | None = None,
        expected_values: dict | None = None,
    ) -> tuple[str, str, bool]:
        applicant_ref = (
            self.applicants.document(applicant_id)
            if applicant_id
            else self.applicants.document()
        )
        note_ref = applicant_ref.collection("notes").document(request_id)
        transaction = self.client.transaction()

        @self.firestore.transactional
        def commit(txn):
            snapshot = applicant_ref.get(transaction=txn)
            existing = (snapshot.to_dict() or {}) if snapshot.exists else None
            if existing is None:
                name = (new_applicant_name or "").strip()
                if not name:
                    raise ValueError("A name is required to create an applicant.")
                merged = {
                    "name": name,
                    "phone": "",
                    "email": "",
                    "generalArea": "",
                    "precedence": "normal",
                    "priorService": "",
                    "age": None,
                    "physicalHealth": "",
                    "legalIssues": "",
                    "educationLevel": "",
                    "maritalStatus": "",
                    "dependents": 0,
                    "tattoosBrandsPiercings": "",
                    "statusStage": "Initial Appointment",
                    "waiverType": None,
                    "waiverStatus": None,
                    "nextAction": "",
                    "nextActionDate": "",
                    "archived": False,
                    "archiveFolder": None,
                    "archivedAt": None,
                    "archivedFiscalYear": None,
                    "createdAt": self.firestore.SERVER_TIMESTAMP,
                }
            else:
                is_archived = bool(
                    existing.get("archived", False) or existing.get("archiveFolder")
                )
                if is_archived and not unarchive:
                    raise ArchivedApplicantError(
                        "This applicant is archived; explicitly unarchive before syncing."
                    )
                merged = dict(existing)
                for field, expected in (expected_values or {}).items():
                    if existing.get(field) != expected:
                        raise SyncConflictError(
                            f"PIBASE field '{field}' changed after review. Refresh the proposal."
                        )

            merged.update(approved_values)
            merged["flagNeedsReview"] = bool(
                str(merged.get("physicalHealth") or "").strip()
                or str(merged.get("legalIssues") or "").strip()
            )
            merged["updatedAt"] = self.firestore.SERVER_TIMESTAMP
            if unarchive and existing is not None and is_archived:
                merged["archived"] = False
                merged["archiveFolder"] = None
                merged["archivedAt"] = None
                merged["archivedFiscalYear"] = None
                merged["previousStage"] = None
                merged["restoredAt"] = self.firestore.SERVER_TIMESTAMP
            txn.set(applicant_ref, merged)
            txn.set(
                note_ref,
                {
                    "text": note,
                    "createdAt": self.firestore.SERVER_TIMESTAMP,
                    "source": "Interview sync",
                    "interviewId": interview_id,
                    "approvedBy": approved_by,
                },
            )
            return bool(existing and is_archived and unarchive)

        was_unarchived = commit(transaction)
        return applicant_ref.id, note_ref.id, was_unarchived


_gateway: FirestoreGateway | None = None
_gateway_lock = Lock()


def get_firestore_gateway() -> FirestoreGateway:
    global _gateway
    if _gateway is not None:
        return _gateway
    with _gateway_lock:
        if _gateway is not None:
            return _gateway
        credential_path = settings.google_application_credentials
        if not credential_path or not Path(credential_path).is_file():
            raise FirestoreConfigurationError(
                "GOOGLE_APPLICATION_CREDENTIALS does not reference a readable file."
            )
        metadata = json.loads(Path(credential_path).read_text())
        if metadata.get("project_id") != settings.firestore_project_id:
            raise FirestoreConfigurationError(
                "Firebase credential project does not match FIRESTORE_PROJECT_ID."
            )
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
        except ImportError as error:  # pragma: no cover
            raise FirestoreConfigurationError("firebase-admin is not installed.") from error

        app_name = "interview-pibase-sync"
        try:
            firebase_app = firebase_admin.get_app(app_name)
        except ValueError:
            firebase_app = firebase_admin.initialize_app(
                credentials.Certificate(str(credential_path)),
                {"projectId": settings.firestore_project_id},
                name=app_name,
            )
        _gateway = FirestoreGateway(firestore.client(app=firebase_app), firestore)
        return _gateway
