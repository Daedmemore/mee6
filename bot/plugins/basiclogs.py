from plugin import Plugin
import logging
import asyncio

logs = logging.getLogger('discord')

class BasicLogs(Plugin):

    is_global = True

    async def on_message(self, message):
        # Incr the number of received messages
        await self.db.redis.incr('mee6:stats:messages')

        # Logs all mee6's messages
        if message.author.id == self.mee6.user.id:
            server, channel = message.server, message.channel
            logs.info("OUT >> {}#{} >> {}".format(
                server.name,
                channel.name,
                message.clean_content.replace('\n', '~')
            ))


