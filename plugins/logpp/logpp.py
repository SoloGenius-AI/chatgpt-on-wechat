# encoding:utf-8

import plugins
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from common.log import logger
from plugins import *
import datetime
import tiktoken
import csv
from datetime import datetime


def create_csv_file(file_name):
    with open(file_name, mode='w', newline='', encoding='utf-8-sig') as file:
        writer = csv.writer(file)
        writer.writerow(["时间", "用户名", "群聊", "输入token数", "输出token数", "实际请求内容", "输出内容"])


def add_row_to_csv(file_name, current_time, user, group, in_token, out_token, input_text, reply, model=None):
    with open(file_name, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        if model is None:
            writer.writerow([current_time, user, group, in_token, out_token, input_text, reply])
        else:
            writer.writerow([current_time, user, group, in_token, out_token, input_text, reply, model])


def num_tokens_from_string(string: str, encoding) -> int:
    """Returns the number of tokens in a text string."""
    num_tokens = len(encoding.encode(string))
    return num_tokens


@plugins.register(
    name="logpp",
    desire_priority=5,
    hidden=True,
    desc="A plugin that the usage of each user(group) as a csv file",
    version="0.1",
    author="kk",
)
class logpp(Plugin):
    def __init__(self):
        super().__init__()
        if not os.path.exists(os.path.join(os.path.dirname(__file__), 'logs')):
            os.makedirs(os.path.join(os.path.dirname(__file__), 'logs'))

        self.handlers[Event.ON_DECORATE_REPLY] = self.on_decorate_reply  # 输出的部分，在其他插件装饰回复前就计算
        self.encoding = tiktoken.get_encoding(
            "cl100k_base")  # support gpt-4, gpt-3.5-turbo, text-embedding-ada-002. Davinci(GPT-3) not supported

        logger.info("[logpp] inited")

    @property
    def csv(self):
        if not os.path.exists(os.path.join(os.path.dirname(__file__), 'logs', self.today + ".csv")):
            create_csv_file(os.path.join(os.path.dirname(__file__), 'logs', self.today + ".csv"))
        return os.path.join(os.path.dirname(__file__), 'logs', self.today + ".csv")

    @property
    def new_csv(self):
        if not os.path.exists(os.path.join(os.path.dirname(__file__), 'logs', self.month + ".csv")):
            create_csv_file(os.path.join(os.path.dirname(__file__), 'logs', self.month + ".csv"))
        return os.path.join(os.path.dirname(__file__), 'logs', self.month + ".csv")

    @property
    def today(self):
        return datetime.now().strftime("%Y-%m-%d")

    @property
    def month(self):
        return datetime.now().strftime("%Y-%m")

    @property
    def now(self):
        return datetime.now().strftime("%H:%M:%S")

    @property
    def new_now(self):
        return datetime.now().strftime("%d-%H:%M:%S")

    def on_decorate_reply(self, e_context: EventContext):
        try:
            if e_context["context"].type not in [
                ContextType.TEXT,
                ContextType.IMAGE
            ]:
                return

            if e_context["reply"].type not in [
                ReplyType.TEXT,
                ReplyType.IMAGE
            ]:
                return

            content = e_context['context'].content
            is_group = e_context['context'].kwargs['msg'].is_group  # certain group
            group = e_context['context'].kwargs['msg'].other_user_nickname
            if is_group:
                user = e_context['context'].kwargs['msg'].actual_user_nickname
            else:
                user = e_context['context'].kwargs['msg'].from_user_nickname
            reply = e_context['reply']
            addition_info = reply.addition_info
            model_name = addition_info.get('model', '') if addition_info is not None else ''
            total_tokens = addition_info.get('total_tokens', '') if addition_info is not None else ''
            prompt_tokens = addition_info.get('prompt_tokens', '') if addition_info is not None else ''
            completion_tokens = addition_info.get('completion_tokens', '') if addition_info is not None else ''

            if e_context["context"].type == ContextType.TEXT:
                # "时间", "用户名", "群聊", "输入token数", "输出token数", "实际请求内容", "输出内容"
                if reply.type == ReplyType.TEXT:
                    if is_group:
                        add_row_to_csv(self.csv, self.now, user, group, num_tokens_from_string(content, self.encoding),
                                       num_tokens_from_string(reply.content, self.encoding), content, reply.content,
                                       model_name)
                        add_row_to_csv(self.new_csv, self.new_now, user, group, prompt_tokens, completion_tokens,
                                       content,
                                       reply.content, model_name)
                    else:
                        add_row_to_csv(self.csv, self.now, user, "", num_tokens_from_string(content, self.encoding),
                                       num_tokens_from_string(reply.content, self.encoding), content, reply.content,
                                       model_name)
                        add_row_to_csv(self.new_csv, self.new_now, user, "", prompt_tokens, completion_tokens,
                                       content, reply.content, model_name)
                elif reply.type == ReplyType.IMAGE:
                    if is_group:
                        add_row_to_csv(self.csv, self.now, user, group, num_tokens_from_string(content, self.encoding),
                                       0,
                                       content, "image")
                    else:
                        add_row_to_csv(self.csv, self.now, user, "", num_tokens_from_string(content, self.encoding), 0,
                                       content, "image")
                return

            if e_context["context"].type == ContextType.IMAGE:
                if reply.type == ReplyType.TEXT:
                    if is_group:
                        add_row_to_csv(self.csv, self.now, user, group, 0,
                                       num_tokens_from_string(reply.content, self.encoding), "image", reply.content)
                    else:
                        add_row_to_csv(self.csv, self.now, user, "", 0,
                                       num_tokens_from_string(reply.content, self.encoding), "image", reply.content)
                elif reply.type == ReplyType.IMAGE:
                    if is_group:
                        add_row_to_csv(self.csv, self.now, user, group, 0, 0, "image", "image")
                    else:
                        add_row_to_csv(self.csv, self.now, user, "", 0, 0, "image", "image")
                return
        except Exception as e_:
            logger.error(f'记录token时错误: {e_}')

    def get_help_text(self, **kwargs):
        help_text = f"后台统计用户请求与回复token数\n"
        return help_text
