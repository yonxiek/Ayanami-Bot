import json
from datetime import datetime, timezone

import aiosqlite


class Database:
    _instance = None

    def __new__(cls, db_path="data/bot.db"):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance.db_path = db_path
            cls._instance.conn = None
        return cls._instance

    async def connect(self):
        if not self.conn:
            self.conn = await aiosqlite.connect(self.db_path, timeout=30)
            self.conn.row_factory = aiosqlite.Row
            await self.conn.execute('PRAGMA journal_mode=WAL;')
            await self.conn.execute('PRAGMA synchronous=NORMAL;')
            await self.conn.commit()

    async def init_db(self):
        await self.connect()
        tables = [
            '''CREATE TABLE IF NOT EXISTS users (
                guild_id TEXT, user_id TEXT, balance INTEGER DEFAULT 0,
                joined_at TIMESTAMP, exp INTEGER DEFAULT 0, level INTEGER DEFAULT 1,
                total_messages INTEGER DEFAULT 0, total_voice_minutes INTEGER DEFAULT 0,
                total_commands INTEGER DEFAULT 0, reputation INTEGER DEFAULT 0, 
                roblox_nick TEXT DEFAULT 'Не указан', raids_attended INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, user_id))''',
            '''CREATE TABLE IF NOT EXISTS guild_config (guild_id TEXT PRIMARY KEY, config TEXT NOT NULL)''',
            '''CREATE TABLE IF NOT EXISTS mod_stats (guild_id TEXT, moderator_id TEXT, action_type TEXT, count INTEGER DEFAULT 0, PRIMARY KEY (guild_id, moderator_id, action_type))''',
            '''CREATE TABLE IF NOT EXISTS warns (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id TEXT, user_id TEXT, moderator_id TEXT, reason TEXT, timestamp TEXT)''',
            '''CREATE TABLE IF NOT EXISTS temporary_bans (guild_id TEXT, user_id TEXT, moderator_id TEXT, reason TEXT, until TEXT, timestamp TEXT)''',
            '''CREATE TABLE IF NOT EXISTS mod_notes (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id TEXT, user_id TEXT, moderator_id TEXT, note TEXT, timestamp TEXT)''',
            '''CREATE TABLE IF NOT EXISTS level_roles (guild_id TEXT, level INTEGER, role_id TEXT, PRIMARY KEY (guild_id, level))''',
            '''CREATE TABLE IF NOT EXISTS bounties (
                id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id TEXT, creator_id TEXT, 
                target TEXT, reward INTEGER, channel_id TEXT, message_id TEXT, status TEXT DEFAULT 'active'
            )''',
            '''CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id TEXT, host_id TEXT, 
                type TEXT, start_time TIMESTAMP, channel_id TEXT, message_id TEXT, 
                attendees TEXT DEFAULT '[]', pinged INTEGER DEFAULT 0
            )''',
            '''CREATE TABLE IF NOT EXISTS raid_attendance (
                raid_msg_id TEXT, user_id TEXT, 
                PRIMARY KEY (raid_msg_id, user_id)
            )''',
            '''CREATE TABLE IF NOT EXISTS scheduled_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                channel_id TEXT,
                message_id TEXT,
                end_time TIMESTAMP,
                task_type TEXT,
                metadata TEXT
            )''',
            '''CREATE TABLE IF NOT EXISTS raids_v3 (
                message_id TEXT PRIMARY KEY,
                channel_id TEXT,
                target_channel_id TEXT,
                link TEXT,
                enemies TEXT,
                alliance TEXT,
                ping_role_id TEXT,
                queue_data TEXT DEFAULT '[]',
                status TEXT DEFAULT 'started',
                created_at TIMESTAMP
            )''',
            '''CREATE TABLE IF NOT EXISTS security_warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                user_id TEXT,
                reason TEXT,
                issued_at TIMESTAMP,
                expires_at TIMESTAMP,
                active INTEGER DEFAULT 1
            )''',
            '''CREATE TABLE IF NOT EXISTS game_scores (
                guild_id TEXT,
                user_id TEXT,
                wins INTEGER DEFAULT 0,
                total INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )''',
            '''CREATE TABLE IF NOT EXISTS daily_quests (
                guild_id TEXT,
                quest_id TEXT,
                name TEXT,
                description TEXT,
                quest_type TEXT,
                target INTEGER,
                reward INTEGER,
                reset_hour INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                PRIMARY KEY (guild_id, quest_id)
            )''',
            '''CREATE TABLE IF NOT EXISTS user_quests (
                guild_id TEXT,
                user_id TEXT,
                quest_id TEXT,
                progress INTEGER DEFAULT 0,
                completed INTEGER DEFAULT 0,
                claimed INTEGER DEFAULT 0,
                last_reset TEXT,
                PRIMARY KEY (guild_id, user_id, quest_id)
            )''',
            '''CREATE TABLE IF NOT EXISTS shop_items (
                guild_id TEXT,
                item_id TEXT,
                name TEXT,
                description TEXT,
                price INTEGER,
                item_type TEXT,
                role_id TEXT,
                metadata TEXT DEFAULT '{}',
                stock INTEGER DEFAULT -1,
                enabled INTEGER DEFAULT 1,
                PRIMARY KEY (guild_id, item_id)
            )''',
            '''CREATE TABLE IF NOT EXISTS user_inventory (
                guild_id TEXT,
                user_id TEXT,
                item_id TEXT,
                quantity INTEGER DEFAULT 1,
                purchased_at TEXT,
                PRIMARY KEY (guild_id, user_id, item_id)
            )''',
            '''CREATE TABLE IF NOT EXISTS user_titles (
                guild_id TEXT,
                user_id TEXT,
                title TEXT,
                emoji TEXT DEFAULT '🏷️',
                active INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, user_id, title)
            )''',
            '''CREATE TABLE IF NOT EXISTS user_activities (
                guild_id TEXT,
                user_id TEXT,
                activity_type TEXT,
                amount INTEGER DEFAULT 0,
                last_updated TEXT,
                PRIMARY KEY (guild_id, user_id, activity_type)
            )''',
            '''CREATE TABLE IF NOT EXISTS daily_rewards (
                guild_id TEXT,
                user_id TEXT,
                last_claim TEXT,
                streak INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )''',
            '''CREATE TABLE IF NOT EXISTS random_quest_pool (
                guild_id TEXT,
                pool_id TEXT,
                name TEXT,
                description TEXT,
                quest_type TEXT,
                target INTEGER,
                reward INTEGER,
                weight INTEGER DEFAULT 1,
                enabled INTEGER DEFAULT 1,
                PRIMARY KEY (guild_id, pool_id)
            )''',
            '''CREATE TABLE IF NOT EXISTS random_quest_config (
                guild_id TEXT PRIMARY KEY,
                count INTEGER DEFAULT 3,
                interval_hours INTEGER DEFAULT 6,
                last_rotation TEXT
            )''',
            '''CREATE TABLE IF NOT EXISTS temporary_roles (
                guild_id TEXT,
                user_id TEXT,
                role_id TEXT,
                expires_at TEXT,
                PRIMARY KEY (guild_id, user_id, role_id)
            )''',
            '''CREATE TABLE IF NOT EXISTS xp_boosts (
                guild_id TEXT,
                user_id TEXT,
                multiplier REAL DEFAULT 1.5,
                expires_at TEXT,
                PRIMARY KEY (guild_id, user_id)
            )''',
            '''CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                user_id TEXT,
                channel_id TEXT,
                remind_at TEXT,
                text TEXT,
                done INTEGER DEFAULT 0
            )''',
            '''CREATE TABLE IF NOT EXISTS achievements (
                guild_id TEXT,
                user_id TEXT,
                achievement_id TEXT,
                earned_at TEXT,
                PRIMARY KEY (guild_id, user_id, achievement_id)
            )''',
            '''CREATE TABLE IF NOT EXISTS duel_stats (
                guild_id TEXT,
                user_id TEXT,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                draws INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )''',
            '''CREATE TABLE IF NOT EXISTS weekly_stats (
                guild_id TEXT,
                user_id TEXT,
                week_key TEXT,
                messages INTEGER DEFAULT 0,
                voice_minutes INTEGER DEFAULT 0,
                commands INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, user_id, week_key)
            )''',
            '''CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                user_id TEXT,
                channel_id TEXT,
                ticket_number INTEGER,
                category_name TEXT,
                status TEXT DEFAULT 'open',
                created_at TEXT,
                closed_at TEXT
            )''',
            '''CREATE TABLE IF NOT EXISTS polls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                creator_id TEXT,
                channel_id TEXT,
                message_id TEXT,
                question TEXT,
                options TEXT,
                multi_select INTEGER DEFAULT 0,
                anonymous INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                created_at TEXT,
                ends_at TEXT
            )''',
            '''CREATE TABLE IF NOT EXISTS poll_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                poll_id INTEGER,
                user_id TEXT,
                option_index INTEGER,
                created_at TEXT,
                UNIQUE(poll_id, user_id, option_index)
            )''',
            '''CREATE TABLE IF NOT EXISTS clans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                name TEXT,
                tag TEXT,
                leader_id TEXT,
                description TEXT DEFAULT '',
                icon TEXT DEFAULT '⚔️',
                balance INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                exp INTEGER DEFAULT 0,
                created_at TEXT,
                UNIQUE(guild_id, name),
                UNIQUE(guild_id, tag)
            )''',
            '''CREATE TABLE IF NOT EXISTS clan_members (
                guild_id TEXT,
                user_id TEXT,
                clan_id INTEGER,
                role TEXT DEFAULT 'member',
                joined_at TEXT,
                PRIMARY KEY (guild_id, user_id)
            )''',
            '''CREATE TABLE IF NOT EXISTS collectible_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                card_id TEXT,
                name TEXT,
                description TEXT DEFAULT '',
                rarity TEXT DEFAULT 'common',
                emoji TEXT DEFAULT '🃏',
                image_url TEXT,
                drop_rate REAL DEFAULT 0.1,
                enabled INTEGER DEFAULT 1,
                UNIQUE(guild_id, card_id)
            )''',
            '''CREATE TABLE IF NOT EXISTS user_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                user_id TEXT,
                card_id TEXT,
                quantity INTEGER DEFAULT 1,
                obtained_at TEXT,
                UNIQUE(guild_id, user_id, card_id)
            )''',
            '''CREATE TABLE IF NOT EXISTS ai_moderation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                user_id TEXT,
                channel_id TEXT,
                message_id TEXT,
                original_text TEXT,
                action TEXT,
                reason TEXT,
                confidence REAL,
                created_at TEXT
            )''',
            '''CREATE TABLE IF NOT EXISTS server_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                creator_id TEXT,
                channel_id TEXT,
                message_id TEXT,
                name TEXT,
                description TEXT DEFAULT '',
                starts_at TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT
            )''',
            '''CREATE TABLE IF NOT EXISTS event_rsvps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER,
                user_id TEXT,
                response TEXT,
                created_at TEXT,
                UNIQUE(event_id, user_id)
            )'''
        ]
        
        for table in tables:
            await self.conn.execute(table)
            
        migration_columns = [
            ('users', 'roblox_nick', "TEXT DEFAULT 'Не указан'"),
            ('users', 'raids_attended', 'INTEGER DEFAULT 0'),
            ('shop_items', 'item_id', 'TEXT'),
            ('shop_items', 'name', 'TEXT'),
            ('shop_items', 'description', 'TEXT'),
            ('shop_items', 'price', 'INTEGER'),
            ('shop_items', 'item_type', 'TEXT'),
            ('shop_items', 'role_id', 'TEXT'),
            ('shop_items', 'metadata', "TEXT DEFAULT '{}'"),
            ('shop_items', 'stock', 'INTEGER DEFAULT -1'),
            ('shop_items', 'enabled', 'INTEGER DEFAULT 1'),
            ('user_inventory', 'quantity', 'INTEGER DEFAULT 1'),
            ('user_inventory', 'purchased_at', 'TEXT'),
            ('user_titles', 'emoji', "TEXT DEFAULT '🏷️'"),
            ('user_titles', 'active', 'INTEGER DEFAULT 0'),
            ('user_activities', 'amount', 'INTEGER DEFAULT 0'),
            ('user_activities', 'last_updated', 'TEXT'),
            ('daily_rewards', 'last_claim', 'TEXT'),
            ('daily_rewards', 'streak', 'INTEGER DEFAULT 0'),
            ('daily_quests', 'is_random', 'INTEGER DEFAULT 0'),
            ('users', 'last_xp_time', 'TEXT'),
        ]

        try:
            cursor = await self.conn.execute("PRAGMA table_info(shop_items)")
            cols = [row[1] for row in await cursor.fetchall()]
            if 'item_id' not in cols:
                await self.conn.execute('DROP TABLE IF EXISTS shop_items')
                await self.conn.execute('''CREATE TABLE IF NOT EXISTS shop_items (
                    guild_id TEXT,
                    item_id TEXT,
                    name TEXT,
                    description TEXT,
                    price INTEGER,
                    item_type TEXT,
                    role_id TEXT,
                    metadata TEXT DEFAULT '{}',
                    stock INTEGER DEFAULT -1,
                    enabled INTEGER DEFAULT 1,
                    PRIMARY KEY (guild_id, item_id)
                )''')
        except Exception:
            pass

        for table, column, col_type in migration_columns:
            try:
                await self.conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {col_type}')
            except Exception:
                pass

        # Миграция старой схемы напоминаний (remind_time/message/completed -> remind_at/text/done)
        try:
            cursor = await self.conn.execute("PRAGMA table_info(reminders)")
            cols = {row[1] for row in await cursor.fetchall()}
            if 'remind_at' not in cols and 'remind_time' in cols:
                await self.conn.execute('ALTER TABLE reminders ADD COLUMN remind_at TEXT')
                await self.conn.execute('UPDATE reminders SET remind_at = remind_time WHERE remind_at IS NULL')
            if 'text' not in cols and 'message' in cols:
                await self.conn.execute('ALTER TABLE reminders ADD COLUMN text TEXT')
                await self.conn.execute('UPDATE reminders SET text = message WHERE text IS NULL')
            if 'done' not in cols and 'completed' in cols:
                await self.conn.execute('ALTER TABLE reminders ADD COLUMN done INTEGER DEFAULT 0')
                await self.conn.execute('UPDATE reminders SET done = completed')
        except Exception:
            pass

        await self.conn.commit()

    async def create_user(self, guild_id: str, user_id: str):
        await self.conn.execute('INSERT OR IGNORE INTO users (guild_id, user_id, joined_at) VALUES (?, ?, ?)',
                                (guild_id, user_id, datetime.now(timezone.utc).isoformat()))
        await self.conn.commit()

    async def get_or_create_user(self, guild_id: str, user_id: str) -> dict:
        await self.create_user(guild_id, user_id)
        cursor = await self.conn.execute('SELECT * FROM users WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        row = await cursor.fetchone()
        return dict(row) if row else {}

    async def update_user_balance(self, guild_id: str, user_id: str, amount: int):
        await self.create_user(guild_id, user_id)
        await self.conn.execute('UPDATE users SET balance = balance + ? WHERE guild_id = ? AND user_id = ?', (amount, guild_id, user_id))
        await self.conn.commit()

    async def get_top_users(self, guild_id: str, limit: int = 10) -> list:
        cursor = await self.conn.execute('SELECT user_id, balance FROM users WHERE guild_id = ? ORDER BY balance DESC LIMIT ?', (guild_id, limit))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def increment_mod_stat(self, guild_id: str, moderator_id: str, action_type: str, amount: int = 1):
        await self.conn.execute('''
            INSERT INTO mod_stats (guild_id, moderator_id, action_type, count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, moderator_id, action_type) 
            DO UPDATE SET count = count + ?
        ''', (guild_id, moderator_id, action_type, amount, amount))
        await self.conn.commit()

    async def get_mod_stats(self, guild_id: str, moderator_id: str) -> dict[str, int]:
        try:
            cursor = await self.conn.execute('SELECT action_type, count FROM mod_stats WHERE guild_id = ? AND moderator_id = ?', (guild_id, moderator_id))
            rows = await cursor.fetchall()
            return {row['action_type']: row['count'] for row in rows}
        except: return {}

    async def get_guild_config(self, guild_id: str) -> dict:
        try:
            cursor = await self.conn.execute('SELECT config FROM guild_config WHERE guild_id = ?', (guild_id,))
            row = await cursor.fetchone()
            return json.loads(row['config']) if row else {}
        except: return {}

    async def update_guild_config(self, guild_id: str, **kwargs):
        config = await self.get_guild_config(guild_id)
        config.update(kwargs)
        await self.conn.execute('INSERT OR REPLACE INTO guild_config (guild_id, config) VALUES (?, ?)',
                                (guild_id, json.dumps(config, ensure_ascii=False)))
        await self.conn.commit()

    async def update_config_field(self, guild_id: str, key: str, value):
        config = await self.get_guild_config(guild_id)
        config[key] = value
        await self.conn.execute('INSERT OR REPLACE INTO guild_config (guild_id, config) VALUES (?, ?)',
                                (guild_id, json.dumps(config, ensure_ascii=False)))
        await self.conn.commit()

    async def update_user_stats(self, guild_id: str, user_id: str, **kwargs):
        if not kwargs: return
        set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
        await self.conn.execute(f"UPDATE users SET {set_clause} WHERE guild_id = ? AND user_id = ?", list(kwargs.values()) + [guild_id, user_id])
        await self.conn.commit()

    # ==========================================
    #     SECURITY WARNINGS
    # ==========================================

    async def add_security_warning(self, guild_id: str, user_id: str, reason: str, expires_in_hours: int = 24):
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=expires_in_hours)
        await self.conn.execute(
            'INSERT INTO security_warnings (guild_id, user_id, reason, issued_at, expires_at, active) VALUES (?, ?, ?, ?, ?, 1)',
            (guild_id, user_id, reason, now.isoformat(), expires.isoformat())
        )
        await self.conn.commit()

    async def get_active_warnings(self, guild_id: str, user_id: str) -> int:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self.conn.execute(
            'SELECT COUNT(*) FROM security_warnings WHERE guild_id = ? AND user_id = ? AND active = 1 AND expires_at > ?',
            (guild_id, user_id, now)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def clear_user_warnings(self, guild_id: str, user_id: str):
        await self.conn.execute(
            'UPDATE security_warnings SET active = 0 WHERE guild_id = ? AND user_id = ? AND active = 1',
            (guild_id, user_id)
        )
        await self.conn.commit()

    async def deactivate_expired_warnings(self) -> int:
        """Деактивирует просроченные security_warnings. Возвращает количество обработанных записей."""
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self.conn.execute(
            'UPDATE security_warnings SET active = 0 WHERE active = 1 AND expires_at <= ?',
            (now,)
        )
        await self.conn.commit()
        return cursor.rowcount

    # ==========================================
    #     DAILY QUESTS
    # ==========================================

    async def create_quest(self, guild_id: str, quest_id: str, name: str, description: str,
                           quest_type: str, target: int, reward: int, reset_hour: int = 0):
        await self.conn.execute(
            'INSERT OR REPLACE INTO daily_quests (guild_id, quest_id, name, description, quest_type, target, reward, reset_hour) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (guild_id, quest_id, name, description, quest_type, target, reward, reset_hour)
        )
        await self.conn.commit()

    async def delete_quest(self, guild_id: str, quest_id: str):
        await self.conn.execute('DELETE FROM daily_quests WHERE guild_id = ? AND quest_id = ?', (guild_id, quest_id))
        await self.conn.commit()

    async def get_guild_quests(self, guild_id: str) -> list:
        cursor = await self.conn.execute(
            'SELECT quest_id, name, description, quest_type, target, reward, reset_hour, enabled FROM daily_quests WHERE guild_id = ?',
            (guild_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_user_quest_progress(self, guild_id: str, user_id: str, quest_id: str) -> dict:
        cursor = await self.conn.execute(
            'SELECT progress, completed, claimed, last_reset FROM user_quests WHERE guild_id = ? AND user_id = ? AND quest_id = ?',
            (guild_id, user_id, quest_id)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def reset_daily_quests(self, guild_id: str):
        await self.conn.execute(
            'UPDATE user_quests SET progress = 0, completed = 0, claimed = 0, last_reset = ? WHERE guild_id = ?',
            (datetime.now(timezone.utc).isoformat(), guild_id)
        )
        await self.conn.commit()

    async def increment_quest_progress(self, guild_id: str, user_id: str, quest_type: str, amount: int = 1) -> list:
        cursor = await self.conn.execute(
            'SELECT q.quest_id, q.target, q.reward, q.name FROM daily_quests q '
            'WHERE q.guild_id = ? AND q.quest_type = ? AND q.enabled = 1',
            (guild_id, quest_type)
        )
        rows = await cursor.fetchall()
        completed_quests = []
        for row in rows:
            quest_id = row['quest_id']
            target = row['target']
            user_quest = await self.get_user_quest_progress(guild_id, user_id, quest_id)
            if not user_quest:
                await self.conn.execute(
                    'INSERT INTO user_quests (guild_id, user_id, quest_id, progress, completed, claimed, last_reset) '
                    'VALUES (?, ?, ?, 0, 0, 0, ?)',
                    (guild_id, user_id, quest_id, datetime.now(timezone.utc).isoformat())
                )
                await self.conn.commit()
                user_quest = {'progress': 0, 'completed': False, 'claimed': False}
            if not user_quest['completed']:
                new_progress = user_quest['progress'] + amount
                if new_progress >= target:
                    await self.conn.execute(
                        'UPDATE user_quests SET completed = 1 WHERE guild_id = ? AND user_id = ? AND quest_id = ?',
                        (guild_id, user_id, quest_id)
                    )
                    await self.update_user_balance(guild_id, user_id, row['reward'])
                    await self.conn.execute(
                        'UPDATE user_quests SET claimed = 1 WHERE guild_id = ? AND user_id = ? AND quest_id = ?',
                        (guild_id, user_id, quest_id)
                    )
                    await self.conn.commit()
                    completed_quests.append({
                        'quest_id': quest_id,
                        'name': row['name'],
                        'reward': row['reward'],
                    })
                else:
                    await self.conn.execute(
                        'UPDATE user_quests SET progress = ? WHERE guild_id = ? AND user_id = ? AND quest_id = ?',
                        (new_progress, guild_id, user_id, quest_id)
                    )
                    await self.conn.commit()
        return completed_quests

    async def clear_all_quest_progress(self, guild_id: str):
        await self.conn.execute('DELETE FROM user_quests WHERE guild_id = ?', (guild_id,))
        await self.conn.commit()

    async def clear_quest_progress(self, guild_id: str, quest_id: str):
        await self.conn.execute('DELETE FROM user_quests WHERE guild_id = ? AND quest_id = ?', (guild_id, quest_id))
        await self.conn.commit()

    async def clear_all_quests(self, guild_id: str):
        await self.conn.execute('DELETE FROM daily_quests WHERE guild_id = ?', (guild_id,))
        await self.conn.execute('DELETE FROM user_quests WHERE guild_id = ?', (guild_id,))
        await self.conn.commit()

    async def clear_random_pool(self, guild_id: str):
        await self.conn.execute('DELETE FROM random_quest_pool WHERE guild_id = ?', (guild_id,))
        await self.conn.commit()

    async def clear_user_activity(self, guild_id: str):
        await self.conn.execute('DELETE FROM user_activities WHERE guild_id = ?', (guild_id,))
        await self.conn.commit()

    async def clear_levels(self, guild_id: str):
        await self.conn.execute('UPDATE users SET exp = 0, level = 1 WHERE guild_id = ?', (guild_id,))
        await self.conn.commit()

    async def clear_balances(self, guild_id: str):
        await self.conn.execute('UPDATE users SET balance = 0 WHERE guild_id = ?', (guild_id,))
        await self.conn.commit()

    async def clear_daily_rewards(self, guild_id: str):
        await self.conn.execute('DELETE FROM daily_rewards WHERE guild_id = ?', (guild_id,))
        await self.conn.commit()

    async def clear_message_stats(self, guild_id: str):
        await self.conn.execute('UPDATE users SET total_messages = 0 WHERE guild_id = ?', (guild_id,))
        await self.conn.execute('UPDATE weekly_stats SET messages = 0 WHERE guild_id = ?', (guild_id,))
        await self.conn.commit()

    async def clear_voice_stats(self, guild_id: str):
        await self.conn.execute('UPDATE users SET total_voice_minutes = 0 WHERE guild_id = ?', (guild_id,))
        await self.conn.execute('UPDATE weekly_stats SET voice_minutes = 0 WHERE guild_id = ?', (guild_id,))
        await self.conn.commit()

    async def clear_command_stats(self, guild_id: str):
        await self.conn.execute('UPDATE users SET total_commands = 0 WHERE guild_id = ?', (guild_id,))
        await self.conn.execute('UPDATE weekly_stats SET commands = 0 WHERE guild_id = ?', (guild_id,))
        await self.conn.commit()

    async def clear_weekly_stats(self, guild_id: str):
        await self.conn.execute('DELETE FROM weekly_stats WHERE guild_id = ?', (guild_id,))
        await self.conn.commit()

    async def clear_reputation(self, guild_id: str):
        await self.conn.execute('UPDATE users SET reputation = 0 WHERE guild_id = ?', (guild_id,))
        await self.conn.commit()

    async def clear_achievements(self, guild_id: str):
        await self.conn.execute('DELETE FROM achievements WHERE guild_id = ?', (guild_id,))
        await self.conn.commit()

    async def clear_duel_stats(self, guild_id: str):
        await self.conn.execute('DELETE FROM duel_stats WHERE guild_id = ?', (guild_id,))
        await self.conn.commit()

    async def clear_game_scores(self, guild_id: str):
        await self.conn.execute('DELETE FROM game_scores WHERE guild_id = ?', (guild_id,))
        await self.conn.commit()

    async def clear_all_activity(self, guild_id: str):
        await self.conn.execute('DELETE FROM user_activities WHERE guild_id = ?', (guild_id,))
        await self.conn.execute(
            'UPDATE users SET total_messages = 0, total_voice_minutes = 0, total_commands = 0, '
            'reputation = 0, exp = 0, level = 1, raids_attended = 0 WHERE guild_id = ?',
            (guild_id,)
        )
        await self.conn.execute('DELETE FROM weekly_stats WHERE guild_id = ?', (guild_id,))
        await self.conn.execute('DELETE FROM daily_rewards WHERE guild_id = ?', (guild_id,))
        await self.conn.execute('DELETE FROM achievements WHERE guild_id = ?', (guild_id,))
        await self.conn.execute('DELETE FROM duel_stats WHERE guild_id = ?', (guild_id,))
        await self.conn.execute('DELETE FROM game_scores WHERE guild_id = ?', (guild_id,))
        await self.conn.commit()

    async def clear_all_data(self, guild_id: str):
        guild_tables = [
            'users', 'mod_stats', 'warns', 'temporary_bans', 'mod_notes', 'level_roles',
            'bounties', 'events', 'scheduled_tasks', 'security_warnings', 'game_scores',
            'daily_quests', 'user_quests', 'shop_items', 'user_inventory', 'user_titles',
            'user_activities', 'daily_rewards', 'random_quest_pool', 'random_quest_config',
            'temporary_roles', 'xp_boosts', 'reminders', 'achievements', 'duel_stats',
            'weekly_stats', 'tickets', 'polls', 'clans', 'clan_members', 'collectible_cards',
            'user_cards', 'ai_moderation_log', 'server_events'
        ]
        for table in guild_tables:
            await self.conn.execute(f'DELETE FROM {table} WHERE guild_id = ?', (guild_id,))
        await self.conn.execute('DELETE FROM poll_votes WHERE poll_id IN (SELECT id FROM polls WHERE guild_id = ?)', (guild_id,))
        await self.conn.execute('DELETE FROM event_rsvps WHERE event_id IN (SELECT id FROM server_events WHERE guild_id = ?)', (guild_id,))
        await self.conn.execute('DELETE FROM raids_v3', ())
        await self.conn.execute('DELETE FROM raid_attendance', ())
        await self.conn.execute('DELETE FROM guild_config WHERE guild_id = ?', (guild_id,))
        await self.conn.commit()

    async def get_quest_progress_stats(self, guild_id: str) -> dict:
        cursor = await self.conn.execute(
            'SELECT quest_id, COUNT(*) as total, SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) as done '
            'FROM user_quests WHERE guild_id = ? GROUP BY quest_id',
            (guild_id,)
        )
        rows = await cursor.fetchall()
        return {row['quest_id']: {'total': row['total'], 'done': row['done']} for row in rows}

    # ==========================================
    #     RANDOM QUEST POOL
    # ==========================================

    async def get_random_quest_pool(self, guild_id: str) -> list:
        cursor = await self.conn.execute(
            'SELECT * FROM random_quest_pool WHERE guild_id = ? AND enabled = 1',
            (guild_id,)
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def add_random_quest(self, guild_id: str, pool_id: str, name: str, description: str,
                               quest_type: str, target: int, reward: int, weight: int = 1):
        await self.conn.execute(
            'INSERT OR REPLACE INTO random_quest_pool (guild_id, pool_id, name, description, quest_type, target, reward, weight, enabled) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)',
            (guild_id, pool_id, name, description, quest_type, target, reward, weight)
        )
        await self.conn.commit()

    async def remove_random_quest(self, guild_id: str, pool_id: str):
        await self.conn.execute(
            'DELETE FROM random_quest_pool WHERE guild_id = ? AND pool_id = ?',
            (guild_id, pool_id)
        )
        await self.conn.commit()

    async def get_random_quest_config(self, guild_id: str) -> dict:
        cursor = await self.conn.execute(
            'SELECT * FROM random_quest_config WHERE guild_id = ?',
            (guild_id,)
        )
        row = await cursor.fetchone()
        if not row:
            await self.conn.execute(
                'INSERT OR IGNORE INTO random_quest_config (guild_id) VALUES (?)',
                (guild_id,)
            )
            await self.conn.commit()
            return {'guild_id': guild_id, 'count': 3, 'interval_hours': 6, 'last_rotation': None}
        return dict(row)

    async def update_random_quest_config(self, guild_id: str, **kwargs):
        await self.get_random_quest_config(guild_id)
        for key, value in kwargs.items():
            await self.conn.execute(
                f'UPDATE random_quest_config SET {key} = ? WHERE guild_id = ?',
                (value, guild_id)
            )
        await self.conn.commit()

    async def rotate_random_quests(self, guild_id: str) -> list:
        import random as rnd
        config = await self.get_random_quest_config(guild_id)
        pool = await self.get_random_quest_pool(guild_id)
        if not pool:
            return []

        await self.conn.execute(
            'DELETE FROM daily_quests WHERE guild_id = ? AND is_random = 1',
            (guild_id,)
        )

        count = min(config['count'], len(pool))
        weights = [item['weight'] for item in pool]
        selected = rnd.choices(pool, weights=weights, k=count)

        now = datetime.now(timezone.utc).isoformat()
        new_quests = []
        for item in selected:
            await self.conn.execute(
                'INSERT OR REPLACE INTO daily_quests '
                '(guild_id, quest_id, name, description, quest_type, target, reward, enabled, is_random) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1)',
                (guild_id, f"random_{item['pool_id']}_{int(now)}", item['name'], item['description'],
                 item['quest_type'], item['target'], item['reward'])
            )
            new_quests.append(item['name'])

        await self.conn.execute(
            'UPDATE random_quest_config SET last_rotation = ? WHERE guild_id = ?',
            (now, guild_id)
        )
        await self.conn.commit()
        return new_quests

    # ==========================================
    #     TEMPORARY ROLES & XP BOOSTS
    # ==========================================

    async def add_temporary_role(self, guild_id: str, user_id: str, role_id: str, expires_at: str):
        await self.conn.execute(
            'INSERT OR REPLACE INTO temporary_roles (guild_id, user_id, role_id, expires_at) VALUES (?, ?, ?, ?)',
            (guild_id, user_id, role_id, expires_at)
        )
        await self.conn.commit()

    async def remove_expired_roles(self) -> list:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self.conn.execute(
            'SELECT * FROM temporary_roles WHERE expires_at <= ?', (now,)
        )
        expired = [dict(row) for row in await cursor.fetchall()]
        if expired:
            await self.conn.execute(
                'DELETE FROM temporary_roles WHERE expires_at <= ?', (now,)
            )
            await self.conn.commit()
        return expired

    async def add_xp_boost(self, guild_id: str, user_id: str, multiplier: float, expires_at: str):
        await self.conn.execute(
            'INSERT OR REPLACE INTO xp_boosts (guild_id, user_id, multiplier, expires_at) VALUES (?, ?, ?, ?)',
            (guild_id, user_id, multiplier, expires_at)
        )
        await self.conn.commit()

    async def get_xp_boost(self, guild_id: str, user_id: str) -> dict:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self.conn.execute(
            'SELECT * FROM xp_boosts WHERE guild_id = ? AND user_id = ? AND expires_at > ?',
            (guild_id, user_id, now)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def remove_expired_boosts(self) -> list:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self.conn.execute(
            'SELECT * FROM xp_boosts WHERE expires_at <= ?', (now,)
        )
        expired = [dict(row) for row in await cursor.fetchall()]
        if expired:
            await self.conn.execute(
                'DELETE FROM xp_boosts WHERE expires_at <= ?', (now,)
            )
            await self.conn.commit()
        return expired

    # ==========================================
    #     TEMPORARY BANS (временные баны)
    # ==========================================

    async def add_temporary_ban(self, guild_id: str, user_id: str, moderator_id: str, reason: str, until: str):
        await self.conn.execute(
            'INSERT OR REPLACE INTO temporary_bans (guild_id, user_id, moderator_id, reason, until, timestamp) VALUES (?, ?, ?, ?, ?, ?)',
            (guild_id, user_id, moderator_id, reason, until, datetime.now(timezone.utc).isoformat())
        )
        await self.conn.commit()

    async def get_temporary_ban(self, guild_id: str, user_id: str) -> dict:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self.conn.execute(
            'SELECT * FROM temporary_bans WHERE guild_id = ? AND user_id = ? AND until > ?',
            (guild_id, user_id, now)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def remove_temporary_ban(self, guild_id: str, user_id: str):
        await self.conn.execute(
            'DELETE FROM temporary_bans WHERE guild_id = ? AND user_id = ?',
            (guild_id, user_id)
        )
        await self.conn.commit()

    async def get_guild_temporary_bans(self, guild_id: str) -> list:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self.conn.execute(
            'SELECT * FROM temporary_bans WHERE guild_id = ? AND until > ?',
            (guild_id, now)
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def remove_expired_temporary_bans(self) -> list:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self.conn.execute(
            'SELECT * FROM temporary_bans WHERE until <= ?', (now,)
        )
        expired = [dict(row) for row in await cursor.fetchall()]
        if expired:
            await self.conn.execute(
                'DELETE FROM temporary_bans WHERE until <= ?', (now,)
            )
            await self.conn.commit()
        return expired

    # ==========================================
    #     LEVELING SYSTEM
    # ==========================================

    async def add_xp(self, guild_id: str, user_id: str, amount: int) -> dict:
        await self.create_user(guild_id, user_id)
        cursor = await self.conn.execute(
            'SELECT exp, level FROM users WHERE guild_id = ? AND user_id = ?',
            (guild_id, user_id)
        )
        row = await cursor.fetchone()
        if not row:
            return {'leveled_up': False, 'new_level': 1, 'total_xp': amount}

        old_level = row['level']
        new_xp = row['exp'] + amount
        new_level = int((new_xp / 100) ** 0.5) + 1

        await self.conn.execute(
            'UPDATE users SET exp = ?, level = ? WHERE guild_id = ? AND user_id = ?',
            (new_xp, new_level, guild_id, user_id)
        )
        await self.conn.commit()

        return {
            'leveled_up': new_level > old_level,
            'new_level': new_level,
            'total_xp': new_xp,
            'old_level': old_level,
        }

    async def get_level_roles(self, guild_id: str) -> list:
        cursor = await self.conn.execute(
            'SELECT level, role_id FROM level_roles WHERE guild_id = ? ORDER BY level',
            (guild_id,)
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def set_level_role(self, guild_id: str, level: int, role_id: str):
        await self.conn.execute(
            'INSERT OR REPLACE INTO level_roles (guild_id, level, role_id) VALUES (?, ?, ?)',
            (guild_id, level, role_id)
        )
        await self.conn.commit()

    async def get_top_users_by_level(self, guild_id: str, limit: int = 10) -> list:
        cursor = await self.conn.execute(
            'SELECT user_id, exp, level FROM users WHERE guild_id = ? ORDER BY exp DESC LIMIT ?',
            (guild_id, limit)
        )
        return [dict(row) for row in await cursor.fetchall()]

    # ==========================================
    #     SHOP
    # ==========================================

    async def create_shop_item(self, guild_id: str, item_id: str, name: str, description: str,
                               price: int, item_type: str, role_id: str = None, metadata: dict = None, stock: int = -1):
        import json
        await self.conn.execute(
            'INSERT OR REPLACE INTO shop_items (guild_id, item_id, name, description, price, item_type, role_id, metadata, stock, enabled) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)',
            (guild_id, item_id, name, description, price, item_type, role_id, json.dumps(metadata or {}, ensure_ascii=False), stock)
        )
        await self.conn.commit()

    async def delete_shop_item(self, guild_id: str, item_id: str):
        await self.conn.execute('DELETE FROM shop_items WHERE guild_id = ? AND item_id = ?', (guild_id, item_id))
        await self.conn.commit()

    async def get_shop_items(self, guild_id: str) -> list:
        cursor = await self.conn.execute(
            'SELECT item_id, name, description, price, item_type, role_id, metadata, stock, enabled FROM shop_items WHERE guild_id = ? AND enabled = 1',
            (guild_id,)
        )
        rows = await cursor.fetchall()
        result = []
        import json
        for row in rows:
            item = dict(row)
            item['metadata'] = json.loads(item['metadata'])
            result.append(item)
        return result

    async def get_shop_item(self, guild_id: str, item_id: str) -> dict:
        import json
        cursor = await self.conn.execute(
            'SELECT item_id, name, description, price, item_type, role_id, metadata, stock, enabled FROM shop_items WHERE guild_id = ? AND item_id = ?',
            (guild_id, item_id)
        )
        row = await cursor.fetchone()
        if row:
            item = dict(row)
            item['metadata'] = json.loads(item['metadata'])
            return item
        return None

    async def buy_shop_item(self, guild_id: str, user_id: str, item_id: str) -> bool:
        item = await self.get_shop_item(guild_id, item_id)
        if not item or not item['enabled']:
            return False
        if item['stock'] == 0:
            return False

        user = await self.get_or_create_user(guild_id, user_id)
        if user.get('balance', 0) < item['price']:
            return False

        await self.conn.execute(
            'UPDATE users SET balance = balance - ? WHERE guild_id = ? AND user_id = ?',
            (item['price'], guild_id, user_id)
        )
        await self.conn.execute(
            'INSERT OR REPLACE INTO user_inventory (guild_id, user_id, item_id, quantity, purchased_at) VALUES (?, ?, ?, COALESCE((SELECT quantity FROM user_inventory WHERE guild_id = ? AND user_id = ? AND item_id = ?), 0) + 1, ?)',
            (guild_id, user_id, item_id, guild_id, user_id, item_id, datetime.now(timezone.utc).isoformat())
        )
        if item['stock'] > 0:
            await self.conn.execute(
                'UPDATE shop_items SET stock = stock - 1 WHERE guild_id = ? AND item_id = ?',
                (guild_id, item_id)
            )
        await self.conn.commit()
        return True

    async def get_user_inventory(self, guild_id: str, user_id: str) -> list:
        cursor = await self.conn.execute(
            'SELECT ui.item_id, ui.quantity, si.name, si.description, si.item_type, si.role_id '
            'FROM user_inventory ui '
            'LEFT JOIN shop_items si ON ui.item_id = si.item_id AND ui.guild_id = si.guild_id '
            'WHERE ui.guild_id = ? AND ui.user_id = ?',
            (guild_id, user_id)
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def add_user_title(self, guild_id: str, user_id: str, title: str, emoji: str = '🏷️'):
        try:
            await self.conn.execute(
                'INSERT OR IGNORE INTO user_titles (guild_id, user_id, title, emoji, active) VALUES (?, ?, ?, ?, 0)',
                (guild_id, user_id, title, emoji)
            )
            await self.conn.commit()
            return True
        except Exception:
            return False

    async def get_user_titles(self, guild_id: str, user_id: str) -> list:
        cursor = await self.conn.execute(
            'SELECT title, emoji, active FROM user_titles WHERE guild_id = ? AND user_id = ?',
            (guild_id, user_id)
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def set_active_title(self, guild_id: str, user_id: str, title: str):
        await self.conn.execute(
            'UPDATE user_titles SET active = 0 WHERE guild_id = ? AND user_id = ?',
            (guild_id, user_id)
        )
        await self.conn.execute(
            'UPDATE user_titles SET active = 1 WHERE guild_id = ? AND user_id = ? AND title = ?',
            (guild_id, user_id, title)
        )
        await self.conn.commit()

    # ==========================================
    #     DAILY REWARDS / ACTIVITIES
    # ==========================================

    async def claim_daily_reward(self, guild_id: str, user_id: str, base_reward: int = 100) -> tuple[bool, int, int]:
        cursor = await self.conn.execute(
            'SELECT last_claim, streak FROM daily_rewards WHERE guild_id = ? AND user_id = ?',
            (guild_id, user_id)
        )
        row = await cursor.fetchone()
        now = datetime.now(timezone.utc)
        streak = 1

        if row:
            last_claim = datetime.fromisoformat(row['last_claim'])
            diff = now - last_claim
            if diff.total_seconds() < 86400:
                return False, 0, 0
            if diff.total_seconds() < 172800:
                streak = row['streak'] + 1
            else:
                streak = 1

        reward = base_reward + (streak - 1) * 25

        await self.conn.execute(
            'INSERT OR REPLACE INTO daily_rewards (guild_id, user_id, last_claim, streak) VALUES (?, ?, ?, ?)',
            (guild_id, user_id, now.isoformat(), streak)
        )
        await self.update_user_balance(guild_id, user_id, reward)
        return True, reward, streak

    async def get_daily_streak(self, guild_id: str, user_id: str) -> int:
        cursor = await self.conn.execute(
            'SELECT streak FROM daily_rewards WHERE guild_id = ? AND user_id = ?',
            (guild_id, user_id)
        )
        row = await cursor.fetchone()
        return row['streak'] if row else 0

    async def update_activity(self, guild_id: str, user_id: str, activity_type: str, amount: int = 1):
        await self.conn.execute(
            'INSERT INTO user_activities (guild_id, user_id, activity_type, amount, last_updated) VALUES (?, ?, ?, ?, ?) '
            'ON CONFLICT(guild_id, user_id, activity_type) DO UPDATE SET amount = amount + ?, last_updated = ?',
            (guild_id, user_id, activity_type, amount, datetime.now(timezone.utc).isoformat(), amount, datetime.now(timezone.utc).isoformat())
        )
        await self.conn.commit()

    async def get_user_activities(self, guild_id: str, user_id: str) -> dict:
        cursor = await self.conn.execute(
            'SELECT activity_type, amount FROM user_activities WHERE guild_id = ? AND user_id = ?',
            (guild_id, user_id)
        )
        rows = await cursor.fetchall()
        return {row['activity_type']: row['amount'] for row in rows}

    # ==========================================
    #     REMINDERS (напоминания)
    # ==========================================

    async def add_reminder(self, guild_id: str, user_id: str, channel_id: int, remind_at: str, text: str):
        await self.conn.execute(
            'INSERT INTO reminders (guild_id, user_id, channel_id, remind_at, text) VALUES (?, ?, ?, ?, ?)',
            (guild_id, user_id, str(channel_id), remind_at, text)
        )
        await self.conn.commit()

    async def get_active_reminder_count(self, user_id: str) -> int:
        cursor = await self.conn.execute(
            'SELECT COUNT(*) AS cnt FROM reminders WHERE user_id = ? AND done = 0',
            (user_id,)
        )
        row = await cursor.fetchone()
        return row['cnt'] if row else 0

    async def get_due_reminders(self) -> list:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self.conn.execute(
            'SELECT * FROM reminders WHERE done = 0 AND remind_at <= ?',
            (now,)
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def mark_reminder_done(self, reminder_id: int):
        await self.conn.execute(
            'UPDATE reminders SET done = 1 WHERE id = ?',
            (reminder_id,)
        )
        await self.conn.commit()

    async def delete_reminder(self, reminder_id: int, user_id: str) -> bool:
        cursor = await self.conn.execute(
            'DELETE FROM reminders WHERE id = ? AND user_id = ?',
            (reminder_id, user_id)
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def get_user_reminders(self, user_id: str) -> list:
        cursor = await self.conn.execute(
            'SELECT id, guild_id, channel_id, remind_at, text FROM reminders WHERE user_id = ? AND done = 0 ORDER BY remind_at',
            (user_id,)
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def clear_expired_reminders(self, keep_days: int = 7):
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).isoformat()
        await self.conn.execute(
            'DELETE FROM reminders WHERE done = 1 AND remind_at < ?',
            (cutoff,)
        )
        await self.conn.commit()

    # ==========================================
    #     ACHIEVEMENTS (достижения)
    # ==========================================

    async def award_achievement(self, guild_id: str, user_id: str, achievement_id: str) -> bool:
        """Возвращает True, если достижение выдано впервые."""
        from datetime import datetime, timezone
        cursor = await self.conn.execute(
            'SELECT 1 FROM achievements WHERE guild_id = ? AND user_id = ? AND achievement_id = ?',
            (guild_id, user_id, achievement_id)
        )
        if await cursor.fetchone():
            return False
        await self.conn.execute(
            'INSERT INTO achievements (guild_id, user_id, achievement_id, earned_at) VALUES (?, ?, ?, ?)',
            (guild_id, user_id, achievement_id, datetime.now(timezone.utc).isoformat())
        )
        await self.conn.commit()
        return True

    async def get_user_achievements(self, guild_id: str, user_id: str) -> list:
        cursor = await self.conn.execute(
            'SELECT achievement_id, earned_at FROM achievements WHERE guild_id = ? AND user_id = ? ORDER BY earned_at',
            (guild_id, user_id)
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def count_achievements(self, guild_id: str, user_id: str) -> int:
        cursor = await self.conn.execute(
            'SELECT COUNT(*) AS cnt FROM achievements WHERE guild_id = ? AND user_id = ?',
            (guild_id, user_id)
        )
        row = await cursor.fetchone()
        return row['cnt'] if row else 0

    async def count_completed_quests(self, guild_id: str, user_id: str) -> int:
        cursor = await self.conn.execute(
            'SELECT COUNT(*) AS cnt FROM user_quests WHERE guild_id = ? AND user_id = ? AND completed = 1',
            (guild_id, user_id)
        )
        row = await cursor.fetchone()
        return row['cnt'] if row else 0

    # ==========================================
    #     DUEL STATS (дуэли)
    # ==========================================

    async def add_duel_result(self, guild_id: str, user_id: str, result: str):
        """result: 'win' | 'loss' | 'draw'"""
        column = {'win': 'wins', 'loss': 'losses', 'draw': 'draws'}.get(result, 'draws')
        await self.conn.execute(
            f'INSERT INTO duel_stats (guild_id, user_id, wins, losses, draws) VALUES (?, ?, ?, ?, ?) '
            f'ON CONFLICT(guild_id, user_id) DO UPDATE SET {column} = {column} + 1',
            (guild_id, user_id, 1 if result == 'win' else 0, 1 if result == 'loss' else 0, 1 if result == 'draw' else 0)
        )
        await self.conn.commit()

    async def get_duel_stats(self, guild_id: str, user_id: str) -> dict:
        cursor = await self.conn.execute(
            'SELECT wins, losses, draws FROM duel_stats WHERE guild_id = ? AND user_id = ?',
            (guild_id, user_id)
        )
        row = await cursor.fetchone()
        if not row:
            await self.conn.execute(
                'INSERT OR IGNORE INTO duel_stats (guild_id, user_id) VALUES (?, ?)',
                (guild_id, user_id)
            )
            await self.conn.commit()
            return {'wins': 0, 'losses': 0, 'draws': 0}
        return dict(row)

    # ==========================================
    #     WEEKLY STATS (недельная статистика)
    # ==========================================

    async def increment_weekly(self, guild_id: str, user_id: str, week_key: str, field: str, amount: int = 1):
        if field not in ('messages', 'voice_minutes', 'commands'):
            return
        await self.conn.execute(
            f'INSERT INTO weekly_stats (guild_id, user_id, week_key, messages, voice_minutes, commands) VALUES (?, ?, ?, ?, ?, ?) '
            f'ON CONFLICT(guild_id, user_id, week_key) DO UPDATE SET {field} = {field} + ?',
            (guild_id, user_id, week_key,
             1 if field == 'messages' else 0,
             1 if field == 'voice_minutes' else 0,
             1 if field == 'commands' else 0,
             amount)
        )
        await self.conn.commit()

    async def get_weekly_top(self, guild_id: str, week_key: str, field: str, limit: int = 10) -> list:
        cursor = await self.conn.execute(
            f'SELECT user_id, {field} AS amount FROM weekly_stats '
            f'WHERE guild_id = ? AND week_key = ? AND {field} > 0 ORDER BY {field} DESC LIMIT ?',
            (guild_id, week_key, limit)
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def prune_weekly_stats(self, keep_weeks: int = 4):
        from datetime import datetime
        iso = datetime.now().isocalendar()
        cursor = await self.conn.execute('SELECT DISTINCT week_key FROM weekly_stats')
        for row in await cursor.fetchall():
            key = row['week_key']
            parts = key.split('-W')
            if len(parts) != 2:
                continue
            try:
                year, week = int(parts[0]), int(parts[1])
            except ValueError:
                continue
            current_year, current_week_num = iso[0], iso[1]
            weeks_ago = (current_year - year) * 52 + (current_week_num - week)
            if weeks_ago >= keep_weeks:
                await self.conn.execute('DELETE FROM weekly_stats WHERE week_key = ?', (key,))
        await self.conn.commit()

    # ==========================================
    #     НОВЫЕ МОДУЛИ: тикеты, карточки
    # ==========================================

    async def count_tickets(self, guild_id: str, user_id: str) -> int:
        cursor = await self.conn.execute(
            'SELECT COUNT(*) AS cnt FROM tickets WHERE guild_id = ? AND user_id = ?',
            (guild_id, user_id))
        row = await cursor.fetchone()
        return row['cnt'] if row else 0

    async def count_unique_cards(self, guild_id: str, user_id: str) -> int:
        cursor = await self.conn.execute(
            'SELECT COUNT(*) AS cnt FROM user_cards WHERE guild_id = ? AND user_id = ?',
            (guild_id, user_id))
        row = await cursor.fetchone()
        return row['cnt'] if row else 0

    async def get_card(self, guild_id: str, card_id: str) -> dict | None:
        cursor = await self.conn.execute(
            'SELECT card_id, name, description, rarity, emoji, drop_rate FROM collectible_cards '
            'WHERE guild_id = ? AND card_id = ? AND enabled = 1', (guild_id, card_id))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def buy_card(self, guild_id: str, user_id: str, card_id: str, price: int) -> bool:
        card = await self.get_card(guild_id, card_id)
        if not card:
            return False
        user = await self.get_or_create_user(guild_id, user_id)
        if user.get('balance', 0) < price:
            return False
        await self.conn.execute(
            'UPDATE users SET balance = balance - ? WHERE guild_id = ? AND user_id = ?',
            (price, guild_id, user_id))
        await self.conn.execute(
            'INSERT INTO user_cards (guild_id, user_id, card_id, quantity, obtained_at) VALUES (?, ?, ?, 1, ?) '
            'ON CONFLICT(guild_id, user_id, card_id) DO UPDATE SET quantity = quantity + 1',
            (guild_id, user_id, card_id, datetime.now(timezone.utc).isoformat()))
        await self.conn.commit()
        return True

    async def sell_card(self, guild_id: str, user_id: str, card_id: str, amount: int, price: int) -> int:
        cursor = await self.conn.execute(
            'SELECT quantity FROM user_cards WHERE guild_id = ? AND user_id = ? AND card_id = ?',
            (guild_id, user_id, card_id))
        row = await cursor.fetchone()
        if not row or row['quantity'] < amount:
            return 0
        await self.conn.execute(
            'UPDATE user_cards SET quantity = quantity - ? WHERE guild_id = ? AND user_id = ? AND card_id = ?',
            (amount, guild_id, user_id, card_id))
        await self.conn.execute(
            'DELETE FROM user_cards WHERE guild_id = ? AND user_id = ? AND card_id = ? AND quantity <= 0',
            (guild_id, user_id, card_id))
        await self.get_or_create_user(guild_id, user_id)
        await self.conn.execute(
            'UPDATE users SET balance = balance + ? WHERE guild_id = ? AND user_id = ?',
            (price * amount, guild_id, user_id))
        await self.conn.commit()
        return price * amount