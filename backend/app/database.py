"""Application-owned SQLAlchemy tables; PostgreSQL is configured explicitly."""
from copy import deepcopy

from sqlalchemy import JSON, Integer, String, create_engine, delete, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class Patient(Base):
    __tablename__ = "retinagram_patients"
    patient_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    age: Mapped[int] = mapped_column(Integer)
    gender: Mapped[str] = mapped_column(String(20))
    phone: Mapped[str] = mapped_column(String(40), default="")
    email: Mapped[str] = mapped_column(String(254), default="")
    details: Mapped[dict] = mapped_column(JSON)


class ScanSession(Base):
    __tablename__ = "retinagram_sessions"
    session_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(100), index=True)
    record: Mapped[dict] = mapped_column(JSON)


class Setting(Base):
    __tablename__ = "retinagram_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class DatabaseStore:
    def __init__(self, url: str):
        self.engine = create_engine(url, pool_pre_ping=True)
        # Add only our own tables. Never drop/recreate the database or schema.
        Base.metadata.create_all(self.engine)

    def health(self):
        try:
            with self.engine.connect() as connection:
                return connection.execute(text("SELECT 1")).scalar_one() == 1
        except Exception:
            return False

    def list_records(self):
        with Session(self.engine) as session:
            return [deepcopy(row.record) for row in session.scalars(select(ScanSession))]

    def save_record(self, record):
        with Session(self.engine) as session, session.begin():
            session.merge(ScanSession(session_id=record["session_id"], patient_id=record["patient_id"], record=record))

    def list_patients(self):
        with Session(self.engine) as session:
            return [deepcopy(row.details) for row in session.scalars(select(Patient))]

    def save_patient(self, patient):
        with Session(self.engine) as session, session.begin():
            session.merge(Patient(patient_id=patient["patientIdNumber"], name=patient["name"],
                                  age=patient["age"], gender=patient["gender"],
                                  phone=patient.get("phone", ""), email=patient.get("email", ""), details=patient))

    def settings(self):
        with Session(self.engine) as session:
            row = session.get(Setting, "sync")
            return deepcopy(row.value) if row else {}

    def save_settings(self, value):
        with Session(self.engine) as session, session.begin():
            session.merge(Setting(key="sync", value=value))

    def import_legacy(self, records, patients):
        with Session(self.engine) as session, session.begin():
            if session.get(Setting, "legacy_json_import_v1"):
                return
            for patient in patients:
                if not session.get(Patient, patient["patientIdNumber"]):
                    session.add(Patient(patient_id=patient["patientIdNumber"], name=patient["name"], age=patient["age"],
                                        gender=patient["gender"], phone=patient.get("phone", ""), email=patient.get("email", ""), details=patient))
            for record in records:
                if not session.get(ScanSession, record["session_id"]):
                    session.add(ScanSession(session_id=record["session_id"], patient_id=record["patient_id"], record=record))
            session.add(Setting(key="legacy_json_import_v1", value={"complete": True}))

    def clear_history(self):
        with Session(self.engine) as session, session.begin():
            session.execute(delete(ScanSession))
            session.execute(delete(Patient))
        # Keep settings, the import marker, schema, and every unrelated table.
