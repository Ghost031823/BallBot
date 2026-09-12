from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._connection:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS guild_config (
                    guild_id INTEGER PRIMARY KEY,
                    giveaway_role_id INTEGER,
                    chain_channel_id INTEGER,
                    chain_message_id INTEGER,
                    ticket_transcript_channel_id INTEGER,
                    ticket_category_id INTEGER,
                    ticket_staff_role_ids TEXT NOT NULL DEFAULT '[]',
                    ticket_panel_channel_id INTEGER,
                    ticket_panel_message_id INTEGER,
                    ticket_counter INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS chain_roles (
                    guild_id INTEGER NOT NULL,
                    position INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    PRIMARY KEY (guild_id, position)
                );

                CREATE TABLE IF NOT EXISTS giveaways (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL UNIQUE,
                    host_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    winners_count INTEGER NOT NULL,
                    end_at TEXT NOT NULL,
                    ended INTEGER NOT NULL DEFAULT 0,
                    required_role_id INTEGER,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS giveaway_entries (
                    giveaway_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    entered_at TEXT NOT NULL,
                    PRIMARY KEY (giveaway_id, user_id),
                    FOREIGN KEY (giveaway_id) REFERENCES giveaways(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    number INTEGER NOT NULL,
                    opener_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL UNIQUE,
                    ticket_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    closed_at TEXT,
                    transcript_path TEXT,
                    transcript_url TEXT
                );
                """
            )

    def _ensure_guild(self, guild_id: int) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)",
                (guild_id,),
            )

    def get_guild_config(self, guild_id: int) -> dict[str, Any]:
        self._ensure_guild(guild_id)
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM guild_config WHERE guild_id = ?",
                (guild_id,),
            ).fetchone()

        config = dict(row) if row else {"guild_id": guild_id}
        config["ticket_staff_role_ids"] = json.loads(config.get("ticket_staff_role_ids", "[]"))
        config["chain_role_ids"] = self.get_chain_roles(guild_id)
        return config

    def update_guild_config(self, guild_id: int, **fields: Any) -> None:
        if not fields:
            return

        self._ensure_guild(guild_id)
        payload = dict(fields)
        if "ticket_staff_role_ids" in payload:
            payload["ticket_staff_role_ids"] = json.dumps(payload["ticket_staff_role_ids"])

        columns = ", ".join(f"{key} = ?" for key in payload)
        values = list(payload.values()) + [guild_id]

        with self._lock, self._connection:
            self._connection.execute(
                f"UPDATE guild_config SET {columns} WHERE guild_id = ?",
                values,
            )

    def get_chain_roles(self, guild_id: int) -> list[int]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT role_id FROM chain_roles WHERE guild_id = ? ORDER BY position ASC",
                (guild_id,),
            ).fetchall()
        return [row["role_id"] for row in rows]

    def set_chain_roles(self, guild_id: int, role_ids: list[int]) -> None:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM chain_roles WHERE guild_id = ?", (guild_id,))
            self._connection.executemany(
                "INSERT INTO chain_roles (guild_id, position, role_id) VALUES (?, ?, ?)",
                [(guild_id, index, role_id) for index, role_id in enumerate(role_ids, start=1)],
            )

    def create_giveaway(
        self,
        *,
        guild_id: int,
        channel_id: int,
        message_id: int,
        host_id: int,
        title: str,
        description: str,
        winners_count: int,
        end_at: str,
        required_role_id: int | None,
    ) -> int:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO giveaways (
                    guild_id, channel_id, message_id, host_id, title, description,
                    winners_count, end_at, required_role_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    channel_id,
                    message_id,
                    host_id,
                    title,
                    description,
                    winners_count,
                    end_at,
                    required_role_id,
                    utcnow_iso(),
                ),
            )
            return int(cursor.lastrowid)

    def get_giveaway(self, giveaway_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM giveaways WHERE id = ?",
                (giveaway_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_giveaway_by_message(self, message_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM giveaways WHERE message_id = ?",
                (message_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_due_giveaways(self, current_time: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM giveaways WHERE ended = 0 AND end_at <= ? ORDER BY end_at ASC",
                (current_time,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_giveaway_entry(self, giveaway_id: int, user_id: int) -> bool:
        try:
            with self._lock, self._connection:
                self._connection.execute(
                    "INSERT INTO giveaway_entries (giveaway_id, user_id, entered_at) VALUES (?, ?, ?)",
                    (giveaway_id, user_id, utcnow_iso()),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def count_giveaway_entries(self, giveaway_id: int) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) AS count FROM giveaway_entries WHERE giveaway_id = ?",
                (giveaway_id,),
            ).fetchone()
        return int(row["count"]) if row else 0

    def list_giveaway_entries(self, giveaway_id: int) -> list[int]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT user_id FROM giveaway_entries WHERE giveaway_id = ?",
                (giveaway_id,),
            ).fetchall()
        return [row["user_id"] for row in rows]

    def end_giveaway(self, giveaway_id: int) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE giveaways SET ended = 1 WHERE id = ?",
                (giveaway_id,),
            )

    def increment_ticket_counter(self, guild_id: int) -> int:
        self._ensure_guild(guild_id)
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE guild_config SET ticket_counter = ticket_counter + 1 WHERE guild_id = ?",
                (guild_id,),
            )
            row = self._connection.execute(
                "SELECT ticket_counter FROM guild_config WHERE guild_id = ?",
                (guild_id,),
            ).fetchone()
        return int(row["ticket_counter"])

    def release_ticket_counter(self, guild_id: int, reserved_number: int) -> None:
        self._ensure_guild(guild_id)
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE guild_config
                SET ticket_counter = ticket_counter - 1
                WHERE guild_id = ? AND ticket_counter = ?
                """,
                (guild_id, reserved_number),
            )

    def create_ticket(
        self,
        *,
        guild_id: int,
        number: int,
        opener_id: int,
        channel_id: int,
        ticket_type: str,
    ) -> int:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO tickets (
                    guild_id, number, opener_id, channel_id, ticket_type, status, created_at
                ) VALUES (?, ?, ?, ?, ?, 'open', ?)
                """,
                (guild_id, number, opener_id, channel_id, ticket_type, utcnow_iso()),
            )
            return int(cursor.lastrowid)

    def delete_ticket_by_channel(self, channel_id: int) -> None:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM tickets WHERE channel_id = ?", (channel_id,))

    def get_ticket_by_channel(self, channel_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM tickets WHERE channel_id = ?",
                (channel_id,),
            ).fetchone()
        return dict(row) if row else None

    def close_ticket(self, channel_id: int, transcript_path: str, transcript_url: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE tickets
                SET status = 'closed', closed_at = ?, transcript_path = ?, transcript_url = ?
                WHERE channel_id = ?
                """,
                (utcnow_iso(), transcript_path, transcript_url, channel_id),
            )
