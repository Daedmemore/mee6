package main

import (
	"errors"
	log "github.com/Sirupsen/logrus"
	"github.com/bwmarrin/discordgo"
	"github.com/otium/ytdl"
	"os"
	"os/signal"
)

var (
	discord *discordgo.Session
)

func onReady(s *discordgo.Session, event *discordgo.Ready) {
	log.Info("Recieved READY packet")
}

// Function from Airhorn bot
// Attemps to find the current user voice channel inside a guild
func getCurrentVoiceChannel(user *discordgo.User, guild *discordgo.Guild) *discordgo.Channel {
	for _, vs := range guild.VoiceStates {
		if vs.UserID == user.ID {
			channel, _ := discord.State.Channel(vs.ChannelID)
			return channel
		}
	}
	return nil
}

func playYt(youtubeURL string, vc *discordgo.VoiceConnection) error {
	log.WithFields(log.Fields{
		"url": youtubeURL,
	}).Info("Playing music")

	if vc == nil {
		return errors.New("No voice connection")
	}

	videoInfo, err := ytdl.GetVideoInfo(youtubeURL)
	if err != nil {
		return err
	}

	downloadURL, err := videoInfo.GetDownloadURL(ytdl.FORMATS[22])
	if err != nil {
		return err
	}

	log.WithFields(log.Fields{
		"url": downloadURL,
	}).Info("Found download URL")

	vc.Speaking(true)
	defer vc.Speaking(false)

	return nil
}

func onMessageCreate(s *discordgo.Session, m *discordgo.MessageCreate) {
	if m.Content == "!join" {

		log.Info("Received !join cmd")

		channel, _ := discord.State.Channel(m.ChannelID)
		if channel == nil {
			log.WithFields(log.Fields{
				"channel": m.ChannelID,
			}).Warning("Failed to get channel")
		}

		guild, _ := discord.State.Guild(channel.GuildID)
		if guild == nil {
			log.WithFields(log.Fields{
				"guild": channel.GuildID,
			}).Warning("Failed to get guild")
		}

		voice_channel := getCurrentVoiceChannel(m.Author, guild)
		if voice_channel == nil {
			log.WithFields(log.Fields{
				"username": m.Author.Username,
				"discrim":  m.Author.Discriminator,
				"guild":    guild.Name,
			}).Warning("User not in a voice channel")
			return
		}

		log.WithFields(log.Fields{
			"guild":   guild.ID,
			"channel": voice_channel.ID,
		}).Info("Trying to join voice channel")

		vc, err := discord.ChannelVoiceJoin(guild.ID, voice_channel.ID, false, false)
		if err != nil {
			log.WithFields(log.Fields{
				"error": err,
			}).Error("Failed to connect to voice channel")
			return
		}

		err = playYt("https://www.youtube.com/watch?v=Ur9yIzUYZso", vc)
		if err != nil {
			log.WithFields(log.Fields{
				"error": err,
			}).Warning("An error occured when trying to play yt video")
		}

		return
	}

}

func main() {
	var (
		err error
	)

	// Get the token
	token := os.Getenv("MEE6_TOKEN")
	if &token != nil {
		log.Info("Token found")
	} else {
		log.Fatal("Token not found")
	}

	// Create discord session
	discord, err = discordgo.New(token)
	if err != nil {
		log.WithFields(log.Fields{
			"error": err,
		}).Fatal("Failed to create discord session")
	}

	// Register EVENTS
	discord.AddHandler(onReady)
	discord.AddHandler(onMessageCreate)

	// Establish websocket connection
	log.Info("Establishing connection to the Gateway...")
	err = discord.Open()
	if err != nil {
		log.WithFields(log.Fields{
			"error": err,
		}).Fatal("Failed to establish Gateway connection")
	}

	// Everything is fine
	log.Info("Connected to the Gateway")

	// Wait for os kill signal
	c := make(chan os.Signal, 1)
	signal.Notify(c, os.Interrupt, os.Kill)
	<-c
}
