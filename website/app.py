from flask import Flask, session, request, url_for, render_template, redirect, \
jsonify, make_response, flash, abort, Response
import os
from functools import wraps
from requests_oauthlib import OAuth2Session
import redis
import json
import binascii
from math import floor
import datetime
import functools

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", "qdaopdsjDJ9u&çed&ndlnad&pjéà&jdndqld")

REDIS_URL = os.environ.get('REDIS_URL')
OAUTH2_CLIENT_ID = os.environ['OAUTH2_CLIENT_ID']
OAUTH2_CLIENT_SECRET = os.environ['OAUTH2_CLIENT_SECRET']
OAUTH2_REDIRECT_URI = os.environ.get('OAUTH2_REDIRECT_URI', 'http://localhost:5000/confirm_login')
API_BASE_URL = os.environ.get('API_BASE_URL', 'https://discordapp.com/api')
AUTHORIZATION_BASE_URL = API_BASE_URL + '/oauth2/authorize'
DOMAIN = os.environ.get('VIRTUAL_HOST', 'localhost:5000')
TOKEN_URL = API_BASE_URL + '/oauth2/token'
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

db = redis.Redis.from_url(REDIS_URL, decode_responses=True)

# CSRF
@app.before_request
def csrf_protect():
    if request.method == "POST":
        token = session.pop('_csrf_token', None)
        if not token or token != request.form.get('_csrf_token'):
            abort(403)

def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = str(binascii.hexlify(os.urandom(15)))
    return session['_csrf_token']

app.jinja_env.globals['csrf_token'] = generate_csrf_token

def token_updater(token):
    session['oauth2_token'] = token

def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = session.get('user')
        if user is None:
            return redirect(url_for('login'))

        return f(*args, **kwargs)
    return wrapper

def make_session(token=None, state=None, scope=None):
    return OAuth2Session(
        client_id=OAUTH2_CLIENT_ID,
        token=token,
        state=state,
        scope=scope,
        redirect_uri=OAUTH2_REDIRECT_URI,
        auto_refresh_kwargs={
            'client_id': OAUTH2_CLIENT_ID,
            'client_secret': OAUTH2_CLIENT_SECRET,
        },
        auto_refresh_url=TOKEN_URL,
        token_updater=token_updater)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/logout')
def logout():
    session.pop('user')

    return redirect(url_for('index'))

@app.route('/login')
def login():
    user = session.get('user')
    if user is not None:
        return redirect(url_for('select_server'))

    scope = 'identify guilds'.split()
    discord = make_session(scope=scope)
    authorization_url, state = discord.authorization_url(AUTHORIZATION_BASE_URL)
    session['oauth2_state'] = state
    return redirect(authorization_url)

@app.route('/confirm_login')
def confirm_login():
    if request.values.get('error'):
        return redirect(url_for('index'))

    discord = make_session(state=session.get('oauth2_state'))
    token = discord.fetch_token(
        TOKEN_URL,
        client_secret=OAUTH2_CLIENT_SECRET,
        authorization_response=request.url)
    session['oauth2_token'] = token
    get_or_update_user()

    return redirect(url_for('select_server'))

def get_or_update_user():
    oauth2_token = session.get('oauth2_token')
    if oauth2_token:
        discord = make_session(token=oauth2_token)
        session['user'] = discord.get(API_BASE_URL + '/users/@me').json()
        session['guilds'] = discord.get(API_BASE_URL + '/users/@me/guilds').json()
        if session['user'].get('avatar') is None:
            session['user']['avatar'] = url_for('static', filename='img/no_logo.png')
        else:
            session['user']['avatar'] = "https://cdn.discordapp.com/avatars/"+session['user']['id']+"/"+session['user']['avatar']+".jpg"


def get_user_servers(user, guilds):
    return list(filter(lambda g: (g['owner'] is True) or bool(( int(g['permissions'])>> 5) & 1), guilds))

@app.route('/servers')
@require_auth
def select_server():
    guild_id = request.args.get('guild_id')
    if guild_id:
        return redirect(url_for('dashboard', server_id=int(guild_id)))

    get_or_update_user()
    user_servers = get_user_servers(session['user'], session['guilds'])
    return render_template('select-server.html', user_servers=user_servers)

