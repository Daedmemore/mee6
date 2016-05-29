import os
import requests
import pymongo
import redis
import json
import binascii
import datetime
import logging
import paypalrestsdk
from math import floor
import re
from functools import wraps
from requests_oauthlib import OAuth2Session
from flask import Flask, session, request, url_for, render_template, redirect, \
 jsonify, flash, abort, Response
from itsdangerous import JSONWebSignatureSerializer

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY",
                                          "qdaopdsjDJ9u&çed&ndlnad&pjéà&jdndqld"
                                          )

REDIS_URL = os.environ.get('REDIS_URL')
OAUTH2_CLIENT_ID = os.environ['OAUTH2_CLIENT_ID']
OAUTH2_CLIENT_SECRET = os.environ['OAUTH2_CLIENT_SECRET']
OAUTH2_REDIRECT_URI = os.environ.get('OAUTH2_REDIRECT_URI',
                                     'http://localhost:5000/confirm_login')
API_BASE_URL = os.environ.get('API_BASE_URL', 'https://discordapp.com/api')
AUTHORIZATION_BASE_URL = API_BASE_URL + '/oauth2/authorize'
AVATAR_BASE_URL = "https://cdn.discordapp.com/avatars/"
ICON_BASE_URL = "https://cdn.discordapp.com/icons/"
DEFAULT_AVATAR = "https://discordapp.com/assets/"\
                "1cbd08c76f8af6dddce02c5138971129.png"
DOMAIN = os.environ.get('VIRTUAL_HOST', 'localhost:5000')
TOKEN_URL = API_BASE_URL + '/oauth2/token'
MEE6_TOKEN = os.getenv('MEE6_TOKEN')
MONGO_URL = os.environ.get('MONGO_URL')
FLASK_DEBUG = os.getenv('FLASK_DEBUG')


db = redis.Redis.from_url(REDIS_URL, decode_responses=True)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
mongo = pymongo.MongoClient(MONGO_URL)

"""
    JINJA2 Filters
"""


@app.template_filter('avatar')
def avatar(user):
    if user.get('avatar'):
        return AVATAR_BASE_URL + user['id'] + '/' + user['avatar'] + '.jpg'
    else:
        return DEFAULT_AVATAR

"""
    Discord DATA logic
"""


def get_user(token):
    # If it's an api_token, go fetch the discord_token
    if token.get('api_key'):
        discord_token_str = db.get('user:{}:discord_token'.format(
            token['user_id']
        ))
        token = json.loads(discord_token_str)

    discord = make_session(token=token)

    req = discord.get(API_BASE_URL + '/users/@me')
    if req.status_code != 200:
        abort(req.status_code)

    user = req.json()
    # Saving that to the session for easy template access
    session['user'] = user

    # Saving that to the db
    db.sadd('users', user['id'])
    db.set('user:{}'.format(user['id']), json.dumps(user))

    points = db.get('user:'+user['id']+':points') or 0
    user['points'] = int(points)
    return user


def get_user_guilds(token):
    # If it's an api_token, go fetch the discord_token
    if token.get('api_key'):
        user_id = token['user_id']
        discord_token_str = db.get('user:{}:discord_token'.format(
            token['user_id']
        ))
        token = json.loads(discord_token_str)
    else:
        user_id = get_user(token)['id']

    discord = make_session(token=token)

    req = discord.get(API_BASE_URL + '/users/@me/guilds')
    if req.status_code != 200:
        abort(req.status_code)

    guilds = req.json()
    # Saving that to the db
    db.set('user:{}:guilds'.format(user_id), json.dumps(guilds))
    return guilds


def get_user_managed_servers(user, guilds):
    return list(
        filter(
            lambda g: (g['owner'] is True) or
            bool((int(g['permissions']) >> 5) & 1),
            guilds)
    )

"""
    CRSF Security
"""


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

"""
    AUTH logic
"""


def token_updater(discord_token):
    user = get_user(discord_token)
    # Save the new discord_token
    db.set('user:{}:discord_token'.format(user['id']),
           json.dumps(discord_token))


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
        token_updater=token_updater
    )


@app.route('/login')
def login():
    scope = ['identify', 'guilds']
    discord = make_session(scope=scope)
    authorization_url, state = discord.authorization_url(
        AUTHORIZATION_BASE_URL,
        access_type="offline"
    )
    session['oauth2_state'] = state
    return redirect(authorization_url)


@app.route('/confirm_login')
def confirm_login():
    # Check for state and for 0 errors
    state = session.get('oauth2_state')
    if not state or request.values.get('error'):
        return redirect(url_for('index'))

    # Fetch token
    discord = make_session(state=state)
    discord_token = discord.fetch_token(
        TOKEN_URL,
        client_secret=OAUTH2_CLIENT_SECRET,
        authorization_response=request.url)
    if not discord_token:
        return redirect(url_for('index'))

    # Fetch the user
    user = get_user(discord_token)
    # Generate api_key from user_id
    serializer = JSONWebSignatureSerializer(app.config['SECRET_KEY'])
    api_key = str(serializer.dumps({'user_id': user['id']}))
    # Store api_key
    db.set('user:{}:api_key'.format(user['id']), api_key)
    # Store token
    db.set('user:{}:discord_token'.format(user['id']),
           json.dumps(discord_token))
    # Store api_token in client session
    api_token = {
        'api_key': api_key,
        'user_id': user['id']
    }
    session.permanent = True
    session['api_token'] = api_token
    return redirect(url_for('select_server'))


