from mee6 import Mee6
import os
import logging

from plugins.commands import Commands
from plugins.help import Help
from plugins.levels import Levels
from plugins.welcome import Welcome
from plugins.animu import AnimuAndMango
from plugins.logs import Logs
from plugins.git import Git
from plugins.streamers import Streamers
from plugins.moderator import Moderator
from plugins.early_backers import EarlyBackers
from plugins.music import Music
#from plugins.reddit import Reddit

# Global plugins
from plugins.basiclogs import BasicLogs
#from plugins.stats import Stats
from plugins.changelog import ChangeLog
from plugins.asciiwelcome import AsciiWelcome
from plugins.mee6game import Mee6Game

token = os.getenv('MEE6_TOKEN')
redis_url = os.getenv('REDIS_URL')
mongo_url = os.getenv('MONGO_URL')
mee6_debug = os.getenv('MEE6_DEBUG')
shard = os.getenv('SHARD') or 0
shard_count = os.getenv('SHARD_COUNT') or 1
if mee6_debug:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)

bot = Mee6(shard_id=int(shard), shard_count=int(shard_count), redis_url=redis_url, mongo_url=mongo_url)
bot.run(token)
