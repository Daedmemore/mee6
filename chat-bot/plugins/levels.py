from plugin import Plugin
import logging
from random import randint
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
        return int(100*(1.2**n))

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
            response = 'Go check **{}**\'s leaderboard here : {} ! :wink:'.format(
                message.server.name,
                url
            )
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
            cooldown = await storage.get('player:{}:cooldown'.format(message.author.id))
            if cooldown is not None:
                return
            await storage.set('player:{}:cooldown'.format(message.author.id), '1')
            await storage.expire('player:{}:cooldown'.format(message.author.id), cooldown_duration)

            if message.mentions != []:
                player = message.mentions[0]
            else:
                player = message.author
            players = await storage.smembers('players')
            if player.id not in players:
                resp = '{}, It seems like you are not ranked. Start talking in the chat to get ranked :wink:.'
                if player != message.author:
                    resp = '{}, It seems like '+player.mention+' is not ranked :cry:.'
                await self.mee6.send_message(message.channel,
                    resp.format(
                        message.author.mention
                    )
                )
                return

            player_total_xp = await storage.get('player:{}:xp'.format(player.id))
            player_lvl = await storage.get('player:{}:lvl'.format(player.id))
            x = 0
            for l in range(0,int(player_lvl)):
                x += int(100*(1.2**l))
            remaining_xp = int(int(player_total_xp) - x)
            level_xp = int(Levels._get_level_xp(int(player_lvl)))
            players = await storage.sort('players'.format(message.server.id),
                        by='player:*:xp'.format(message.server.id),
                        offset=0,
                        count=-1
                        )
            players = list(reversed(players))
            player_rank = players.index(player.id)+1

            if player != message.author:
                response = '{} : **{}**\'s rank > **LEVEL {}** | **XP {}/{}** | **TOTAL XP {}** | **Rank {}/{}**'.format(
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
                response = '{} : **LEVEL {}** | **XP {}/{}** | **TOTAL XP {}** | **Rank {}/{}**'.format(
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
        await self.mee6.db.redis.set('server:{}:name'.format(server.id), server.name)
        if server.icon:
            await self.mee6.db.redis.set('server:{}:icon'.format(server.id), server.icon)
        if server.icon:
            await storage.sadd('server:icon', server.icon)
        await storage.sadd('players', player.id)
        await storage.set('player:{}:name'.format(player.id), player.name)
        await storage.set('player:{}:discriminator'.format(player.id), player.discriminator)
        if player.avatar:
            await storage.set('player:{}:avatar'.format(player.id), player.avatar)

        # Is the player good to go ?
        check = await storage.get('player:{}:check'.format(player.id))
        if check:
            return

        # Get the player lvl
        lvl = await storage.get('player:{}:lvl'.format(player.id))
        if lvl is None:
            await storage.set('player:{}:lvl'.format(player.id), 0)
            lvl = 0
        else:
            lvl = int(lvl)

        # Give random xp between 5 and 10
        await storage.incrby('player:{}:xp'.format(player.id), randint(5,10))
        # Block the player for 60 sec (that's 1 min btw...)
        await storage.set('player:{}:check'.format(player.id), '1', expire=60)
        # Get the new player xp
        player_xp = await storage.get('player:{}:xp'.format(player.id))
        # Update the level
        await storage.set('player:{}:lvl'.format(player.id), Levels._get_level_from_xp(player_xp))
        # Comparing the level before and after
        new_level = int(await storage.get('player:{}:lvl'.format(player.id)))
        if new_level != lvl:
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
