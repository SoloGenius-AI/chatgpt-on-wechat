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
import magic


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
        self.magic_type_dict = {'text/plain': '文本'}

    def on_send_reply(self, e_context: EventContext):
        channel = e_context['channel']
        context = e_context['context']
        reply = e_context['reply']

        reply_text = reply.content
        logger.info(f'wait for sep str: {reply_text}')
        reply_text = re.sub(r'`+.*\n*.*\n*`+\n+', '', reply_text)
        reply_text = re.sub(r'\n+', '\n\n', reply_text)
        reply.content = reply_text.strip()

        links = re.findall(r'[(]https?://.*?[)]', reply_text)
        links_content_dict = {}
        for link in links.copy():
            link_ = link.replace('(', '').replace(')', '')
            reply_text = reply_text.replace(link, f'「{link_}」')
            try:
                r = requests.get(link_, allow_redirects=True, verify=False)
                kind = filetype.guess_extension(r.content)
                type_ = filetype.guess_mime(r.content)
                magic_type_ = self.file_type(r.content)
                if kind is None and magic_type_ is None:
                    logger.warning(f'移除不能识别的URL: {link_}')
                    links.remove(link)
                else:
                    links_content_dict[link_] = {'r': r, 'kind': kind, 'type_': type_, 'magic_type_': magic_type_}
                    logger.info(f'识别类型为: ({type_}+{magic_type_}), 保留URL: {link_}')
            except Exception as e_:
                logger.warning(f'移除识别异常的URL: {link_}, err: {e_}')
                links.remove(link)

        reply_text = reply_text.strip()
        reply.content = reply_text
        links = list(map(lambda x_: x_.replace('(', '「').replace(')', '」'), links))
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

            link = link.replace('「', '').replace('」', '')
            # r = requests.get(link, allow_redirects=True, verify=False)
            r = links_content_dict[link]['r']
            kind = links_content_dict[link]['kind']
            type_ = links_content_dict[link]['type_']
            magic_type_ = links_content_dict[link]['magic_type_']
            # kind = filetype.guess_extension(r.content)
            # type_ = filetype.guess_mime(r.content)
            # if kind is None:
            #     logger.error(f'Cannot guess file type!: {link}')

            file_name = link.split('/')[-1].strip()
            file_name = file_name if len(file_name) > 0 else f'{random.randint(0, 1000000000)}.{kind if kind is not None else magic_type_}'
            file_path_ = f'{self.download_dir}/{file_name}'
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
                logger.error(f'关闭文件: {o_f}异常: {e_}')
        self.delete_files(file_path_list)
        e_context.action = EventAction.BREAK_PASS
        logger.info(f'sep_result: {reply.content}')

    def delete_files(self, file_path_list):
        for file_path in file_path_list:
            try:
                os.remove(file_path)
            except Exception as e_:
                logger.error(f'remove file err: {e_}')

    def file_type(self, content):
        mine_str = magic.from_buffer(content, mime=True)
        return self.magic_type_dict.get(mine_str, None)
