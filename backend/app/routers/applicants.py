from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Applicant, Interview
from ..schemas import ApplicantCreate, ApplicantOut

router = APIRouter(prefix="/api/applicants", tags=["applicants"])


def _to_out(db: Session, a: Applicant) -> ApplicantOut:
    count = (
        db.query(func.count(Interview.id))
        .filter(Interview.applicant_id == a.id)
        .scalar()
    )
    return ApplicantOut(
        id=a.id, name=a.name, notes=a.notes, created_at=a.created_at,
        interview_count=count or 0,
    )


@router.get("", response_model=list[ApplicantOut])
def list_applicants(db: Session = Depends(get_db)):
    applicants = db.query(Applicant).order_by(Applicant.name).all()
    return [_to_out(db, a) for a in applicants]


@router.post("", response_model=ApplicantOut, status_code=201)
def create_applicant(payload: ApplicantCreate, db: Session = Depends(get_db)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "Name is required.")
    existing = db.query(Applicant).filter(func.lower(Applicant.name) == name.lower()).first()
    if existing:
        return _to_out(db, existing)
    applicant = Applicant(name=name, notes=payload.notes)
    db.add(applicant)
    db.commit()
    db.refresh(applicant)
    return _to_out(db, applicant)


@router.get("/{applicant_id}", response_model=ApplicantOut)
def get_applicant(applicant_id: int, db: Session = Depends(get_db)):
    a = db.get(Applicant, applicant_id)
    if not a:
        raise HTTPException(404, "Applicant not found.")
    return _to_out(db, a)


@router.delete("/{applicant_id}", status_code=204)
def delete_applicant(applicant_id: int, db: Session = Depends(get_db)):
    a = db.get(Applicant, applicant_id)
    if not a:
        raise HTTPException(404, "Applicant not found.")
    db.delete(a)
    db.commit()