def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        # Does the user have an api_token?
        api_token = session.get('api_token')
        if api_token is None:
            return redirect(url_for('login'))

        # Does his api_key is in the db?
        user_api_key = db.get('user:{}:api_key'.format(api_token['user_id']))
        if user_api_key != api_token['api_key']:
            return redirect(url_for('logout'))

        return f(*args, **kwargs)
    return wrapper


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

"""
    DISCORD RELATED PARSERS
"""


def typeahead_members(_members):
    members = []
    for m in _members:
        user = {
            'username': m['user']['username']+'#'+m['user']['discriminator'],
            'name': m['user']['username'],
        }
        if m['user']['avatar']:
            user['image'] = 'https://cdn.discordapp.com/"\
                "avatars/{}/{}.jpg'.format(
                m['user']['id'],
                m['user']['avatar']
            )
        else:
            user['image'] = url_for('static', filename='img/no_logo.png')
        members.append(user)
    return members


def get_mention_parser(server_id, members=None):
    _members = members
    if members is None:
        _members = get_guild_members(server_id)
    __members = {}
    for member in _members:
        key = '<@{}>'.format(member['user']['id'])
        __members[key] = '@{}#{}'.format(member['user']['username'],
                                         member['user']['discriminator'])

    pattern = r'(<@[0-9]*>)'

    def repl(k):
        key = k.groups()[0]
        val = __members.get(key)
        if val:
            return val
        return key
    return lambda string: re.sub(pattern, repl, string)


def get_mention_decoder(server_id, members=None):
    _members = members
    if members is None:
        _members = get_guild_members(server_id)
    members = {}
    for member in _members:
        key = member['user']['username']+'#'+member['user']['discriminator']
        members[key] = "<@{}>".format(member['user']['id'])
    pattern = r'@(.*?#[0-9]{4})'

    def repl(k):
        key = k.groups()[0]
        val = members.get(key)
        if val:
            return val
        return key

    return lambda string: re.sub(pattern, repl, string)

"""
    STATIC pages
"""


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/thanks')
@require_auth
def thanks():
    user = get_user(session['api_token'])
    return render_template('thanks.html',
                           points=user['points'])


@app.route('/debug_token')
def debug_token():
    if not session.get('api_token'):
        return jsonify({'error': 'no api_token'})
    token = db.get('user:{}:discord_token'.format(
        session['api_token']['user_id']
    ))
    return token


@app.route('/servers')
@require_auth
def select_server():
    guild_id = request.args.get('guild_id')
    if guild_id:
        return redirect(url_for('dashboard', server_id=int(guild_id)))

    user = get_user(session['api_token'])
    guilds = get_user_guilds(session['api_token'])
    user_servers = sorted(
        get_user_managed_servers(user, guilds),
        key=lambda s: s['name'].lower()
    )
    return render_template('select-server.html',
                           user=user, user_servers=user_servers)


