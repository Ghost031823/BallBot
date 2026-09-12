from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import error_embed, info_embed, warning_embed

if TYPE_CHECKING:
    from bot import BallBot


class ChainCog(commands.GroupCog, group_name="chain", group_description="Chain of command tools"):
    def __init__(self, bot: BallBot) -> None:
        self.bot = bot
        super().__init__()

    def build_chain_embed(self, guild: discord.Guild) -> discord.Embed:
        role_ids = self.bot.db.get_chain_roles(guild.id)
        if not role_ids:
            return warning_embed("Chain of Command", "No chain roles have been configured yet.")

        embed = info_embed("Chain of Command", "Live role holder tracking for the configured chain.")

        for index, role_id in enumerate(role_ids, start=1):
            role = guild.get_role(role_id)
            if role is None:
                embed.add_field(
                    name=f"{index}. Missing role",
                    value=f"Role ID `{role_id}` could not be found.",
                    inline=False,
                )
                continue

            members = sorted(role.members, key=lambda member: member.display_name.lower())
            holders = "\n".join(member.mention for member in members) if members else "Vacant"
            embed.add_field(name=f"{index}. {role.mention}", value=holders, inline=False)

        return embed

    async def refresh_chain_for_guild(self, guild: discord.Guild) -> tuple[bool, str]:
        config = self.bot.db.get_guild_config(guild.id)
        channel_id = config.get("chain_channel_id")
        if not channel_id:
            return False, "Chain display channel is not configured."

        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return False, "Configured chain display channel is missing."

        embed = self.build_chain_embed(guild)
        message_id = config.get("chain_message_id")

        try:
            if message_id:
                message = await channel.fetch_message(message_id)
                await message.edit(embed=embed)
            else:
                message = await channel.send(embed=embed)
                self.bot.db.update_guild_config(guild.id, chain_message_id=message.id)
        except discord.NotFound:
            message = await channel.send(embed=embed)
            self.bot.db.update_guild_config(guild.id, chain_message_id=message.id)
        except discord.Forbidden:
            return False, "I do not have permission to post or edit the chain display channel."
        except discord.HTTPException:
            return False, "Discord rejected the chain display update."

        return True, "Chain display refreshed."

    @app_commands.command(name="show", description="Show the current chain of command.")
    async def show(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Unavailable", "This command can only be used in a server."),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(embed=self.build_chain_embed(interaction.guild))

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        tracked_roles = set(self.bot.db.get_chain_roles(after.guild.id))
        if not tracked_roles:
            return

        before_roles = {role.id for role in before.roles}
        after_roles = {role.id for role in after.roles}
        if tracked_roles.isdisjoint(before_roles.symmetric_difference(after_roles)):
            return

        await self.refresh_chain_for_guild(after.guild)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        for guild in self.bot.guilds:
            if self.bot.db.get_guild_config(guild.id).get("chain_channel_id"):
                await self.refresh_chain_for_guild(guild)


async def setup(bot: BallBot) -> None:
    await bot.add_cog(ChainCog(bot))
