import discord
import asyncio
import logging
from plugin_manager import PluginManager
from database import Db
from time import time
from datadog import DDAgent

log = logging.getLogger('discord')

class Mee6(discord.Client):
    """A modified discord.Client class

    This mod dispatched most events to the different plugins.

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.redis_url = kwargs.get('redis_url')
        self.mongo_url = kwargs.get('mongo_url')
        self.dd_agent_url = kwargs.get('dd_agent_url')
        self.db = Db(self.redis_url, self.mongo_url, self.loop)
        self.plugin_manager = PluginManager(self)
        self.plugin_manager.load_all()
        self.last_messages = []
        self.stats = DDAgent(self.dd_agent_url)


    async def on_ready(self):
        """Called when the bot is ready.

        Connects to the database
        Dispatched all the ready events

        """
        log.info('Connected to the database')

        if hasattr(self, 'shard_id'):
            msg = 'Chat Shard {}/{} restarted'.format(self.shard_id, self.shard_count)
        else:
            msg = 'Mee6 Chat restarted'
        self.stats.event(msg, 'Server count: {}'.format(len(self.servers)))

        await self.add_all_servers()
        for plugin in self.plugins:
            self.loop.create_task(plugin.on_ready())

    async def add_all_servers(self):
        """Syncing all the servers to the DB"""
        log.debug('Syncing servers and db')
        for server in self.servers:
            self.stats.set('mee6.servers', server.id)
            log.debug('Adding server {}\'s id to db'.format(server.id))
            await self.db.redis.sadd('servers', server.id)
            if server.name:
                await self.db.redis.set('server:{}:name'.format(server.id), server.name)
            if server.icon:
                await self.db.redis.set('server:{}:icon'.format(server.id), server.icon)

    async def on_server_join(self, server):
        """Called when joining a new server"""

        self.stats.set('mee6.servers', server.id)
        self.stats.incr('mee6.server_join')

        log.info('Joined {} server : {} !'.format(server.owner.name, server.name))
        log.debug('Adding server {}\'s id to db'.format(server.id))
        await self.db.redis.sadd('servers', server.id)
        await self.db.redis.set('server:{}:name'.format(server.id), server.name)
        if server.icon:
            await self.db.redis.set('server:{}:icon'.format(server.id), server.icon)
        # Dispatching to global plugins
        for plugin in self.plugins:
            if plugin.is_global:
                self.loop.create_task(plugin.on_server_join(server))

    async def on_server_remove(self, server):
        """Called when leaving or kicked from a server

        Removes the server from the db.

        """
        log.info('Leaving {} server : {} !'.format(server.owner.name, server.name))
        log.debug('Removing server {}\'s id from the db'.format(server.id))
        await self.db.redis.srem('servers', server.id)

    async def get_plugins(self, server):
        plugins = await self.plugin_manager.get_all(server)
        return plugins

    async def delete_messages(self, messages):
        if messages is None or len(messages) == 0:
            return

        payload = {
            'messages': [message.id for message in messages]
        }

        url = "{base}/channels/{channel_id}/messages/bulk_delete".format(
            base=discord.endpoints.API_BASE,
            channel_id=messages[0].channel.id
        )

        resp = await self._rate_limit_helper(
            'delete_messages',
            'POST',
            url,
            discord.utils.to_json(payload)
        )

    async def send_message(self, *args, **kwargs):
        self.stats.incr('mee6.sent_messages')
        return await super().send_message(*args, **kwargs)

    async def on_message(self, message):
        self.stats.incr('mee6.recv_messages')
        if message.channel.is_private:
            return

        server = message.server

        if message.content == "!shard?":
            if hasattr(self, 'shard_id'):
                await self.send_message(message.channel, "shard {}/{}".format(self.shard_id+1,
                                                                              self.shard_count))

        enabled_plugins = await self.get_plugins(server)
        for plugin in enabled_plugins:
            self.loop.create_task(plugin.on_message(message))

    async def on_message_edit(self, before, after):
        if before.channel.is_private:
            return

        server = after.server
        enabled_plugins = await self.get_plugins(server)
        for plugin in enabled_plugins:
            self.loop.create_task(plugin.on_message_edit(before, after))

    async def on_message_delete(self, message):
        if message.channel.is_private:
            return

        server = message.server
        enabled_plugins = await self.get_plugins(server)
        for plugin in enabled_plugins:
            self.loop.create_task(plugin.on_message_delete(message))

    async def on_channel_create(self, channel):
        if channel.is_private:
            return

        server = channel.server
        enabled_plugins = await self.get_plugins(server)
        for plugin in enabled_plugins:
            self.loop.create_task(plugin.on_channel_create(channel))

    async def on_channel_update(self, before, after):
        if before.is_private:
            return

        server = after.server
        enabled_plugins = await self.get_plugins(server)
        for plugin in enabled_plugins:
            self.loop.create_task(plugin.on_channel_update(before, after))

    async def on_channel_delete(self, channel):
        if channel.is_private:
            return

        server = channel.server
        enabled_plugins = await self.get_plugins(server)
        for plugin in enabled_plugins:
            self.loop.create_task(plugin.on_channel_delete(channel))

    async def on_member_join(self, member):
        server = member.server
        enabled_plugins = await self.get_plugins(server)
        for plugin in enabled_plugins:
            self.loop.create_task(plugin.on_member_join(member))

    async def on_member_remove(self, member):
        server = member.server
        enabled_plugins = await self.get_plugins(server)
        for plugin in enabled_plugins:
            self.loop.create_task(plugin.on_member_remove(member))

    async def on_member_update(self, before, after):
        server = after.server
        enabled_plugins = await self.get_plugins(server)
        for plugin in enabled_plugins:
            self.loop.create_task(plugin.on_member_update(before, after))

    async def on_server_update(self, before, after):
        server = after
        enabled_plugins = await self.get_plugins(server)
        for plugin in enabled_plugins:
            self.loop.create_task(plugin.on_server_update(before, after))

    async def on_server_role_create(self, server, role):
        enabled_plugins = await self.get_plugins(server)
        for plugin in enabled_plugins:
            self.loop.create_task(plugin.on_server_role_create(server, role))

    async def on_server_role_delete(self, server, role):
        enabled_plugins = await self.get_plugins(server)
        for plugin in enabled_plugins:
            self.loop.create_task(plugin.on_server_role_delete(server, role))

    async def on_server_role_update(self, before, after):
        server = None
        for s in self.servers:
            if after.id in map(lambda r:r.id, s.roles):
                server = s
                break

        if server is None:
            return

        enabled_plugins = await self.get_plugins(server)
        for plugin in enabled_plugins:
            self.loop.create_task(plugin.on_server_role_update(before, after))

    async def on_voice_state_update(self, before, after):
        if after is None:
            server = before.server
        elif before is None:
            server = after.server
        else:
            return

        enabled_plugins = await self.get_plugins(server)
        for plugin in enabled_plugins:
            self.loop.create_task(plugin.on_voice_state_update(before, after))

    async def on_member_ban(self, member):
        server = member.server
        enabled_plugins = await self.get_plugins(server)
        for plugin in enabled_plugins:
            self.loop.create_task(plugin.on_member_ban(member))

    async def on_member_unban(self, member):
        server = member.server
        enabled_plugins = await self.get_plugins(server)
        for plugin in enabled_plugins:
            self.loop.create_task(plugin.on_member_unban(member))

    async def on_typing(self, channel, user, when):
        if channel.is_private:
            return

        server = channel.server
        enabled_plugins = await self.get_plugins(server)
        for plugin in enabled_plugins:
            self.loop.create_task(plugin.on_typing(channel, user, when))

