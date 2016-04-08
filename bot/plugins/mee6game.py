from plugin import Plugin
import discord

class Mee6Game(Plugin):

    is_global = True
    game = 'http://mee6.xyz'

    async def on_ready(self):
        await self.mee6.change_status(
            game=discord.Game(
                name=self.game
            )
        )
