import os.path
import random
import filetype

import requests

import plugins
import re
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from common.log import logger
from plugins import *


@plugins.register(
    name="sep_reply",
    desire_priority=1,
    hidden=True,
    desc="A plugin that separate the reply",
    version="0.1",
    author="kk",
)
class sep_reply(Plugin):
    def __init__(self):
        super().__init__()

        self.download_dir = './tmp_download'
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)

        self.handlers[Event.ON_SEND_REPLY] = self.on_send_reply  # 输出的部分
        logger.info("[sep_reply] inited")

    def on_send_reply(self, e_context: EventContext):
        channel = e_context['channel']
        context = e_context['context']
        reply = e_context['reply']

        reply_text = reply.content
        logger.info(f'wait for sep str: {reply_text}')

        links = re.findall(r'[(]https?://.*?[)]', reply_text)
        for link in links.copy():
            link_ = link.replace('(', '').replace(')', '')
            r = requests.get(link_, allow_redirects=True, verify=False)
            kind = filetype.guess_extension(r.content)
            type_ = filetype.guess_mime(r.content)
            if kind is None or 'image' not in type_:
                links.remove(link)
        if len(links) < 1:
            return

        st_idx = 0
        reply_list = []
        file_path_list = []
        open_file_list = []

        for link in links:
            ed_inx = reply_text.index(link)
            if ed_inx - st_idx > 1:
                reply_list.append(Reply(ReplyType.TEXT, content=reply_text[st_idx: ed_inx]))
            st_idx = ed_inx

            link = link.replace('(', '').replace(')', '')
            r = requests.get(link, allow_redirects=True, verify=False)
            kind = filetype.guess_extension(r.content)
            type_ = filetype.guess_mime(r.content)
            if kind is None:
                logger.error(f'Cannot guess file type!: {link}')

            file_path_ = f'{self.download_dir}/{random.random}.{kind}'
            file_path_list.append(file_path_)
            with open(file_path_, 'wb') as f_:
                f_.write(r.content)
            if kind is not None and 'image' in type_:
                open_file_list.append(open(file_path_, 'rb'))
                reply_list.append(Reply(ReplyType.IMAGE, content=open_file_list[-1]))
            else:
                reply_list.append(Reply(ReplyType.FILE, content=file_path_))

        final_text = reply_text[st_idx:]
        if len(final_text) > 1:
            reply_list.append(Reply(ReplyType.TEXT, content=final_text))

        for reply_ in reply_list:
            channel.send(reply_, context)

        for o_f in open_file_list:
            try:
                o_f.close()
            except Exception as e_:
                logger.error(f'close file err: {e_}')
        self.delete_files(file_path_list)
        e_context.action = EventAction.BREAK_PASS

    def delete_files(self, file_path_list):
        for file_path in file_path_list:
            try:
                os.remove(file_path)
            except Exception as e_:
                logger.error(f'remove file err: {e_}')
