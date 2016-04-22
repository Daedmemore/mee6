"use strict"

var redisURL = process.env.REDIS_URL,
    redis = require('redis'),
    redisClient = redis.createClient(redisURL),
    ytdl = require('ytdl-core'),
    apiKey = process.env.GOOGLE_API_KEY,
    request = require('request'),
    shards = process.env.SHARDS;

var Discordie = require("discordie");
var Events = Discordie.Events

shards = shards.split("");

var client = new Discordie();
client.connect({token: process.env.MEE6_TOKEN});
var utils = require('./utils');

client.Dispatcher.on(Events.GATEWAY_READY, e => {
  console.log("Connected as: " + client.User.username);
});

let isAllowed = (member, cb) => {
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
      if (roles.indexOf(role.name) > -1){
        cb(true);
        return;
      }
    }
    cb(false);
  });
};

// The b1nzy way!
let shardContains = (guildId) => {
  if (shards.indexOf(guildId[guildId.length-5]) > -1) {
    return true;
  }

  return false;
};

let queueUp = (video, message) => {
  var guild = message.guild;
  utils.isMusicEnabled(guild, (musicEnabled) => {
    if (!musicEnabled)
      return;
    video.addedBy = {
      name: message.author.username,
      discriminator: message.author.discriminator,
      avatar: message.author.avatarURL
    };
    redisClient.rpush("Music."+guild.id+":request_queue", JSON.stringify(video), (error) => {
      if (error){
        message.channel.sendMessage("An error happened when Queuing up the video...");
        console.log(error);
      } 
      else
        message.channel.sendMessage("**"+ video.snippet.title +"** added! :ok_hand:")
    });
  });
};

let getStreamFromYT = (video) => {
  var link = "http://youtube.com/?v="+video.id.videoId;
  return ytdl(link, {filter: format => format.container == 'mp4', quality: 'lowest'});
};

let getVideoInfo = (video) => {
  var link = "http://youtube.com/?v="+video.id.videoId;
}

function playRemote(video, guild, info) {
  var remote = "http://youtube.com/?v="+video.id.videoId;
  function onMediaInfo(err, mediaInfo) {
    if (err) return console.log("ytdl error:", err);
    // sort by bitrate, high to low; prefer webm over anything else
    var formats = mediaInfo.formats.filter(f => f.container === "webm")
    .sort((a, b) => b.audioBitrate - a.audioBitrate);

    // get first audio-only format or fallback to non-dash video
    var bestaudio = formats.find(f => f.audioBitrate > 0 && !f.bitrate) ||
                    formats.find(f => f.audioBitrate > 0);
    if (!bestaudio) return console.log("[playRemote] No valid formats");
    if (!info) return console.log("[play] Voice not connected");
    var encoder = info.voiceConnection.createExternalEncoder({
      type: "ffmpeg", source: bestaudio.url
    });
    encoder.once("end", () => playOrNext(null, guild));
    encoder.play();
  }
  try {
    ytdl.getInfo(remote, onMediaInfo);
  } catch (e) { console.log("ytdl threw:", e); }
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
    
    var voiceConnection = client.VoiceConnections.getForGuild(guild);
    if (!voiceConnection){
      if (message)
        message.channel.sendMessage("I'm not connected to the voice channel yet :grimacing:...");
      return;
    }
    redisClient.lpop("Music."+guild.id+":request_queue", (error, video) => {
      if (!video) {
        if (message)
          message.channel.sendMessage("Nothing to play... :grimacing:");
        return;
      }
      video = JSON.parse(video);
      playRemote(video, guild, voiceConnection);
      redisClient.set("Music."+guild.id+":now_playing", JSON.stringify(video));
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

client.Dispatcher.on(Events.MESSAGE_CREATE, e => {
  if (!e.message.guild)
    return;

  if (e.message.content == "!musicstats") {
    var voiceCo = client.VoiceConnections.filter(vc => vc.voiceConnection.guildId != null)
      .filter(vc => shardContains(vc.voiceConnection.guildId));
    var guilds = client.Guilds.filter(g => shardContains(g.id));
    e.message.channel.sendMessage(":headphones: **Shard "+shards.join(',')+"** "+
        "Currently connected to **"+guilds.length+" guild"+(guilds.length > 1 ? "s" : "")+
          "** & **"+voiceCo.length+" voice channel"+ (voiceCo.length > 1 ? "s" : "") +"** :ok_hand:.");
  }

  if (shardContains(e.message.guild.id) == false)
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
        var search = e.message.content.substring(command.length+1, e.message.content.length);
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
            queueUp(video, e.message);
          
          }
          else {
            e.message.channel.sendMessage("An error occured durring the search :frowning:")
          }
        });
      }

      if (e.message.content == "!join") {
        var voiceChannels = e.message.guild.voiceChannels
          .filter( vc => vc.members.map(m => m.id).indexOf(e.message.author.id) > -1 );
        if (voiceChannels.length > 0) {
          voiceChannels[0].join(false, false);
          let check = (msg) => {
             if (client.VoiceConnections.getForGuild(msg.guild))
                msg.edit("Successfully connected :ok_hand:!");
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

      if (e.message.content == "!playlist") {
        var playlistString = "";
        var voiceConnection = client.VoiceConnections.getForGuild(e.message.guild);
          redisClient.get("Music."+e.message.guild.id+":now_playing", (err, video) => {
            if (!err && voiceConnection && video){
              video = JSON.parse(video);
              playlistString += "`NOW PLAYING` **"+video.snippet.title+"** added by **"+video.addedBy.name+"**\n\n";
            }

            redisClient.lrange("Music."+e.message.guild.id+":request_queue", 0, 4, (err, playlist) =>{
              playlist.forEach( (video, index) => {
                video = JSON.parse(video);
                playlistString += "`#"+(index+1)+"` **"+video.snippet.title+"** added by **"+video.addedBy.name+"**\n";
              });
              playlistString += "\n `Full Playlist > ` https://mee6.xyz/request_playlist/" + e.message.guild.id;
              e.message.channel.sendMessage(playlistString);
            });

          });
      }

    });

  });
});

