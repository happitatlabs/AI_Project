from __future__ import annotations

from datetime import date, datetime
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mellow_link.infra.database import DailyState

DAILY_BRICK_MAX_LENGTH = 300
NOTES_MAX_LENGTH = 4000


class PainScores(BaseModel):
    wrist: int = Field(..., ge=0, le=10)
    elbow: int = Field(..., ge=0, le=10)
    back: int = Field(..., ge=0, le=10)
    foot: int = Field(..., ge=0, le=10)


class MoodScores(BaseModel):
    anxiety: int = Field(..., ge=0, le=10)
    depression: int = Field(..., ge=0, le=10)
    irritation: int = Field(..., ge=0, le=10)


class SafetyCheck(BaseModel):
    self_harm_urge: int = Field(..., ge=0, le=10, alias="selfHarmUrge")

    model_config = ConfigDict(populate_by_name=True)


class MealChecks(BaseModel):
    breakfast: bool = False
    lunch: bool = False
    dinner: bool = False


class MedicationChecks(BaseModel):
    morning: bool = False
    evening: bool = False


class DailyStateBase(BaseModel):
    date: date
    sleep_hours: float = Field(..., ge=0, le=24, alias="sleepHours")
    wake_count: int = Field(..., ge=0, alias="wakeCount")
    pain: PainScores
    mood: MoodScores
    safety: SafetyCheck
    meals: MealChecks = Field(default_factory=MealChecks)
    hydration: float = Field(..., ge=0)
    medication_checks: MedicationChecks = Field(
        default_factory=MedicationChecks, alias="medicationChecks"
    )
    energy: int = Field(..., ge=0, le=10)
    daily_brick: str = Field("", max_length=DAILY_BRICK_MAX_LENGTH, alias="dailyBrick")
    daily_brick_completed: bool = Field(False, alias="dailyBrickCompleted")
    notes: str = Field("", max_length=NOTES_MAX_LENGTH)

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("date", mode="before")
    @classmethod
    def validate_local_date(cls, value):
        if isinstance(value, datetime):
            raise ValueError("date must be a local YYYY-MM-DD date, not a datetime")
        if isinstance(value, str):
            if len(value) != 10:
                raise ValueError("date must use YYYY-MM-DD format")
            try:
                return date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("date must be a valid local date") from exc
        return value

    @field_validator("wake_count")
    @classmethod
    def validate_wake_count_integer(cls, value: int) -> int:
        if isinstance(value, bool):
            raise ValueError("wakeCount must be an integer")
        return value


class DailyStateCreate(DailyStateBase):
    pass


class DailyStateUpdate(DailyStateBase):
    pass


class DailyStateResponse(DailyStateBase):
    id: int
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True)


class DailyStateRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, user_id: int, payload: DailyStateCreate) -> DailyState:
        record = DailyState(user_id=user_id)
        _apply_payload(record, payload)
        self.db.add(record)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise DuplicateDailyStateError(payload.date) from exc
        self.db.refresh(record)
        return record

    def get_by_date(self, user_id: int, target_date: date) -> DailyState | None:
        return (
            self.db.query(DailyState)
            .filter(DailyState.user_id == user_id, DailyState.date == target_date)
            .first()
        )

    def update(
        self, user_id: int, target_date: date, payload: DailyStateUpdate
    ) -> DailyState:
        record = self.get_by_date(user_id, target_date)
        if record is None:
            raise DailyStateNotFoundError(target_date)
        if payload.date != target_date:
            raise HTTPException(
                status_code=422,
                detail="payload date must match target date",
            )
        _apply_payload(record, payload)
        record.updated_at = datetime.utcnow()
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise DuplicateDailyStateError(payload.date) from exc
        self.db.refresh(record)
        return record

    def list_range(
        self, user_id: int, start_date: date, end_date: date
    ) -> list[DailyState]:
        return (
            self.db.query(DailyState)
            .filter(DailyState.user_id == user_id)
            .filter(DailyState.date >= start_date)
            .filter(DailyState.date <= end_date)
            .order_by(DailyState.date.asc())
            .all()
        )


