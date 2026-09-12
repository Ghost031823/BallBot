from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from utils.embeds import error_embed, info_embed, success_embed, warning_embed
from utils.transcripts import save_ticket_transcript

if TYPE_CHECKING:
    from bot import BallBot


TICKET_TYPES: list[tuple[str, str, str]] = [
    ("questions", "Questions", "Need help or clarification?"),
    ("suggestions", "Suggestions", "Share an idea or improvement."),
]


class TranscriptLinkView(discord.ui.View):
    def __init__(self, url: str) -> None:
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Open Transcript", style=discord.ButtonStyle.link, url=url))


class TicketPanelSelect(discord.ui.Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(label=label, value=value, description=description)
            for value, label, description in TICKET_TYPES
        ]
        super().__init__(
            placeholder="Choose a ticket type...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket:open",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        cog = interaction.client.get_cog("TicketsCog")
        if cog is None:
            await interaction.response.send_message(
                embed=error_embed("Unavailable", "The ticket system is not ready yet."),
                ephemeral=True,
            )
            return

        await cog.handle_ticket_open(interaction, self.values[0])


class TicketPanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(TicketPanelSelect())


class TicketCloseView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="ticket:close",
    )
    async def close(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        cog = interaction.client.get_cog("TicketsCog")
        if cog is None:
            await interaction.response.send_message(
                embed=error_embed("Unavailable", "The ticket system is not ready yet."),
                ephemeral=True,
            )
            return

        await cog.handle_close_ticket(interaction)


class TicketsCog(commands.Cog):
    def __init__(self, bot: BallBot) -> None:
        self.bot = bot

    def build_panel_embed(self) -> discord.Embed:
        embed = info_embed("Support Tickets", "Choose a ticket type from the dropdown below to open a private support channel.")
        for _value, label, description in TICKET_TYPES:
            embed.add_field(name=label, value=description, inline=False)
        return embed

    def build_welcome_embed(self, opener: discord.Member, ticket_type: str, number: int) -> discord.Embed:
        pretty_type = dict((value, label) for value, label, _desc in TICKET_TYPES).get(ticket_type, ticket_type.title())
        embed = info_embed(
            f"Ticket #{number:04d}",
            f"{opener.mention}, thanks for opening a **{pretty_type}** ticket.",
        )
        embed.add_field(name="Status", value="Open", inline=True)
        embed.add_field(name="Opened By", value=opener.mention, inline=True)
        embed.add_field(name="Close", value="Use the button below when this ticket is resolved.", inline=False)
        return embed

    def can_manage_ticket(self, member: discord.Member, ticket: dict, config: dict) -> bool:
        if member.id == ticket["opener_id"] or member.id == member.guild.owner_id:
            return True
        member_role_ids = {role.id for role in member.roles}
        return bool(member_role_ids.intersection(config.get("ticket_staff_role_ids", [])))

    async def handle_ticket_open(self, interaction: discord.Interaction, ticket_type: str) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=error_embed("Unavailable", "Tickets can only be opened inside a server."),
                ephemeral=True,
            )
            return

        config = self.bot.db.get_guild_config(interaction.guild.id)
        category_id = config.get("ticket_category_id")
        if not category_id:
            await interaction.response.send_message(
                embed=warning_embed("Missing Configuration", "The ticket category has not been configured yet."),
                ephemeral=True,
            )
            return

        category = interaction.guild.get_channel(category_id)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                embed=error_embed("Missing Category", "The configured ticket category no longer exists."),
                ephemeral=True,
            )
            return

        staff_roles = [interaction.guild.get_role(role_id) for role_id in config.get("ticket_staff_role_ids", [])]
        bot_member = interaction.guild.me or interaction.guild.get_member(interaction.client.user.id)
        if bot_member is None:
            await interaction.response.send_message(
                embed=error_embed("Unavailable", "I could not resolve my server membership."),
                ephemeral=True,
            )
            return

        number = self.bot.db.increment_ticket_counter(interaction.guild.id)
        channel_name = f"ticket-{number:04d}"
        overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            bot_member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True,
            ),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            ),
        }
        for role in staff_roles:
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True,
                )

        try:
            ticket_channel = await interaction.guild.create_text_channel(
                channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"{ticket_type}|{interaction.user.id}",
            )
        except discord.Forbidden:
            self.bot.db.release_ticket_counter(interaction.guild.id, number)
            await interaction.response.send_message(
                embed=error_embed("Missing Permissions", "I cannot create ticket channels in the configured category."),
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            self.bot.db.release_ticket_counter(interaction.guild.id, number)
            await interaction.response.send_message(
                embed=error_embed("Discord Error", "Discord rejected the ticket channel creation."),
                ephemeral=True,
            )
            return

        try:
            await ticket_channel.send(
                embed=self.build_welcome_embed(interaction.user, ticket_type, number),
                view=TicketCloseView(),
            )
        except discord.Forbidden:
            self.bot.db.release_ticket_counter(interaction.guild.id, number)
            try:
                await ticket_channel.delete(reason="Rollback failed ticket initialization")
            except (discord.Forbidden, discord.HTTPException):
                pass
            await interaction.response.send_message(
                embed=error_embed("Missing Permissions", "I created the ticket channel but could not initialize it."),
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            self.bot.db.release_ticket_counter(interaction.guild.id, number)
            try:
                await ticket_channel.delete(reason="Rollback failed ticket initialization")
            except (discord.Forbidden, discord.HTTPException):
                pass
            await interaction.response.send_message(
                embed=error_embed("Discord Error", "Discord rejected the initial ticket message."),
                ephemeral=True,
            )
            return

        self.bot.db.create_ticket(
            guild_id=interaction.guild.id,
            number=number,
            opener_id=interaction.user.id,
            channel_id=ticket_channel.id,
            ticket_type=ticket_type,
        )
        await interaction.response.send_message(
            embed=success_embed("Ticket Opened", f"Your ticket is ready: {ticket_channel.mention}"),
            ephemeral=True,
        )

    async def handle_close_ticket(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=error_embed("Unavailable", "This action can only be used inside a ticket channel."),
                ephemeral=True,
            )
            return

        ticket = self.bot.db.get_ticket_by_channel(interaction.channel.id)
        if ticket is None:
            await interaction.response.send_message(
                embed=error_embed("Not a Ticket", "This channel is not tracked as a ticket."),
                ephemeral=True,
            )
            return

        if ticket["status"] == "closed":
            await interaction.response.send_message(
                embed=warning_embed("Already Closed", "This ticket has already been closed."),
                ephemeral=True,
            )
            return

        config = self.bot.db.get_guild_config(interaction.guild.id)
        if not self.can_manage_ticket(interaction.user, ticket, config):
            await interaction.response.send_message(
                embed=error_embed("Not Allowed", "Only the opener, configured staff, or the server owner can close tickets."),
                ephemeral=True,
            )
            return

        transcript_channel_id = config.get("ticket_transcript_channel_id")
        if not transcript_channel_id:
            await interaction.response.send_message(
                embed=warning_embed("Missing Configuration", "Set a ticket transcript channel before closing tickets."),
                ephemeral=True,
            )
            return

        transcript_channel = interaction.guild.get_channel(transcript_channel_id)
        if not isinstance(transcript_channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=error_embed("Missing Channel", "The configured transcript channel no longer exists."),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        absolute_transcript = Path(self.bot.db.path).parent / "transcripts" / f"{interaction.guild.id}-{ticket['number']:04d}.html"
        saved_path = await save_ticket_transcript(interaction.channel, absolute_transcript)

        try:
            transcript_message = await transcript_channel.send(
                embed=success_embed(
                    "Ticket Transcript",
                    f"Transcript for ticket #{ticket['number']:04d} opened by <@{ticket['opener_id']}>.",
                ),
                file=discord.File(saved_path, filename=saved_path.name),
            )
        except discord.Forbidden:
            saved_path.unlink(missing_ok=True)
            await interaction.followup.send(
                embed=error_embed("Missing Permissions", "I cannot post transcripts in the configured channel."),
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            saved_path.unlink(missing_ok=True)
            await interaction.followup.send(
                embed=error_embed("Discord Error", "Discord rejected the transcript upload."),
                ephemeral=True,
            )
            return

        transcript_url = transcript_message.jump_url
        self.bot.db.close_ticket(interaction.channel.id, str(saved_path), transcript_url)

        try:
            opener = interaction.guild.get_member(ticket["opener_id"])
            if opener is not None:
                await interaction.channel.set_permissions(
                    opener,
                    view_channel=True,
                    send_messages=False,
                    read_message_history=True,
                )

            for role_id in config.get("ticket_staff_role_ids", []):
                role = interaction.guild.get_role(role_id)
                if role is not None:
                    await interaction.channel.set_permissions(
                        role,
                        view_channel=True,
                        send_messages=False,
                        read_message_history=True,
                        attach_files=False,
                    )

            await interaction.channel.edit(name=f"closed-{ticket['number']:04d}")
            await interaction.channel.send(
                embed=info_embed("Ticket Closed", "Transcript saved. Use the button below to open it."),
                view=TranscriptLinkView(transcript_url),
            )
        except discord.Forbidden:
            await interaction.followup.send(
                embed=warning_embed("Partially Closed", "The transcript was saved, but I could not fully lock the ticket channel."),
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                embed=warning_embed("Partially Closed", "The transcript was saved, but Discord rejected part of the channel close flow."),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            embed=success_embed("Ticket Closed", "The transcript has been generated and the ticket is now read-only."),
            ephemeral=True,
        )


async def setup(bot: BallBot) -> None:
    await bot.add_cog(TicketsCog(bot))
