"""ORM models.

Data model
----------
Applicant  1---*  Interview  1---1  Transcript
                              1---1  Profile
                              1---1  Job (latest processing job)
Interview  *---*  Label  (via interview_labels)

Each interview is a single record tying together: applicant, interview date,
audio file, transcript, and extracted profile.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InterviewStatus(str, enum.Enum):
    """Workflow statuses. Stored as strings so the set stays easy to extend."""

    PENDING_REVIEW = "Pending Review"
    PRIORITY = "Priority"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class JobState(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


interview_labels = Table(
    "interview_labels",
    Base.metadata,
    Column("interview_id", ForeignKey("interviews.id", ondelete="CASCADE"), primary_key=True),
    Column("label_id", ForeignKey("labels.id", ondelete="CASCADE"), primary_key=True),
)


class Applicant(Base):
    __tablename__ = "applicants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    interviews: Mapped[list["Interview"]] = relationship(
        back_populates="applicant",
        cascade="all, delete-orphan",
        order_by="Interview.interview_date.desc()",
    )


class Label(Base):
    __tablename__ = "labels"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    color: Mapped[str] = mapped_column(String(16), default="#64748b")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    interviews: Mapped[list["Interview"]] = relationship(
        secondary=interview_labels, back_populates="labels"
    )


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    applicant_id: Mapped[int] = mapped_column(
        ForeignKey("applicants.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    interview_date: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    status: Mapped[str] = mapped_column(
        String(40), default=InterviewStatus.PENDING_REVIEW.value, index=True
    )

    audio_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    audio_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    applicant: Mapped[Applicant] = relationship(back_populates="interviews")
    labels: Mapped[list[Label]] = relationship(
        secondary=interview_labels, back_populates="interviews"
    )
    transcript: Mapped["Transcript | None"] = relationship(
        back_populates="interview", cascade="all, delete-orphan", uselist=False
    )
    profile: Mapped["Profile | None"] = relationship(
        back_populates="interview", cascade="all, delete-orphan", uselist=False
    )
    jobs: Mapped[list["Job"]] = relationship(
        back_populates="interview",
        cascade="all, delete-orphan",
        order_by="Job.created_at.desc()",
    )


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[int] = mapped_column(primary_key=True)
    interview_id: Mapped[int] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), unique=True
    )
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Full plain-text transcript (labeled, speaker-turn joined).
    text: Mapped[str] = mapped_column(Text, default="")
    # List[{speaker, start, end, text}] as JSON.
    segments_json: Mapped[str] = mapped_column(Text, default="[]")
    # Mapping of raw speaker id -> friendly role, e.g. {"Speaker 1": "Applicant"}.
    speaker_labels_json: Mapped[str] = mapped_column(Text, default="{}")
    # Which raw speaker id is the applicant (for profile extraction).
    applicant_speaker: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    interview: Mapped[Interview] = relationship(back_populates="transcript")


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    interview_id: Mapped[int] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), unique=True
    )
    # Structured profile as JSON (schema in schemas.ApplicantProfile).
    data_json: Mapped[str] = mapped_column(Text, default="{}")
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    interview: Mapped[Interview] = relationship(back_populates="profile")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    interview_id: Mapped[int] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40), default="transcribe")
    state: Mapped[str] = mapped_column(String(20), default=JobState.QUEUED.value)
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    stage: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    interview: Mapped[Interview] = relationship(back_populates="jobs")
