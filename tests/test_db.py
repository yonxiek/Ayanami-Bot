from datetime import datetime, timezone


async def test_get_or_create_user(db):
    user = await db.get_or_create_user("111", "222")
    assert user["balance"] == 0
    assert user["level"] == 1
    user2 = await db.get_or_create_user("111", "222")
    assert user2["user_id"] == "222"


async def test_update_user_balance(db):
    await db.update_user_balance("111", "222", 100)
    user = await db.get_or_create_user("111", "222")
    assert user["balance"] == 100


async def test_buy_card_success(db):
    await db.update_user_balance("111", "222", 500)
    await db.conn.execute(
        "INSERT INTO collectible_cards (guild_id, card_id, name, description, rarity, emoji, drop_rate, enabled) "
        "VALUES ('111', 'c1', 'Тест', '', 'epic', '🟣', 0.1, 1)")
    await db.conn.commit()

    ok = await db.buy_card("111", "222", "c1", 400)
    assert ok is True
    user = await db.get_or_create_user("111", "222")
    assert user["balance"] == 100
    assert await db.count_unique_cards("111", "222") == 1


async def test_buy_card_insufficient_funds(db):
    await db.conn.execute(
        "INSERT INTO collectible_cards (guild_id, card_id, name, description, rarity, emoji, drop_rate, enabled) "
        "VALUES ('111', 'c1', 'Тест', '', 'epic', '🟣', 0.1, 1)")
    await db.conn.commit()

    ok = await db.buy_card("111", "222", "c1", 400)
    assert ok is False
    assert await db.count_unique_cards("111", "222") == 0


async def test_buy_card_unknown(db):
    ok = await db.buy_card("111", "222", "ghost", 10)
    assert ok is False


async def test_sell_card(db):
    await db.conn.execute(
        "INSERT INTO collectible_cards (guild_id, card_id, name, description, rarity, emoji, drop_rate, enabled) "
        "VALUES ('111', 'c1', 'Тест', '', 'rare', '🔵', 0.1, 1)")
    await db.conn.execute(
        "INSERT INTO user_cards (guild_id, user_id, card_id, quantity, obtained_at) "
        "VALUES ('111', '222', 'c1', 3, ?)",
        (datetime.now(timezone.utc).isoformat(),))
    await db.conn.commit()

    earned = await db.sell_card("111", "222", "c1", 2, 150)
    assert earned == 300
    user = await db.get_or_create_user("111", "222")
    assert user["balance"] == 300
    assert await db.count_unique_cards("111", "222") == 1


async def test_sell_card_more_than_owned(db):
    await db.conn.execute(
        "INSERT INTO collectible_cards (guild_id, card_id, name, description, rarity, emoji, drop_rate, enabled) "
        "VALUES ('111', 'c1', 'Тест', '', 'rare', '🔵', 0.1, 1)")
    await db.conn.execute(
        "INSERT INTO user_cards (guild_id, user_id, card_id, quantity, obtained_at) "
        "VALUES ('111', '222', 'c1', 1, ?)",
        (datetime.now(timezone.utc).isoformat(),))
    await db.conn.commit()

    earned = await db.sell_card("111", "222", "c1", 5, 150)
    assert earned == 0
    assert await db.count_unique_cards("111", "222") == 1


async def test_buy_same_card_stacks_quantity(db):
    await db.update_user_balance("111", "222", 1000)
    await db.conn.execute(
        "INSERT INTO collectible_cards (guild_id, card_id, name, description, rarity, emoji, drop_rate, enabled) "
        "VALUES ('111', 'c1', 'Тест', '', 'rare', '🔵', 0.1, 1)")
    await db.conn.commit()

    assert await db.buy_card("111", "222", "c1", 100) is True
    assert await db.buy_card("111", "222", "c1", 100) is True
    assert await db.buy_card("111", "222", "c1", 100) is True

    assert await db.count_unique_cards("111", "222") == 1
    cursor = await db.conn.execute(
        "SELECT quantity FROM user_cards WHERE guild_id = '111' AND user_id = '222' AND card_id = 'c1'")
    row = await cursor.fetchone()
    assert row["quantity"] == 3


async def test_sell_part_of_stacked_cards(db):
    await db.conn.execute(
        "INSERT INTO collectible_cards (guild_id, card_id, name, description, rarity, emoji, drop_rate, enabled) "
        "VALUES ('111', 'c1', 'Тест', '', 'rare', '🔵', 0.1, 1)")
    await db.conn.execute(
        "INSERT INTO user_cards (guild_id, user_id, card_id, quantity, obtained_at) "
        "VALUES ('111', '222', 'c1', 3, ?)",
        (datetime.now(timezone.utc).isoformat(),))
    await db.conn.commit()

    earned = await db.sell_card("111", "222", "c1", 2, 150)
    assert earned == 300
    assert await db.count_unique_cards("111", "222") == 1
    cursor = await db.conn.execute(
        "SELECT quantity FROM user_cards WHERE guild_id = '111' AND user_id = '222' AND card_id = 'c1'")
    row = await cursor.fetchone()
    assert row["quantity"] == 1


