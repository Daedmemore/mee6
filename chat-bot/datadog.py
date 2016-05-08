import aiomeasures
import logging

log = logging.getLogger('discord')

class DDAgent:

    def __init__(self, dd_agent_url=None):
        self.dd_agent_url = dd_agent_url
        self.agent = None

        if dd_agent_url:
            self.agent = aiomeasures.Datadog(dd_agent_url)

    def send(self, *args, **kwargs):
        if self.agent:
            return self.agent.send(*args, **kwargs)
        else:
            log.debug('No Datadog agent found...')

    def set(self, *args, **kwargs):
        if self.agent:
            return self.agent.set(*args, **kwargs)
        else:
            log.debug('No Datadog agent found...')

    def incr(self, *args, **kwargs):
        if self.agent:
            return self.agent.incr(*args, **kwargs)
        else:
            log.debug('No Datadog agent found...')
