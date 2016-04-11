from plugin import Plugin
import asyncio
import logging
import discord

logs = logging.getLogger('discord')

class Stats(Plugin):

    is_global = True

    async def on_server_join(self, server):
        for member in server.members:
            await self.db.redis.sadd('mee6:stats:users', member.id)

    async def on_channel_create(self, channel):
        await self.db.redis.sadd('mee6:stats:channels', channel.id)

    async def on_message(self, message):
        if message.author.id == self.mee6.user.id:
            await self.db.redis.incr('mee6:stats:msg')

    async def on_ready(self):
        """Initialize stats"""

        # Total members
        members = set(self.mee6.get_all_members())
        channels = set(self.mee6.get_all_channels())

        for channel in channels:
            await self.db.redis.sadd('mee6:stats:channels', channel.id)
        for member in members:
            await self.db.redis.sadd('mee6:stats:users', member.id)

