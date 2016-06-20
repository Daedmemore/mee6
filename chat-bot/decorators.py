import re
import logging
import asyncio

from functools import wraps

log = logging.getLogger('discord')


def bg_task(sleep_time, ignore_errors=True):
    def actual_decorator(func):
        @wraps(func)
        async def wrapper(self):
            await self.mee6.wait_until_ready()
            while True:
                if ignore_errors:
                    try:
                        await func(self)
                    except Exception as e:
                        log.info("An error occured in the {} bg task"
                                 " retrying in {} seconds".format(func.__name__,
                                                                  sleep_time))
                        log.info(e)
                else:
                    await func(self)

                await asyncio.sleep(sleep_time)

        wrapper._bg_task = True
        return wrapper

    return actual_decorator


def command(pattern=None, db_check=False, user_check=None, db_name=None,
            require_role="", require_one_of_roles="", banned_role="",
            banned_roles="", cooldown=0, global_cooldown=0,
            description="", usage=None):
    def actual_decorator(func):
        name = func.__name__
        cmd_name = "!" + name
        prog = re.compile(pattern or cmd_name)
        @wraps(func)
        async def wrapper(self, message):

            # Is it matching?
            match = prog.match(message.content)
            if not match:
                return

            args = match.groups()
            server = message.server
            author = message.author
            author_role_ids = [role.id for role in author.roles]
            storage = await self.get_storage(server)

            is_admin = any([role.permissions.manage_server
                            for role in author.roles])

            # Checking if the command is enabled
            if db_check:
                check = await storage.get(db_name or name)
                if not check:
                    return

            # Cooldown
            if isinstance(cooldown, str):
                cooldown_dur = int(await storage.get(cooldown) or 0)
            else:
                cooldown_dur = cooldown

            if isinstance(global_cooldown, str):
                global_cooldown_dur = int(await storage.get(global_cooldown) or
                                          0)
            else:
                global_cooldown_dur = global_cooldown

            if global_cooldown_dur != 0:
                check = await storage.get("cooldown:" + name)
                if check:
                    return

            if cooldown_dur != 0:
                check = await storage.get("cooldown:" + name + ":" + author.id)
                if check:
                    return

            # Checking the member with the predicate
            if user_check and not is_admin:
                authorized = await user_check(message.author)
                if not authorized:
                    return

            # Checking roles
            if require_role and not is_admin:
                role_id = await storage.get(require_role)
                if role_id not in author_role_ids:
                    return

            if require_one_of_roles and not is_admin:
                role_ids = await storage.smembers(require_one_of_roles)
                authorized = False
                for role in author.roles:
                    if role.id in role_ids:
                        authorized = True
                        break

                if not authorized:
                    return

            if banned_role:
                role_id = await storage.get(banned_role)
                if role_id in author_role_ids:
                    return

            if banned_roles:
                role_ids = await storage.smembers(banned_roles)
                if any([role_id in author_role_ids
                        for role_id in role_ids]):
                    return

            log.info("{}#{}@{} >> {}".format(message.author.name,
                                             message.author.discriminator,
                                             message.server.name,
                                             message.clean_content))
            if global_cooldown_dur != 0:
                await storage.set("cooldown:" + name, "1")
                await storage.expire("cooldown:" + name, global_cooldown_dur)

            if cooldown_dur != 0:
                await storage.set("cooldown:" + name + ":" + author.id, "1")
                await storage.expire("cooldown:" + name + ":" + author.id,
                                     global_cooldown_dur)

            await func(self, message, args)
        wrapper._db_check = db_check
        wrapper._db_name = db_name or func.__name__
        wrapper._is_command = True
        if usage:
            command_name = usage
        else:
            command_name = "!" + func.__name__
        wrapper.info = {"name": command_name,
                        "description": description}
        return wrapper
    return actual_decorator
