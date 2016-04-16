git pull
cd chat-bot/
docker build --no-cache -t mee6-bot .
cd ../website
docker build --no-cache -t mee6-web .
cd ../
