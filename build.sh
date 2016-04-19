git pull
cd chat-bot/
docker build --no-cache -t mee6-text .
cd ../website
docker build --no-cache -t mee6-web .
cd ../
