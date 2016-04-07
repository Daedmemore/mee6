from plugin import Plugin
import logging
import asyncio
import aiohttp
import discord

logs = logging.getLogger('discord')

class Reddit(Plugin):
    """A plugin for Reddit feeds"""

    async def get_posts(self, sub):
        url = "https://www.reddit.com/r/{}/new.json".format(sub)
        posts = []
        with aiohttp.ClientSession() as session:
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        json = await resp.json()
                        posts = json['data']['children']
            except:
                pass
        return posts

    async def display_post(self, post, server):
        storage = self.get_storage(server)
        destination_name = storage.get('display_channel')
        display_channel = discord.utils.get(server.channels, name=destination_name)
        destination = display_channel or server

        selftext = post['selftext']
        if selftext:
            selftext = post['selftext'][:400]

        response = """*New post from /r/{subreddit}*

        **{title}** *by {author}*
        {content}
        **Link** {link}
        """.format(
            title=post['title'],
            subreddit=post['subreddit'],
            author=post['author'],
            content=selftext,
            link=post['url']
        )

        await self.mee6.send_message(destination, response)
        storage.set('{}:last'.format(post['subreddit'].lower()), post['id'])

    async def cron_job(self):
        for server in self.mee6.servers:
            storage = self.get_storage(server)
            if storage is None:
                continue

            subs = storage.smembers('subs'.format(server.id))
            for sub in subs:
                last_posts = await self.get_posts(sub)
                if not last_posts:
                    continue

                i = 0
                post = last_posts[0]['data']
                while i<len(post) and i<6:
                    last_posted = storage.get('{}:last'.format(sub))
                    if last_posted == post['id']:
                        break

                    await self.display_post(post, server)
                    i += 1

    async def on_ready(self):
        while True:
            try:
                await self.cron_job()
            except Exception:
                logs.info('An error occured in the Reddit cron job! '
                         'Retrying in 20 sec...'
                         )
            await asyncio.sleep(20)
