from plugin import Plugin
import asyncio
import logging

logs = logging.getLogger('discord')

class ChangeLog(Plugin):
    """A Plugin to forward the changelogs to all the server owners"""

    is_global = True
    change_log_channel_id = ''
    change_log_server_id = ''

    async def on_message(self, message):
        if message.server.id!=self.change_log_server_id:
            return
        if message.channel.id!=self.change_log_channel_id:
            return

        owners = set(server.owner for server in self.servers)
        for owner in owners:
            try:
                await self.mee6.send_message(
                    owner,
                    message.content
                )
            except Exception:
                logs.info("Couldn't send changelog to {}#{}".format(
                    owner.name,
                    owner.discriminator
                ))

            await asyncio.sleep(2)
