from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine

from langflow.services.database.models.custom_model_provider import CustomModelProvider
from langflow.services.database.models.user.model import User


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def _user(username: str) -> User:
    return User(id=uuid4(), username=username, password="test", is_active=True)


def _provider(user: User, name: str) -> CustomModelProvider:
    return CustomModelProvider(
        user_id=user.id,
        name=name,
        normalized_name="ignored",
        base_url="https://models.example/v1",
        api_key="encrypted",
    )


def test_active_provider_names_are_case_insensitively_unique_per_user(session: Session):
    first_user = _user("first")
    second_user = _user("second")
    session.add_all([first_user, second_user])
    session.commit()

    session.add_all([_provider(first_user, "Company Gateway"), _provider(second_user, "company gateway")])
    session.commit()

    session.add(_provider(first_user, " company gateway "))
    with pytest.raises(IntegrityError):
        session.commit()


def test_soft_delete_clears_secret_and_releases_name(session: Session):
    user = _user("owner")
    provider = _provider(user, "Local Models")
    session.add_all([user, provider])
    session.commit()

    provider.soft_delete()
    session.add(provider)
    session.commit()

    assert provider.api_key is None
    assert provider.deleted_at is not None

    replacement = _provider(user, "LOCAL MODELS")
    session.add(replacement)
    session.commit()
    assert replacement.id != provider.id
