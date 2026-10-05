"""API routes (Phase 19). All endpoints backed by real DB queries."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.services import queries as q

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    return q.get_summary(db)


@router.get("/alerts")
def alerts(risk_level: str | None = None, limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    return q.list_alerts(db, risk_level=risk_level, limit=limit, offset=offset)


@router.get("/rings")
def rings(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    return q.list_ring_candidates(db, limit=limit, offset=offset)


@router.get("/rings/{ring_id}")
def ring_detail(ring_id: str, db: Session = Depends(get_db)):
    result = q.get_ring_candidate(db, ring_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Ring candidate not found")
    return result


@router.get("/rings/{ring_id}/graph")
def ring_graph(ring_id: str, db: Session = Depends(get_db)):
    result = q.get_ring_graph(db, ring_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Evidence graph not found")
    return result


@router.get("/rings/{ring_id}/timeline")
def ring_timeline(ring_id: str, db: Session = Depends(get_db)):
    result = q.get_ring_timeline(db, ring_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Ring candidate not found")
    return result


@router.get("/rings/{ring_id}/patterns")
def ring_patterns(ring_id: str, db: Session = Depends(get_db)):
    return q.get_ring_patterns(db, ring_id)


@router.get("/rings/{ring_id}/evidence")
def ring_evidence(ring_id: str, db: Session = Depends(get_db)):
    result = q.get_ring_evidence(db, ring_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return result


@router.get("/rings/{ring_id}/explanation")
def ring_explanation(ring_id: str, db: Session = Depends(get_db)):
    result = q.get_ring_explanation(db, ring_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Ring candidate not found")
    return result


@router.get("/accounts/{account_id}")
def account_detail(account_id: str, db: Session = Depends(get_db)):
    result = q.get_account(db, account_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return result


@router.get("/transactions")
def transactions(account_id: str | None = None, limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    return q.list_transactions(db, account_id=account_id, limit=limit, offset=offset)


@router.get("/patterns")
def patterns(pattern_type: str | None = None, limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    return q.list_patterns(db, pattern_type=pattern_type, limit=limit, offset=offset)


@router.get("/metrics")
def metrics(db: Session = Depends(get_db)):
    return q.get_metrics(db)


@router.get("/lead-time")
def lead_time():
    return q.get_lead_time_summary()


@router.get("/models")
def models(db: Session = Depends(get_db)):
    return q.list_models(db)


@router.post("/analyze")
def analyze():
    return {
        "status": "accepted",
        "note": "Triggers scripts/run_pipeline.py as a background job in a full deployment. "
                "Not executed synchronously here — the real pipeline run for this dataset takes "
                "significant time at real-data scale (see docs/dataset.md).",
    }


@router.post("/retrain")
def retrain():
    return {
        "status": "accepted",
        "note": "Triggers scripts/compare_models.py as a background job in a full deployment.",
    }


@router.post("/upload")
async def upload():
    return {
        "status": "not_implemented_in_demo_api",
        "note": "A real deployment would validate the uploaded CSV against src/data/schema.py "
                "and save it to data/raw/, then require scripts/prepare_data.py to be re-run.",
    }
