from __future__ import annotations

from datetime import timezone
from html import escape
from pathlib import Path

import discord


async def save_ticket_transcript(channel: discord.TextChannel, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'>",
        f"<title>Transcript for {escape(channel.name)}</title>",
        "<style>",
        "body { font-family: Arial, sans-serif; background: #111827; color: #f3f4f6; padding: 24px; }",
        ".message { border: 1px solid #374151; border-radius: 8px; padding: 12px; margin-bottom: 12px; }",
        ".meta { color: #9ca3af; font-size: 0.9rem; margin-bottom: 8px; }",
        ".attachments { margin-top: 8px; }",
        "a { color: #60a5fa; }",
        "pre { white-space: pre-wrap; word-break: break-word; margin: 0; }",
        "</style></head><body>",
        f"<h1>Transcript for #{escape(channel.name)}</h1>",
    ]

    async for message in channel.history(limit=None, oldest_first=True):
        created_at = message.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        attachments = "".join(
            f"<li><a href='{escape(attachment.url)}'>{escape(attachment.filename)}</a></li>"
            for attachment in message.attachments
        )
        embed_summaries = []
        for embed in message.embeds:
            summary = " | ".join(filter(None, [embed.title, embed.description]))
            if summary:
                embed_summaries.append(summary)
        embed_text = "\n".join(embed_summaries)
        content = "\n".join(part for part in [message.content, embed_text] if part)
        if not content:
            content = "[No text content]"

        lines.extend(
            [
                "<div class='message'>",
                f"<div class='meta'>{escape(str(message.author))} • {created_at}</div>",
                f"<pre>{escape(content)}</pre>",
            ]
        )

        if attachments:
            lines.append(f"<div class='attachments'><strong>Attachments</strong><ul>{attachments}</ul></div>")

        lines.append("</div>")

    lines.append("</body></html>")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
