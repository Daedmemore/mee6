"use strict"

var redisURL = process.env.REDIS_URL;
var redis = require("redis");

var redisClient = redis.createClient(redisURL);

let isMusicEnabled = (guild, cb) => {
	redisClient.smembers("plugins:"+guild.id, (err, plugins) => {
		if (err!=null)
			console.log(err);
		else
			cb(plugins.indexOf("Music") > -1);
	});
};

let getMusicChannel = (guild, cb) => {
	redisClient.get("Music."+guild.id+":channel", (err, channelName) => {
		if (err!=null)
			console.log(err);
		else{
			var channel = guild.voiceChannels.filter(c => c.name === channelName);
			if (channel!=[])
				cb(channel);
			else
				cb(null)
		}
	});
};

let getPlaylist = (guild, cb) => {
	redisClient.lrange("Music."+guild.id+":playlist", 0, -1, (err, playlist) => {
		if (err!=null)
			console.log(err);
		else{
			cb(playlist);
		}
	});
};

let getCurrentSongIndex = (guild, cb) => {
	getPlaylist( playlist => {
		if (playlist === [])
			cb(-1);
		else{
			redisClient.get("Music."+guild.id+":songindex", (err, songIndex) => {
				if (err!=null)
					console.log(err);
				else
					cb(parseInt(songIndex));
			});
		}
	});	
};

let getNextSong = (guild, cb) => {
	getPlaylist(guild, playlist => {
		getCurrentSongIndex(guild, songIndex => {
			if (songIndex === -1)
				cb(null);
			else
				if (playlist.length > songIndex + 2)
					cb(0, playlist[0]);
				else
					cb(songIndex+1, playlist[songIndex+1]);
		});
	});
};

module.exports.getNextSong = getNextSong;
module.exports.getCurrentSongIndex = getCurrentSongIndex;
module.exports.getPlaylist = getPlaylist;
module.exports.getMusicChannel = getMusicChannel;
module.exports.isMusicEnabled = isMusicEnabled;
