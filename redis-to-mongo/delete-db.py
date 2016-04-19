import redis
import json
import os

r = redis.Redis.from_url(os.getenv('REDIS_URL'), decode_responses=True)
i = 0

for server in r.smembers('servers'):
    for date in r.smembers('Logs.{}:message_logs'.format(server)):
        for channel in r.smembers('Logs.{}:message_logs:{}'.format(server, date)):
            r.delete('Logs.{}:message_logs:{}:{}'.format(server, date, channel))
            print('{} OK!'.format(i))
            i+=1
