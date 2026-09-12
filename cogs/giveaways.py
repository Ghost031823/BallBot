from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.db import utcnow_iso
from utils.embeds import error_embed, info_embed, success_embed, warning_embed

if TYPE_CHECKING:
    from bot import BallBot


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)


class GiveawayEntryView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Enter Giveaway",
        style=discord.ButtonStyle.success,
        custom_id="giveaway:enter",
        emoji="🎉",
    )
    async def enter(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        cog = interaction.client.get_cog("GiveawaysCog")
        if cog is None:
            await interaction.response.send_message(
                embed=error_embed("Unavailable", "The giveaway system is not ready yet."),
                ephemeral=True,
            )
            return

        await cog.handle_entry(interaction)


class GiveawaysCog(commands.GroupCog, group_name="giveaway", group_description="Giveaway management"):
    def __init__(self, bot: BallBot) -> None:
        self.bot = bot
        super().__init__()
        self.giveaway_watcher.start()

    def cog_unload(self) -> None:
        self.giveaway_watcher.cancel()

    def build_giveaway_embed(
        self,
        *,
        title: str,
        description: str,
        winners_count: int,
        ends_at: datetime,
        required_role_id: int | None,
        giveaway_id: int | None,
        entries: int = 0,
        ended: bool = False,
    ) -> discord.Embed:
        status = "Ended" if ended else "Open"
        role_value = f"<@&{required_role_id}>" if required_role_id else "No role restriction"
        embed = info_embed(title, description or "No description provided.")
        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="Winners", value=str(winners_count), inline=True)
        embed.add_field(name="Entries", value=str(entries), inline=True)
        embed.add_field(name="Required Role", value=role_value, inline=False)
        embed.add_field(name="Ends", value=f"<t:{int(ends_at.timestamp())}:F>\n<t:{int(ends_at.timestamp())}:R>", inline=False)
        if giveaway_id is not None:
            embed.add_field(name="Giveaway ID", value=str(giveaway_id), inline=False)
        return embed

    async def update_giveaway_message(self, giveaway: dict) -> None:
        guild = self.bot.get_guild(giveaway["guild_id"])
        if guild is None:
            return

        channel = guild.get_channel(giveaway["channel_id"])
        if not isinstance(channel, discord.TextChannel):
            return

        try:
            message = await channel.fetch_message(giveaway["message_id"])
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

        embed = self.build_giveaway_embed(
            title=giveaway["title"],
            description=giveaway["description"] or "",
            winners_count=giveaway["winners_count"],
            ends_at=parse_timestamp(giveaway["end_at"]),
            required_role_id=giveaway["required_role_id"],
            giveaway_id=giveaway["id"],
            entries=self.bot.db.count_giveaway_entries(giveaway["id"]),
            ended=bool(giveaway["ended"]),
        )
        try:
            await message.edit(embed=embed, view=None if giveaway["ended"] else GiveawayEntryView())
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

    async def finish_giveaway(self, giveaway: dict) -> tuple[bool, str]:
        if giveaway["ended"]:
            return False, "Giveaway already ended."

        self.bot.db.end_giveaway(giveaway["id"])
        giveaway["ended"] = 1
        entrants = self.bot.db.list_giveaway_entries(giveaway["id"])
        guild = self.bot.get_guild(giveaway["guild_id"])

        winners: list[int] = []
        if entrants:
            winners = random.sample(entrants, k=min(len(entrants), giveaway["winners_count"]))

        if guild is None:
            return True, "Giveaway ended in storage, but the guild is unavailable."

        channel = guild.get_channel(giveaway["channel_id"])
        if not isinstance(channel, discord.TextChannel):
            return True, "Giveaway ended in storage, but the giveaway channel is missing."

        try:
            await self.update_giveaway_message(giveaway)
            if winners:
                mentions = ", ".join(f"<@{winner_id}>" for winner_id in winners)
                await channel.send(
                    embed=success_embed(
                        "Giveaway Ended",
                        f"**{giveaway['title']}** has ended.\nWinners: {mentions}",
                    )
                )
            else:
                await channel.send(
                    embed=warning_embed(
                        "Giveaway Ended",
                        f"**{giveaway['title']}** ended with no valid entrants.",
                    )
                )
        except discord.Forbidden:
            return True, "Giveaway ended, but I could not update the channel."
        except discord.HTTPException:
            return True, "Giveaway ended, but Discord rejected the final update."

        return True, "Giveaway ended successfully."

    async def handle_entry(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=error_embed("Unavailable", "Giveaways can only be entered from a server."),
                ephemeral=True,
            )
            return

        message = interaction.message
        if message is None:
            await interaction.response.send_message(
                embed=error_embed("Unavailable", "This giveaway entry button is not attached to a message."),
                ephemeral=True,
            )
            return

        giveaway = self.bot.db.get_giveaway_by_message(message.id)
        if giveaway is None:
            await interaction.response.send_message(
                embed=error_embed("Unavailable", "This giveaway could not be found."),
                ephemeral=True,
            )
            return

        if giveaway["ended"] or parse_timestamp(giveaway["end_at"]) <= datetime.now(timezone.utc):
            await self.finish_giveaway(giveaway)
            await interaction.response.send_message(
                embed=warning_embed("Giveaway Closed", "This giveaway has already ended."),
                ephemeral=True,
            )
            return

        required_role_id = giveaway["required_role_id"]
        if required_role_id and interaction.guild.get_role(required_role_id) is None:
            await interaction.response.send_message(
                embed=error_embed("Missing Role", "The required giveaway role no longer exists. Ask the server owner to reconfigure it."),
                ephemeral=True,
            )
            return

        if required_role_id and required_role_id not in {role.id for role in interaction.user.roles}:
            role = interaction.guild.get_role(required_role_id)
            role_label = role.mention if role else f"role ID `{required_role_id}`"
            await interaction.response.send_message(
                embed=error_embed(
                    "Not Eligible",
                    f"You need {role_label} to enter this giveaway.",
                ),
                ephemeral=True,
            )
            return

        created = self.bot.db.add_giveaway_entry(giveaway["id"], interaction.user.id)
        if not created:
            await interaction.response.send_message(
                embed=warning_embed("Already Entered", "You have already entered this giveaway."),
                ephemeral=True,
            )
            return

        await self.update_giveaway_message(giveaway)
        await interaction.response.send_message(
            embed=success_embed("Entry Confirmed", "You have been entered into the giveaway."),
            ephemeral=True,
        )

    @app_commands.command(name="start", description="Create a new giveaway.")
    @app_commands.describe(
        title="Title shown on the giveaway embed",
        description="Optional giveaway description",
        duration_minutes="How long the giveaway should stay open",
        winners="How many winners should be selected",
        channel="Optional channel for the giveaway message",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def start(
        self,
        interaction: discord.Interaction,
        title: str,
        duration_minutes: app_commands.Range[int, 1, 10080],
        winners: app_commands.Range[int, 1, 25],
        description: str = "Click the button below to enter.",
        channel: discord.TextChannel | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Unavailable", "This command can only be used in a server."),
                ephemeral=True,
            )
            return

        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=error_embed("Unsupported Channel", "Giveaways can only be hosted in text channels."),
                ephemeral=True,
            )
            return

        config = self.bot.db.get_guild_config(interaction.guild.id)
        required_role_id = config.get("giveaway_role_id")
        if required_role_id and interaction.guild.get_role(required_role_id) is None:
            await interaction.response.send_message(
                embed=error_embed("Missing Role", "The configured giveaway role no longer exists. Ask the server owner to set it again."),
                ephemeral=True,
            )
            return

        ends_at = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)

        preview = self.build_giveaway_embed(
            title=title,
            description=description,
            winners_count=winners,
            ends_at=ends_at,
            required_role_id=required_role_id,
            giveaway_id=None,
        )

        try:
            message = await target_channel.send(embed=preview, view=GiveawayEntryView())
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("Missing Permissions", "I cannot post giveaways in that channel."),
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.response.send_message(
                embed=error_embed("Discord Error", "Discord rejected the giveaway message."),
                ephemeral=True,
            )
            return

        try:
            giveaway_id = self.bot.db.create_giveaway(
                guild_id=interaction.guild.id,
                channel_id=target_channel.id,
                message_id=message.id,
                host_id=interaction.user.id,
                title=title,
                description=description,
                winners_count=winners,
                end_at=ends_at.isoformat(),
                required_role_id=required_role_id,
            )
            giveaway = self.bot.db.get_giveaway(giveaway_id)
            if giveaway:
                await self.update_giveaway_message(giveaway)
        except Exception:
            try:
                await message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass
            await interaction.response.send_message(
                embed=error_embed("Database Error", "I could not store the giveaway after posting it."),
                ephemeral=True,
            )
            return

        role_note = f"Restricted to <@&{required_role_id}>." if required_role_id else "No role restriction configured."
        await interaction.response.send_message(
            embed=success_embed("Giveaway Created", f"Giveaway `{giveaway_id}` posted in {target_channel.mention}. {role_note}"),
            ephemeral=True,
        )

    @app_commands.command(name="end", description="End an active giveaway and pick winners.")
    @app_commands.default_permissions(manage_guild=True)
    async def end(self, interaction: discord.Interaction, giveaway_id: int) -> None:
        giveaway = self.bot.db.get_giveaway(giveaway_id)
        if giveaway is None or giveaway["guild_id"] != interaction.guild_id:
            await interaction.response.send_message(
                embed=error_embed("Not Found", "That giveaway ID does not exist."),
                ephemeral=True,
            )
            return

        ended_now, message = await self.finish_giveaway(giveaway)
        if ended_now:
            embed = success_embed("Giveaway Updated", message)
        else:
            embed = warning_embed("Giveaway Updated", message)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="reroll", description="Pick a fresh winner set for an ended giveaway.")
    @app_commands.default_permissions(manage_guild=True)
    async def reroll(self, interaction: discord.Interaction, giveaway_id: int) -> None:
        giveaway = self.bot.db.get_giveaway(giveaway_id)
        if giveaway is None or giveaway["guild_id"] != interaction.guild_id:
            await interaction.response.send_message(
                embed=error_embed("Not Found", "That giveaway ID does not exist."),
                ephemeral=True,
            )
            return

        if not giveaway["ended"]:
            await interaction.response.send_message(
                embed=warning_embed("Still Active", "End the giveaway before rerolling winners."),
                ephemeral=True,
            )
            return

        entrants = self.bot.db.list_giveaway_entries(giveaway_id)
        if not entrants:
            await interaction.response.send_message(
                embed=warning_embed("No Entrants", "There are no entrants to reroll."),
                ephemeral=True,
            )
            return

        winners = random.sample(entrants, k=min(len(entrants), giveaway["winners_count"]))
        guild = interaction.guild
        channel = guild.get_channel(giveaway["channel_id"]) if guild else None
        mentions = ", ".join(f"<@{winner_id}>" for winner_id in winners)

        if isinstance(channel, discord.TextChannel):
            await channel.send(
                embed=success_embed(
                    "Giveaway Rerolled",
                    f"New winners for **{giveaway['title']}**: {mentions}",
                )
            )

        await interaction.response.send_message(
            embed=success_embed("Reroll Complete", f"Selected new winners: {mentions}"),
            ephemeral=True,
        )

    @tasks.loop(seconds=30)
    async def giveaway_watcher(self) -> None:
        await self.bot.wait_until_ready()
        for giveaway in self.bot.db.list_due_giveaways(utcnow_iso()):
            await self.finish_giveaway(giveaway)


async def setup(bot: BallBot) -> None:
    await bot.add_cog(GiveawaysCog(bot))
