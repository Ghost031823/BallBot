from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

from cogs.giveaways import GiveawayEntryView
from cogs.tickets import TicketCloseView, TicketPanelView
from utils.db import Database


load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"


class BallBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.messages = True
        intents.message_content = True

        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
        )
        database_path = os.getenv("DATABASE_PATH", "data/ballbot.sqlite3")
        self.db = Database(BASE_DIR / database_path)

    async def setup_hook(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        self.db.initialize()

        for extension in (
            "cogs.commands",
            "cogs.setup",
            "cogs.giveaways",
            "cogs.chain",
            "cogs.tickets",
        ):
            await self.load_extension(extension)

        self.add_view(GiveawayEntryView())
        self.add_view(TicketPanelView())
        self.add_view(TicketCloseView())
        await self.tree.sync()

    async def on_ready(self) -> None:
        logging.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "unknown")


async def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is not set.")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    async with BallBot() as bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
