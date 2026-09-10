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