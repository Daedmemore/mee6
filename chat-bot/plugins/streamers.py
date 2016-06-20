from plugin import Plugin
from collections import defaultdict
from decorators import bg_task
import aiohttp
import logging
import json
import re

log = logging.getLogger("discord")


class Platform:
    def __init__(self, name, db_name=None):
        self.name = name
        self.db_name = db_name or name

    def collector(self, collector_func):
        self.collector = collector_func


class Streamer:
    def __init__(self, name, display_name, link, stream_id):
        self.name = name
        self.display_name = display_name
        self.link = link
        self.stream_id = stream_id

"""
   Twitch
"""
twitch_platform = Platform("twitch", db_name="streamers")


@twitch_platform.collector
async def twitch_collector(streamers):
    streamers = list(map(lambda s: s.replace(' ', '_'), streamers))
    live_streamers = []
    for i in range(0, len(streamers), 100):
        chunk = streamers[i:i+100]
        url = "https://api.twitch.tv/"\
            "kraken/streams?channel={}&limit=100".format(",".join(chunk))
        with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                result = await resp.json()
                for stream in result['streams']:
                    streamer = Streamer(
                        stream['channel']['name'],
                        stream['channel']['display_name'],
                        stream['channel']['url'],
                        str(stream['_id'])
                    )
                    live_streamers.append(streamer)

    return live_streamers

"""
    HitBox
"""
hitbox_platform = Platform("hitbox", db_name="hitbox_streamers")


@hitbox_platform.collector
async def hitbox_collector(streamers):
    streamers = list(map(lambda s: s.replace(' ', '_'), streamers))
    live_streamers = []
    url="https://api.hitbox.tv/media/live/{}?fast=1&live_only=1".format(
        ",".join(streamers)
    )
    live_streamers = []
    with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            result = await resp.text()
            result = json.loads(result)
            if result['livestream']:
                for live in result['livestream']:
                    if live["media_is_live"] == "1":
                        streamer = Streamer(
                            live["media_name"],
                            live["media_display_name"],
                            live["channel"]["channel_link"],
                            live["media_live_since"]
                        )
                        live_streamers.append(streamer)
    return live_streamers

"""
    Beam
"""
beam_platform = Platform("beam", db_name="beam_streamers")


@beam_platform.collector
async def beam_collector(streamers):
    streamers = list(map(lambda s: s.replace(' ', '_'), streamers))
    live_streamers = []
    url = "http://beam.pro/api/v1/channels?where=online.eq.1,token.in.{}".format(
        ";".join(streamers)
    )

    with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            resp = await resp.json()
            for stream in resp:
                url = "https://beam.pro/api/v1/channels/{}/manifest.light".format(
                    stream['id']
                )
                async with session.get(url) as manifest:
                    manifest = await manifest.json()
                    streamer = Streamer(
                        stream['user']['username'].lower(),
                        stream['user']['username'],
                        "https://beam.pro/"+stream['user']['username'],
                        manifest['since']
                    )
                    live_streamers.append(streamer)
    return live_streamers

"""
    Plugin logic
"""
class Streamers(Plugin):

    fancy_name = "Streamers"

    platforms = [twitch_platform, hitbox_platform, beam_platform]

    async def get_servers_list(self):
        servers = []
        for server in list(self.mee6.servers):
            plugins = await self.mee6.db.redis.smembers("plugins:"+server.id)
            if "Streamers" in plugins:
                servers.append(server)
        return servers

    async def get_live_streamers_by_servers(self):
        servers = await self.get_servers_list()
        data = defaultdict(list)
        for platform in self.platforms:
            streamers = []
            temp_data = {}
            for server in servers:
                server_streamers = await self.mee6.db.redis.smembers(
                    'Streamers.'+server.id+':'+platform.db_name
                )
                server_streamers = list(server_streamers)
                temp_data[server] = server_streamers
                streamers += server_streamers
            streamers = set(streamers)
            if len(streamers) == 0:
                continue

            pattern = "[^0-9a-zA-Z_]+"
            streamers = set(map(lambda s: re.sub(pattern, '', s), streamers))
            try:
                live_streamers = await platform.collector(streamers)
                for server, server_streamers in temp_data.items():
                    for streamer in live_streamers:
                        if streamer.name in server_streamers:
                            data[server.id].append(streamer)
            except Exception as e:
                log.info("Cannot gather live streamers from "+platform.name)
                log.info("With streamers: {}".format(",".join(streamers)))
                log.info(e)
        return data

    @bg_task(30)
    async def streamer_check(self):
        data = await self.get_live_streamers_by_servers()
        for server_id, live_streamers in data.items():
            server = self.mee6.get_server(server_id)
            if not server:
                continue

            storage = await self.get_storage(server)
            channel_id = await storage.get('announcement_channel')
            announcement_channel = self.mee6.get_channel(channel_id) or server
            announcement_message = await storage.get('announcement_msg')
            for streamer in live_streamers:
                streamer_streams_id = await storage.smembers(
                    'check:' + streamer.link
                ) or []
                check = streamer.stream_id in streamer_streams_id
                if check:
                    continue
                try:
                    await self.mee6.send_message(
                        announcement_channel,
                        announcement_message.replace(
                            '{streamer}',
                            streamer.name
                        ).replace(
                            '{link}',
                            streamer.link
                        )
                    )
                    await storage.sadd('check:'+streamer.link, streamer.stream_id)
                except Exception as e:
                    log.info(e)
