import logging
from plugin import Plugin

log = logging.getLogger('discord')

class PluginManager:

    def __init__(self, mee6):
        self.mee6 = mee6
        self.db = mee6.db
        self.mee6.plugins = []

    def load(self, plugin):
        log.info('Loading plugin {}.'.format(plugin.__name__))
        plugin_instance = plugin(self.mee6)
        self.mee6.plugins.append(plugin_instance)
        log.info('Plugin {} loaded.'.format(plugin.__name__))

    def load_all(self):
        for plugin in Plugin.plugins:
            self.load(plugin)

    async def get_all(self, server):
        plugin_names = await self.db.redis.smembers('plugins:{}'.format(server.id))
        plugins = []
        for plugin in self.mee6.plugins:
            if plugin.is_global:
                plugins.append(plugin)
            if plugin.__class__.__name__ in plugin_names:
                plugins.append(plugin)
        return plugins