async def test_get_user_achievements(db):
    assert await db.award_achievement("111", "222", "first_ticket") is True
    assert await db.award_achievement("111", "222", "tickets_5") is True
    achievements = await db.get_user_achievements("111", "222")
    ids = [a["achievement_id"] for a in achievements]
    assert ids == ["first_ticket", "tickets_5"]
    assert await db.count_achievements("111", "222") == 2


async def test_update_activity_counts(db):
    await db.update_activity("111", "222", "voice_join")
    await db.update_activity("111", "222", "voice_join")
    await db.update_activity("111", "222", "reactions")
    activities = await db.get_user_activities("111", "222")
    assert activities["voice_join"] == 2
    assert activities["reactions"] == 1


async def test_award_achievement_once(db):
    first = await db.award_achievement("111", "222", "first_ticket")
    second = await db.award_achievement("111", "222", "first_ticket")
    assert first is True
    assert second is False
    assert await db.count_achievements("111", "222") == 1


async def test_count_tickets(db):
    from datetime import datetime
    for n in range(3):
        await db.conn.execute(
            "INSERT INTO tickets (guild_id, user_id, channel_id, ticket_number, category_name, status, created_at) "
            "VALUES ('111', '222', ?, ?, 'Тест', 'open', ?)",
            (str(100 + n), n + 1, datetime.now(timezone.utc).isoformat()))
    await db.conn.commit()
    assert await db.count_tickets("111", "222") == 3
    assert await db.count_tickets("111", "999") == 0


async def test_reminders_schema_migration(tmp_path):
    """Старая БД (remind_time/message/completed) должна мигрировать при init_db."""
    import aiosqlite

    from db import Database

    old_path = str(tmp_path / "old.db")
    conn = await aiosqlite.connect(old_path)
    await conn.execute(
        'CREATE TABLE reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id TEXT, '
        'user_id TEXT, channel_id TEXT, remind_time TEXT, message TEXT, created_at TEXT, completed INTEGER)')
    await conn.execute(
        "INSERT INTO reminders (guild_id, user_id, channel_id, remind_time, message, created_at, completed) "
        "VALUES ('111', '222', '333', '2099-01-01T00:00:00+00:00', 'тест', '2026-01-01', 0)")
    await conn.commit()
    await conn.close()

    Database._instance = None
    db = Database(old_path)
    await db.init_db()

    assert await db.get_active_reminder_count("222") == 1
    rows = await db.get_due_reminders()
    assert len(rows) == 0
    await db.clear_expired_reminders()
    if db.conn:
        await db.conn.close()


async def test_reminders_old_rows_carried_over(tmp_path):
    """Завершённые старые напоминания должны получить done = 1."""
    import aiosqlite

    from db import Database

    old_path = str(tmp_path / "old2.db")
    conn = await aiosqlite.connect(old_path)
    await conn.execute(
        'CREATE TABLE reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id TEXT, '
        'user_id TEXT, channel_id TEXT, remind_time TEXT, message TEXT, created_at TEXT, completed INTEGER)')
    await conn.execute(
        "INSERT INTO reminders (guild_id, user_id, channel_id, remind_time, message, created_at, completed) "
        "VALUES ('111', '222', '333', '2020-01-01T00:00:00+00:00', 'старое', '2026-01-01', 1)")
    await conn.commit()
    await conn.close()

    Database._instance = None
    db = Database(old_path)
    await db.init_db()

    assert await db.get_active_reminder_count("222") == 0
    await db.clear_expired_reminders(keep_days=0)
    rows = await db.get_user_reminders("222")
    assert rows == []
    if db.conn:
        await db.conn.close()


async def test_deactivate_expired_warnings(db):
    await db.add_security_warning("111", "222", "прошлая", expires_in_hours=-1)
    await db.add_security_warning("111", "222", "будущая", expires_in_hours=24)
    assert await db.get_active_warnings("111", "222") == 1

    deactivated = await db.deactivate_expired_warnings()
    assert deactivated == 1
    assert await db.get_active_warnings("111", "222") == 1


