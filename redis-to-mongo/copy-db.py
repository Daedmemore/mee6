import redis
import json
import os
import pymongo

r = redis.Redis.from_url(os.getenv('REDIS_URL'), decode_responses=True)
mongo = pymongo.MongoClient(os.getenv('MONGO_URL'))
db = mongo.logs
i = 0

for server in r.smembers('servers'):
    for date in r.smembers('Logs.{}:message_logs'.format(server)):
        for channel in r.smembers('Logs.{}:message_logs:{}'.format(server, date)):
            msgs = r.lrange('Logs.{}:message_logs:{}:{}'.format(server, date, channel), 0, -1)
            for msg in reversed(msgs):
                message = json.loads(msg)
                db['{}:{}:{}'.format(server, date, channel)].insert(message)
                print('{} OK!'.format(i))
                i+=1

