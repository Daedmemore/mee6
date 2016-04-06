from plugin import Plugin
import aiohttp
import asyncio
import discord
import logging

logs = logging.getLogger('discord')

class Streamers(Plugin):
    """A plugin for twitch lives announcement

    EVERY X seconds:
        -> Get all the streamers in the db
        -> Get all the streamers live
        -> Foreach server which has enabled the plugins
            -> Foreach streamers of the channel
                -> Check if not announced
                    -> Get announcement_msg
                    -> Get announcement_channel
                    -> Mark as announced
    """

    def get_streamers(self):
        """Gets all the streamers in the db"""
        streamers = []
        # Getting all the streamers in the db
        for server in self.mee6.servers:
            if 'Streamers' not in self.db.redis.smembers('plugins:{}'.format(server.id)):
                continue
            storage = self.get_storage(server)
            streamers += list(storage.smembers('streamers'))

        return set(streamers)


    async def get_live_streamers(self, streamers):
        """Gets all the streamers that are live from a list of streamers"""
        # Getting all the streamers live
        url = "https://api.twitch.tv/kraken/streams?channel={}&stream_type=live&limit=100"
        with aiohttp.ClientSession() as session:
            async with session.get(url.format(",".join(streamers))) as resp:
                result = await resp.json()
                live_streamers_list = map(lambda s:(s['channel']['name'], s), result['streams'])
                live_streamers = {name: info for name, info in live_streamers_list}
        return live_streamers

    async def announce_live(self, server, live_streamers):
        """Announce the lives if not already announced"""
        # Check if plugin enabled
        if 'Streamers' not in self.db.redis.smembers('plugins:{}'.format(server.id)):
           return
        storage = self.get_storage(server)
        streamers = storage.smembers('streamers')
        for streamer in streamers:
            # Grab the streamers that are live
            if streamer in live_streamers:
                live_streamer = live_streamers[streamer]
                streamer_ids = storage.smembers('streamer:{}'.format(
                    live_streamer['channel']['name']
                ))
                # Check if already announced
                if str(live_streamer['_id']) in streamer_ids:
                    return
                # Announce
                announcement_msg = storage.get('announcement_msg').format(
                    streamer=live_streamer['channel']['name']
                )
                a_c = storage.get('announcement_channel')
                announcement_channel = discord.utils.get(
                        server.channels,
                        name=a_c
                ) or server

                try:
                    await self.mee6.send_message(announcement_channel, announcement_msg)
                    # Mark as announcement
                    storage.sadd('streamer:{}'.format(
                        live_streamer['channel']['name']),
                        live_streamer['_id']
                    )
                except:
                    pass


    async def on_ready(self):
        while True:
            # Getting all the streamers
            streamers = self.get_streamers()
            # Getting all lve streamers
            live_streamers = await self.get_live_streamers(streamers)
            # Handle announcement
            for server in self.mee6.servers:
                await self.announce_live(server, live_streamers)
            # Wait till next round
            await asyncio.sleep(10)
