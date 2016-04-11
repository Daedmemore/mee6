import discord
import asyncio
import logging
from plugin_manager import PluginManager
from database import Db
from time import time

from plugins.commands import Commands
from plugins.help import Help
from plugins.levels import Levels
from plugins.welcome import Welcome
from plugins.animu import AnimuAndMango
from plugins.logs import Logs
from plugins.git import Git
from plugins.streamers import Streamers
#from plugins.reddit import Reddit

# Global plugins
from plugins.basiclogs import BasicLogs
from plugins.stats import Stats
from plugins.changelog import ChangeLog
from plugins.asciiwelcome import AsciiWelcome
from plugins.mee6game import Mee6Game

log = logging.getLogger('discord')

class Mee6(discord.Client):
    """A modified discord.Client class

    This mod dispatched most events to the different plugins.

    """

    def __init__(self, *args, **kwargs):
        discord.Client.__init__(self, *args, **kwargs)
        self.redis_url = kwargs.get('redis_url')
        self.db = Db(self.redis_url, self.loop)
        self.plugin_manager = PluginManager(self)
        self.plugin_manager.load_all()
        self.last_messages = []

    async def on_ready(self):
        """Called when the bot is ready.

        Launched heartbeat, update_stats cron jobs
        Connects to the database
        Dispatched all the ready events

        """
        log.info('Connected to the database')
        await self.add_all_servers()
        discord.utils.create_task(self.heartbeat(5), loop=self.loop)
        for plugin in self.plugins:
            self.loop.create_task(plugin.on_ready())

    async def add_all_servers(self):
        """Syncing all the servers to the DB"""
        log.debug('Syncing servers and db')
        await self.db.redis.delete('servers')
        for server in self.servers:
            log.debug('Adding server {}\'s id to db'.format(server.id))
            await self.db.redis.sadd('servers', server.id)
            if server.name:
                await self.db.redis.set('server:{}:name'.format(server.id), server.name)
            if server.icon:
                await self.db.redis.set('server:{}:icon'.format(server.id), server.icon)

    async def on_server_join(self, server):
        """Called when joining a new server

        Adds the server to the db.
        Also adds its name and it's icon if it has one.

        """
        log.info('Joined {} server : {} !'.format(server.owner.name, server.name))
        log.debug('Adding server {}\'s id to db'.format(server.id))
        await self.db.redis.sadd('servers', server.id)
        await self.db.redis.set('server:{}:name'.format(server.id), server.name)
        if server.icon:
            await self.db.redis.set('server:{}:icon'.format(server.id), server.icon)

    async def on_server_remove(self, server):
        """Called when leaving or kicked from a server

        Removes the server from the db.

        """
        log.info('Leaving {} server : {} !'.format(server.owner.name, server.name))
        log.debug('Removing server {}\'s id from the db'.format(server.id))
        await self.db.redis.srem('servers', server.id)

    async def heartbeat(self, interval):
        """Sends a heartbeat to the db every interval seconds"""
        while self.is_logged_in:
            await self.db.redis.set('heartbeat', 1, expire=interval)
            await asyncio.sleep(0.9 * interval)

    async def update_stats(self, interval):
        """Send basic stats to the db every interval seconds"""
        while self.is_logged_in:
            # Total members and online members
            members = list(self.get_all_members())
            online_members = filter(lambda m: m.status is discord.Status.online, members)
            online_members = list(online_members)
            await self.db.redis.set('mee6:stats:online_members', len(online_members))
            await self.db.redis.set('mee6:stats:members', len(members))

            # Last messages
            for index, timestamp in enumerate(self.last_messages):
                if timestamp + interval < time():
                    self.last_messages.pop(index)
            await self.db.redis.set('mee6:stats:last_messages', len(self.last_messages))

            await asyncio.sleep(interval)

    async def get_plugins(self, server):
        plugins = await self.plugin_manager.get_all(server)
        return plugins

    async def send_message(self, *args, **kwargs):
        counter = 0
        while counter!=3:
            try:
                await super().send_message(*args, **kwargs)
                counter=2
            except discord.errors.HTTPException as e:
                if e.response.status==502:
                    log.info('502 HTTP Exception, retrying...')
                else:
                    log.info('{} HTTP Exception.'.format(
                        e.response.status
                    ))
                    counter=2
            counter+=1

    async def on_message(self, message):
        if message.channel.is_private:
            return

        server = message.server
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
        if not hasattr(channel, 'server'):
            return
        server = channel.server
        enabled_plugins = await self.get_plugins(server)
        for plugin in enabled_plugins:
            self.loop.create_task(plugin.on_channel_create(channel))

    async def on_channel_update(self, before, after):
        server = after.server
        enabled_plugins = await self.get_plugins(server)
        for plugin in enabled_plugins:
            self.loop.create_task(plugin.on_channel_update(before, after))

    async def on_channel_delete(self, channel):
        if not hasattr(channel, 'server'):
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


    def run(self, token):
        """A patch method to enable bot token"""
        self.token = token
        self.headers['authorization'] = token
        self._is_logged_in.set()
        try:
            self.loop.run_until_complete(self.connect())
        except KeyboardInterrupt:
            self.loop.run_until_complete(self.logout())
            pending = asyncio.Task.all_tasks()
            gathered = asyncio.gather(*pending)
            try:
                gathered.cancel()
                self.loop.run_forever()
                gathered.exception()
            except:
                pass
        finally:
            self.loop.close()
