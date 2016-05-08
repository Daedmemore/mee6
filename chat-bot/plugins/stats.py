from plugin import Plugin
import asyncio
import logging
import discord
import aiohttp
import json
import os

logs = logging.getLogger('discord')

class Stats(Plugin):

    is_global = True

    async def carbon_stats(self):
        carbon_key = os.getenv('CARBONITEX_KEY')
        if not carbon_key:
            return

        url = 'https://www.carbonitex.net/discord/data/botdata.php?id={}'.format(
            self.mee6.user.id
        )
        with aiohttp.ClientSession() as session:
            payload = {
                'key': carbon_key,
                'servercount': len(self.mee6.servers)
            }
            headers = {'content-type': 'application/json'}
            async with session.post(url, headers=headers,
                                    data=json.dumps(payload)) as resp:
                pass

    async def on_server_join(self, server):
        await self.mee6.stats.incr('mee6.server_join')
        for member in server.members:

    async def on_channel_create(self, channel):
        await self.db.redis.sadd('mee6:stats:channels', channel.id)

    async def on_message(self, message):
        await self.mee6.stats.incr('mee6.received_messages')
        if message.author.id == self.mee6.user.id:
            await self.mee6.stats.incr('mee6.sent_messages')

    async def on_ready(self):
        """Initialize stats"""
        #await self.carbon_stats()

        # Total members
        members = set(self.mee6.get_all_members())
        channels = set(self.mee6.get_all_channels())
        servers = mee6.servers
        for server in servers:
            await self.mee6.stats.set('mee6.servers', server.id)
        for channel in channels:
            await self.mee6.stats.set('mee6.channels', channel.id)
        for member in members:
            await self.mee6.stats.set('mee6.users', member.id)

