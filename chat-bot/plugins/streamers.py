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

    async def get_streamers(self):
        """Gets all the streamers in the db"""
        streamers = []
        # Getting all the streamers in the db
        for server in self.mee6.servers:
            enabled_plugins = await self.mee6.get_plugins(server)
            if self not in enabled_plugins:
                continue
            storage = await self.get_storage(server)
            streamers += list(await storage.smembers('streamers'))

        return set(streamers)


    async def get_live_streamers(self, streamers):
        """Gets all the streamers that are live from a list of streamers"""
        # Getting all the streamers live
        live_streamers = {}
        streamers = list(map(lambda s: s.replace(' ', ''), streamers))
        for i in range(0, 1+int(len(streamers)/100)):
            url = "https://api.twitch.tv/kraken/streams?channel={}&stream_type=live&limit=100"
            with aiohttp.ClientSession() as session:
                async with session.get(url.format(",".join(streamers[i*100:(i+1)*100]))) as resp:
                    result = await resp.json()
                    live_streamers_list = map(lambda s:(s['channel']['name'], s),
                                                   result['streams'])
                    live_streamers_str = ",".join(map(lambda s:s[0], live_streamers_list))
                    logs.debug("Getting streams info of: "+live_streamers_str)
                    _live_streamers = {name: info for name, info in live_streamers_list}
                    live_streamers = {**live_streamers, **_live_streamers}
        return live_streamers

    async def announce_live(self, server, live_streamers):
        """Announce the lives if not already announced"""
        # Check if plugin enabled
        enabled_plugins = await self.mee6.get_plugins(server)
        if self not in enabled_plugins:
           return
        storage = await self.get_storage(server)
        streamers = await storage.smembers('streamers')
        for streamer in streamers:
            # Grab the streamers that are live
            if streamer in live_streamers:
                live_streamer = live_streamers[streamer]
                streamer_ids = await storage.smembers('streamer:{}'.format(
                    live_streamer['channel']['name']
                ))
                # Check if already announced
                if str(live_streamer['_id']) in streamer_ids:
                    continue
                # Announce
                announcement_msg = await storage.get('announcement_msg')
                announcement_msg = announcement_msg.replace(
                    '{streamer}',
                    live_streamer['channel']['name']
                ).replace(
                    '{link}',
                    'http://twitch.tv/'+live_streamer['channel']['name']
                )
                a_c = await storage.get('announcement_channel')
                announcement_channel = discord.utils.get(
                        server.channels,
                        name=a_c
                )
                if announcement_channel is None:
                    announcement_channel = discord.utils.get(
                        server.channels,
                        id = a_c
                    ) or server

                msg = await self.mee6.send_message(announcement_channel, announcement_msg)
                # Mark as announcement
                if not msg:
                    continue
                await storage.sadd('streamer:{}'.format(
                    live_streamer['channel']['name']),
                    live_streamer['_id']
                )


    async def on_ready(self):
        while True:
            try:
                # Getting all the streamers
                streamers = await self.get_streamers()
                # Getting all lve streamers
                live_streamers = await self.get_live_streamers(streamers)
                # Handle announcement
                for server in self.mee6.servers:
                    await self.announce_live(server, live_streamers)
                # Wait till next round
            except Exception as e:
                logs.info('An error occured in Streamer plugin cron job. Retrying...')
                logs.info(e)
            await asyncio.sleep(10)
