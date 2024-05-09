# FROM ghcr.io/zhayujie/chatgpt-on-wechat:latest
#
# ENTRYPOINT ["/entrypoint.sh"]

FROM python:3.9.16
RUN pip3 install -r requirements.txt
WORKDIR /home
ADD . .
CMD python3 app.py
