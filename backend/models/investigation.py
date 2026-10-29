"""Anomalies, investigations and the evidence/hypothesis traceability graph."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.session import Base


class Anomaly(Base):
    __tablename__ = "anomalies"
    anomaly_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    sku_id: Mapped[str] = mapped_column(ForeignKey("products.sku_id"), index=True)
    region_id: Mapped[str] = mapped_column(ForeignKey("regions.region_id"), index=True)
    start_date: Mapped[dt.date] = mapped_column(Date, index=True)
    end_date: Mapped[dt.date] = mapped_column(Date)
    peak_date: Mapped[dt.date] = mapped_column(Date)
    duration_days: Mapped[int] = mapped_column(Integer)
    forecast_qty: Mapped[float] = mapped_column(Float)  # sum over window
    recorded_sales_qty: Mapped[float] = mapped_column(Float)  # sum over window
    variance_pct: Mapped[float] = mapped_column(Float)
    peak_robust_z: Mapped[float] = mapped_column(Float)
    direction: Mapped[str] = mapped_column(String(10))  # NEGATIVE | POSITIVE
    severity: Mapped[str] = mapped_column(String(10))  # HIGH | MEDIUM | LOW
    detection_method: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20), default="NEW")  # NEW | INVESTIGATING | INVESTIGATED
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    detected_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())

    investigations: Mapped[list["Investigation"]] = relationship(back_populates="anomaly")


class Investigation(Base):
    __tablename__ = "investigations"
    investigation_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    anomaly_id: Mapped[str] = mapped_column(ForeignKey("anomalies.anomaly_id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")  # RUNNING | COMPLETED | FAILED
    analysis_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)  # llm | deterministic
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    limitations: Mapped[list] = mapped_column(JSON, default=list)
    statistics: Mapped[dict] = mapped_column(JSON, default=dict)
    stage_log: Mapped[list] = mapped_column(JSON, default=list)
    timings: Mapped[dict] = mapped_column(JSON, default=dict)
    llm_notes: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    anomaly: Mapped[Anomaly] = relationship(back_populates="investigations")
    candidates: Mapped[list["CandidateDriver"]] = relationship(
        cascade="all, delete-orphan", order_by="CandidateDriver.rank"
    )
    evidence: Mapped[list["EvidenceRecord"]] = relationship(
        cascade="all, delete-orphan", order_by="EvidenceRecord.evidence_id"
    )
    hypotheses: Mapped[list["Hypothesis"]] = relationship(
        cascade="all, delete-orphan", order_by="Hypothesis.rank"
    )


class CandidateDriver(Base):
    __tablename__ = "candidate_drivers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.investigation_id"), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    source_table: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[str] = mapped_column(String(40), index=True)
    driver_type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    event_date: Mapped[dt.date] = mapped_column(Date)
    event_end_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    region_id: Mapped[str] = mapped_column(String(80))
    relevance_score: Mapped[float] = mapped_column(Float)
    component_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    reasons: Mapped[dict] = mapped_column(JSON, default=dict)


class EvidenceRecord(Base):
    __tablename__ = "evidence_records"
    evidence_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.investigation_id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # fact | statistical | context
    polarity: Mapped[str] = mapped_column(String(20))  # supporting | contradicting | neutral
    driver_types: Mapped[list] = mapped_column(JSON, default=list)
    source_table: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class Hypothesis(Base):
    __tablename__ = "hypotheses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.investigation_id"), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    driver_type: Mapped[str] = mapped_column(String(40))
    evidence_strength: Mapped[str] = mapped_column(String(20))  # STRONG | MODERATE | WEAK | INSUFFICIENT
    claim_type: Mapped[str] = mapped_column(String(20))  # fact | association | hypothesis | assumption
    explanation: Mapped[str] = mapped_column(Text)
    recommended_actions: Mapped[list] = mapped_column(JSON, default=list)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    generated_by: Mapped[str] = mapped_column(String(20))  # llm | deterministic

    links: Mapped[list["HypothesisEvidence"]] = relationship(cascade="all, delete-orphan")
    feedback: Mapped[list["AnalystFeedback"]] = relationship(
        cascade="all, delete-orphan", order_by="AnalystFeedback.created_at"
    )


class HypothesisEvidence(Base):
    __tablename__ = "hypothesis_evidence"
    hypothesis_id: Mapped[int] = mapped_column(ForeignKey("hypotheses.id"), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence_records.evidence_id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20))  # supporting | contradicting


class AnalystFeedback(Base):
    __tablename__ = "analyst_feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hypothesis_id: Mapped[int] = mapped_column(ForeignKey("hypotheses.id"), index=True)
    verdict: Mapped[str] = mapped_column(String(30))  # CONFIRMED | PLAUSIBLE | REJECTED | NEEDS_INVESTIGATION
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
