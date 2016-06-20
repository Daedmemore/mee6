from plugin import Plugin
from random import randint
from decorators import command, bg_task
import logging
log = logging.getLogger('discord')


def check_add_role_perm(adder_roles, role):
    manage_role_perms = any(map(lambda r: r.permissions.manage_roles,
                                adder_roles))
    highest_role = max(adder_roles, key=lambda r: r.position)
    return manage_role_perms and role.position < highest_role.position


class Levels(Plugin):

    fancy_name = 'Levels'

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

    async def is_not_banned(self, member):
        return not await self.is_ban(member)

    @command(pattern="!levels",
             description="Get a link to the server leaderboard",
             banned_roles="banned_roles")
    async def levels(self, message, args):
        url = "http://mee6.xyz/levels/" + message.server.id
        response = "Go check **" + message.server.name + "**'s leaderboard: "
        response += url + " :wink: "
        await self.mee6.send_message(message.channel, response)

    @command(pattern="(^!rank$)|(^!rank <@!?[0-9]*>$)",
             description="Get a player info and rank",
             cooldown="cooldown",
             banned_roles="banned_roles")
    async def rank(self, message, args):
        if message.mentions:
            player = message.mentions[0]
        else:
            player = message.author

        player_info = await self.get_player_info(player)

        if not player_info:
            resp = "{}, It seems like you are not ranked. "\
                "Start talking in the chat to get ranked :wink:."
            if player != message.author:
                resp = "{}, It seems like " + player.mention + \
                    " is not ranked :cry:."
            await self.mee6.send_message(message.channel,
                                        resp.format(message.author.mention))
            return

        if player != message.author:
            response = '{} : **{}**\'s rank > **LEVEL {}** | **XP {}/{}** '\
                '| **TOTAL XP {}** | **Rank {}/{}**'.format(
                    message.author.mention,
                    player.name,
                    player_info['lvl'],
                    player_info['remaining_xp'],
                    player_info['level_xp'],
                    player_info['total_xp'],
                    player_info['rank'],
                    player_info['total_players']
                )
        else:
            response = '{} : **LEVEL {}** | **XP {}/{}** | '\
                '**TOTAL XP {}** | **Rank {}/{}**'.format(
                    player.mention,
                    player_info['lvl'],
                    player_info['remaining_xp'],
                    player_info['level_xp'],
                    player_info['total_xp'],
                    player_info['rank'],
                    player_info['total_players']
                )

        await self.mee6.send_message(message.channel, response)

    async def get_player_info(self, member):
        server = member.server
        storage = await self.get_storage(server)
        players = await storage.smembers('players')
        if member.id not in players:
            return None

        player_total_xp = int(await storage.get('player:' + member.id + ':xp'))
        player_lvl = self._get_level_from_xp(player_total_xp)
        x = 0
        for l in range(0, int(player_lvl)):
            x += self._get_level_xp(l)
        remaining_xp = int(player_total_xp - x)
        level_xp = Levels._get_level_xp(player_lvl)
        players = await storage.sort('players',
                                     by='player:*:xp',
                                     offset=0,
                                     count=-1)
        players = list(reversed(players))
        player_rank = players.index(member.id)+1

        return {"total_xp": player_total_xp,
                "lvl": player_lvl,
                "remaining_xp": remaining_xp,
                "level_xp": level_xp,
                "rank": player_rank,
                "total_players": len(players)}

    async def on_message(self, message):
        if message.author.id == self.mee6.user.id or message.author.bot:
            return

        is_banned = await self.is_ban(message.author)
        if is_banned:
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
        if check_add_role_perm(member.server.me.roles, role):
            return await self.mee6.add_roles(member, role)

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

    @bg_task(60)
    async def update_rewards_job(self):
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
