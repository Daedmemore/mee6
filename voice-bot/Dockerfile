FROM node:wheezy

ENV DEBIAN_FRONTEND noninteractive

# Update and install minimal.
RUN \
  apt-get update \
            --quiet \
  && apt-get install \ 
            --yes \
            --no-install-recommends \
            --no-install-suggests \
        autoconf \
        automake \
        build-essential \
        ca-certificates \
        git-core \
        libass-dev \
        libgpac-dev \
        libtheora-dev \
        libtool \
        libvorbis-dev \
        pkg-config \
        python-minimal \
        texi2html \
        zlib1g-dev \
	openssl \
	libssl-dev \
	libmp3lame-dev \

# Clean up packages.
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Prepare for cloning/building.

## Yasm
RUN git clone git://github.com/yasm/yasm.git \
    && cd yasm \
    && ./autogen.sh \
    && ./configure \
    && make -j`getconf _NPROCESSORS_ONLN` \
    && make install \
    && make distclean \
    && cd /tmp \
    && rm -rf /tmp/yasm

## libopus
RUN git clone git://git.opus-codec.org/opus.git \
    && cd opus \
    && ./autogen.sh \
    && ./configure --disable-shared \
    && make -j`getconf _NPROCESSORS_ONLN` \
    && make install \
    && make distclean \
    && cd /tmp \
    && rm -rf /tmp/opus

## libvpx
RUN git clone https://chromium.googlesource.com/webm/libvpx \
    && cd libvpx \
    && ./configure --disable-shared \
    && make -j`getconf _NPROCESSORS_ONLN` \
    && make install \
    && make clean \
    && cd /tmp \
    && rm -rf /tmp/libvpx

## AAC
RUN     wget -O fdk-aac.tar.gz https://github.com/mstorsjo/fdk-aac/tarball/master \
	&& tar xzvf fdk-aac.tar.gz \
	&& cd mstorsjo-fdk-aac* \
	&& autoreconf -fiv \
	&& ./configure --disable-shared \
	&& make \
	&& make install

## ffmpeg
RUN git clone git://source.ffmpeg.org/ffmpeg.git \
    && cd ffmpeg \
    && ./configure \
        --disable-debug \
        --enable-small \
	--enable-nonfree \
        --extra-libs=-ldl \
        --enable-libass \
        --enable-libopus \
 	--enable-libfdk-aac \
  	--enable-libfreetype \
  	--enable-libmp3lame \
        --enable-libtheora \
        --enable-libvorbis \
        --enable-libvpx \
	--enable-openssl \

    && make -j`getconf _NPROCESSORS_ONLN` \
    && make install \
    && make distclean \
    && cd /tmp \
    && rm -rf /tmp/ffmpeg

ADD . /
RUN npm install
CMD [ "npm", "start" ]
