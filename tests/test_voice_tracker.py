from voice_tracker import VoiceTrackerMixin


class Tracker(VoiceTrackerMixin):
    pass


def test_join_then_leave_returns_minutes():
    tracker = Tracker()
    tracker.track_voice_join("1", "100")
    minutes, start = tracker.track_voice_leave("1", "100")
    assert minutes >= 0
    assert start is not None


def test_leave_without_join_returns_zero():
    tracker = Tracker()
    assert tracker.track_voice_leave("1", "100") == (0, None)


def test_leave_pops_session():
    tracker = Tracker()
    tracker.track_voice_join("1", "100")
    tracker.track_voice_leave("1", "100")
    assert tracker.track_voice_leave("1", "100") == (0, None)


def test_get_ongoing_minutes_zero_if_no_session():
    assert Tracker().get_ongoing_minutes("1", "100") == 0


def test_get_ongoing_minutes_positive_if_active():
    tracker = Tracker()
    tracker.track_voice_join("1", "100")
    assert tracker.get_ongoing_minutes("1", "100") >= 0


def test_restore_voice_sessions():
    class FakeMember:
        def __init__(self, uid, bot=False):
            self.id = uid
            self.bot = bot

    class FakeVC:
        def __init__(self, members):
            self.members = members

    class FakeGuild:
        def __init__(self, gid, voice_channels):
            self.id = gid
            self.voice_channels = voice_channels

    class FakeBot:
        def __init__(self, guilds):
            self.guilds = guilds

    tracker = Tracker()
    bot = FakeBot([
        FakeGuild(1, [
            FakeVC([FakeMember(1, bot=False), FakeMember(2, bot=True), FakeMember(3, bot=False)]),
            FakeVC([])
        ])
    ])
    tracker.restore_voice_sessions(bot)
    assert "1" in tracker.voice_sessions
    assert "1" in tracker.voice_sessions["1"]
    assert "3" in tracker.voice_sessions["1"]
    assert "2" not in tracker.voice_sessions.get("1", {})