class DailyStateService:
    def __init__(self, repository: DailyStateRepository):
        self.repository = repository

    def create(self, user_id: int, payload: DailyStateCreate) -> DailyStateResponse:
        return to_response(self.repository.create(user_id, payload))

    def get_by_date(self, user_id: int, target_date: date) -> DailyStateResponse:
        record = self.repository.get_by_date(user_id, target_date)
        if record is None:
            raise DailyStateNotFoundError(target_date)
        return to_response(record)

    def update(
        self, user_id: int, target_date: date, payload: DailyStateUpdate
    ) -> DailyStateResponse:
        return to_response(self.repository.update(user_id, target_date, payload))

    def list_range(
        self, user_id: int, start_date: date, end_date: date
    ) -> list[DailyStateResponse]:
        if start_date > end_date:
            raise HTTPException(
                status_code=422,
                detail="startDate must be on or before endDate",
            )
        return [
            to_response(record)
            for record in self.repository.list_range(user_id, start_date, end_date)
        ]


class DailyStateNotFoundError(Exception):
    def __init__(self, target_date: date):
        super().__init__(f"DailyState not found for {target_date.isoformat()}")
        self.target_date = target_date


class DuplicateDailyStateError(Exception):
    def __init__(self, target_date: date):
        super().__init__(f"DailyState already exists for {target_date.isoformat()}")
        self.target_date = target_date


def parse_local_date(value: str, field_name: str = "date") -> date:
    try:
        return DailyStateBase.model_validate(
            {
                "date": value,
                "sleepHours": 0,
                "wakeCount": 0,
                "pain": {"wrist": 0, "elbow": 0, "back": 0, "foot": 0},
                "mood": {"anxiety": 0, "depression": 0, "irritation": 0},
                "safety": {"selfHarmUrge": 0},
                "hydration": 0,
                "energy": 0,
            }
        ).date
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} must be a valid local YYYY-MM-DD date",
        ) from exc


def to_response(record: DailyState) -> DailyStateResponse:
    return DailyStateResponse(
        id=record.id,
        date=record.date,
        sleepHours=record.sleep_hours,
        wakeCount=record.wake_count,
        pain=PainScores(
            wrist=record.pain_wrist,
            elbow=record.pain_elbow,
            back=record.pain_back,
            foot=record.pain_foot,
        ),
        mood=MoodScores(
            anxiety=record.mood_anxiety,
            depression=record.mood_depression,
            irritation=record.mood_irritation,
        ),
        safety=SafetyCheck(selfHarmUrge=record.self_harm_urge),
        meals=MealChecks(
            breakfast=record.meal_breakfast,
            lunch=record.meal_lunch,
            dinner=record.meal_dinner,
        ),
        hydration=record.hydration,
        medicationChecks=MedicationChecks(
            morning=record.medication_morning,
            evening=record.medication_evening,
        ),
        energy=record.energy,
        dailyBrick=record.daily_brick or "",
        dailyBrickCompleted=record.daily_brick_completed,
        notes=record.notes or "",
        createdAt=record.created_at,
        updatedAt=record.updated_at,
    )


def _apply_payload(record: DailyState, payload: DailyStateBase) -> None:
    record.date = payload.date
    record.sleep_hours = payload.sleep_hours
    record.wake_count = payload.wake_count
    record.pain_wrist = payload.pain.wrist
    record.pain_elbow = payload.pain.elbow
    record.pain_back = payload.pain.back
    record.pain_foot = payload.pain.foot
    record.mood_anxiety = payload.mood.anxiety
    record.mood_depression = payload.mood.depression
    record.mood_irritation = payload.mood.irritation
    record.self_harm_urge = payload.safety.self_harm_urge
    record.meal_breakfast = payload.meals.breakfast
    record.meal_lunch = payload.meals.lunch
    record.meal_dinner = payload.meals.dinner
    record.hydration = payload.hydration
    record.medication_morning = payload.medication_checks.morning
    record.medication_evening = payload.medication_checks.evening
    record.energy = payload.energy
    record.daily_brick = payload.daily_brick
    record.daily_brick_completed = payload.daily_brick_completed
    record.notes = payload.notes
