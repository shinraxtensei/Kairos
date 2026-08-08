"""Engine, session factory, and the declarative base every context's tables inherit.

Each bounded context owns its own tables (CONTEXT.md §3.1) and defines them in
its own infrastructure/ package. This module only provides the plumbing.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from kairos.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
