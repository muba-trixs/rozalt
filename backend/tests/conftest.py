from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import backend.models  # noqa: F401
from backend.database.session import Base, get_db, make_engine


@pytest.fixture()
def db(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db):
    from backend.app.main import app
    from backend.database.session import get_session_factory

    def _override():
        yield db

    factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_session_factory] = lambda: factory
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def loaded_db(tmp_path_factory):
    """One synthetic dataset shared by the scenario tests (loading takes a few seconds)."""
    from backend.services.synthetic_loader import load_synthetic

    path = tmp_path_factory.mktemp("synthetic") / "synthetic.db"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    load_synthetic(session)
    yield session
    session.close()
    engine.dispose()
