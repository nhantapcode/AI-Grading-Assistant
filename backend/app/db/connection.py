"""The connection dependency owns request transactions."""
from collections.abc import Iterator

import psycopg
from psycopg.rows import dict_row

from app.core.config import settings


def get_db() -> Iterator[psycopg.Connection]:
    with psycopg.connect(settings.database_url, row_factory=dict_row) as connection:
        yield connection
