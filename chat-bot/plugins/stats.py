from plugin import Plugin
import asyncio
import logging
import discord

logs = logging.getLogger('discord')

class Stats(Plugin):

    is_global = True

    async def on_ready(self):
        """Send basic stats to the db every interval seconds"""
        while True:
            # Total members and online members
            members = (self.mee6.get_all_members())
            online_members = filter(lambda m: m.status is discord.Status.online, members)
            online_members = list(online_members)
            members = list(members)
            await self.db.redis.set('mee6:stats:online_members', len(online_members))
            await self.db.redis.set('mee6:stats:members', len(members))

            await asyncio.sleep(10)

