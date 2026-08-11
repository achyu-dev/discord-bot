from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from src.cogs.mod.groups import ModGroups
from src.utils import decorators as bot_decorators
from src.utils import general as ug

if TYPE_CHECKING:
    from src.bot import DiscordBot


class LinkCommands:
    client: DiscordBot

    @ModGroups.mod_link.command(name="info", description="Get PESU account linking info about a user")
    @app_commands.describe(user="User to fetch PESU account linking info about")
    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(bot_decorators.FunctionalRole.ADMIN, bot_decorators.FunctionalRole.MOD)
    @bot_decorators.handle_command_errors(
        not_found="The specified user does not exist or is not in the server",
    )
    async def mod_link_info(self, interaction: discord.Interaction, user: discord.Member) -> None:
        embed = ug.build_embed(
            title="Link Info (Protected)",
            color=discord.Color.greyple(),
            fields=[{"name": "User", "value": user.mention}],
            thumbnail=user.display_avatar.url,
        )

        link_record = await self.client.stores.links.find_one(discord_user_id=str(user.id))
        if not link_record:
            embed.add_field(name="Status", value="This user is not linked yet", inline=False)
            await interaction.followup.send(embed=embed)
            return

        if not link_record.prn:
            embed.add_field(name="Error", value="Missing data!!!", inline=False)
            await interaction.followup.send(embed=embed)
            return

        embed.add_field(name="PRN", value=link_record.prn, inline=False)
        await interaction.followup.send(embed=embed)

    @ModGroups.mod_link.command(name="disconnect", description="Disconnect a user's PESU account from Discord")
    @app_commands.describe(user="User to disconnect")
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_env(bot_decorators.AppEnvironment.PROD)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(bot_decorators.FunctionalRole.ADMIN, bot_decorators.FunctionalRole.MOD)
    @bot_decorators.handle_command_errors(
        not_found="The specified user does not exist or is not in the server",
    )
    async def mod_link_disconnect(self, interaction: discord.Interaction, user: discord.Member) -> None:
        result = await self.client.stores.links.delete_one(discord_user_id=str(user.id))
        if result.deleted_count == 0:
            await interaction.followup.send(content="This user was not linked in the first place", ephemeral=True)
            return

        roles_to_remove = []
        for role in user.roles:
            if role.id != interaction.guild.id:
                roles_to_remove.append(role)

        try:
            await user.remove_roles(*roles_to_remove, reason="Disconnecting")
            await user.add_roles(self.client.config.just_joined_role)
        except discord.Forbidden:
            await interaction.followup.send(
                content="I am unable to remove roles from this user although they were disconnected. Please check my permissions",  # noqa: E501
                ephemeral=True,
            )
            return

        await interaction.followup.send(content=f"Disconnected {user.mention}")

    @ModGroups.mod_link.command(
        name="remind",
        description="Post a PESU linking reminder to Ask a Senior (or another channel)",
    )
    @app_commands.describe(target_channel="Channel or thread to post in (default: Ask a Senior)")
    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(
        bot_decorators.FunctionalRole.ADMIN,
        bot_decorators.FunctionalRole.MOD,
        bot_decorators.FunctionalRole.JUNIOR_MOD,
    )
    @bot_decorators.handle_command_errors(
        not_found="The specified channel does not exist",
        forbidden="I do not have permission to send messages in that channel",
    )
    async def mod_link_remind(
        self,
        interaction: discord.Interaction,
        target_channel: discord.TextChannel | discord.Thread | None = None,
    ) -> None:
        channel = target_channel or self.client.config.get_channel("ASK_A_SENIOR")
        just_joined = self.client.config.just_joined_role
        welcome = self.client.config.get_channel("WELCOME")
        access_help = self.client.config.get_channel("ACCESS_HELP")

        message = (
            f"Hi {just_joined.mention}, friendly reminder: Authenticate using your PESU credentials "
            "to gain access to the rest of the server. This channel is public. Authentication "
            "restricts access to outsiders and protects your identity and conversations. "
            "This is a temporary channel that will be shut down after admissions end. "
            f"Instructions to authenticate can be found in {welcome.mention}. "
            f"If you are facing errors, reach out to the mods in {access_help.mention}."
        )
        await channel.send(content=message)
        await interaction.followup.send(content=f"Reminder sent to {channel.mention}", ephemeral=True)
