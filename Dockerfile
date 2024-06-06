FROM python:3.10-slim-bullseye

LABEL maintainer="foo@bar.com"
ARG TZ='Asia/Shanghai'

RUN echo /etc/apt/sources.list
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list

# Set the build prefix and repository URL
ENV BUILD_PREFIX=/app
ENV REPO_URL=https://github.com/SoloGenius-AI/chatgpt-on-wechat.git

# Update package lists and install required packages
RUN apt-get update \
    &&apt-get install -y --no-install-recommends git

# Clone the repository
RUN git clone ${REPO_URL} ${BUILD_PREFIX}
RUN cp ${BUILD_PREFIX}/config-template.json ${BUILD_PREFIX}/config.json
RUN git config --global pull.rebase false

RUN apt-get install -y --no-install-recommends bash ffmpeg espeak libavcodec-extra

# Install Python dependencies
RUN cd ${BUILD_PREFIX} \
    && /usr/local/bin/python -m pip install --no-cache --upgrade pip \
    && pip install --no-cache -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/\
    && pip install --no-cache -r requirements-optional.txt -i https://mirrors.aliyun.com/pypi/simple/\
    && pip install azure-cognitiveservices-speech -i https://mirrors.aliyun.com/pypi/simple/

WORKDIR ${BUILD_PREFIX}

# Pull the latest code when the container starts
CMD git pull && python app.py
