from plugin import Plugin

class AsciiWelcome(Plugin):

    is_global = True

    async def on_ready(self):
        print('here')
        with open('welcome_ascii.txt') as f:
            print(f.read())
