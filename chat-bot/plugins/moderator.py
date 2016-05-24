from plugin import Plugin
from functools import wraps

import logging
import asyncio
import re

logs = logging.getLogger("discord")


def command(pattern, db_name):
    def actual_decorator(func):
        @wraps(func)
        async def wrapper(self, message):
            # Check command syntax
            match = re.match(pattern, message.content)
            if not match:
                return

            # Get the args
            args = match.groups()
            server = message.server

            # Check if command enabled
            storage = await self.get_storage(server)
            check = await storage.get(db_name)
            if not check:
                return

            authorized = await self.check_auth(message.author)
            if not authorized:
                return

            await func(self, message, args)
        return wrapper
    return actual_decorator


class Moderator(Plugin):

    async def check_auth(self, member):
        # Check if the author if authorized
        storage = await self.get_storage(member.server)
        role_names = await storage.smembers('roles')
        authorized = False
        for role in member.roles:
            authorized = any([role.name in role_names,
                             role.id in role_names,
                             role.permissions.manage_server])
            if authorized:
                break
        return authorized

    @command(r'^!clear ([0-9]*)$', 'clear')
    async def clear_num(self, message, args):
        number = min(int(args[0]), 1000)
        if number < 1:
            return
        deleted_messages = await self.mee6.purge_from(
            message.channel,
            limit=number+1
        )

        message_number = len(deleted_messages) - 1
        confirm_message = await self.mee6.send_message(
            message.channel,
            "`Deleted {} message{}!` :thumbsup: ".format(
                message_number,
                "" if message_number < 2 else "s"
            )
        )
        await asyncio.sleep(3)

        await self.mee6.delete_message(confirm_message)

    @command(r'^!clear <@!?([0-9]*)>$', 'clear')
    async def clear_user(self, message, args):
        if not message.mentions:
            return
        user = message.mentions[0]
        if not user:
            return

        deleted_messages = await self.mee6.purge_from(
            message.channel,
            check=lambda m: m.author.id == user.id or m == message
        )

        message_number = len(deleted_messages)
        confirm = await self.mee6.send_message(
            message.channel,
            "`Deleted {} messages!` :thumbsup: ".format(message_number)
        )
        await asyncio.sleep(3)
        await self.mee6.delete_message(confirm)

    @command(r'^!mute <@!?([0-9]*)>$', 'mute')
    async def mute(self, message, args):
        if not message.mentions:
            return
        member = message.mentions[0]
        check = await self.check_auth(member)
        if check:
            return

        allow, deny = message.channel.overwrites_for(member)
        allow.send_messages = False
        deny.send_messages = True
        await self.mee6.edit_channel_permissions(
            message.channel,
            member,
            allow=allow,
            deny=deny
        )
        await self.mee6.send_message(
            message.channel,
            "{} is now :speak_no_evil: here!".format(member.mention)
        )

    @command(r'^!unmute <@!?([0-9]*)>$', 'mute')
    async def unmute(self, message, args):
        if not message.mentions:
            return
        member = message.mentions[0]

        check = await self.check_auth(member)
        if check:
            return

        allow, deny = message.channel.overwrites_for(member)
        allow.send_messages = True
        deny.send_messages = False
        await self.mee6.edit_channel_permissions(
            message.channel,
            member,
            allow=allow,
            deny=deny
        )
        await self.mee6.send_message(
            message.channel,
            "{} is no longer :speak_no_evil: here! He/she "
            "can speak :monkey_face:!".format(member.mention)
        )

    @command(r'!slowmode ([0-9]*)', 'slowmode')
    async def slowmode(self, message, args):
        num = int(args[0])
        if num == 0:
            await self.mee6.send_message(
                message.channel,
                "The slow mode interval cannot be 0 :wink:."
            )
            return
        storage = await self.get_storage(message.server)
        await storage.sadd(
            'slowmode:channels',
            message.channel.id
        )
        await storage.set(
            'slowmode:{}:interval'.format(
                message.channel.id
            ),
            num
        )
        await self.mee6.send_message(
            message.channel,
            "{} is now in :snail: mode. ({} seconds)".format(
                message.channel.mention,
                num
            )
        )

    @command(r'^!slowoff$', 'slowmode')
    async def slowoff(self, message, args):
        storage = await self.get_storage(message.server)
        # Get the slowed_channels
        slowed_channels = await storage.smembers('slowmode:channels')
        if message.channel.id not in slowed_channels:
            return
        # Delete the channel from the slowed channel
        await storage.srem('slowmode:channels', message.channel.id)
        # Get the slowed_members
        slowed_members = await storage.smembers(
            'slowmode:{}:slowed'.format(message.channel.id)
        )
        # Delete the slowed_members TTL
        for user_id in slowed_members:
            await storage.delete('slowmode:{}:slowed:{}'.format(
                message.channel.id,
                user_id
            ))
        # Delete the slowed_members list
        await storage.delete('slowmode:{}:slowed'.format(
            message.channel.id
        ))
        # Confirm message
        await self.mee6.send_message(
            message.channel,
            "{} is no longer in :snail: mode :wink:.".format(
                message.channel.mention
            )
        )

    async def slow_check(self, message):
        storage = await self.get_storage(message.server)
        # Check if the user isn't auth
        check = await self.check_auth(message.author)
        if check:
            return
        # Check if the channel is in slowmode
        slowed_channels = await storage.smembers('slowmode:channels')
        if message.channel.id not in slowed_channels:
            return
        # Grab the slowmode interval
        interval = await storage.get(
            'slowmode:{}:interval'.format(message.channel.id)
        )
        if not interval:
            return

        # If the user not in the slowed list
        # Add the user to the slowed list
        await storage.sadd(
            'slowmode:{}:slowed'.format(
                message.channel.id
            ),
            message.author.id
        )
        # Check if user slowed
        slowed = await storage.get('slowmode:{}:slowed:{}'.format(
            message.channel.id,
            message.author.id)
        ) is not None

        if slowed:
            await self.mee6.delete_message(message)
        else:
            # Register a TTL key for the user
            await storage.set(
                'slowmode:{}:slowed:{}'.format(
                    message.channel.id,
                    message.author.id
                ),
                interval
            )
            await storage.expire(
                'slowmode:{}:slowed:{}'.format(
                    message.channel.id,
                    message.author.id
                ),
                int(interval)
            )

    async def banned_words(self, message):
        storage = await self.get_storage(message.server)
        banned_words = await storage.get('banned_words')
        if banned_words:
            banned_words = banned_words.split(',')
        else:
            banned_words = []

        words = list(map(lambda w: w.lower(), message.content.split()))
        for banned_word in banned_words:
            if banned_word.lower() in words:
                await self.mee6.delete_message(message)
                msg = await self.mee6.send_message(
                    message.channel,
                    "{}, **LANGUAGE!!!** :rage:".format(
                        message.author.mention
                    )
                )
                await asyncio.sleep(3)
                await self.mee6.delete_message(msg)
                return

    async def on_message_edit(self, before, after):
        await self.banned_words(after)

    async def on_message(self, message):
        if message.author.id == self.mee6.user.id:
            return

        await self.clear_num(message)
        await self.clear_user(message)
        await self.banned_words(message)
        await self.mute(message)
        await self.unmute(message)
        await self.slowmode(message)
        await self.slowoff(message)
        await self.slow_check(message)
