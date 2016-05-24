from plugin import Plugin
import logging
import asyncio
import aiohttp
import discord


log = logging.getLogger('discord')


class Reddit(Plugin):

    fancy_name = "Reddit"

    message_format = "`New post from /r/{subreddit}`\n\n"\
                     "**{title}** *by {author}*\n"\
                     "{content}\n"\
                     "**Link** {link}"

    async def get_posts(self, subreddit):
        """Gets the n last posts of a subreddit

        Args:
            subreddit: Subbredit name
            n: The number of posts you want

        Returns:
            A list of posts
        """

        url = "https://www.reddit.com/r/{}/new.json".format(subreddit)
        posts = []

        try:
            with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        json = await resp.json()
                        posts = json['data']['children']
                        posts = list(map(lambda p: p['data'], posts))
        except Exception as e:
            log.info("Cannot get posts from {}".format(subreddit))
            log.info(e)
            return []

        return posts[:4]

    async def display_posts(self, subreddit, posts, server):
        """Display a list of posts into the corresponding destination channel.

        This function only displays posts that hasn't been posted previously.
        """
        posts = reversed(posts)
        storage = await self.get_storage(server)
        destination_id = await storage.get('display_channel')
        destination = discord.utils.get(server.channels, id=destination_id)
        if destination is None:
            return

        posted = await storage.smembers(subreddit+':posted')
        for post in posts:
            was_posted = post['id'] in posted
            if was_posted:
                continue

            selftext = post['selftext'] or ""
            message = self.message_format.format(
                title=post['title'],
                subreddit=post['subreddit'],
                author=post['author'],
                content=selftext[:300],
                link="http://redd.it/"+post['id']
            )

            await self.mee6.send_message(destination, message)
            await storage.sadd(subreddit+':posted', post['id'])

    async def get_all_subreddits_posts(self):
        all_subreddits = []

        for server in list(self.mee6.servers):
            plugins = await self.mee6.db.redis.smembers('plugins:'+server.id)
            if "Reddit" not in plugins:
                continue

            storage = await self.get_storage(server)
            for subreddit in await storage.smembers('subs'):
                all_subreddits.append(subreddit)

        all_subreddits = set(all_subreddits)
        all_subreddits_posts = {}
        for subreddit in all_subreddits:
            all_subreddits_posts[subreddit] = await self.get_posts(subreddit)

        return all_subreddits_posts

    async def on_ready(self):
        while True:
            try:
                all_subreddits_posts = await self.get_all_subreddits_posts()
                for server in list(self.mee6.servers):
                    try:
                        plugins = await self.mee6.db.redis.smembers(
                            'plugins:'+server.id
                        )
                        if "Reddit" not in plugins:
                            continue

                        storage = await self.get_storage(server)
                        subreddits = await storage.smembers('subs')
                        for subreddit in subreddits:
                            subreddit_posts = all_subreddits_posts.get(
                                subreddit,
                                []
                            )
                            await self.display_posts(subreddit,
                                                    subreddit_posts,
                                                 server)
                    except Exception as e:
                        log.info("An error occured in Reddit plugin with"
                                 " server {}".format(server.id))
                        log.info(e)
            except Exception as e:
                log.info("An error occured in Reddit plugin...Retrying...")
                log.info(e)
            await asyncio.sleep(30)
