extern crate discord;
extern crate redis;
extern crate rustc_serialize;

use std::env;
use std::thread;
use std::process::exit;
use discord::{Discord, State, ChannelRef, Connection};
use discord::model::{Event, ChannelType};
use redis::Commands;
use rustc_serialize::json;

///////////////////
//// REDIS QUEUE
//////////////////

#[derive(RustcDecodable, RustcEncodable)]
struct MusicRequester {
    name: String,
    discriminator: String,
    avatar: String
}

#[derive(RustcDecodable, RustcEncodable)]
struct Music {
    title: String,
    url: String,
    thumbnail: String,
    addedBy: MusicRequester
}

struct MusicBot {
    state: State,
    client: Discord,
    connection: Connection,
    redis: redis::Connection
}

fn queue_up(rcon: &redis::Connection, music: &Music, guild_id:&discord::model::ServerId) {
    let json_music = json::encode(music).unwrap();
    let key = format!("Music.{}:request_queue", guild_id.0);
    let _ : () = rcon.rpush(key, json_music).unwrap();
}

fn pop_out(rcon: &redis::Connection, guild_id:&discord::model::ServerId) -> Music {
    let key = format!("Music.{}:request_queue", guild_id.0);
    let json_music : String = rcon.lpop(key).unwrap();
    let music : Music = json::decode(&json_music).unwrap();
    music
}

///////////////////////////
//// PERMS & PLUGIN CHECKS
//////////////////////////

fn is_music_enabled(rcon: &redis::Connection, guild_id:&discord::model::ServerId) -> bool {
    let key = format!("plugins:{}", guild_id.0);
    let plugin_enabled : bool = rcon.sismember(key, "Music").unwrap();
    let key = format!("buffs:{}:music", guild_id.0);
    let buff : bool = rcon.exists(key).unwrap();

    return buff && plugin_enabled
}

fn is_member_requester(rcon: &redis::Connection, guild_id:&discord::model::ServerId, user_id : &discord::model::UserId) -> bool {
   true 
}

fn is_member_moderator(rcon: &redis::Connection, guild_id:&discord::model::ServerId, user_id : &discord::model::UserId) -> bool {
   true 
}

/////////////////////
//// CMDS HANDLING
////////////////////

fn handle_join(bot : &mut MusicBot, message : &discord::model::Message, server : &discord::model::LiveServer, channel : &discord::model::PublicChannel) {
    let voice = bot.connection.voice(server.id);
    let voice_channel = voice.current_channel();
    let allowed = match voice_channel {
        Some(ChannelId) => {
            is_member_moderator(&bot.redis, &server.id, &message.author.id)
        }
        None => {
            true    
        }
    };
    if !allowed {
        let response = "You don't have the permission to use that command :frowning:...";
        bot.client.send_message(&channel.id, &response, "", false);
        return
    }
    
    let mut user_voice_channel_id = discord::model::ChannelId(0);
    let connected : bool = match bot.state.find_voice_user(message.author.id) {
        Some((ServerId, ChannelId)) => {
            user_voice_channel_id = ChannelId;
            ServerId == server.id
        }
        None => {
            false
        }
    };
    if !connected {
        let response = "You aren't connected to any voice channel :frowning:...";
        bot.client.send_message(&message.channel_id, &response, "", false);
        return
    }

    voice.connect(user_voice_channel_id);
    let response = "Connecting to voice channel...";
    bot.client.send_message(&message.channel_id, &response, "", false);
}

fn handle_add(bot : &mut MusicBot, message : &discord::model::Message, server : &discord::model::LiveServer, channel : &discord::model::PublicChannel) {
    println!("received add");
}

fn handle_play(bot : &mut MusicBot, message : &discord::model::Message, server : &discord::model::LiveServer, channel : &discord::model::PublicChannel) {
    println!("received play");
}

fn handle_next(bot : &mut MusicBot, message : &discord::model::Message, server : &discord::model::LiveServer, channel : &discord::model::PublicChannel) {
    println!("received next");
}

fn handle_playlist(bot : &mut MusicBot, message : &discord::model::Message, server : &discord::model::LiveServer, channel : &discord::model::PublicChannel) {
    println!("received playlist");
}

fn handle_leave(bot : &mut MusicBot, message : &discord::model::Message, server : &discord::model::LiveServer, channel : &discord::model::PublicChannel) {
    println!("received leave");
}

pub fn main() {
    let discord = Discord::from_bot_token(&env::var("MEE6_TOKEN").expect("Bad DISCORD_TOKEN").as_str()).expect("Login failed");

    let (mut connection, ready) = discord.connect().expect("connect failed");
    println!("Connected as {} to {} servers", ready.user.username,  ready.servers.len());
    let mut state = State::new(ready);

    let redis_client = redis::Client::open("redis://127.0.0.1/").unwrap();
    let rcon = redis_client.get_connection().unwrap();

    let mut bot = MusicBot{client: discord, redis: rcon, state: state, connection: connection}; 
    loop {
        let event = match bot.connection.recv_event() {
            Ok(event) => event,
            Err(err) => {
                println!("Websocket connection dropped");
                exit(1);
            },
        };
        bot.state.update(&event);

        match event {
            Event::MessageCreate(message) => {
                let channel = &bot.state.find_channel(&message.channel_id);
                match channel {
                    Some(ChannelRef::Public(server, channel)) => {
                        if is_music_enabled(&bot.redis, &server.id) {
                            let mut split = message.content.split(" ");
                            let first_word = split.next().unwrap_or("");
                            
                            match first_word {
                                "!join" => {handle_join(&mut bot, &message, &server, &channel);}
                                "!add" => {handle_add(&mut bot, &message, &server, &channel);}
                                "!play" => {handle_play(&mut bot, &message, &server, &channel);}
                                "!next" => {handle_next(&mut bot, &message, &server, &channel);}
                                "!playlist" => {handle_playlist(&mut bot, &message, &server, &channel);}
                                "!leave" => {handle_leave(&mut bot, &message, &server, &channel);}
                                _ => {}
                            }
                        }
                    }
                    _ => {}

                }
                
            },
            _ => {},
        }
    }
}
