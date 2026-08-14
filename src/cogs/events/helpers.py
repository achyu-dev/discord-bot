from __future__ import annotations

import re
from datetime import timedelta
from typing import TYPE_CHECKING

import discord

from src.utils import general as ug
from src.utils.general import build_embed

if TYPE_CHECKING:
    import asyncio

    from src.bot import DiscordBot


class EventHelpers:
    client: DiscordBot
    _fafo_lock: asyncio.Lock
    _fafo_message_id: int | None

    def _build_fafo_banner(self) -> discord.Embed:
        return build_embed(
            title="DO NOT SEND MESSAGES IN THIS CHANNEL",
            description=(
                "This channel is used to catch spam bots. Any messages sent here will result in a **timeout and kick**."
            ),
            color=discord.Color.red(),
            thumbnail="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f36f.png",
        )

    @staticmethod
    def _build_fafo_view(count: int) -> discord.ui.View:
        view = discord.ui.View(timeout=None)
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label=f"🍯 Timeouts & Kicks: {count}",
                disabled=True,
            )
        )
        return view

    async def _ensure_fafo_banner(self) -> discord.Message:
        async with self._fafo_lock:
            channel = self.client.config.honeypot_channel

            if self._fafo_message_id is not None:
                try:
                    return await channel.fetch_message(self._fafo_message_id)
                except discord.NotFound:
                    self._fafo_message_id = None

            # Find the existing banner after a bot restart.
            async for message in channel.pins(limit=None):
                if (
                    message.author.id == self.client.user.id
                    and message.embeds
                    and message.embeds[0].title == "DO NOT SEND MESSAGES IN THIS CHANNEL"
                ):
                    self._fafo_message_id = message.id
                    return message

            # Create the banner only when it does not already exist.
            count = 0
            banner = await channel.send(
                embed=self._build_fafo_banner(),
                view=self._build_fafo_view(count),
            )
            await banner.pin(reason="FAFO honeypot banner")
            self._fafo_message_id = banner.id
            return banner

    async def _update_fafo_banner(self) -> None:
        banner = await self._ensure_fafo_banner()

        # pre compute the count from the button label
        count = 0
        if banner.components:
            row = banner.components[0]
            if hasattr(row, "children") and row.children:
                button = row.children[0]
                if hasattr(button, "label") and button.label:
                    match = re.search(r"\d+", button.label)
                    if match:
                        count = int(match.group(0))

        count += 1
        view = self._build_fafo_view(count)
        await banner.edit(embed=self._build_fafo_banner(), view=view)

    async def _apply_honeypot_action(self, member: discord.Member, source_message: discord.Message) -> str:
        reason = f"Honeypot trap in #{source_message.channel} ({source_message.channel.id})"
        dm_embed = build_embed(
            title="You have been removed",
            color=discord.Color.red(),
            description=(
                f"You were removed from **{member.guild.name}** for triggering "
                "the honeypot channel.\n\n"
                "Rejoin the server with this link: "
                "https://discord.gg/eZ3uFs2"
            ),
        )
        await ug.send_dm_safely(member, embed=dm_embed)

        if self.HONEYPOT_ACTION == "ban":
            await member.ban(delete_message_seconds=0, reason=reason)
            return "Banned"

        until = discord.utils.utcnow() + timedelta(hours=24)
        await member.timeout(until, reason=reason)

        await member.kick(reason=reason)
        return "Timed out & Kicked"

    @staticmethod
    def _filter_reply_mentions(message: discord.Message) -> list[discord.User | discord.Member]:
        """Filter out reply mentions from the mentions list."""
        mentions = message.mentions

        if (
            message.type == discord.MessageType.reply
            and message.reference is not None
            and message.reference.resolved is not None
        ):
            try:
                resolved = message.reference.resolved
                if isinstance(resolved, discord.Message):
                    replied_user = resolved.author
                    if replied_user in mentions:
                        mentions = [m for m in mentions if m.id != replied_user.id]
            except Exception:
                pass

        return mentions

    @staticmethod
    def _add_everyone_ping_field(embed: discord.Embed, message: discord.Message) -> None:
        """Add everyone/here ping field if applicable."""
        if message.mention_everyone:
            embed.add_field(
                name="@everyone/@here pings",
                value=f"{message.author.mention} ghost pinged `@everyone/@here` in {message.channel.mention}",
                inline=False,
            )

    @staticmethod
    def _add_role_ping_fields(embed: discord.Embed, role_mentions: list, message: discord.Message) -> None:
        """Add role ping fields if applicable."""
        if role_mentions:
            ping_list = " ".join(role.mention for role in role_mentions)
            embed.add_field(
                name="Role pings",
                value=f"{message.author.mention} ghost pinged {ping_list} in {message.channel.mention}",
                inline=False,
            )

    @staticmethod
    def _add_member_ping_fields(
        embed: discord.Embed, mentions: list[discord.User | discord.Member], message: discord.Message
    ) -> None:
        """Add member ping fields if applicable."""
        user_mentions = [member for member in mentions if not member.bot]
        if user_mentions:
            ping_list = " ".join(member.mention for member in user_mentions)
            embed.add_field(
                name="Member pings",
                value=f"{message.author.mention} ghost pinged {ping_list} in {message.channel.mention}",
                inline=False,
            )