async def _seed_user_stats(db, guild_id="111", user_id="222"):
    await db.create_user(guild_id, user_id)
    await db.conn.execute(
        "UPDATE users SET total_messages = 100, total_voice_minutes = 50, total_commands = 20, "
        "reputation = 5, exp = 1500, level = 12 WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id))
    await db.increment_weekly(guild_id, user_id, "2099-W01", "messages", 10)
    await db.increment_weekly(guild_id, user_id, "2099-W01", "voice_minutes", 5)
    await db.increment_weekly(guild_id, user_id, "2099-W01", "commands", 3)
    await db.update_activity(guild_id, user_id, "voice_join", 4)
    await db.award_achievement(guild_id, user_id, "first_ticket")
    await db.conn.commit()


async def test_clear_message_stats(db):
    await _seed_user_stats(db)
    await db.clear_message_stats("111")
    user = await db.get_or_create_user("111", "222")
    assert user["total_messages"] == 0
    assert user["total_voice_minutes"] == 50
    cursor = await db.conn.execute("SELECT messages FROM weekly_stats WHERE guild_id = '111'")
    row = await cursor.fetchone()
    assert row["messages"] == 0


async def test_clear_voice_and_command_stats(db):
    await _seed_user_stats(db)
    await db.clear_voice_stats("111")
    await db.clear_command_stats("111")
    user = await db.get_or_create_user("111", "222")
    assert user["total_voice_minutes"] == 0
    assert user["total_commands"] == 0
    assert user["total_messages"] == 100
    cursor = await db.conn.execute("SELECT voice_minutes, commands FROM weekly_stats WHERE guild_id = '111'")
    row = await cursor.fetchone()
    assert row["voice_minutes"] == 0
    assert row["commands"] == 0


async def test_clear_weekly_stats_and_reputation(db):
    await _seed_user_stats(db)
    await db.clear_weekly_stats("111")
    await db.clear_reputation("111")
    user = await db.get_or_create_user("111", "222")
    assert user["reputation"] == 0
    cursor = await db.conn.execute("SELECT COUNT(*) as c FROM weekly_stats WHERE guild_id = '111'")
    row = await cursor.fetchone()
    assert row["c"] == 0


async def test_clear_all_activity(db):
    await _seed_user_stats(db)
    await db.clear_all_activity("111")
    user = await db.get_or_create_user("111", "222")
    assert user["total_messages"] == 0
    assert user["total_voice_minutes"] == 0
    assert user["total_commands"] == 0
    assert user["reputation"] == 0
    assert user["exp"] == 0
    assert user["level"] == 1
    assert await db.count_achievements("111", "222") == 0
    assert await db.get_user_activities("111", "222") == {}
    cursor = await db.conn.execute("SELECT COUNT(*) as c FROM weekly_stats WHERE guild_id = '111'")
    assert (await cursor.fetchone())["c"] == 0


async def test_clear_all_data_resets_config(db):
    await db.update_guild_config("111", prefix="!", modules={"chat": False})
    await _seed_user_stats(db)
    await db.clear_all_data("111")
    assert await db.get_guild_config("111") == {}
    cursor = await db.conn.execute("SELECT COUNT(*) as c FROM users WHERE guild_id = '111'")
    assert (await cursor.fetchone())["c"] == 0
    cursor = await db.conn.execute("SELECT COUNT(*) as c FROM clans WHERE guild_id = '111'")
    assert (await cursor.fetchone())["c"] == 0


async def test_migrates_adds_missing_user_columns(tmp_path):
    """БД с roblox_nick, но без raids_attended должны покрываться идемпотентной миграцией."""
    import aiosqlite

    from db import Database

    old_path = str(tmp_path / "old_users.db")
    conn = await aiosqlite.connect(old_path)
    await conn.execute(
        'CREATE TABLE users (guild_id TEXT, user_id TEXT, balance INTEGER DEFAULT 0, '
        'joined_at TIMESTAMP, exp INTEGER DEFAULT 0, level INTEGER DEFAULT 1, '
        'total_messages INTEGER DEFAULT 0, total_voice_minutes INTEGER DEFAULT 0, '
        'total_commands INTEGER DEFAULT 0, reputation INTEGER DEFAULT 0, '
        'roblox_nick TEXT DEFAULT "Не указан", PRIMARY KEY (guild_id, user_id))')
    await conn.commit()
    await conn.close()

    Database._instance = None
    db = Database(old_path)
    await db.init_db()

    cursor = await db.conn.execute("PRAGMA table_info(users)")
    cols = {row[1] for row in await cursor.fetchall()}
    assert "roblox_nick" in cols
    assert "raids_attended" in cols
    if db.conn:
        await db.conn.close()

    Database._instance = None
    db = Database(old_path)
    await db.init_db()
    await db.clear_all_activity("111")
    if db.conn:
        await db.conn.close()