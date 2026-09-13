async def test_user_tasks_lifecycle(db):
    tid = await db.add_user_task("111", "222", "Купить подарок")
    assert tid > 0

    tasks = await db.get_user_tasks("111", "222")
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Купить подарок"
    assert tasks[0]["status"] == "open"
    assert tasks[0]["task_id"] == tid

    other = await db.get_user_tasks("111", "333")
    assert other == []

    assert await db.complete_user_task("111", "222", tid) is True
    assert await db.complete_user_task("111", "222", tid) is False

    tasks = await db.get_user_tasks("111", "222")
    assert tasks[0]["status"] == "done"
    assert tasks[0]["completed_at"]

    assert await db.delete_user_task("111", "222", tid) is True
    assert await db.delete_user_task("111", "222", tid) is False
    assert await db.get_user_tasks("111", "222") == []


async def test_user_tasks_ordered(db):
    await db.add_user_task("111", "222", "Первая")
    done_id = await db.add_user_task("111", "222", "Вторая")
    await db.complete_user_task("111", "222", done_id)
    await db.add_user_task("111", "222", "Третья")

    tasks = await db.get_user_tasks("111", "222")
    assert tasks[0]["title"] == "Первая"
    assert tasks[1]["title"] == "Третья"
    assert tasks[2]["title"] == "Вторая"
    assert tasks[2]["status"] == "done"


async def test_voice_roles_query(db):
    await db.create_user("111", "222")
    await db.create_user("111", "333")
    await db.conn.execute(
        "UPDATE users SET total_voice_minutes = 3600 WHERE guild_id = ? AND user_id = ?",
        ("111", "222"))
    await db.conn.execute(
        "UPDATE users SET total_voice_minutes = 30 WHERE guild_id = ? AND user_id = ?",
        ("111", "333"))
    await db.conn.commit()

    rows = await db.get_users_by_voice_minutes("111", 60)
    assert [r["user_id"] for r in rows] == ["222"]
    assert rows[0]["total_voice_minutes"] == 3600

    assert len(await db.get_users_by_voice_minutes("111", 1)) == 2
    assert await db.get_users_by_voice_minutes("111", 99999) == []