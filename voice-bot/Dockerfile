FROM node:wheezy
RUN ["echo", "\"deb http://www.deb-multimedia.org wheezy main non-free\" >> /etc/apt/sources.list"]
RUN ["echo", "\"deb-src http://www.deb-multimedia.org wheezy main non-free\" >> /etc/apt/sources.list"]
RUN ["apt-get", "update"]
# Run ffmpeg build script
RUN ["apt-get", "install", "-y", "ffmpeg"]
COPY . /
RUN npm install
CMD [ "npm", "start" ]
