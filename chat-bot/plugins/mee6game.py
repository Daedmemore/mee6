from plugin import Plugin
import discord
import os


class Mee6Game(Plugin):

    is_global = True
    game = os.getenv("MEE6_GAME", 'mee6bot.com')

    async def on_ready(self):
        await self.mee6.change_status(
            game=discord.Game(
                name=self.game
            )
        )
