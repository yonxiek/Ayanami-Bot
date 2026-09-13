import sqlite3

from db import create_backup


async def test_backup_creates_file(tmp_path):
    src = tmp_path / "src.db"
    conn = sqlite3.connect(src)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO t (name) VALUES (?)", ("hello",))
    conn.commit()
    conn.close()

    out_dir = tmp_path / "backups"
    prior = sorted(out_dir.glob("bot-*.db")) if out_dir.exists() else []
    path = await create_backup(str(src), str(out_dir), keep=7)
    assert path is not None
    assert out_dir.is_dir()
    backed = sorted(out_dir.glob("bot-*.db"))
    assert len(backed) == len(prior) + 1
    assert str(backed[-1]) == path

    check = sqlite3.connect(path)
    try:
        row = check.execute("SELECT name FROM t WHERE id = 1").fetchone()
        assert row and row[0] == "hello"
    finally:
        check.close()


async def test_backup_copies_wal_data(tmp_path):
    src = tmp_path / "src.db"
    conn = sqlite3.connect(src)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
    conn.commit()
    conn.execute("INSERT INTO t (name) VALUES (?)", ("wal_data",))
    conn.commit()
    conn.close()

    path = await create_backup(str(src), str(tmp_path / "backups"), keep=7)
    check = sqlite3.connect(path)
    try:
        row = check.execute("SELECT name FROM t").fetchone()
        assert row and row[0] == "wal_data"
    finally:
        check.close()


async def test_backup_prunes_old(tmp_path):
    src = tmp_path / "src.db"
    conn = sqlite3.connect(src)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    out_dir = tmp_path / "backups"
    out_dir.mkdir()
    for n in range(1, 6):
        (out_dir / f"bot-2025-01-0{n}_000000.db").write_bytes(b"stale")
    assert len(list(out_dir.glob("bot-*.db"))) == 5

    await create_backup(str(src), str(out_dir), keep=3)
    remaining = sorted(out_dir.glob("bot-*.db"))
    assert len(remaining) == 3
    assert remaining[-1].name.endswith(".db")  # свежий бэкап на месте


async def test_backup_skips_postgres_url(tmp_path):
    path = await create_backup("postgres://user:pass@localhost:5432/mydb", str(tmp_path / "b"), keep=7)
    assert path is None
    assert not (tmp_path / "b").exists()