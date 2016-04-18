from plugin import Plugin


class Music(Plugin):

    fancy_name = "Music"

    async def get_commands(self, server):
        commands = [
            {
                'name': '!join',
                'description': 'Makes me join your voice channel'
            },
            {
                'name': '!add music_name',
                'description': 'Adds a music to the queue'
            },
            {
                'name': '!playlist',
                'description': 'Shows the music queue'
            },
            {
                'name': '!stop',
                'description': 'Stops the music'
            },
            {
                'name': '!next',
                'description': 'Goes to the next song'
            }
        ]
        return commands

