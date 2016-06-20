from plugin import Plugin
import asyncio
import logging

logs = logging.getLogger('discord')

class ChangeLog(Plugin):
    """A Plugin to forward the changelogs to all the server owners"""

    is_global = True
    change_log_channel_id = '159962941502783488'
    change_log_server_id = '159962941502783488'

