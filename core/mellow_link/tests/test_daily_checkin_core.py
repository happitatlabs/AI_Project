import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from mellow_link.infra.database import Base, User, get_password_hash
from mellow_link.services.daily_checkin import (
    DailyStateCreate,
    DailyStateNotFoundError,
    DailyStateRepository,
    DailyStateService,
    DailyStateUpdate,
    DuplicateDailyStateError,
)


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'daily_checkin.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def users(db_session):
    first = User(
        username="daily_user_a", hashed_password=get_password_hash("password-a")
    )
    second = User(
        username="daily_user_b", hashed_password=get_password_hash("password-b")
    )
    db_session.add_all([first, second])
    db_session.commit()
    db_session.refresh(first)
    db_session.refresh(second)
    return first, second


@pytest.fixture()
def service(db_session):
    return DailyStateService(DailyStateRepository(db_session))


def valid_payload(**overrides):
    payload = {
        "date": "2026-07-14",
        "sleepHours": 7.5,
        "wakeCount": 1,
        "pain": {"wrist": 2, "elbow": 1, "back": 3, "foot": 0},
        "mood": {"anxiety": 4, "depression": 2, "irritation": 1},
        "safety": {"selfHarmUrge": 0},
        "meals": {"breakfast": True, "lunch": True, "dinner": False},
        "hydration": 6,
        "medicationChecks": {"morning": True, "evening": False},
        "energy": 5,
        "dailyBrick": "write one focused note",
        "dailyBrickCompleted": False,
        "notes": "synthetic test note",
    }
    payload.update(overrides)
    return payload


def make_create(**overrides):
    return DailyStateCreate.model_validate(valid_payload(**overrides))


def test_create_valid_daily_state(service, users):
    first, _ = users

    created = service.create(first.id, make_create())

    assert created.id
    assert created.date.isoformat() == "2026-07-14"
    assert created.sleep_hours == 7.5
    assert created.pain.wrist == 2
    assert created.medication_checks.morning is True


def test_get_created_record_by_date(service, users):
    first, _ = users
    service.create(first.id, make_create())

    found = service.get_by_date(first.id, make_create().date)

    assert found.date.isoformat() == "2026-07-14"
    assert found.daily_brick == "write one focused note"


def test_update_existing_record(service, users):
    first, _ = users
    service.create(first.id, make_create())

    updated = service.update(
        first.id,
        make_create().date,
        DailyStateUpdate.model_validate(
            valid_payload(energy=8, dailyBrickCompleted=True)
        ),
    )

    assert updated.energy == 8
    assert updated.daily_brick_completed is True


def test_list_date_range(service, users):
    first, _ = users
    service.create(first.id, make_create(date="2026-07-13", dailyBrick="first"))
    service.create(first.id, make_create(date="2026-07-14", dailyBrick="second"))
    service.create(first.id, make_create(date="2026-07-16", dailyBrick="outside"))

    records = service.list_range(
        first.id,
        make_create(date="2026-07-13").date,
        make_create(date="2026-07-14").date,
    )

    assert [record.date.isoformat() for record in records] == [
        "2026-07-13",
        "2026-07-14",
    ]


def test_duplicate_date_create_is_rejected(service, users):
    first, _ = users
    service.create(first.id, make_create())

    with pytest.raises(DuplicateDailyStateError):
        service.create(first.id, make_create())


def test_missing_record_get_is_consistent_error(service, users):
    first, _ = users

    with pytest.raises(DailyStateNotFoundError):
        service.get_by_date(first.id, make_create().date)


def test_missing_record_update_is_consistent_error(service, users):
    first, _ = users

    with pytest.raises(DailyStateNotFoundError):
        service.update(
            first.id,
            make_create().date,
            DailyStateUpdate.model_validate(valid_payload()),
        )


def test_update_rejects_payload_date_mismatch(service, users):
    first, _ = users
    service.create(first.id, make_create())

    with pytest.raises(HTTPException) as exc:
        service.update(
            first.id,
            make_create().date,
            DailyStateUpdate.model_validate(valid_payload(date="2026-07-15")),
        )

    assert exc.value.status_code == 422


def test_zero_and_ten_boundaries_are_allowed(service, users):
    first, _ = users
    created = service.create(
        first.id,
        make_create(
            pain={"wrist": 0, "elbow": 10, "back": 0, "foot": 10},
            mood={"anxiety": 0, "depression": 10, "irritation": 0},
            safety={"selfHarmUrge": 10},
            energy=10,
        ),
    )

    assert created.pain.elbow == 10
    assert created.mood.anxiety == 0
    assert created.safety.self_harm_urge == 10


def test_out_of_range_pain_score_is_rejected():
    with pytest.raises(ValidationError):
        make_create(pain={"wrist": 11, "elbow": 1, "back": 1, "foot": 1})


def test_out_of_range_mood_score_is_rejected():
    with pytest.raises(ValidationError):
        make_create(mood={"anxiety": 1, "depression": -1, "irritation": 1})


def test_invalid_sleep_hours_is_rejected():
    with pytest.raises(ValidationError):
        make_create(sleepHours=24.5)


def test_negative_wake_count_or_hydration_is_rejected():
    with pytest.raises(ValidationError):
        make_create(wakeCount=-1)
    with pytest.raises(ValidationError):
        make_create(hydration=-0.5)


def test_invalid_date_is_rejected():
    with pytest.raises(ValidationError):
        make_create(date="2026-02-30")


def test_local_date_string_is_not_shifted_by_utc_conversion(service, users):
    first, _ = users
    created = service.create(first.id, make_create(date="2026-01-01"))

    assert created.date.isoformat() == "2026-01-01"


def test_user_data_is_isolated_by_owner(service, users):
    first, second = users
    service.create(first.id, make_create(dailyBrick="first user"))
    service.create(second.id, make_create(dailyBrick="second user"))

    first_record = service.get_by_date(first.id, make_create().date)
    second_record = service.get_by_date(second.id, make_create().date)

    assert first_record.daily_brick == "first user"
    assert second_record.daily_brick == "second user"
