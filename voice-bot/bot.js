"use strict"

var redisURL = process.env.REDIS_URL,
    redis = require('redis'),
    redisClient = redis.createClient(redisURL),
    ytdl = require('ytdl-core'),
    apiKey = process.env.GOOGLE_API_KEY,
    request = require('request'),
    shard = process.env.SHARD || 0,
    shard_count = process.env.SHARD_COUNT || 0,
    threads = process.env.THREADS || 1,
    compression_level = process.env.COMPRESSION_LEVEL || 7,
    youtubedl = require('youtube-dl');
var utils = require('./utils');

var Discordie = require("discordie");
var Events = Discordie.Events

shard = parseInt(shard);
shard_count = parseInt(shard_count);
var options = {};
if (shard_count!=0) {
  options = {
    shardId: shard,
    shardCount: shard_count,
  }
}

var client = new Discordie(options);
client.Messages.setMessageLimit(50);
client.connect({token: process.env.MEE6_TOKEN});


client.Dispatcher.on(Events.GATEWAY_READY, e => {
  console.log("Connected as: " + client.User.username + " to " + client.Guilds.length + " guilds");
});

let isAllowed = (member, cb) => {
  var vc = member.getVoiceChannel();
  if (!vc) {
    cb(false);
  }
  if (member.can(Discordie.Permissions.General.MANAGE_GUILD, member.guild)) {
    cb(true);
    return;
  }
  redisClient.smembers('Music.'+member.guild.id+':allowed_roles', (err, roles) => {
    if (roles.indexOf("@everyone") > -1){
      cb(true);
      return;
    }
    for (var role of member.roles){
      if (roles.indexOf(role.name) > -1 || roles.indexOf(role.id) > -1){
        cb(true);
        return;
      }
    }
    cb(false);
  });
};

let queueUp = (music, message) => {
  var guild = message.guild;
  utils.isMusicEnabled(guild, (musicEnabled) => {
    if (!musicEnabled)
      return;
    music.addedBy = {
      name: message.author.username,
      discriminator: message.author.discriminator,
      avatar: message.author.avatarURL
    };
    redisClient.rpush("Music."+guild.id+":request_queue", JSON.stringify(music), (error) => {
      if (error){
        message.channel.sendMessage("An error happened when Queuing up the music...");
        console.log(error);
      } 
      else
        message.channel.sendMessage("**"+ music.title +"** added! :ok_hand:")
    });
  });
};

function playRemote(music, guild, voiceConnectionInfo) {
  var remote = music.url;
  if (!music.url) return;
    try {
      if (!voiceConnectionInfo) return console.log("Voice not connected");
      var encoder = voiceConnectionInfo.voiceConnection.createExternalEncoder({
        type: "ffmpeg",
        source: music.url,
        outputArgs: ["-compression_level", compression_level]
      });
      encoder.once("end", () => playOrNext(null, guild));
      encoder.play();
    } catch (e) { console.log("encode throw", e); }
}

let playOrNext = (message, guild) => {
  if (!message)
    var guild = guild;
  else
    var guild = message.guild;
  utils.isMusicEnabled(guild, (musicEnabled) => {
    if (!musicEnabled){
      stop(message);
      return;
    }
    
    var voiceConnectionInfo = client.VoiceConnections.getForGuild(guild);
    if (!voiceConnectionInfo){
      if (message)
        message.channel.sendMessage("I'm not connected to the voice channel yet :grimacing:...");
      return;
    }
    redisClient.lpop("Music."+guild.id+":request_queue", (error, music) => {
      if (!music) {
        if (message)
          message.channel.sendMessage("Nothing to play... :grimacing:");
        return;
      }
      music = JSON.parse(music);
      playRemote(music, guild, voiceConnectionInfo);
      redisClient.set("Music."+guild.id+":now_playing", JSON.stringify(music));
    });
  });
};

let stop = (message) => {
  var info = client.VoiceConnections.getForGuild(message.guild);
  if (info) {
    var encoderStream = info.voiceConnection.getEncoderStream();
    encoderStream.unpipeAll();
  }
};

let leave = (message) => {
  var voiceCo = client.VoiceConnections.getForGuild(message.guild);
  if (voiceCo) {
    voiceCo.disconnect();
  }
}