def server_check(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        server_id = kwargs.get('server_id')
        server_ids = db.smembers('servers')

        if str(server_id) not in server_ids:
            url = "https://discordapp.com/oauth2/authorize?&client_id={}"\
                  "&scope=bot&permissions={}&guild_id={}&response_type=code"\
                  "&redirect_uri=http://{}/servers".format(
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
        user = get_user(session['api_token'])
        guilds = get_user_guilds(session['api_token'])
        user_servers = get_user_managed_servers(user, guilds)
        if str(server_id) not in map(lambda g: g['id'], user_servers):
            return redirect(url_for('select_server'))

        return f(*args, **kwargs)
    return wrapper


def my_dash(f):
    # tfw when elixir's |>...
    return require_auth(require_bot_admin(server_check(f)))


def plugin_method(f):
    return my_dash(f)


def plugin_page(plugin_name, buff=None):
    def decorator(f):
        @require_auth
        @require_bot_admin
        @server_check
        @wraps(f)
        def wrapper(server_id):
            user = get_user(session['api_token'])
            if buff:
                not_buff = db.get('buffs:'+str(server_id)+':'+buff) is None
                if not_buff:
                    db.srem('plugins:{}'.format(server_id), plugin_name)
                    return redirect(url_for('shop', server_id=server_id))

            disable = request.args.get('disable')
            if disable:
                db.srem('plugins:{}'.format(server_id), plugin_name)
                return redirect(url_for('dashboard', server_id=server_id))

            db.sadd('plugins:{}'.format(server_id), plugin_name)
            servers = get_user_guilds(session['api_token'])
            server = list(filter(lambda g: g['id'] == str(server_id), servers))
            server = server[0]
            enabled_plugins = db.smembers('plugins:{}'.format(server_id))

            ignored = db.get('user:{}:ignored'.format(user['id']))
            notification = not ignored

            return render_template(
                f.__name__.replace('_', '-') + '.html',
                server=server,
                enabled_plugins=enabled_plugins,
                notification=notification,
                **f(server_id)
            )
        return wrapper

    return decorator


@app.route('/dashboard/<int:server_id>')
@my_dash
def dashboard(server_id):
    user = get_user(session['api_token'])
    guilds = get_user_guilds(session['api_token'])
    server = list(filter(lambda g: g['id'] == str(server_id), guilds))[0]
    enabled_plugins = db.smembers('plugins:{}'.format(server_id))
    ignored = db.get('user:{}:ignored'.format(user['id']))
    notification = not ignored

    buffs_base = 'buffs:'+server['id']+':'
    music_buff = {'name': 'music',
                  'active': db.get(buffs_base+'music')
                  is not None,
                  'remaining': db.ttl(buffs_base+'music')}
    server['buffs'] = [music_buff]
    return render_template('dashboard.html',
                           server=server,
                           enabled_plugins=enabled_plugins,
                           notification=notification)


@app.route('/dashboard/notification/<int:server_id>')
@my_dash
def notification(server_id):
    user = get_user(session['api_token'])
    ignored = db.get('user:{}:ignored'.format(user['id']))
    if ignored:
        db.delete('user:{}:ignored'.format(user['id']))
    else:
        db.set('user:{}:ignored'.format(user['id']), '1')

    return redirect(url_for('dashboard', server_id=server_id))


def get_guild(server_id):
    headers = {'Authorization': 'Bot '+MEE6_TOKEN}
    r = requests.get(API_BASE_URL+'/guilds/{}'.format(server_id),
                     headers=headers)
    if r.status_code == 200:
        return r.json()
    return None


def get_guild_members(server_id):
    headers = {'Authorization': 'Bot '+MEE6_TOKEN}
    members = []
    while len(members) % 1000 == 0:
        r = requests.get(
            API_BASE_URL+'/guilds/{}/members'.format(server_id),
            params={'limit': 1000, 'offset': len(members)},
            headers=headers)
        if r.status_code == 200:
            chunk = r.json()
            members += chunk
        if chunk == []:
            break
    return members


def get_guild_channels(server_id, voice=True, text=True):
    headers = {'Authorization': 'Bot '+MEE6_TOKEN}
    r = requests.get(API_BASE_URL+'/guilds/{}/channels'.format(server_id),
                     headers=headers)
    if r.status_code == 200:
        all_channels = r.json()
        if not voice:
            channels = list(filter(lambda c: c['type'] != 'voice',
                                   all_channels))
        if not text:
            channels = list(filter(lambda c: c['type'] != 'text', all_channels))
        return channels
    return None


"""
    Shop
"""

BUFFS = {'music30': {'name': 'music30',
                     'buff_name': 'music',
                     'fancy_name': 'Music Plugin',
                     'description': 'Enables the music plugin in your server'
                     ' for 30 days.',
                     'price': 300,
                     'duration': 3600*24*30},
         'musicinfinite': {'name': 'musicinfinite',
                           'buff_name': 'music',
                           'fancy_name': 'Infinite Music Plugin',
                           'description': 'Enabled the music plugin in your'
                           ' server for life!',
                           'price': 2500,
                           'duration': -1}}


@app.route('/dashboard/<int:server_id>/shop')
@my_dash
def shop(server_id):
    last_buys = db.lrange('shop:buys', 0, 10) or []
    last_buys = list(map(json.loads, last_buys))
    user = get_user(session['api_token'])

    is_earlybacker = user['id'] in db.smembers('early_backers')
    is_elligible = is_earlybacker and user['id'] not in db.smembers('eb_served')

    guilds = get_user_guilds(session['api_token'])
    server = list(filter(lambda g: g['id'] == str(server_id), guilds))[0]
    enabled_plugins = db.smembers('plugins:{}'.format(server_id))
    ignored = db.get('user:{}:ignored'.format(user['id']))
    notification = not ignored
    return render_template('shop.html',
                           last_buys=last_buys,
                           server=server,
                           is_elligible=is_elligible,
                           enabled_plugins=enabled_plugins,
                           notification=notification)


@app.route('/dashboard/<int:server_id>/buy')
@plugin_method
def buy(server_id):
    item = request.args.get('item')
    if not item or item not in BUFFS.keys():
        return redirect(url_for('index'))
    item = BUFFS[item]
    user = get_user(session['api_token'])

    # EARLY BACKER PROMO
    eb_promo = request.args.get('eb_promo')
    if eb_promo:
        is_earlybacker = user['id'] in db.smembers('early_backers')
        is_elligible = is_earlybacker and user['id'] \
            not in db.smembers('eb_served')
        if not is_elligible:
            return redirect(url_for('index'))
        item_key = 'buffs:'+str(server_id)+':music'
        db.set(item_key, "1")
        db.sadd('eb_served', user['id'])
        flash('Thanks for your purchase!', 'success')
        return redirect(url_for('shop', server_id=server_id))

    if user['points'] < item['price']:
        flash('Sorry you don\'t have enough points to buy that :(', 'warning')
        return redirect(url_for('shop', server_id=server_id))

    item_key = 'buffs:'+str(server_id)+':'+BUFFS[item['name']]['buff_name']
    item_buff = db.get(item_key)
    if not item_buff:
        db.set(item_key, "1")
        if item['duration'] != -1:
            db.expire(item_key, item['duration'])
    else:
        item_buff_ttl = db.ttl(item_key)
        if not item_buff_ttl:
            flash('You already have that buff!', 'warning')
            return redirect(url_for('shop', server_id=server_id))
        else:
            db.set(item_key, "1")
            if item['duration'] != -1:
                db.expire(item_key, item_buff_ttl+item['duration'])

    db.set('user:'+user['id']+':points', user['points']-item['price'])
    flash('Thanks for your purchase!', 'success')
    return redirect(url_for('shop', server_id=server_id))


@app.route('/donate')
@require_auth
def donate():
    return render_template('donate.html')


@app.route('/checkout', methods=['POST'])
@require_auth
def checkout():
    donation_amount = request.form.get('amount')
    if not donation_amount:
        return redirect(url_for('index'))

    donation_amount = "{0:.2f}".format(float(donation_amount))
    payer = {"payment_method": "paypal"}
    items = [{"name": "Mee6 Contribution",
              "price": donation_amount,
              "currency": "EUR",
              "quantity": "1"}]
    amount = {"total": donation_amount,
              "currency": "EUR"}
    description = "Contribute to the Mee6 Bot project!"
    redirect_urls = {"return_url": "http://" + DOMAIN +
                     url_for('checkout_confirm') + "?success=true",
                     "cancel_url": "http://" + DOMAIN + url_for('index')}
    payment = paypalrestsdk.Payment({"intent": "sale",
                                     "payer": payer,
                                     "redirect_urls": redirect_urls,
                                     "transactions": [{"item_list": {"items":
                                                                     items},
                                                       "amount": amount,
                                                       "description":
                                                       description}]})
    if payment.create():
        for link in payment.links:
            if link['method'] == "REDIRECT":
                return redirect(link["href"])

    return redirect(url_for('index'))


@app.route("/checkout-confirm")
@require_auth
def checkout_confirm():
    if not request.args.get('success'):
        return redirect(url_for('index'))

    user = get_user(session['api_token'])
    payment = paypalrestsdk.Payment.find(request.args.get('paymentId'))
    if payment.execute({"payer_id": request.args.get('PayerID')}):
        amount = float(payment.transactions[0]["amount"]["total"])
        points = int(amount * 100)
        new_points = user['points'] + points
        db.set('user:'+user['id']+':points', new_points)
        return redirect(url_for('thanks'))
    else:
        return redirect(url_for('index'))

"""
    Command Plugin
"""


@app.route('/dashboard/<int:server_id>/commands')
@plugin_page('Commands')
def plugin_commands(server_id):
    commands = []
    commands_names = db.smembers('Commands.{}:commands'.format(server_id))
    _members = get_guild_members(server_id)
    mention_parser = get_mention_parser(server_id, _members)
    members = typeahead_members(_members)
    for cmd in commands_names:
        message = db.get('Commands.{}:command:{}'.format(server_id, cmd))
        message = mention_parser(message)
        command = {
            'name': cmd,
            'message': message
        }
        commands.append(command)
    commands = sorted(commands, key=lambda k: k['name'])
    return {
        'guild_members': members,
        'commands': commands
    }


@app.route('/dashboard/<int:server_id>/commands/add', methods=['POST'])
@plugin_method
def add_command(server_id):
    cmd_name = request.form.get('cmd_name', '')
    cmd_message = request.form.get('cmd_message', '')
    mention_decoder = get_mention_decoder(server_id)
    cmd_message = mention_decoder(cmd_message)

    edit = cmd_name in db.smembers('Commands.{}:commands'.format(server_id))

    cb = url_for('plugin_commands', server_id=server_id)
    if len(cmd_name) == 0 or len(cmd_name) > 15:
        flash('A command name should be between 1 and 15 character long !',
              'danger')
    elif not edit and not re.match("^[A-Za-z0-9_-]*$", cmd_name):
        flash('A command name should only contain '
              'letters from a to z, numbers, _ or -', 'danger')
    elif len(cmd_message) == 0 or len(cmd_message) > 2000:
        flash('A command message should be between '
              '1 and 2000 character long !', 'danger')
    else:
        if not edit:
            cmd_name = '!'+cmd_name
        db.sadd('Commands.{}:commands'.format(server_id), cmd_name)
        db.set('Commands.{}:command:{}'.format(server_id, cmd_name),
               cmd_message)
        if edit:
            flash('Command {} edited !'.format(cmd_name), 'success')
        else:
            flash('Command {} added !'.format(cmd_name), 'success')

    return redirect(cb)


@app.route('/dashboard/<int:server_id>/commands/<string:command>/delete')
@plugin_method
def delete_command(server_id, command):
    db.srem('Commands.{}:commands'.format(server_id), command)
    db.delete('Commands.{}:command:{}'.format(server_id, command))
    flash('Command {} deleted !'.format(command), 'success')
    return redirect(url_for('plugin_commands', server_id=server_id))

"""
    Help Plugin
"""


@app.route('/dashboard/<int:server_id>/help')
@plugin_page('Help')
def plugin_help(server_id):
    if db.get('Help.{}:whisp'.format(server_id)):
        whisp = "1"
    else:
        whisp = None

    return {
        "whisp": whisp
    }


@app.route('/dashboard/<int:server_id>/update_help', methods=['POST'])
@plugin_method
def update_help(server_id):
    whisp = request.form.get('whisp')
    db.delete('Help.{}:whisp'.format(server_id))
    if whisp:
        db.set('Help.{}:whisp'.format(server_id), "1")
    flash('Plugin updated!', 'success')
    return redirect(url_for('plugin_help', server_id=server_id))

"""
    Levels Plugin
"""


@app.route('/dashboard/<int:server_id>/levels')
@plugin_page('Levels')
def plugin_levels(server_id):
    initial_announcement = 'GG {player}, '\
        'you just advanced to **level {level}** !'
    announcement_enabled = db.get('Levels.{}:announcement_enabled'.format(
        server_id))
    whisp = db.get('Levels.{}:whisp'.format(server_id))
    announcement = db.get('Levels.{}:announcement'.format(server_id))
    if announcement is None:
        db.set('Levels.{}:announcement'.format(server_id), initial_announcement)
        db.set('Levels.{}:announcement_enabled'.format(server_id), '1')
        announcement_enabled = '1'

    announcement = db.get('Levels.{}:announcement'.format(server_id))

    db_banned_roles = db.smembers('Levels.{}:banned_roles'.format(server_id))\
        or []
    guild = get_guild(server_id)
    guild_roles = guild['roles']
    banned_roles = list(filter(
        lambda r: r['name'] in db_banned_roles or r['id'] in db_banned_roles,
        guild_roles
    ))
    reward_roles = list(map(
        lambda r: {'name': r['name'],
                   'id': r['id'],
                   'color': hex(r['color']).split('0x')[1],
                   'level': int(db.get('Levels.{}:reward:{}'.format(
                       server_id,
                       r['id'])) or 0)
                   },
        guild_roles
    )
    )
    cooldown = db.get('Levels.{}:cooldown'.format(server_id)) or 0
    return {
        'announcement': announcement,
        'announcement_enabled': announcement_enabled,
        'banned_roles': banned_roles,
        'guild_roles': guild_roles,
        'reward_roles': reward_roles,
        'cooldown': cooldown,
        'whisp': whisp
    }


@app.route('/dashboard/<int:server_id>/levels/update', methods=['POST'])
@plugin_method
def update_levels(server_id):
    banned_roles = request.form.get('banned_roles').split(',')
    announcement = request.form.get('announcement')
    enable = request.form.get('enable')
    whisp = request.form.get('whisp')
    cooldown = request.form.get('cooldown')

    for k, v in request.form.items():
        if k.startswith('rolereward_'):
            db.set('Levels.{}:reward:{}'.format(
                server_id,
                k.split('_')[1]),
                v)

    try:
        cooldown = int(cooldown)
    except ValueError:
        flash('The cooldown that you provided isn\'t an integer!', 'warning')
        return redirect(url_for('plugin_levels', server_id=server_id))

    if announcement == '' or len(announcement) > 2000:
        flash('The level up announcement'
              ' could not be empty or have 2000+ characters.', 'warning')
    else:
        db.set('Levels.{}:announcement'.format(server_id), announcement)
        db.set('Levels.{}:cooldown'.format(server_id), cooldown)

        db.delete('Levels.{}:banned_roles'.format(server_id))
        if len(banned_roles) > 0:
            db.sadd('Levels.{}:banned_roles'.format(server_id), *banned_roles)

        if enable:
            db.set('Levels.{}:announcement_enabled'.format(server_id), '1')
        else:
            db.delete('Levels.{}:announcement_enabled'.format(server_id))

        if whisp:
            db.set('Levels.{}:whisp'.format(server_id), '1')
        else:
            db.delete('Levels.{}:whisp'.format(server_id))

        flash('Settings updated ;) !', 'success')

    return redirect(url_for('plugin_levels', server_id=server_id))


def get_level_xp(n):
    return 5*(n**2)+50*n+100


def get_level_from_xp(xp):
    remaining_xp = int(xp)
    level = 0
    while remaining_xp >= get_level_xp(level):
        remaining_xp -= get_level_xp(level)
        level += 1
    return level


@app.route('/levels/<int:server_id>')
def levels(server_id):
    is_admin = False
    if session.get('api_token'):
        user_servers = get_user_managed_servers(
            get_user(session['api_token']),
            get_user_guilds(session['api_token'])
        )
        is_admin = str(server_id) in list(map(lambda s: s['id'], user_servers))

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

    guild = get_guild(server_id)
    roles = guild['roles']
    from collections import defaultdict
    reward_roles = defaultdict(list)
    reward_levels = []
    for role in roles:
        level = int(db.get('Levels.{}:reward:{}'.format(
            server_id,
            role['id'])) or 0)
        if level == 0:
            continue
        reward_levels.append(level)
        role['color'] = hex(role['color']).split('0x')[1]
        reward_roles[level].append(
            role
        )
    reward_levels = list(sorted(set(reward_levels)))

    _players = db.sort('Levels.{}:players'.format(server_id),
                       by='Levels.{}:player:*:xp'.format(server_id),
                       get=[
                           'Levels.{}:player:*:xp'.format(server_id),
                           'Levels.{}:player:*:name'.format(server_id),
                           'Levels.{}:player:*:avatar'.format(server_id),
                           'Levels.{}:player:*:discriminator'.format(server_id),
                           '#'
                       ],
                       start=0,
                       num=100,
                       desc=True)

    players = []
    for i in range(0, len(_players), 5):
        total_xp = int(_players[i])
        lvl = get_level_from_xp(total_xp)
        lvl_xp = get_level_xp(lvl)
        x = 0
        for l in range(0, lvl):
            x += get_level_xp(l)
        remaining_xp = int(total_xp - x)
        player = {
            'total_xp': int(_players[i]),
            'xp': remaining_xp,
            'lvl_xp': lvl_xp,
            'lvl': lvl,
            'xp_percent': floor(100*(remaining_xp)/lvl_xp),
            'name': _players[i+1],
            'avatar': _players[i+2],
            'discriminator': _players[i+3],
            'id': _players[i+4]
        }
        players.append(player)
    return render_template(
        'levels.html',
        small_title="Leaderboard",
        is_admin=is_admin,
        players=players,
        server=server,
        reward_roles=reward_roles,
        reward_levels=reward_levels,
        title="{} leaderboard - Mee6 bot".format(server['name'])
    )


@app.route('/levels/reset/<int:server_id>/<int:player_id>')
@plugin_method
def reset_player(server_id, player_id):
    db.delete('Levels.{}:player:{}:xp'.format(server_id, player_id))
    db.delete('Levels.{}:player:{}:lvl'.format(server_id, player_id))
    db.srem('Levels.{}:players'.format(server_id), player_id)
    return redirect(url_for('levels', server_id=server_id))


@app.route('/levels/reset_all/<int:server_id>')
@plugin_method
def reset_all_players(server_id):
    for player_id in db.smembers('Levels.{}:players'.format(server_id)):
        db.delete('Levels.{}:player:{}:xp'.format(server_id, player_id))
        db.delete('Levels.{}:player:{}:lvl'.format(server_id, player_id))
        db.srem('Levels.{}:players'.format(server_id), player_id)
    return redirect(url_for('levels', server_id=server_id))

"""
    Welcome Plugin
"""


@app.route('/dashboard/<int:server_id>/welcome')
@plugin_page('Welcome')
def plugin_welcome(server_id):
    _members = get_guild_members(server_id)
    mention_parser = get_mention_parser(server_id, _members)
    members = typeahead_members(_members)

    initial_welcome = '{user}, Welcome to **{server}**!'\
        ' Have a great time here :wink: !'
    initial_gb = '**{user}** just left **{server}**. Bye bye **{user}**...'
    welcome_message = db.get('Welcome.{}:welcome_message'.format(server_id))
    private = db.get('Welcome.{}:private'.format(server_id)) or None
    gb_message = db.get('Welcome.{}:gb_message'.format(server_id))
    db_welcome_channel = db.get('Welcome.{}:channel_name'.format(server_id))
    guild_channels = get_guild_channels(server_id, voice=False)
    welcome_channel = None
    for channel in guild_channels:
        if channel['name'] == db_welcome_channel or \
                channel['id'] == db_welcome_channel:
            welcome_channel = channel
            break
    if welcome_message is None:
        db.set('Welcome.{}:welcome_message'.format(server_id), initial_welcome)
        welcome_message = initial_welcome
    if gb_message is None:
        db.set('Welcome.{}:gb_message'.format(server_id), initial_gb)
        gb_message = initial_gb

    welcome_message = mention_parser(welcome_message)
    gb_message = mention_parser(gb_message)

    return {
        'guild_members': members,
        'welcome_message': welcome_message,
        'private': private,
        'gb_message': gb_message,
        'guild_channels': guild_channels,
        'welcome_channel': welcome_channel
    }


@app.route('/dashboard/<int:server_id>/welcome/update', methods=['POST'])
@plugin_method
def update_welcome(server_id):

    mention_decoder = get_mention_decoder(server_id)

    welcome_message = request.form.get('welcome_message')
    welcome_message = mention_decoder(welcome_message)
    private = request.form.get('private')

    gb_message = request.form.get('gb_message')
    gb_message = mention_decoder(gb_message)

    channel = request.form.get('channel')

    if private:
        db.set('Welcome.{}:private'.format(server_id), "1")
    else:
        db.delete('Welcome.{}:private'.format(server_id))

    if welcome_message == '' or len(welcome_message) > 2000:
        flash('The welcome message cannot be empty or have 2000+ characters.',
              'warning')
    else:
        if gb_message == '' or len(gb_message) > 2000:
            flash('The good bye message cannot be empty'
                  ' or have 2000+ characters.', 'warning')
        else:
            db.set('Welcome.{}:welcome_message'.format(server_id),
                   welcome_message)
            db.set('Welcome.{}:gb_message'.format(server_id), gb_message)
            db.set('Welcome.{}:channel_name'.format(server_id), channel)
            flash('Settings updated ;) !', 'success')

    return redirect(url_for('plugin_welcome', server_id=server_id))

"""
    Animu and Mango Plugin
"""


@app.route('/dashboard/<int:server_id>/animu')
@plugin_page('AnimuAndMango')
def plugin_animu(server_id):
    return {}

"""
    Git Plugin
"""


@app.route('/dashboard/<int:server_id>/git')
@plugin_page('Git')
def plugin_git(server_id):
    return {}

"""
    Logs Plugin
"""


@app.route('/dashboard/<int:server_id>/logs')
@plugin_page('Logs')
def plugin_logs(server_id):
    logs = db.lrange('Logs.{}:logs'.format(server_id), start=0, end=100)

    return {
        'logs': logs
    }


@app.route('/logs/<int:server_id>')
def logs_homepage(server_id):
    json = request.args.get('json', None)
    servers = db.smembers('servers')
    servers = [server for server in servers
               if 'Logs' in db.smembers('plugins:{}'.format(server))]

    if str(server_id) not in servers:
        return redirect(url_for('index'))
    server = {
        'id': server_id,
        'icon': db.get('server:{}:icon'.format(server_id)),
        'name': db.get('server:{}:name'.format(server_id))
    }
    payload = []
    dates = list(db.smembers('Logs.{}:message_logs'.format(server_id)))
    dates = map(lambda d: d.split('-'), dates)
    dates = map(lambda d: (int(d[0]), int(d[1]), int(d[2])), dates)
    dates = sorted(dates, reverse=True)
    dates = map(lambda d: (str(d[0]), str(d[1]), str(d[2])), dates)
    dates = list(map(lambda d: "-".join(d), dates))
    for date in dates:
        info = {
                'dt': date,
                'channels': list(db.smembers('Logs.{}:message_logs:{}'.format(
                    server_id, date)))
                }
        payload.append(info)
    if json is not None:
        return jsonify({
            'number': len(payload),
            'items': payload
            })
    else:
        return render_template('logs-homepage.html',
                               payload=payload, server=server)


@app.route('/message_logs/<int:server_id>/<string:dt>/<string:channel>')
def message_logs(server_id, dt, channel):
    asc = request.args.get('asc')

    json_format = request.args.get('json', None)
    txt = request.args.get('txt', None)
    servers = db.smembers('servers')
    servers = [server for server in servers
               if 'Logs' in db.smembers('plugins:{}'.format(
                   server
               ))]
    if str(server_id) not in servers:
        return redirect(url_for('index'))
    server = {
        'id': server_id,
        'icon': db.get('server:{}:icon'.format(server_id)),
        'name': db.get('server:{}:name'.format(server_id))
    }
    mongo_db = mongo.logs
    collection = mongo_db['{}:{}:{}'.format(server['id'], dt, channel)]
    messages = [message for message in collection.find({}, {'_id': 0})]
    if asc != "1":
        messages = list(reversed(messages))

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
                txt += " "
                txt += "|".join(list(map(lambda a: a['url'],
                                         msg['attachments'])))
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
        messages = list(map(
            lambda m: {**m, 'date': datetime.datetime.fromtimestamp(
                m['timestamp']
            ).strftime('%H:%M:%S')},
            messages))
        return render_template('message-logs.html',
                               server=server,
                               channel=channel,
                               messages=messages,
                               dt=dt)

"""
    Streamers Plugin
"""


@app.route('/dashboard/<int:server_id>/streamers')
@plugin_page('Streamers')
def plugin_streamers(server_id):
    streamers = db.smembers('Streamers.{}:streamers'.format(server_id))
    beam_streamers = db.smembers('Streamers.{}:beam_streamers'.format(
        server_id))
    hitbox_streamers = db.smembers('Streamers.{}:hitbox_streamers'.format(
        server_id))
    streamers = ','.join(streamers)
    beam_streamers = ','.join(beam_streamers)
    hitbox_streamers = ','.join(hitbox_streamers)
    db_announcement_channel = db.get('Streamers.{}:announcement_channel'.format(
        server_id))
    guild_channels = get_guild_channels(server_id, voice=False)
    announcement_channel = None
    for channel in guild_channels:
        if channel['name'] == db_announcement_channel \
                or channel['id'] == db_announcement_channel:
            announcement_channel = channel
            break
    announcement_msg = db.get('Streamers.{}:announcement_msg'.format(server_id))
    if announcement_msg is None:
        announcement_msg = "Hey @everyone! {streamer} is now"\
            " live on {link} ! Go check it out :wink:!"
        db.set('Streamers.{}:announcement_msg'.format(server_id),
               announcement_msg)

    return {
        'announcement_channel': announcement_channel,
        'guild_channels': guild_channels,
        'announcement_msg': announcement_msg,
        'streamers': streamers,
        'hitbox_streamers': hitbox_streamers,
        'beam_streamers': beam_streamers
    }


@app.route('/dashboard/<int:server_id>/update_streamers', methods=['POST'])
@plugin_method
def update_streamers(server_id):
    announcement_channel = request.form.get('announcement_channel')
    announcement_msg = request.form.get('announcement_msg')
    if announcement_msg == "":
        flash('The announcement message should not be empty!', 'warning')
        return redirect(url_for('plugin_streamers', server_id=server_id))

    streamers = request.form.get('streamers').split(',')
    beam_streamers = request.form.get('beam_streamers').split(',')
    hitbox_streamers = request.form.get('hitbox_streamers').split(',')
    db.set('Streamers.{}:announcement_channel'.format(server_id),
           announcement_channel)
    db.set('Streamers.{}:announcement_msg'.format(server_id), announcement_msg)
    db.delete('Streamers.{}:streamers'.format(server_id))
    db.delete('Streamers.{}:beam_streamers'.format(server_id))
    db.delete('Streamers.{}:twitch_streamers'.format(server_id))
    for streamer in streamers:
        if streamer != "":
            db.sadd('Streamers.{}:streamers'.format(server_id),
                    streamer.replace(' ', '_').lower())
    for streamer in beam_streamers:
        if streamer != "":
            db.sadd('Streamers.{}:beam_streamers'.format(server_id),
                    streamer.replace(' ', '_').lower())
    for streamer in hitbox_streamers:
        if streamer != "":
            db.sadd('Streamers.{}:hitbox_streamers'.format(server_id),
                    streamer.replace(' ', '_').lower())

    flash('Configuration updated with success!',
          'success')
    return redirect(url_for('plugin_streamers', server_id=server_id))

"""
    Reddit Plugin
"""


@app.route('/dashboard/<int:server_id>/reddit')
@plugin_page('Reddit')
def plugin_reddit(server_id):
    subs = db.smembers('Reddit.{}:subs'.format(server_id))
    subs = ','.join(subs)
    guild_channels = get_guild_channels(server_id, voice=False)
    display_channel = db.get('Reddit.{}:display_channel'.format(server_id))
    return {
        'subs': subs,
        'display_channel': display_channel,
        'guild_channels': guild_channels,
    }


@app.route('/dashboard/<int:server_id>/update_reddit', methods=['POST'])
@plugin_method
def update_reddit(server_id):
    display_channel = request.form.get('display_channel')
    subs = request.form.get('subs').split(',')
    db.set('Reddit.{}:display_channel'.format(server_id), display_channel)
    db.delete('Reddit.{}:subs'.format(server_id))
    for sub in subs:
        if sub != "":
            db.sadd('Reddit.{}:subs'.format(server_id), sub.lower())

    flash('Configuration updated with success!', 'success')
    return redirect(url_for('plugin_reddit', server_id=server_id))

"""
    Moderator Plugin
"""


@app.route('/dashboard/<int:server_id>/moderator')
@plugin_page('Moderator')
def plugin_moderator(server_id):
    db_moderator_roles = db.smembers('Moderator.{}:roles'.format(server_id))\
        or []
    guild = get_guild(server_id)
    guild_roles = guild['roles']
    moderator_roles = list(filter(
        lambda r: r['name'] in db_moderator_roles or
        r['id'] in db_moderator_roles,
        guild_roles
    ))
    clear = db.get('Moderator.{}:clear'.format(server_id))
    banned_words = db.get('Moderator.{}:banned_words'.format(server_id))
    slowmode = db.get('Moderator.{}:slowmode'.format(server_id))
    mute = db.get('Moderator.{}:mute'.format(server_id))
    return {
        'moderator_roles': moderator_roles,
        'guild_roles': guild_roles,
        'clear': clear,
        'banned_words': banned_words or '',
        'slowmode': slowmode,
        'mute': mute
    }


@app.route('/dashboard/<int:server_id>/update_moderator', methods=['POST'])
@plugin_method
def update_moderator(server_id):
    moderator_roles = request.form.get('moderator_roles').split(',')
    banned_words = request.form.get('banned_words')
    db.delete('Moderator.{}:roles'.format(server_id))
    for role in moderator_roles:
        if role != "":
            db.sadd('Moderator.{}:roles'.format(server_id), role)

    db.delete('Moderator.{}:clear'.format(server_id))
    db.delete('Moderator.{}:slowmode'.format(server_id))
    db.delete('Moderator.{}:mute'.format(server_id))
    db.set('Moderator.{}:banned_words'.format(server_id), banned_words)

    clear = request.form.get('clear')
    slowmode = request.form.get('slowmode')
    mute = request.form.get('mute')

    if clear:
        db.set('Moderator.{}:clear'.format(server_id), '1')
    if slowmode:
        db.set('Moderator.{}:slowmode'.format(server_id), '1')
    if mute:
        db.set('Moderator.{}:mute'.format(server_id), '1')

    flash('Configuration updated ;)!', 'success')

    return redirect(url_for('plugin_moderator', server_id=server_id))

"""
    Music Plugin
"""


@app.route('/dashboard/<int:server_id>/music')
@plugin_page('Music', buff="music")
def plugin_music(server_id):
    db_allowed_roles = db.smembers('Music.{}:allowed_roles'.format(server_id))\
        or []
    db_requesters_roles = db.smembers(
        'Music.{}:requesters_roles'.format(server_id)
    ) or []
    guild = get_guild(server_id)
    guild_roles = guild['roles']
    allowed_roles = filter(
        lambda r: r['name'] in db_allowed_roles or r['id'] in db_allowed_roles,
        guild_roles
    )
    requesters_roles = filter(
        lambda r: r['id'] in db_requesters_roles,
        guild_roles
    )
    return {
        'guild_roles': guild_roles,
        'allowed_roles': list(allowed_roles),
        'requesters_roles': list(requesters_roles)
    }


@app.route('/dashboard/<int:server_id>/update_music', methods=['POST'])
@plugin_method
def update_music(server_id):
    allowed_roles = request.form.get('allowed_roles', '').split(',')
    requesters_roles = request.form.get('requesters_roles', '').split(',')
    print(allowed_roles)
    print(requesters_roles)
    db.delete('Music.{}:allowed_roles'.format(server_id))
    db.delete('Music.{}:requesters_roles'.format(server_id))
    for role in allowed_roles:
        db.sadd('Music.{}:allowed_roles'.format(server_id), role)
    for role in requesters_roles:
        db.sadd('Music.{}:requesters_roles'.format(server_id), role)
    flash('Configuration updated ;)!', 'success')

    return redirect(url_for('plugin_music', server_id=server_id))


@app.route('/request_playlist/<int:server_id>')
def request_playlist(server_id):
    if 'Music' not in db.smembers('plugins:{}'.format(server_id)):
        return redirect(url_for('index'))

    playlist = db.lrange('Music.{}:request_queue'.format(server_id), 0, -1)
    playlist = list(map(lambda v: json.loads(v), playlist))

    is_admin = False
    if session.get('api_token'):
        user_servers = get_user_managed_servers(
            get_user(session['api_token']),
            get_user_guilds(session['api_token'])
        )
        is_admin = str(server_id) in list(map(lambda s: s['id'], user_servers))

    server = {
        'id': server_id,
        'icon': db.get('server:{}:icon'.format(server_id)),
        'name': db.get('server:{}:name'.format(server_id))
    }

    return render_template('request-playlist.html', playlist=playlist,
                           server=server, is_admin=is_admin)


@app.route('/delete_request/<int:server_id>/<int:pos>')
@plugin_method
def delete_request(server_id, pos):
    playlist = db.lrange('Music.{}:request_queue'.format(server_id), 0, -1)
    if pos < len(playlist):
        del playlist[pos]
        db.delete('Music.{}:request_queue'.format(server_id))
        for vid in playlist:
            db.rpush('Music.{}:request_queue'.format(server_id), vid)
    return redirect(url_for('request_playlist', server_id=server_id))


@app.before_first_request
def setup_logging():
    # In production mode, add log handler to sys.stderr.
    app.logger.addHandler(logging.StreamHandler())
    app.logger.setLevel(logging.INFO)


if __name__ == '__main__':
    app.debug = True
    app.run()