def server_check(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        server_id = kwargs.get('server_id')
        server_ids = db.smembers('servers')

        if str(server_id) not in server_ids:
            url = "https://discordapp.com/oauth2/authorize?&client_id={}"\
                "&scope=bot&permissions={}&guild_id={}&response_type=code&redirect_uri=http://{}/servers".format(
                OAUTH2_CLIENT_ID,
                '66321471',
                server_id,
                DOMAIN
                )
            return redirect(url)

        return f(*args, **kwargs)
    return wrapper

def require_bot_admin(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        server_id = kwargs.get('server_id')
        user_servers = get_user_servers(session['user'], session['guilds'])
        if str(server_id) not in list(map(lambda g: g['id'], user_servers)):
            return redirect(url_for('select_server'))

        return f(*args, **kwargs)
    return wrapper

@app.route('/dashboard/<int:server_id>')
@require_auth
@require_bot_admin
@server_check
def dashboard(server_id):
    servers = session['guilds']
    server = list(filter(lambda g: g['id']==str(server_id), servers))[0]
    enabled_plugins = db.smembers('plugins:{}'.format(server_id))
    return render_template('dashboard.html', server=server, enabled_plugins=enabled_plugins)

@app.route('/dashboard/<int:server_id>/commands')
@require_auth
@require_bot_admin
@server_check
def plugin_commands(server_id):
    disable = request.args.get('disable')
    if disable:
        db.srem('plugins:{}'.format(server_id), 'Commands')
        return redirect(url_for('dashboard', server_id=server_id))

    db.sadd('plugins:{}'.format(server_id), 'Commands')

    servers = session['guilds']
    server = list(filter(lambda g: g['id']==str(server_id), servers))[0]
    enabled_plugins = db.smembers('plugins:{}'.format(server_id))

    commands = []
    commands_names = db.smembers('Commands.{}:commands'.format(server_id))
    for cmd in commands_names:
        command = {
            'name': cmd,
            'message': db.get('Commands.{}:command:{}'.format(server_id, cmd))
        }
        commands.append(command)
    commands = sorted(commands, key=lambda k: k['name'])

    return render_template('plugin-commands.html',
        server=server,
        enabled_plugins=enabled_plugins,
        commands=commands
        )

@app.route('/dashboard/<int:server_id>/commands/add', methods=['POST'])
def add_command(server_id):
    cmd_name = request.form.get('cmd_name', '')
    cmd_message = request.form.get('cmd_message', '')

    edit = cmd_name in db.smembers('Commands.{}:commands'.format(server_id))
    print(edit)

    import re
    cb = url_for('plugin_commands', server_id=server_id)
    if len(cmd_name) == 0 or len(cmd_name) > 15:
        flash('A command name should be between 1 and 15 character long !', 'danger')
    elif not edit and not re.match("^[A-Za-z0-9_-]*$", cmd_name):
        flash('A command name should only contain letters from a to z, numbers, _ or -', 'danger')
    elif len(cmd_message) == 0 or len(cmd_message)>2000:
        flash('A command message should be between 1 and 2000 character long !', 'danger')
    else:
        if not edit :
            cmd_name = '!'+cmd_name
        db.sadd('Commands.{}:commands'.format(server_id), cmd_name)
        db.set('Commands.{}:command:{}'.format(server_id, cmd_name), cmd_message)
        if edit:
            flash('Command {} edited !'.format(cmd_name), 'success')
        else:
            flash('Command {} added !'.format(cmd_name), 'success')

    return redirect(cb)

@app.route('/dashboard/<int:server_id>/commands/<string:command>/delete')
@require_auth
@require_bot_admin
@server_check
def delete_command(server_id, command):
    db.srem('Commands.{}:commands'.format(server_id), command)
    db.delete('Commands.{}:command:{}'.format(server_id, command))
    flash('Command {} deleted !'.format(command), 'success')
    return redirect(url_for('plugin_commands', server_id=server_id))

@app.route('/dashboard/<int:server_id>/help')
@require_auth
@require_bot_admin
@server_check
def plugin_help(server_id):
    disable = request.args.get('disable')
    if disable:
        db.srem('plugins:{}'.format(server_id), 'Help')
        return redirect(url_for('dashboard', server_id=server_id))

    db.sadd('plugins:{}'.format(server_id), 'Help')

    servers = session['guilds']
    server = list(filter(lambda g: g['id']==str(server_id), servers))[0]
    enabled_plugins = db.smembers('plugins:{}'.format(server_id))

    return render_template('plugin-help.html',
        server=server,
        enabled_plugins=enabled_plugins
        )

@app.route('/dashboard/<int:server_id>/levels')
@require_auth
@require_bot_admin
@server_check
def plugin_levels(server_id):
    disable = request.args.get('disable')
    if disable:
        db.srem('plugins:{}'.format(server_id), 'Levels')
        return redirect(url_for('dashboard', server_id=server_id))
    db.sadd('plugins:{}'.format(server_id), 'Levels')
    servers = session['guilds']
    server = list(filter(lambda g: g['id']==str(server_id), servers))[0]
    enabled_plugins = db.smembers('plugins:{}'.format(server_id))

    initial_announcement = 'GG {player}, you just advanced to **level {level}** !'
    announcement_enabled = db.get('Levels.{}:announcement_enabled'.format(server_id))
    announcement = db.get('Levels.{}:announcement'.format(server_id))
    if announcement is None:
        db.set('Levels.{}:announcement'.format(server_id), initial_announcement)
        db.set('Levels.{}:announcement_enabled'.format(server_id), '1')
        announcement_enabled = '1'

    announcement = db.get('Levels.{}:announcement'.format(server_id))

    banned_members = db.smembers('Levels.{}:banned_members'.format(server_id)) or []
    banned_roles = db.smembers('Levels.{}:banned_roles'.format(server_id)) or []

    cooldown = db.get('Levels.{}:cooldown'.format(server_id)) or 0

    return render_template('plugin-levels.html',
        server = server,
        enabled_plugins = enabled_plugins,
        announcement = announcement,
        announcement_enabled = announcement_enabled,
        banned_members = banned_members,
        banned_roles = banned_roles,
        cooldown = cooldown
        )

@app.route('/dashboard/<int:server_id>/levels/update', methods=['POST'])
@require_auth
@require_bot_admin
@server_check
def update_levels(server_id):
    servers = session['guilds']
    server = list(filter(lambda g: g['id']==str(server_id), servers))[0]

    banned_members = request.form.getlist('banned_members[]')
    banned_roles = request.form.getlist('banned_roles[]')
    announcement = request.form.get('announcement')
    enable = request.form.get('enable')
    cooldown = request.form.get('cooldown')

    try:
        cooldown = int(cooldown)
    except ValueError:
        flash('The cooldown that you provided isn\'t an integer!', 'warning')
        return redirect(url_for('plugin_levels', server_id=server_id))

    if announcement == '' or len(announcement) > 2000:
        flash('The level up announcement could not be empty or have 2000+ characters.', 'warning')
    else:
        db.set('Levels.{}:announcement'.format(server_id), announcement)
        db.set('Levels.{}:cooldown'.format(server_id), cooldown)

        db.delete('Levels.{}:banned_members'.format(server_id))
        if len(banned_members)>0:
            db.sadd('Levels.{}:banned_members'.format(server_id), *banned_members)

        db.delete('Levels.{}:banned_roles'.format(server_id))
        if len(banned_roles)>0:
            db.sadd('Levels.{}:banned_roles'.format(server_id), *banned_roles)

        if enable:
            db.set('Levels.{}:announcement_enabled'.format(server_id), '1')
        else:
            db.delete('Levels.{}:announcement_enabled'.format(server_id))

        flash('Settings updated ;) !', 'success')

    return redirect(url_for('plugin_levels', server_id=server_id))


@app.route('/levels/<int:server_id>')
def levels(server_id):
    server_check = str(server_id) in db.smembers('servers')
    if not server_check:
        return redirect(url_for('index'))
    plugin_check = 'Levels' in db.smembers('plugins:{}'.format(server_id))
    if not plugin_check:
        return redirect(url_for('index'))

    server = {
        'id': server_id,
        'icon': db.get('server:{}:icon'.format(server_id)),
        'name': db.get('server:{}:name'.format(server_id))
    }

    _players = db.sort('Levels.{}:players'.format(server_id),
                by='Levels.{}:player:*:xp'.format(server_id),
                get=[
                    'Levels.{}:player:*:xp'.format(server_id),
                    'Levels.{}:player:*:lvl'.format(server_id),
                    'Levels.{}:player:*:name'.format(server_id),
                    'Levels.{}:player:*:avatar'.format(server_id),
                    'Levels.{}:player:*:discriminator'.format(server_id),
                    '#'
                     ],
                start=0,
                num=100,
                desc=True)

    players = []
    for i in range(0, len(_players),6):
        lvl = int(_players[i+1])
        x = 0
        for l in range(0,lvl):
            x += 100*(1.2**l)
        remaining_xp = int(int(_players[i]) - x)
        player = {
            'total_xp': int(_players[i]),
            'xp': remaining_xp,
            'lvl': _players[i+1],
            'lvl_xp': int(100*(1.2**lvl)),
            'xp_percent': floor(100*(remaining_xp)/(100*(1.2**lvl))),
            'name': _players[i+2],
            'avatar': _players[i+3],
            'discriminator': _players[i+4],
            'id': _players[i+5]
        }
        players.append(player)
    return render_template('levels.html', players=players, server=server, title="{} leaderboard - Mee6 bot".format(server['name']))

@app.route('/dashboard/<int:server_id>/welcome')
@require_auth
@require_bot_admin
@server_check
def plugin_welcome(server_id):
    disable = request.args.get('disable')
    if disable:
        db.srem('plugins:{}'.format(server_id), 'Welcome')
        return redirect(url_for('dashboard', server_id=server_id))
    db.sadd('plugins:{}'.format(server_id), 'Welcome')
    servers = session['guilds']
    server = list(filter(lambda g: g['id']==str(server_id), servers))[0]
    enabled_plugins = db.smembers('plugins:{}'.format(server_id))

    initial_welcome = '{user}, Welcome to **{server}** ! Have a great time here :wink: !'
    welcome_message = db.get('Welcome.{}:welcome_message'.format(server_id))
    channel_name = db.get('Welcome.{}:channel_name'.format(server_id))
    if welcome_message is None:
        db.set('Welcome.{}:welcome_message'.format(server_id), initial_welcome)
        welcome_message = initial_welcome

    return render_template('plugin-welcome.html',
        server=server,
        enabled_plugins=enabled_plugins,
        welcome_message=welcome_message,
        channel_name=channel_name
        )

@app.route('/dashboard/<int:server_id>/welcome/update', methods=['POST'])
@require_auth
@require_bot_admin
@server_check
def update_welcome(server_id):
    servers = session['guilds']
    server = list(filter(lambda g: g['id']==str(server_id), servers))[0]

    welcome_message = request.form.get('welcome_message')
    channel_name = request.form.get('channel_name')

    if welcome_message == '' or len(welcome_message) > 2000:
        flash('The welcome message cannot be empty or have 2000+ characters.', 'warning')
    else:
        db.set('Welcome.{}:welcome_message'.format(server_id), welcome_message)
        db.set('Welcome.{}:channel_name'.format(server_id), channel_name)
        flash('Settings updated ;) !', 'success')

    return redirect(url_for('plugin_welcome', server_id=server_id))

@app.route('/dashboard/<int:server_id>/animu')
@require_auth
@require_bot_admin
@server_check
def plugin_animu(server_id):
    disable = request.args.get('disable')
    if disable:
        db.srem('plugins:{}'.format(server_id), 'AnimuAndMango')
        return redirect(url_for('dashboard', server_id=server_id))

    db.sadd('plugins:{}'.format(server_id), 'AnimuAndMango')

    servers = session['guilds']
    server = list(filter(lambda g: g['id']==str(server_id), servers))[0]
    enabled_plugins = db.smembers('plugins:{}'.format(server_id))

    return render_template('plugin-animu.html',
        server=server,
        enabled_plugins=enabled_plugins
        )

@app.route('/dashboard/<int:server_id>/logs')
@require_auth
@require_bot_admin
@server_check
def plugin_logs(server_id):
    disable = request.args.get('disable')
    if disable:
        db.srem('plugins:{}'.format(server_id), 'Logs')
        return redirect(url_for('dashboard', server_id=server_id))

    db.sadd('plugins:{}'.format(server_id), 'Logs')

    servers = session['guilds']
    server = list(filter(lambda g: g['id']==str(server_id), servers))[0]
    enabled_plugins = db.smembers('plugins:{}'.format(server_id))

    logs = db.lrange('Logs.{}:logs'.format(server_id), start=0, end=100)

    return render_template('plugin-logs.html',
            server=server,
            enabled_plugins=enabled_plugins,
            logs = logs
            )

@app.route('/dashboard/<int:server_id>/git')
@require_auth
@require_bot_admin
@server_check
def plugin_git(server_id):
    disable = request.args.get('disable')
    if disable:
        db.srem('plugins:{}'.format(server_id), 'Git')
        return redirect(url_for('dashboard',server_id=server_id))

    db.sadd('plugins:{}'.format(server_id), 'Git')

    servers = session['guilds']
    server = list(filter(lambda g: g['id']==str(server_id), servers))[0]
    enabled_plugins = db.smembers('plugins:{}'.format(server_id))

    return render_template('plugin-git.html',
                           server=server,
                           enabled_plugins=enabled_plugins,
                           )

@app.route('/logs/<int:server_id>')
def logs_homepage(server_id):
    json = request.args.get('json', None)
    servers = db.smembers('servers')
    servers = [server for server in servers if 'Logs' in db.smembers('plugins:{}'.format(
        server
        ))]
    if str(server_id) not in servers:
        return redirect(url_for('index'))
    server = {
        'id': server_id,
        'icon': db.get('server:{}:icon'.format(server_id)),
        'name': db.get('server:{}:name'.format(server_id))
    }
    payload = []

    @functools.cmp_to_key
    def cmp(d1, d2):
        d1 = d1.split('-')
        d2 = d2.split('-')
        if d1[0]!=d2[0]:
            return int(d1[0])>int(d2[0])
        if d1[1]!=d2[1]:
            return int(d1[1])>int(d2[1])
        else:
            return int(d1[2])>int(d2[2])

    dates = sorted(list(db.smembers('Logs.{}:message_logs'.format(server_id))), key=cmp, reverse=True)
    for date in dates:
        info = {
                'dt': date,
                'channels':list(db.smembers('Logs.{}:message_logs:{}'.format(server_id, date)))
                }
        payload.append(info)
    if json is not None:
        return jsonify({
            'number': len(payload),
            'items': payload
            })
    else:
        return render_template('logs-homepage.html', payload=payload, server=server)

@app.route('/message_logs/<int:server_id>/<string:dt>/<string:channel>')
def message_logs(server_id, dt, channel):
    json_format = request.args.get('json', None)
    txt = request.args.get('txt', None)
    servers = db.smembers('servers')
    servers = [server for server in servers if 'Logs' in db.smembers('plugins:{}'.format(
        server
        ))]
    if str(server_id) not in servers:
        return redirect(url_for('index'))
    server = {
        'id': server_id,
        'icon': db.get('server:{}:icon'.format(server_id)),
        'name': db.get('server:{}:name'.format(server_id))
    }

    messages = db.lrange('Logs.{}:message_logs:{}:{}'.format(server_id, dt, channel), start=0, end=-1)
    messages = list(map(json.loads, messages))
    def render_text(msgs):
        messages = []
        for msg in msgs:
            txt = "{date} <{name}#{discrim}> {content}".format(
                    name=msg['author']['name'],
                    discrim=msg['author']['discriminator'],
                    content=msg['clean_content'],
                    date=datetime.datetime.fromtimestamp(
                        msg['timestamp']
                    ).strftime('%Y-%m-%d %H:%M:%S')
            )
            if msg['attachments']:
                txt+= " "
                txt+= "|".join(list(map(lambda a:a['url'], msg['attachments'])))
            messages.append(txt)
        return "\n".join(messages)

    if json_format is not None:
        return jsonify({
                'date': dt,
                'messages': messages
                })
    elif txt is not None:
        return Response(render_text(messages), mimetype='text/plain')
    else:
        messages = list(map(lambda m: {**m,'date':datetime.datetime.fromtimestamp(m['timestamp']).strftime('%H:%M:%S')}, messages))
        return render_template('message-logs.html', server=server, channel=channel, messages=messages, dt=dt)

@app.route('/dashboard/<int:server_id>/manage_admins')
def manage_admins(server_id):
    servers = session['guilds']
    server = list(filter(lambda g: g['id']==str(server_id), servers))[0]
    enabled_plugins = db.smembers('plugins:{}'.format(server_id))
    return render_template('manage-admins.html',
                           server=server,
                           enabled_plugins=enabled_plugins,
                           )

@app.route('/dashboard/<int:server_id>/streamers')
@require_auth
@require_bot_admin
@server_check
def plugin_streamers(server_id):
    disable = request.args.get('disable')
    if disable:
        db.srem('plugins:{}'.format(server_id), 'Streamers')
        return redirect(url_for('dashboard',server_id=server_id))

    db.sadd('plugins:{}'.format(server_id), 'Streamers')

    servers = session['guilds']
    server = list(filter(lambda g: g['id']==str(server_id), servers))[0]
    enabled_plugins = db.smembers('plugins:{}'.format(server_id))
    streamers = db.smembers('Streamers.{}:streamers'.format(server_id))
    announcement_channel = db.get('Streamers.{}:announcement_channel'.format(server_id))
    announcement_msg = db.get('Streamers.{}:announcement_msg'.format(server_id))
    if announcement_msg is None:
        announcement_msg = "Hey @everyone! {streamer} is now live on http://twitch.tv/{streamer} ! Go check it out :wink:!"
        db.set('Streamers.{}:announcement_msg'.format(server_id), announcement_msg)
    return render_template('plugin-streamers.html',
                           server=server,
                           streamers=streamers,
                           announcement_channel=announcement_channel,
                           announcement_msg=announcement_msg,
                           enabled_plugins=enabled_plugins,
                           )

@app.route('/dashboard/<int:server_id>/update_streamers', methods=['POST'])
@require_auth
@require_bot_admin
@server_check
def update_streamers(server_id):
    servers = session['guilds']
    server = list(filter(lambda g: g['id']==str(server_id), servers))[0]
    announcement_channel = request.form.get('announcement_channel')
    announcement_msg = request.form.get('announcement_msg')
    if announcement_msg == "":
        flash('The announcement message should not be empty!', 'warning')
        return redirect(url_for('plugin_streamers', server_id=server_id))

    streamers = request.form.getlist('streamers[]')
    db.set('Streamers.{}:announcement_channel'.format(server_id), announcement_channel)
    db.set('Streamers.{}:announcement_msg'.format(server_id), announcement_msg)
    db.delete('Streamers.{}:streamers'.format(server_id))
    for streamer in streamers:
        if streamer != "":
            db.sadd('Streamers.{}:streamers'.format(server_id), streamer.lower())

    flash('Configuration updated with success!', 'success')
    return redirect(url_for('plugin_streamers', server_id=server_id))

@app.route('/dashboard/<int:server_id>/reddit')
@require_auth
@require_bot_admin
@server_check
def plugin_reddit(server_id):
    disable = request.args.get('disable')
    if disable:
        db.srem('plugins:{}'.format(server_id), 'Reddit')
        return redirect(url_for('dashboard',server_id=server_id))

    db.sadd('plugins:{}'.format(server_id), 'Reddit')

    servers = session['guilds']
    server = list(filter(lambda g: g['id']==str(server_id), servers))[0]
    enabled_plugins = db.smembers('plugins:{}'.format(server_id))
    subs = db.smembers('Reddit.{}:subs'.format(server_id))
    display_channel = db.get('Reddit.{}:display_channel'.format(server_id))
    return render_template('plugin-reddit.html',
                           server=server,
                           subs=subs,
                           display_channel=display_channel,
                           enabled_plugins=enabled_plugins,
                           )

@app.route('/dashboard/<int:server_id>/update_reddit', methods=['POST'])
@require_auth
@require_bot_admin
@server_check
def update_reddit(server_id):
    servers = session['guilds']
    server = list(filter(lambda g: g['id']==str(server_id), servers))[0]
    display_channel = request.form.get('display_channel')

    subs = request.form.getlist('subs[]')
    db.set('Reddit.{}:display_channel'.format(server_id), display_channel)
    db.delete('Reddit.{}:subs'.format(server_id))
    for sub in subs:
        if sub != "":
            db.sadd('Reddit.{}:subs'.format(server_id), sub.lower())

    flash('Configuration updated with success!', 'success')
    return redirect(url_for('plugin_reddit', server_id=server_id))


if __name__=='__main__':
    app.debug = True
    app.run()
