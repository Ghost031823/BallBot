from __future__ import annotations

import re
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from cogs.tickets import TicketPanelView
from utils.embeds import error_embed, info_embed, success_embed, warning_embed

if TYPE_CHECKING:
    from bot import BallBot


ROLE_PATTERN = re.compile(r"<@&(\d+)>|(\d+)")


class SetupCog(commands.GroupCog, group_name="setup", group_description="Owner-only server setup"):
    def __init__(self, bot: BallBot) -> None:
        self.bot = bot
        super().__init__()

    async def ensure_owner(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Unavailable", "Setup commands can only be used in a server."),
                ephemeral=True,
            )
            return False

        if interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message(
                embed=warning_embed("Owner Only", "Only the server owner can use setup commands."),
                ephemeral=True,
            )
            return False

        return True

    def parse_roles(self, guild: discord.Guild, raw_value: str) -> list[discord.Role]:
        role_ids: list[int] = []
        for match in ROLE_PATTERN.finditer(raw_value):
            role_id = int(match.group(1) or match.group(2))
            if role_id not in role_ids:
                role_ids.append(role_id)
        return [role for role_id in role_ids if (role := guild.get_role(role_id)) is not None]

    async def refresh_chain_if_possible(self, guild: discord.Guild) -> str:
        chain_cog = self.bot.get_cog("ChainCog")
        if chain_cog is None:
            return "Chain cog is not loaded."
        _success, message = await chain_cog.refresh_chain_for_guild(guild)
        return message

    @app_commands.command(name="giveaway-role", description="Set the required role for giveaway entries.")
    async def giveaway_role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        if not await self.ensure_owner(interaction):
            return
        self.bot.db.update_guild_config(interaction.guild.id, giveaway_role_id=role.id)
        await interaction.response.send_message(
            embed=success_embed("Giveaway Updated", f"Giveaway entries now require {role.mention}."),
            ephemeral=True,
        )

    @app_commands.command(name="chain-roles", description="Set the ordered chain-of-command role list.")
    async def chain_roles(self, interaction: discord.Interaction, roles: str) -> None:
        if not await self.ensure_owner(interaction):
            return

        parsed_roles = self.parse_roles(interaction.guild, roles)
        if not parsed_roles:
            await interaction.response.send_message(
                embed=error_embed("Invalid Roles", "Provide role mentions or IDs in the order they should appear."),
                ephemeral=True,
            )
            return

        self.bot.db.set_chain_roles(interaction.guild.id, [role.id for role in parsed_roles])
        refresh_message = await self.refresh_chain_if_possible(interaction.guild)
        ordered = "\n".join(f"{index}. {role.mention}" for index, role in enumerate(parsed_roles, start=1))
        await interaction.response.send_message(
            embed=success_embed("Chain Updated", f"Configured chain roles:\n{ordered}\n\n{refresh_message}"),
            ephemeral=True,
        )

    @app_commands.command(name="chain-channel", description="Set the channel used for the live chain display.")
    async def chain_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if not await self.ensure_owner(interaction):
            return

        self.bot.db.update_guild_config(
            interaction.guild.id,
            chain_channel_id=channel.id,
            chain_message_id=None,
        )
        refresh_message = await self.refresh_chain_if_possible(interaction.guild)
        await interaction.response.send_message(
            embed=success_embed("Chain Channel Updated", f"Chain display channel set to {channel.mention}.\n{refresh_message}"),
            ephemeral=True,
        )

    @app_commands.command(name="ticket-transcripts", description="Set the channel used to store ticket transcripts.")
    async def ticket_transcripts(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if not await self.ensure_owner(interaction):
            return
        self.bot.db.update_guild_config(interaction.guild.id, ticket_transcript_channel_id=channel.id)
        await interaction.response.send_message(
            embed=success_embed("Transcript Channel Updated", f"Ticket transcripts will be stored in {channel.mention}."),
            ephemeral=True,
        )

    @app_commands.command(name="ticket-category", description="Set the category where ticket channels are created.")
    async def ticket_category(self, interaction: discord.Interaction, category: discord.CategoryChannel) -> None:
        if not await self.ensure_owner(interaction):
            return
        self.bot.db.update_guild_config(interaction.guild.id, ticket_category_id=category.id)
        await interaction.response.send_message(
            embed=success_embed("Ticket Category Updated", f"Tickets will be created in **{category.name}**."),
            ephemeral=True,
        )

    @app_commands.command(name="ticket-staff-roles", description="Set the roles that can access ticket channels.")
    async def ticket_staff_roles(self, interaction: discord.Interaction, roles: str) -> None:
        if not await self.ensure_owner(interaction):
            return

        parsed_roles = self.parse_roles(interaction.guild, roles)
        self.bot.db.update_guild_config(interaction.guild.id, ticket_staff_role_ids=[role.id for role in parsed_roles])
        if parsed_roles:
            summary = ", ".join(role.mention for role in parsed_roles)
            message = f"Ticket staff roles set to {summary}."
        else:
            message = "Ticket staff roles cleared."

        await interaction.response.send_message(
            embed=success_embed("Ticket Staff Updated", message),
            ephemeral=True,
        )

    @app_commands.command(name="ticket-panel", description="Post the persistent ticket dropdown panel.")
    async def ticket_panel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        if not await self.ensure_owner(interaction):
            return

        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=error_embed("Unsupported Channel", "The ticket panel must be posted in a text channel."),
                ephemeral=True,
            )
            return

        tickets_cog = self.bot.get_cog("TicketsCog")
        if tickets_cog is None:
            await interaction.response.send_message(
                embed=error_embed("Unavailable", "The ticket system is not ready yet."),
                ephemeral=True,
            )
            return

        try:
            message = await target_channel.send(
                embed=tickets_cog.build_panel_embed(),
                view=TicketPanelView(),
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("Missing Permissions", "I cannot post the ticket panel in that channel."),
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.response.send_message(
                embed=error_embed("Discord Error", "Discord rejected the ticket panel message."),
                ephemeral=True,
            )
            return

        self.bot.db.update_guild_config(
            interaction.guild.id,
            ticket_panel_channel_id=target_channel.id,
            ticket_panel_message_id=message.id,
        )
        await interaction.response.send_message(
            embed=success_embed("Ticket Panel Posted", f"Ticket panel posted in {target_channel.mention}."),
            ephemeral=True,
        )

    @app_commands.command(name="status", description="Review the current BallBot setup values.")
    async def status(self, interaction: discord.Interaction) -> None:
        if not await self.ensure_owner(interaction):
            return

        config = self.bot.db.get_guild_config(interaction.guild.id)
        chain_roles = self.bot.db.get_chain_roles(interaction.guild.id)
        category = interaction.guild.get_channel(config["ticket_category_id"]) if config.get("ticket_category_id") else None
        embed = info_embed("Setup Status", "Current BallBot configuration for this server.")
        embed.add_field(
            name="Giveaway Required Role",
            value=f"<@&{config['giveaway_role_id']}>" if config.get("giveaway_role_id") else "Not configured",
            inline=False,
        )
        embed.add_field(
            name="Chain Roles",
            value="\n".join(f"{index}. <@&{role_id}>" for index, role_id in enumerate(chain_roles, start=1)) or "Not configured",
            inline=False,
        )
        embed.add_field(
            name="Chain Display Channel",
            value=f"<#{config['chain_channel_id']}>" if config.get("chain_channel_id") else "Not configured",
            inline=False,
        )
        embed.add_field(
            name="Ticket Transcript Channel",
            value=f"<#{config['ticket_transcript_channel_id']}>" if config.get("ticket_transcript_channel_id") else "Not configured",
            inline=False,
        )
        embed.add_field(
            name="Ticket Category",
            value=(
                category.name
                if isinstance(category, discord.CategoryChannel)
                else f"Missing category (`{config['ticket_category_id']}`)"
                if config.get("ticket_category_id")
                else "Not configured"
            ),
            inline=False,
        )
        staff_roles = config.get("ticket_staff_role_ids", [])
        embed.add_field(
            name="Ticket Staff Roles",
            value=", ".join(f"<@&{role_id}>" for role_id in staff_roles) if staff_roles else "Not configured",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: BallBot) -> None:
    await bot.add_cog(SetupCog(bot))
