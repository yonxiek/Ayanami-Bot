import pytest_asyncio

from db import Database


@pytest_asyncio.fixture
async def db(tmp_path):
    """Свежая БД на временном файле для каждого теста."""
    Database._instance = None
    path = str(tmp_path / "test_bot.db")
    db = Database(path)
    await db.init_db()
    yield db
    Database._instance = None
    if db.conn:
        await db.conn.close()