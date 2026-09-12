from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import base_embed


HELP_SECTIONS = [
    (
        "🎉 Giveaways",
        "`/giveaway start` to launch an embed-based giveaway.\n"
        "`/giveaway end` and `/giveaway reroll` for winner management.\n"
        "Entrants join with the persistent **Enter Giveaway** button.",
    ),
    (
        "🎫 Tickets",
        "Owners post a dropdown ticket panel with `/setup ticket-panel`.\n"
        "Users open **Questions** or **Suggestions** tickets from the panel.\n"
        "Tickets include a close button, transcripts, and staff-only access.",
    ),
    (
        "🪖 Chain of Command",
        "`/chain show` displays the configured chain embed on demand.\n"
        "Configured display messages refresh automatically when tracked roles change.",
    ),
    (
        "🛠️ Setup Commands",
        "All `/setup ...` commands are restricted to the server owner.\n"
        "Configure giveaway roles, chain roles/channels, and ticket category, staff, transcripts, and panel messages.",
    ),
]


class CommandsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="commands", description="Show the BallBot command menu.")
    async def commands_menu(self, interaction: discord.Interaction) -> None:
        embed = base_embed(
            "BallBot Command Center",
            "Use the sections below to manage giveaways, tickets, chain displays, and owner-only setup.",
            fields=[(name, value, False) for name, value in HELP_SECTIONS],
        )
        embed.set_thumbnail(url=interaction.client.user.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommandsCog(bot))
