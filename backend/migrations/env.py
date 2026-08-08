"""Alembic environment.

The database URL comes from Settings, not from alembic.ini, so there is exactly
one source of truth and no credentials live in a committed file.

Each bounded context defines its own tables in its own infrastructure/ package.
Import them here so autogenerate can see them — a context whose models are not
imported will silently produce empty migrations.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from kairos.config import get_settings

# Imported for the table-registration side effect — add every context's models
# here as they are built, or autogenerate silently emits empty migrations.
from kairos.curation.infrastructure import models as curation_models  # noqa: F401
from kairos.db import Base
from kairos.niche_ranking.infrastructure import models as niche_models  # noqa: F401
from kairos.trend_discovery.infrastructure import models  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
