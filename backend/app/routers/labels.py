from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Label
from ..schemas import LabelCreate, LabelOut

router = APIRouter(prefix="/api/labels", tags=["labels"])


@router.get("", response_model=list[LabelOut])
def list_labels(db: Session = Depends(get_db)):
    return db.query(Label).order_by(Label.name).all()


@router.post("", response_model=LabelOut, status_code=201)
def create_label(payload: LabelCreate, db: Session = Depends(get_db)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "Label name is required.")
    existing = db.query(Label).filter(func.lower(Label.name) == name.lower()).first()
    if existing:
        return existing
    label = Label(name=name, color=payload.color)
    db.add(label)
    db.commit()
    db.refresh(label)
    return label


@router.delete("/{label_id}", status_code=204)
def delete_label(label_id: int, db: Session = Depends(get_db)):
    label = db.get(Label, label_id)
    if not label:
        raise HTTPException(404, "Label not found.")
    db.delete(label)
    db.commit()
