from plugin import Plugin
import asyncio
import logging

logs = logging.getLogger('discord')

class ChangeLog(Plugin):
    """A Plugin to forward the changelogs to all the server owners"""

    is_global = True
    change_log_channel_id = '160784396679380992'
    change_log_server_id = '159962941502783488'

    async def on_message(self, message):
        if message.server.id!=self.change_log_server_id:
            return
        if message.channel.id!=self.change_log_channel_id:
            return

        owners = set(server.owner for server in self.mee6.servers)
        for owner in owners:
            ignored = self.mee6.db.redis.get('user:{}:ignored'.format(
                owner.id
            ))
            if ignored:
                continue

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
