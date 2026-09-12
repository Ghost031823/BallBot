from __future__ import annotations

from typing import Iterable

import discord


SUCCESS_COLOR = discord.Color.green()
ERROR_COLOR = discord.Color.red()
INFO_COLOR = discord.Color.blurple()
WARNING_COLOR = discord.Color.orange()


def base_embed(
    title: str,
    description: str | None = None,
    *,
    color: discord.Color = INFO_COLOR,
    fields: Iterable[tuple[str, str, bool]] | None = None,
) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text="BallBot")
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    return embed


def success_embed(title: str, description: str) -> discord.Embed:
    return base_embed(title, description, color=SUCCESS_COLOR)


def error_embed(title: str, description: str) -> discord.Embed:
    return base_embed(title, description, color=ERROR_COLOR)


def info_embed(title: str, description: str) -> discord.Embed:
    return base_embed(title, description, color=INFO_COLOR)


def warning_embed(title: str, description: str) -> discord.Embed:
    return base_embed(title, description, color=WARNING_COLOR)
