from plugin import Plugin
from random import randint
import logging
import discord
import asyncio
log = logging.getLogger('discord')


class Levels(Plugin):

    fancy_name = 'Levels'

    async def get_commands(self, server):
        commands = [
            {
                'name': '!levels',
                'description': 'Gives you the server leaderboard.'
            },
            {
                'name': '!rank',
                'description': 'Gives you your xp, level and rank.'
            },
            {
                'name': '!rank @username',
                'description': 'Gives username\'s xp, level and rank.'
            }
        ]
        return commands

    @staticmethod
    def _get_level_xp(n):
        return 5*(n**2)+50*n+100

    @staticmethod
    def _get_level_from_xp(xp):
        remaining_xp = int(xp)
        level = 0
        while remaining_xp >= Levels._get_level_xp(level):
            remaining_xp -= Levels._get_level_xp(level)
            level += 1
        return level

    async def is_ban(self, member):
        storage = await self.get_storage(member.server)
        banned_roles = await storage.smembers('banned_roles')
        for role in member.roles:
            if role.name in banned_roles or role.id in banned_roles:
                return True

        return False

    async def on_message(self, message):
        if message.author.id == self.mee6.user.id:
            return

        if message.content == '!levels':
            log.info('{}#{}@{} >> {}'.format(
                message.author.name,
                message.author.discriminator,
                message.server.name,
                message.clean_content
            ))
            url = 'http://mee6.xyz/levels/{}'.format(message.server.id)
            response = "Go check **{}**'s leaderboard here"\
                ": {} ! :wink:".format(message.server.name,
                                       url)
            await self.mee6.send_message(message.channel, response)
            return

        is_ban = await self.is_ban(message.author)
        if is_ban:
            return

        if message.content.startswith('!rank'):
            log.info('{}#{}@{} >> {}'.format(
                message.author.name,
                message.author.discriminator,
                message.server.name,
                message.clean_content
            ))
            storage = await self.get_storage(message.server)

            cooldown_duration = int(await storage.get('cooldown') or 0)
            cooldown = await storage.get(
                'player:'+message.author.id+':cooldown'
            )
            if cooldown is not None:
                return
            await storage.set('player:{}:cooldown'.format(message.author.id),
                              '1')
            await storage.expire('player:{}:cooldown'.format(message.author.id),
                                 cooldown_duration)

            if message.mentions != []:
                player = message.mentions[0]
            else:
                player = message.author
            players = await storage.smembers('players')
            if player.id not in players:
                resp = "{}, It seems like you are not ranked. "\
                    "Start talking in the chat to get ranked :wink:."
                if player != message.author:
                    resp = "{}, It seems like " + player.mention + \
                        " is not ranked :cry:."
                await self.mee6.send_message(message.channel,
                                             resp.format(message.author.mention)
                                             )
                return

            player_total_xp = int(await storage.get('player:{}:xp'.format(
                player.id)
            ))
            player_lvl = self._get_level_from_xp(player_total_xp)
            x = 0
            for l in range(0, int(player_lvl)):
                x += self._get_level_xp(l)
            remaining_xp = int(player_total_xp - x)
            level_xp = Levels._get_level_xp(player_lvl)
            players = await storage.sort(
                'players'.format(message.server.id),
                by='player:*:xp'.format(message.server.id),
                offset=0,
                count=-1)
            players = list(reversed(players))
            player_rank = players.index(player.id)+1

            if player != message.author:
                response = '{} : **{}**\'s rank > **LEVEL {}** | **XP {}/{}** '\
                    '| **TOTAL XP {}** | **Rank {}/{}**'.format(
                        message.author.mention,
                        player.name,
                        player_lvl,
                        remaining_xp,
                        level_xp,
                        player_total_xp,
                        player_rank,
                        len(players)
                    )
            else:
                response = '{} : **LEVEL {}** | **XP {}/{}** | '\
                    '**TOTAL XP {}** | **Rank {}/{}**'.format(
                        player.mention,
                        player_lvl,
                        remaining_xp,
                        level_xp,
                        player_total_xp,
                        player_rank,
                        len(players)
                    )

            await self.mee6.send_message(message.channel, response)
            return

        storage = await self.get_storage(message.server)

        # Updating player's profile
        player = message.author
        server = message.server
        await self.mee6.db.redis.set('server:{}:name'.format(server.id),
                                     server.name)
        if server.icon:
            await self.mee6.db.redis.set('server:{}:icon'.format(server.id),
                                         server.icon)
        if server.icon:
            await storage.sadd('server:icon', server.icon)
        await storage.sadd('players', player.id)
        await storage.set('player:{}:name'.format(player.id), player.name)
        await storage.set('player:{}:discriminator'.format(player.id),
                          player.discriminator)
        if player.avatar:
            await storage.set('player:{}:avatar'.format(player.id),
                              player.avatar)

        # Is the player good to go ?
        check = await storage.get('player:{}:check'.format(player.id))
        if check:
            return

        # Get the player xp
        xp = await storage.get('player:{}:xp'.format(player.id))
        if xp is None:
            xp = 0
        else:
            xp = int(xp)

        # Get the player lvl
        lvl = self._get_level_from_xp(xp)

        # Give random xp between 5 and 10
        await storage.incrby('player:{}:xp'.format(player.id), randint(15, 25))
        # Block the player for 60 sec (that's 1 min btw...)
        await storage.set('player:{}:check'.format(player.id), '1', expire=60)
        # Get the new player xp
        player_xp = int(await storage.get('player:{}:xp'.format(player.id)))
        # Comparing the level before and after
        new_level = self._get_level_from_xp(player_xp)
        if new_level != lvl:
            # Updating rewards
            try:
                await self.update_rewards(message.server)
            except Exception as e:
                log.info('Cannot update rewards of server {}'.format(
                    message.server.id
                ))
                log.info(e)
            # Check if announcement is good
            announcement_enabled = await storage.get('announcement_enabled')
            whisp = await storage.get('whisp')
            if announcement_enabled:
                dest = message.channel
                mention = player.mention
                if whisp:
                    dest = player
                    mention = player.name

                announcement = await storage.get('announcement')
                await self.mee6.send_message(dest, announcement.replace(
                    "{player}",
                    mention,
                ).replace(
                    "{level}",
                    str(new_level)
                ))

    async def get_rewards(self, server):
        storage = await self.get_storage(server)
        rewards = []
        for role in server.roles:
            lvl = int(await storage.get('reward:{}'.format(role.id)) or 0)
            if lvl == 0:
                continue
            rewards.append({'lvl': lvl,
                            'role': role})
        return rewards

    async def add_role(self, member, role):
        try:
            await self.mee6.add_roles(member, role)
        except discord.errors.HTTPException as e:
            if e.response.status != 429:
                raise(e)
            retry = float(e.response.headers['Retry-After']) / 1000.0
            await asyncio.sleep(retry)
            return (await self.add_role(member, role))

    async def update_rewards(self, server):
        rewards = await self.get_rewards(server)
        storage = await self.get_storage(server)
        player_ids = await storage.smembers('players')
        for player_id in player_ids:
            player = server.get_member(player_id)
            if player is None:
                continue
            player_xp = int(await storage.get('player:' + player.id + ':xp') or
                            0)
            player_level = self._get_level_from_xp(player_xp)
            for reward in rewards:
                if reward['lvl'] > player_level:
                    continue
                role = reward['role']
                if role in player.roles:
                    continue
                try:
                    await self.add_role(player, role)
                except Exception as e:
                    log.info('Cannot give {} the {} reward'.format(player.id,
                                                                   role.id))
                    log.info(e)

    async def on_ready(self):
        while True:
            for server in list(self.mee6.servers):
                plugin_enabled = 'Levels' in await self.mee6.db.redis.smembers(
                    'plugins:'+server.id
                )
                if not plugin_enabled:
                    continue
                try:
                    await self.update_rewards(server)
                except Exception as e:
                    log.info('Cannot update the rewards for server '+server.id)
                    log.info(e)
            await asyncio.sleep(60)
