from discord import Server

def find_server(*args, **kwargs):
    for arg in args:
        if isinstance(arg, Server):
            return arg
        elif hasattr(arg, 'server'):
            return arg.server
    for key, value in kwargs.items():
        if isinstance(arg, Server):
            return value
        elif hasattr(value, 'server'):
            return arg.server
    return None
