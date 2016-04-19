from plugin import Plugin
import time
import logging
from datetime import datetime
import json

logger = logging.getLogger('discord')

class Logs(Plugin):

    fancy_name = "Logs"

    async def get_commands(self, server):
        commands = [
            {
                'name': '!logs',
                'description': 'Get the server logs.'
            }
        ]
        return commands

    async def on_message(self, message):
        if(message.content=='!logs'):
            await self.mee6.send_message(message.channel,
                    "Go check the logs here: http://mee6.xyz/logs/{} :wink:!".format(message.server.id))


        now = datetime.utcnow()
        # Formating the msg
        author = message.author
        timestamp = time.mktime(message.timestamp.timetuple()) + message.timestamp.microsecond / 1E6
        msg = {
            "author":{
                    "id": author.id,
                    "name": author.name,
                    "discriminator": author.discriminator,
                    "avatar": author.avatar
                },
            "content": message.content,
            "clean_content": message.clean_content,
            "timestamp": timestamp,
            "attachments": message.attachments
        }
        storage = await self.get_storage(message.server)
        date = now.strftime("%Y-%m-%d %H:%M:%S UTC")
        date = '{}-{}-{}'.format(now.year, now.month, now.day)
        channel = message.channel.name
        # Adding the date to the list of logs
        await storage.sadd('message_logs', date)
        # Adding the channel to the list of today logs
        await storage.sadd('message_logs:{}'.format(date), channel)
        # Adding the message to the logs
        db = self.mee6.db.mongo.logs
        collection = db['{}:{}:{}'.format(message.server.id, date, channel)]
        await collection.insert(msg)
        #await storage.lpush('message_logs:{}:{}'.format(date, channel), json.dumps(msg))

    async def on_member_join(self, member):
        storage = await self.get_storage(member.server)
        log = "{} {}#{} joined the server.".format(
            time.time(),
            member.name,
            member.discriminator
        )
        logger.info("{}#{} joined {}".format(
            member.name,
            member.discriminator,
            member.server.name
        ))
        await storage.lpush('logs', log)

    async def on_member_remove(self, member):
        storage = await self.get_storage(member.server)
        log = "{} {}#{} left the server.".format(
            time.time(),
            member.name,
            member.discriminator
        )
        logger.info("{}#{} left {}".format(
            member.name,
            member.discriminator,
            member.server.name
        ))
        await storage.lpush('logs', log)

    async def on_member_ban(self, member):
        storage = await self.get_storage(member.server)
        log = "{} {}#{} was banned from the server.".format(
                time.time(),
                member.name,
                member.discriminator
        )
        logger.info("{}#{} was banned from {}".format(
            member.name,
            member.discriminator,
            member.server.name
        ))
        await storage.lpush('logs', log)

    async def on_member_unban(self, server, user):
        storage = await self.get_storage(server)
        log = "{} {}#{} was unbanned from the server.".format(
                time.time(),
                user.name,
                user.discriminator
        )
        logger.info("{}#{} was unbanned from {}".format(
            user.name,
            user.discriminator,
            server.name
        ))
        await storage.lpush('logs', log)

