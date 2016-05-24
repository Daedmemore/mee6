extern crate discord;
extern crate redis;
extern crate rustc_serialize;

use std::env;
use std::process::exit;
use discord::{Discord, State};
use discord::model::Event;
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

fn queue_up(rcon: &redis::Connection, music: &Music, guild_id:&String) {
    let json_music = json::encode(music).unwrap();
    let key = format!("Music.{}:request_queue", guild_id);
    let _ : () = rcon.rpush(key, json_music).unwrap();
}

fn pop_out(rcon: &redis::Connection, guild_id:&String) -> Music {
    let key = format!("Music.{}:request_queue", guild_id);
    let json_music : String = rcon.lpop(key).unwrap();
    let music : Music = json::decode(&json_music).unwrap();
    music
}

///////////////////////////
//// PERMS & PLUGIN CHECKS
//////////////////////////

fn is_music_enabled(rcon: &redis::Connection, guild_id:&String) -> bool {
    let key = format!("plugins:{}", guild_id);
    let plugins : Vec<String> = rcon.smembers(key).unwrap();
    let key = format!("buffs:{}:music", guild_id);
    let buff : String = rcon.get(key).unwrap();
    //return (("Music" in plugins) && (buff != ()));
    true
}

fn is_member_requester(rcon: &redis::Connection, guild_id:&String, member_id:&str) -> bool {
   true 
}

fn is_member_moderator(rcon: &redis::Connection, guild_id:&String, member_id:&str) -> bool {
   true 
}

/////////////////////
//// CMDS HANDLING
////////////////////

fn handle_add(message : &discord::model::Message) {
    println!("received add");
}

fn handle_play(message : &discord::model::Message) {
    println!("received play");
}

fn handle_next(message : &discord::model::Message) {
    println!("received next");
}

fn handle_playlist(message : &discord::model::Message) {
    println!("received playlist");
}

fn handle_leave(message : &discord::model::Message) {
    println!("received leave");
}

pub fn main() {
    let token = &env::var("MEE6_TOKEN");
    let discord = Discord::from_bot_token(token.expect("Bad DISCORD_TOKEN").as_str()).expect("Login failed");

    let (mut connection, ready) = discord.connect().expect("connect failed");
    println!("Connected as {} to {} servers", ready.user.username,  ready.servers.len());
    let mut state = State::new(ready);

    let client = redis::Client::open("redis://127.0.0.1/").unwrap();
    let rcon = client.get_connection().unwrap();
    

    loop {
        let event = match connection.recv_event() {
            Ok(event) => event,
            Err(err) => {
                println!("Websocket connection dropped");
                exit(1);
            },
        };
        state.update(&event);

        match event {
            Event::MessageCreate(message) => {
                if is_music_enabled(&rcon, &message.server.id) {
                    let mut split = message.content.split(" ");
                    let first_word = split.next().unwrap_or("");
                    
                    match first_word {
                        "!add" => handle_add(&message),
                        "!play" => handle_play(&message),
                        "!next" => handle_next(&message),
                        "!playlist" => handle_playlist(&message),
                        "!leave" => handle_leave(&message),
                    }
                }
            },
            _ => {},
        }
    }
}
