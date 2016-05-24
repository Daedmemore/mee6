import redis
import requests
import os
import time
import logging

log = logging.getLogger('carbonitex-agent')
logging.basicConfig(level=logging.INFO)


def get_bot_id(bot_token):
    headers = {'Authorization': bot_token}
    r = requests.get('https://discordapp.com/api/users/@me',
                     headers=headers)
    if r.status_code != 200:
        return None
    return r.json()['id']

redis_url = os.getenv('REDIS_URL')
carbon_key = os.getenv('CARBONITEX_KEY')
mee6_token = os.getenv('MEE6_TOKEN')
mee6_id = get_bot_id(mee6_token)
db = redis.Redis.from_url(redis_url)
guild_count = 0


def update_carbon(guild_count, bot_id, carbon_key):
    url = "https://www.carbonitex.net/discord/data/botdata.php?id="+bot_id
    payload = {'key': carbon_key,
               'servercount': guild_count}
    return requests.post(url, json=payload)

while True:
    try:
        new_guild_count = db.scard('servers')
        if new_guild_count != guild_count:
            guild_count = new_guild_count
            update_carbon(guild_count, mee6_id, carbon_key)
            log.info("Updating guild count {} guilds".format(guild_count))
    except Exception as e:
        log.info("An error occured... Retrying...")
        log.info(e)
    time.sleep(10)