client.Dispatcher.on(Events.MESSAGE_CREATE, e => {
  if (!e.message.guild)
    return;

  utils.isMusicEnabled (e.message.guild, (musicEnabled) => {
    if (!musicEnabled)
      return;
    if (!e.message.content.startsWith('!'))
      return;
    isAllowed(e.message.member, (allowed) => {
      if (!allowed)
        return
      var command = '!add';
      if (e.message.content.startsWith(command + ' ')){
        var arg = e.message.content.substring(command.length+1, e.message.content.length);
        if (!arg.startsWith("http")) {
          var search = arg;
          var searchURL = 'https://www.googleapis.com/youtube/v3/search' + 
            '?part=snippet&q='+escape(search)+'&key='+apiKey;
          request(searchURL, (error, response) => {
            if (!error) {
              var payload = JSON.parse(response.body);
              if (payload['items'].length == 0) {
                e.message.channel.sendMessage("Didn't find anything :cry:!");
                return
              }
            
              var videos = payload.items.filter(item => item.id.kind === 'youtube#video');
              if (videos.length === 0){
                e.message.channel.sendMessage("Didn't find any video :cry:!");
                return
              }
              var video = videos[0];
              url = "https://youtube.com/?v="+video.id.videoId;
              youtubedl.getInfo(url, ['-f', "bestaudio"], (err, info) => {
               if (err) {
                e.message.channel.sendMessage("An error occured, sorry :cry:...");
                return;
              }
              var music = {
               title: info.title,
               url: info.url,
               thumbnail: info.thumbnail,
              };
              queueUp(music, e.message);

              });
            }
            else {
              e.message.channel.sendMessage("An error occured durring the search :frowning:");
              return;
            }
          });
        }
        else {
          var url = arg;
          youtubedl.getInfo(url, ['-f', "'bestaudio"], (err, info) => {
            if (err) {
              e.message.channel.sendMessage("An error occured, sorry :cry:...");
              return;
            }
            var music = {
              title: info.title,
              url: info.url,
              thumbnail: info.thumbnail,
            };
            queueUp(music, e.message);
          });
        }

      }

      if (e.message.content == "!join") {
        var voiceChannels = e.message.guild.voiceChannels
          .filter( vc => vc.members.map(m => m.id).indexOf(e.message.author.id) > -1 );
        if (voiceChannels.length > 0) {
          voiceChannels[0].join(false, false);
          let check = (msg) => {
            var voiceConnectionInfo = client.VoiceConnections.getForGuild(msg.guild);
            if (voiceConnectionInfo) {
              if (voiceConnectionInfo.voiceConnection != null) {
                msg.edit("Successfully connected :ok_hand:!");
              }
            }
            else
              setTimeout(()=>{check(msg)}, 1);
          };
          e.message.channel.sendMessage("Connecting to Voice... Please wait...").then((msg, error) => {
            check(msg);
          });
        }
      }
    
      if (e.message.content == "!play"
          || e.message.content == "!next"
          ) {
        playOrNext(e.message, null);
      }

      if (e.message.content == "!stop") {
        stop(e.message);
      }
      
      if (e.message.content == "!leave") {
        leave(e.message);
      }

      if (e.message.content == "!playlist") {
        var playlistString = "";
        var voiceConnection = client.VoiceConnections.getForGuild(e.message.guild);
          redisClient.get("Music."+e.message.guild.id+":now_playing", (err, music) => {
            if (!err && voiceConnection && music){
              music = JSON.parse(music);
              playlistString += "`NOW PLAYING` :notes: **"+music.title+"** added by **"+music.addedBy.name+"**\n\n";
            }

            redisClient.lrange("Music."+e.message.guild.id+":request_queue", 0, 4, (err, playlist) =>{
              playlist.forEach( (music, index) => {
                music = JSON.parse(music);
                playlistString += "`#"+(index+1)+"` **"+music.title+"** added by **"+music.addedBy.name+"**\n";
              });
              playlistString += "\n `Full Playlist > ` <https://mee6.xyz/request_playlist/" + e.message.guild.id + ">";
              e.message.channel.sendMessage(playlistString);
            });

          });
      }

    });

  });
});

