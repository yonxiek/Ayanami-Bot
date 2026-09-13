async def test_afk_lifecycle(db):
    await db.set_afk("111", "222", "сплю")
    afk = await db.get_afk("111", "222")
    assert afk["reason"] == "сплю"
    assert afk["since"]

    await db.clear_afk("111", "222")
    assert await db.get_afk("111", "222") is None


async def test_birthday_lifecycle(db):
    await db.set_birthday("111", "222", 15, 3)
    bday = await db.get_birthday("111", "222")
    assert bday == {"day": 15, "month": 3}

    day_rows = await db.get_birthdays_for("111", 3, 15)
    assert len(day_rows) == 1
    assert day_rows[0]["user_id"] == "222"
    assert await db.get_birthdays_for("111", 4, 1) == []

    await db.mark_birthday_announced("111", "222", "2026-03-15")
    rows = await db.get_birthdays_for("111", 3, 15)
    assert rows[0]["last_announced"] == "2026-03-15"

    await db.remove_birthday("111", "222")
    assert await db.get_birthday("111", "222") is None


async def test_lottery_lifecycle(db):
    await db.set_lottery("111", ticket_price=10, ends_at="2026-01-01T00:00:00+00:00", channel_id="555")
    lottery = await db.get_lottery("111")
    assert lottery["status"] == "active"
    assert lottery["ticket_price"] == 10
    assert lottery["prize_pool"] == 0

    await db.update_user_balance("111", "222", 100)
    ok = await db.buy_lottery_tickets("111", "222", 5, 10)
    assert ok is True
    user = await db.get_or_create_user("111", "222")
    assert user["balance"] == 50

    tickets = await db.get_lottery_tickets("111")
    assert len(tickets) == 1
    assert tickets[0]["tickets"] == 5
    lottery = await db.get_lottery("111")
    assert lottery["prize_pool"] == 50

    poor = await db.buy_lottery_tickets("111", "333", 100, 10)
    assert poor is False

    await db.end_lottery("111")
    lottery = await db.get_lottery("111")
    assert lottery["status"] == "inactive"
    assert await db.get_lottery_tickets("111") == []


async def test_lottery_tickets_accumulate(db):
    await db.set_lottery("111", ticket_price=10, ends_at="2026-01-01T00:00:00+00:00", channel_id="555")
    await db.update_user_balance("111", "222", 500)
    await db.buy_lottery_tickets("111", "222", 2, 10)
    await db.buy_lottery_tickets("111", "222", 3, 10)
    tickets = await db.get_lottery_tickets("111")
    assert tickets[0]["tickets"] == 5