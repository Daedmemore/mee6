from mee6 import Mee6
import os
import logging

token = os.getenv('MEE6_TOKEN')
redis_url = os.getenv('REDIS_URL')
mongo_url = os.getenv('MONGO_URL')
mee6_debug = os.getenv('MEE6_DEBUG')
shard = int(os.getenv('SHARD'))
shard_count = int(os.getenv('SHARD_COUNT'))
if mee6_debug:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)

bot = Mee6(shard_id=shard, shard_count=shard_count, redis_url=redis_url, mongo_url=mongo_url)
bot.run(token)
