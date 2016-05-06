import discord
import asyncio
import aiohttp
import os
import logging
import json

bot = discord.Client(max_messages=150)

log = logging.getLogger('discord')
logging.basicConfig(level=logging.INFO)

carbon_key = os.getenv('CARBONITEX_KEY')
mee6_token = os.getenv('MEE6_TOKEN')
carbonitex_count = 0

async def update_carbon(server_count):
    url = 'https://www.carbonitex.net/discord/data/botdata.php?id={}'.format(
        bot.user.id
    )
    with aiohttp.ClientSession() as session:
        payload = {
            'key': carbon_key,
            'servercount': server_count
        }
        headers = {'content-type': 'application/json'}
        async with session.post(url, headers=headers, data=json.dumps(payload)) as resp:
            pass

@bot.event
async def on_ready():
    global carbonitex_count
    while True:
        try:
            server_count = len(bot.servers)
            if carbonitex_count != server_count:
                await update_carbon(server_count)
                log.info("Updating the server count ({} servers)".format(server_count))
                carbonitex_count = server_count
        except Exception as e:
            log.info("Trying again in a second")
            raise e
        await asyncio.sleep(60)

bot.run(mee6_token)
