# FROM ghcr.io/zhayujie/chatgpt-on-wechat:latest
#
# ENTRYPOINT ["/entrypoint.sh"]

FROM python:3.10-slim-bullseye

LABEL maintainer="foo@bar.com"
ARG TZ='Asia/Shanghai'

RUN echo /etc/apt/sources.list
# RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list
ENV BUILD_PREFIX=/app

ADD . ${BUILD_PREFIX}

RUN apt-get update \
    &&apt-get install -y --no-install-recommends bash ffmpeg espeak libavcodec-extra git\
    && cd ${BUILD_PREFIX} \
    && /usr/local/bin/python -m pip install --no-cache --upgrade pip \
    && pip install --no-cache -r requirements.txt \
    && pip install --no-cache -r requirements-optional.txt \
    && pip install azure-cognitiveservices-speech

WORKDIR ${BUILD_PREFIX}

CMD python app.py
