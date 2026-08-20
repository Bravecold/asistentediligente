import hashlib
import json
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from sqlalchemy.pool import StaticPool


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./asistente_diligente.db")
engine_kwargs = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
    if DATABASE_URL in {"sqlite://", "sqlite:///:memory:"}:
        engine_kwargs["poolclass"] = StaticPool
engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Procedure(Base):
    __tablename__ = "procedures"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    entity: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(80))
    city: Mapped[str] = mapped_column(String(80), default="Bogotá")
    mode: Mapped[str] = mapped_column(String(30), default="accompaniment")
    risk: Mapped[str] = mapped_column(String(20), default="low")
    steps: Mapped[list] = mapped_column(JSON)
    required_items: Mapped[list] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(default=True)
    version: Mapped[int] = mapped_column(default=1)


class Request(Base):
    __tablename__ = "requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    requester_name: Mapped[str] = mapped_column(String(120))
    beneficiary_name: Mapped[str] = mapped_column(String(120))
    procedure_id: Mapped[str] = mapped_column(ForeignKey("procedures.id"))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="submitted", index=True)
    assigned_manager: Mapped[str | None] = mapped_column(String(120), nullable=True)
    consent_version: Mapped[str] = mapped_column(String(30))
    sensitive_consent: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    procedure: Mapped[Procedure] = relationship()


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_role: Mapped[str] = mapped_column(String(30))
    actor_id: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON)
    previous_hash: Mapped[str] = mapped_column(String(64), default="")
    event_hash: Mapped[str] = mapped_column(String(64), unique=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Role(str, Enum):
    customer = "customer"
    beneficiary = "beneficiary"
    manager = "manager"
    supervisor = "supervisor"
    admin = "admin"


class Actor(BaseModel):
    id: str
    role: Role


def actor_from_headers(
    x_demo_role: Annotated[str | None, Header()] = None,
    x_demo_user: Annotated[str | None, Header()] = None,
) -> Actor:
    if os.getenv("APP_ENV", "development") == "production":
        # Production must validate an Entra-issued JWT at the gateway/app layer.
        raise HTTPException(status_code=501, detail="Configure Entra External ID before production use")
    try:
        return Actor(id=x_demo_user or "demo-user", role=Role(x_demo_role or "customer"))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid role") from exc


def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require(*roles: Role):
    def dependency(actor: Actor = Depends(actor_from_headers)) -> Actor:
        if actor.role not in roles:
            raise HTTPException(status_code=403, detail="Role not permitted")
        return actor
    return dependency


class RequestCreate(BaseModel):
    requester_name: str = Field(min_length=2, max_length=120)
    beneficiary_name: str = Field(min_length=2, max_length=120)
    procedure_id: str
    description: str = Field(min_length=10, max_length=2000)
    accept_privacy: bool
    accept_sensitive_data: bool = False
    consent_version: str = "2026-08-20"


class Transition(BaseModel):
    status: str
    note: str = Field(default="", max_length=500)


ALLOWED_TRANSITIONS = {
    "submitted": {"triaged", "cancelled"},
    "triaged": {"assigned", "cancelled"},
    "assigned": {"in_progress", "cancelled"},
    "in_progress": {"waiting_user", "completed", "failed"},
    "waiting_user": {"in_progress", "cancelled"},
    "completed": {"closed"},
    "failed": {"triaged", "closed"},
    "cancelled": set(), "closed": set(),
}


def audit(db: Session, request_id: str, actor: Actor, action: str, payload: dict):
    previous = db.scalar(select(AuditEvent).where(AuditEvent.request_id == request_id).order_by(AuditEvent.occurred_at.desc()))
    previous_hash = previous.event_hash if previous else ""
    canonical = json.dumps({"request_id": request_id, "actor": actor.model_dump(mode="json"), "action": action, "payload": payload, "previous_hash": previous_hash}, sort_keys=True, ensure_ascii=False)
    db.add(AuditEvent(id=str(uuid4()), request_id=request_id, actor_role=actor.role.value, actor_id=actor.id, action=action, payload=payload, previous_hash=previous_hash, event_hash=hashlib.sha256(canonical.encode()).hexdigest()))


app = FastAPI(title="AsistenteDiligente API", version="0.1.0")
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type", "X-Demo-Role", "X-Demo-User"])


@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.scalar(select(Procedure.id).limit(1)):
            db.add_all([
                Procedure(id="ops-cita-eps", entity="EPS (según afiliación)", name="Solicitar cita médica", category="Salud", mode="accompaniment", risk="medium", steps=["Validar entidad y canal oficial", "Confirmar disponibilidad con el usuario", "El usuario introduce sus credenciales", "Registrar confirmación sin historia clínica"], required_items=["Documento del beneficiario", "Tipo de cita", "Disponibilidad"]),
                Procedure(id="ops-medicamentos", entity="EPS/IPS (según afiliación)", name="Orientar solicitud de medicamentos", category="Salud", mode="accompaniment", risk="high", steps=["Verificar canal oficial", "Confirmar fórmula u orden mínima necesaria", "Acompañar la radicación", "Registrar número de solicitud"], required_items=["Orden o fórmula vigente", "Documento del beneficiario"]),
                Procedure(id="ops-vus-movilidad", entity="Ventanilla Única de Servicios", name="Orientar cita para trámite de movilidad", category="Movilidad", mode="accompaniment", risk="low", steps=["Identificar trámite", "Consultar requisitos oficiales", "Acompañar agendamiento", "Guardar confirmación"], required_items=["Documento", "Datos del trámite"]),
            ])
            db.commit()


@app.get("/health")
def health():
    return {"status": "ok", "service": "AsistenteDiligente"}


@app.get("/api/procedures")
def list_procedures(db: Session = Depends(db_session)):
    return db.scalars(select(Procedure).where(Procedure.active.is_(True))).all()


@app.post("/api/requests", status_code=status.HTTP_201_CREATED)
def create_request(data: RequestCreate, actor: Actor = Depends(require(Role.customer, Role.admin)), db: Session = Depends(db_session)):
    procedure = db.get(Procedure, data.procedure_id)
    if not procedure:
        raise HTTPException(404, "Procedure not found")
    if not data.accept_privacy:
        raise HTTPException(422, "Privacy authorization is required")
    if procedure.category == "Salud" and not data.accept_sensitive_data:
        raise HTTPException(422, "Explicit sensitive-data authorization is required for health procedures")
    item = Request(id=str(uuid4()), **data.model_dump(exclude={"accept_privacy", "accept_sensitive_data"}), sensitive_consent=data.accept_sensitive_data)
    db.add(item)
    audit(db, item.id, actor, "request.created", {"procedure_id": item.procedure_id, "consent_version": item.consent_version, "sensitive_consent": item.sensitive_consent})
    db.commit(); db.refresh(item)
    return item


@app.get("/api/requests")
def list_requests(actor: Actor = Depends(require(Role.manager, Role.supervisor, Role.admin)), db: Session = Depends(db_session)):
    return db.scalars(select(Request).order_by(Request.created_at.desc())).all()


@app.post("/api/requests/{request_id}/claim")
def claim_request(request_id: str, actor: Actor = Depends(require(Role.manager)), db: Session = Depends(db_session)):
    item = db.get(Request, request_id)
    if not item: raise HTTPException(404, "Request not found")
    if item.status not in {"submitted", "triaged"}: raise HTTPException(409, "Request cannot be claimed")
    item.assigned_manager, item.status, item.updated_at = actor.id, "assigned", utcnow()
    audit(db, item.id, actor, "request.claimed", {"manager": actor.id})
    db.commit(); db.refresh(item)
    return item


@app.patch("/api/requests/{request_id}/status")
def transition_request(request_id: str, data: Transition, actor: Actor = Depends(require(Role.manager, Role.supervisor, Role.admin)), db: Session = Depends(db_session)):
    item = db.get(Request, request_id)
    if not item: raise HTTPException(404, "Request not found")
    if data.status not in ALLOWED_TRANSITIONS.get(item.status, set()): raise HTTPException(409, f"Invalid transition: {item.status} -> {data.status}")
    if actor.role == Role.manager and item.assigned_manager not in {None, actor.id}: raise HTTPException(403, "Assigned to another manager")
    old = item.status; item.status = data.status; item.updated_at = utcnow()
    audit(db, item.id, actor, "request.status_changed", {"from": old, "to": data.status, "note": data.note})
    db.commit(); db.refresh(item)
    return item


@app.get("/api/requests/{request_id}/audit")
def request_audit(request_id: str, actor: Actor = Depends(require(Role.supervisor, Role.admin)), db: Session = Depends(db_session)):
    return db.scalars(select(AuditEvent).where(AuditEvent.request_id == request_id).order_by(AuditEvent.occurred_at)).all()
