# encoding:utf-8
import json
import os
import threading

import requests

from bot.bot import Bot
from bot.dify.dify_session import DifySession, DifySessionManager
from bridge.context import ContextType, Context
from bridge.reply import Reply, ReplyType
from common.log import logger
from common import const
from config import conf
from common import memory
from PIL import Image


class DifyBot(Bot):
    def __init__(self):
        super().__init__()
        self.sessions = DifySessionManager(DifySession, model=conf().get("model", const.DIFY))
        self.ask_image = False
        self.image_id = None
        self.last_not_image_session_id = ''
        self.last_image_session_id = ''
        self.start_flag = '开启与图像对话'
        self.finish_flag = '结束与图像对话'

    def reply(self, query, context: Context = None):
        # acquire reply content
        if (context.type == ContextType.TEXT or context.type == ContextType.IMAGE_CREATE or
                (context.type == ContextType.IMAGE and conf().get('dify_enable_vision', False))):
            if context.type == ContextType.IMAGE_CREATE:
                query = conf().get('image_create_prefix', ['画'])[0] + query
            logger.info("[DIFY] query={}".format(query))
            session_id = context["session_id"]
            # TODO: 适配除微信以外的其他channel
            channel_type = conf().get("channel_type", "wx")
            user = None
            if channel_type == "wx":
                user = context["msg"].other_user_nickname if context.get("msg") else "default"
            elif channel_type in ["wechatcom_app", "wechatmp", "wechatmp_service", "wechatcom_service", "wework"]:
                user = context["msg"].other_user_id if context.get("msg") else "default"
            else:
                return Reply(ReplyType.ERROR,
                             f"unsupported channel type: {channel_type}, now dify only support wx, wechatcom_app, wechatmp, wechatmp_service channel")
            logger.debug(f"[DIFY] dify_user={user}")
            user = user if user else "default"  # 防止用户名为None，当被邀请进的群未设置群名称时用户名为None
            session = self.sessions.get_session(session_id, user)
            logger.debug(f"[DIFY] session={session} query={query}")

            reply, err = self._reply(query, session, context)
            if err != None:
                reply = Reply(ReplyType.ERROR, "我暂时遇到了一些问题，请您稍后重试~")
            return reply
        else:
            reply = Reply(ReplyType.ERROR, "Bot不支持处理{}类型的消息".format(context.type))
            return reply

    def _get_api_base_url(self) -> str:
        return conf().get("dify_api_base", "https://api.dify.ai/v1")

    def _get_headers(self):
        return {
            'Authorization': f"Bearer {conf().get('dify_api_key', '')}"
        }

    def _get_payload(self, query, session: DifySession, response_mode):
        return {
            'inputs': {},
            "query": query,
            "response_mode": response_mode,
            "conversation_id": session.get_conversation_id(),
            "user": session.get_user()
        }

    def _reply(self, query: str, session: DifySession, context: Context):
        try:
            session.count_user_message()  # 限制一个conversation中消息数，防止conversation过长
            dify_app_type = conf().get('dify_app_type', 'chatbot')
            if dify_app_type == 'chatbot':
                return self._handle_chatbot(query, session, context)
            elif dify_app_type == 'agent':
                return self._handle_agent(query, session, context)
            elif dify_app_type == 'workflow':
                return self._handle_workflow(query, session)
            else:
                return None, "dify_app_type must be agent, chatbot or workflow"

        except Exception as e:
            error_info = f"[DIFY] Exception: {e}"
            logger.exception(error_info)
            return None, error_info

    def _handle_chatbot(self, query: str, session: DifySession, context: Context):
        # TODO: 获取response部分抽取为公共函数
        base_url = self._get_api_base_url()
        chat_url = f'{base_url}/chat-messages'
        headers = self._get_headers()
        response_mode = 'blocking'
        logger.info(f'{self.last_image_session_id=}')
        logger.info(f'{self.last_not_image_session_id=}')
        payload = self._get_payload(query, session, response_mode)
        if query == self.start_flag and not self.ask_image and self.image_id is not None:
            # self.last_not_image_session_id = session.get_session_id()
            session.set_conversation_id(self.last_image_session_id)
            # session.set_conversation_id('')
            self.ask_image = True
            reply = Reply(ReplyType.INFO, f'开启成功，接下来可以进行图像对话了。输入「{self.finish_flag}」以退出图像对话。')
            return reply, None
        elif query == self.finish_flag and self.ask_image:
            self.ask_image = False
            reply = Reply(ReplyType.INFO, '结束图像对话成功。')
            # self.last_image_session_id = session.get_session_id()
            session.set_conversation_id(self.last_not_image_session_id)
            # session.set_conversation_id('')
            return reply, None
        elif context.type != ContextType.IMAGE:
            if self.ask_image:
                payload['inputs']['ask_image'] = 'true'
                payload['files'] = [{'type': 'image', 'transfer_method': 'local_file', 'upload_file_id': self.image_id}]
            else:
                payload['inputs']['ask_image'] = 'false'
            logger.info(f'[DIFY] send {payload=}')
            response = requests.post(chat_url, headers=headers, json=payload)
        else:
            session.set_conversation_id('')
            upload_url = f'{base_url}/files/upload'
            payload_ = {'user': payload['user']}
            context.get("msg").prepare()
            file_path_ = context.content
            save_file_path_ = f'{file_path_}.jpeg'
            try:
                with Image.open(file_path_) as im:
                    # fsize = os.path.getsize(file_path_) / float(1024)
                    im.save(save_file_path_, quality=85, optimize=True)
            except Exception as e_:
                logger.error(f'[DIFY] 图片格式转换失败: {save_file_path_}, err: {e_}')
                save_file_path_ = file_path_

            file_name_ = save_file_path_.split(os.sep)[-1]
            # type=image/[png|jpeg|jpg|webp|gif]
            type_ = 'image/{}'.format(save_file_path_.split('.')[-1].lower())
            # type_ = 'image/jpeg'
            files = {'file': (file_name_, open(save_file_path_, 'rb'), type_)}
            response = requests.post(upload_url, headers=headers, data=payload_, files=files)
            os.remove(file_path_)
            try:
                os.remove(save_file_path_)
            except Exception as e_:
                logger.info(f'[DIFY] remove {save_file_path_} failed. err: {e_}')
        if response.status_code != 200 and response.status_code != 201:
            error_info = f"[DIFY] response text={response.text} status_code={response.status_code}"
            logger.warn(error_info)
            if 'invalid_param' in f'{response.text}' and 'Invalid upload file' in f'{response.text}':
                self.ask_image = False
                self.image_id = None
                reply = Reply(ReplyType.INFO, '图像可能超时，清除并结束此次图像对话。')
                session.set_conversation_id(self.last_not_image_session_id)
                return reply, None
            if response.status_code == 404:
                session.set_conversation_id('')
                self.last_not_image_session_id = ''
                self.last_image_session_id = ''
                reply = Reply(ReplyType.INFO, '或因恢复上个对话超时无法继续，已清除对话并重置。')
                return reply, None
            return None, error_info

        # response:
        # {
        #     "event": "message",
        #     "message_id": "9da23599-e713-473b-982c-4328d4f5c78a",
        #     "conversation_id": "45701982-8118-4bc5-8e9b-64562b4555f2",
        #     "mode": "chat",
        #     "answer": "xxx",
        #     "metadata": {
        #         "usage": {
        #         },
        #         "retriever_resources": []
        #     },
        #     "created_at": 1705407629
        # }
        rsp_data = response.json()
        logger.debug("[DIFY] usage {}".format(rsp_data.get('metadata', {}).get('usage', 0)))
        # TODO: 处理返回的图片文件
        # {"answer": "![image](/files/tools/dbf9cd7c-2110-4383-9ba8-50d9fd1a4815.png?timestamp=1713970391&nonce=0d5badf2e39466042113a4ba9fd9bf83&sign=OVmdCxCEuEYwc9add3YNFFdUpn4VdFKgl84Cg54iLnU=)"}
        if context.type != ContextType.IMAGE:
            add_info_dict = {}
            try:
                add_info_dict['model'] = 'dify'
                add_info_dict['total_tokens'] = rsp_data['metadata']['usage']['total_tokens']
                add_info_dict['prompt_tokens'] = rsp_data['metadata']['usage']['prompt_tokens']
                add_info_dict['completion_tokens'] = rsp_data['metadata']['usage']['completion_tokens']
            except Exception as e_:
                logger.info(f'[DIFY] reply添加add_info_dict异常: {e_}')
            reply = Reply(ReplyType.TEXT, rsp_data['answer'], add_info_dict)
        else:
            self.image_id = rsp_data.get('id', None)
            reply = Reply(ReplyType.INFO, f'图像读取成功，输入「{self.start_flag}」对图像进行相关对话，输入「{self.finish_flag}」以退出。\n对话仅保留最近的一次的图像。')
            return reply, None
        # 设置dify conversation_id, 依靠dify管理上下文
        if session.get_conversation_id() == '' or session.get_session_id().startswith('@'):
            session.set_conversation_id(rsp_data.get('conversation_id', ''))

        if self.ask_image:
            self.last_image_session_id = rsp_data.get('conversation_id', '') if rsp_data.get('conversation_id', '') != self.last_not_image_session_id else self.last_image_session_id
            logger.info(f'[DIFY] set {self.last_image_session_id=}')
        else:
            self.last_not_image_session_id = rsp_data.get('conversation_id', '') if rsp_data.get('conversation_id', '') != self.last_image_session_id else self.last_not_image_session_id
            logger.info(f'[DIFY] set {self.last_not_image_session_id=}')
        return reply, None

    def _handle_agent(self, query: str, session: DifySession, context: Context):
        # TODO: 获取response抽取为公共函数
        base_url = self._get_api_base_url()
        chat_url = f'{base_url}/chat-messages'
        headers = self._get_headers()
        response_mode = 'streaming'
        payload = self._get_payload(query, session, response_mode)
        response = requests.post(chat_url, headers=headers, json=payload)
        if response.status_code != 200:
            error_info = f"[DIFY] response text={response.text} status_code={response.status_code}"
            logger.warn(error_info)
            return None, error_info
        # response:
        # data: {"event": "agent_thought", "id": "8dcf3648-fbad-407a-85dd-73a6f43aeb9f", "task_id": "9cf1ddd7-f94b-459b-b942-b77b26c59e9b", "message_id": "1fb10045-55fd-4040-99e6-d048d07cbad3", "position": 1, "thought": "", "observation": "", "tool": "", "tool_input": "", "created_at": 1705639511, "message_files": [], "conversation_id": "c216c595-2d89-438c-b33c-aae5ddddd142"}
        # data: {"event": "agent_thought", "id": "8dcf3648-fbad-407a-85dd-73a6f43aeb9f", "task_id": "9cf1ddd7-f94b-459b-b942-b77b26c59e9b", "message_id": "1fb10045-55fd-4040-99e6-d048d07cbad3", "position": 1, "thought": "", "observation": "", "tool": "dalle3", "tool_input": "{\"dalle3\": {\"prompt\": \"cute Japanese anime girl with white hair, blue eyes, bunny girl suit\"}}", "created_at": 1705639511, "message_files": [], "conversation_id": "c216c595-2d89-438c-b33c-aae5ddddd142"}
        # data: {"event": "agent_message", "id": "1fb10045-55fd-4040-99e6-d048d07cbad3", "task_id": "9cf1ddd7-f94b-459b-b942-b77b26c59e9b", "message_id": "1fb10045-55fd-4040-99e6-d048d07cbad3", "answer": "I have created an image of a cute Japanese", "created_at": 1705639511, "conversation_id": "c216c595-2d89-438c-b33c-aae5ddddd142"}
        # data: {"event": "message_end", "task_id": "9cf1ddd7-f94b-459b-b942-b77b26c59e9b", "id": "1fb10045-55fd-4040-99e6-d048d07cbad3", "message_id": "1fb10045-55fd-4040-99e6-d048d07cbad3", "conversation_id": "c216c595-2d89-438c-b33c-aae5ddddd142", "metadata": {"usage": {"prompt_tokens": 305, "prompt_unit_price": "0.001", "prompt_price_unit": "0.001", "prompt_price": "0.0003050", "completion_tokens": 97, "completion_unit_price": "0.002", "completion_price_unit": "0.001", "completion_price": "0.0001940", "total_tokens": 184, "total_price": "0.0002290", "currency": "USD", "latency": 1.771092874929309}}}
        msgs, conversation_id = self._handle_sse_response(response)
        channel = context.get("channel")
        # TODO: 适配除微信以外的其他channel
        is_group = context.get("isgroup", False)
        for msg in msgs[:-1]:
            if msg['type'] == 'agent_message':
                if is_group:
                    at_prefix = "@" + context["msg"].actual_user_nickname + "\n"
                    msg['content'] = at_prefix + msg['content']
                reply = Reply(ReplyType.TEXT, msg['content'])
                channel.send(reply, context)
            elif msg['type'] == 'message_file':
                url = self._fill_file_base_url(msg['content']['url'])
                reply = Reply(ReplyType.IMAGE_URL, url)
                thread = threading.Thread(target=channel.send, args=(reply, context))
                thread.start()
        final_msg = msgs[-1]
        reply = None
        if final_msg['type'] == 'agent_message':
            reply = Reply(ReplyType.TEXT, final_msg['content'])
        elif final_msg['type'] == 'message_file':
            url = self._fill_file_base_url(final_msg['content']['url'])
            reply = Reply(ReplyType.IMAGE_URL, url)
        # 设置dify conversation_id, 依靠dify管理上下文
        if session.get_conversation_id() == '':
            session.set_conversation_id(conversation_id)
        return reply, None

    def _handle_workflow(self, query: str, session: DifySession):
        base_url = self._get_api_base_url()
        workflow_url = f'{base_url}/workflows/run'
        headers = self._get_headers()
        payload = self._get_workflow_payload(query, session)
        response = requests.post(workflow_url, headers=headers, json=payload)
        if response.status_code != 200:
            error_info = f"[DIFY] response text={response.text} status_code={response.status_code}"
            logger.warn(error_info)
            return None, error_info
        # {
        #     "log_id": "djflajgkldjgd",
        #     "task_id": "9da23599-e713-473b-982c-4328d4f5c78a",
        #     "data": {
        #         "id": "fdlsjfjejkghjda",
        #         "workflow_id": "fldjaslkfjlsda",
        #         "status": "succeeded",
        #         "outputs": {
        #         "text": "Nice to meet you."
        #         },
        #         "error": null,
        #         "elapsed_time": 0.875,
        #         "total_tokens": 3562,
        #         "total_steps": 8,
        #         "created_at": 1705407629,
        #         "finished_at": 1727807631
        #     }
        # }
        rsp_data = response.json()
        reply = Reply(ReplyType.TEXT, rsp_data['data']['outputs']['text'])
        return reply, None

    def _fill_file_base_url(self, url: str):
        if url.startswith("https://") or url.startswith("http://"):
            return url
        # 补全文件base url, 默认使用去掉"/v1"的dify api base url
        return self._get_file_base_url() + url

    def _get_file_base_url(self) -> str:
        return self._get_api_base_url().replace("/v1", "")

    def _get_workflow_payload(self, query, session: DifySession):
        return {
            'inputs': {
                "query": query
            },
            "response_mode": "blocking",
            "user": session.get_user()
        }

    def _parse_sse_event(self, event_str):
        """
        Parses a single SSE event string and returns a dictionary of its data.
        """
        event_prefix = "data: "
        if not event_str.startswith(event_prefix):
            return None
        trimmed_event_str = event_str[len(event_prefix):]

        # Check if trimmed_event_str is not empty and is a valid JSON string
        if trimmed_event_str:
            try:
                event = json.loads(trimmed_event_str)
                return event
            except json.JSONDecodeError:
                logger.error(f"Failed to decode JSON from SSE event: {trimmed_event_str}")
                return None
        else:
            logger.warn("Received an empty SSE event.")
            return None

    # TODO: 异步返回events
    def _handle_sse_response(self, response: requests.Response):
        events = []
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                event = self._parse_sse_event(decoded_line)
                if event:
                    events.append(event)

        merged_message = []
        accumulated_agent_message = ''
        conversation_id = None
        for event in events:
            event_name = event['event']
            if event_name == 'agent_message' or event_name == 'message':
                accumulated_agent_message += event['answer']
                logger.debug("[DIFY] accumulated_agent_message: {}".format(accumulated_agent_message))
                # 保存conversation_id
                if not conversation_id:
                    conversation_id = event['conversation_id']
            elif event_name == 'agent_thought':
                self._append_agent_message(accumulated_agent_message, merged_message)
                accumulated_agent_message = ''
                logger.debug("[DIFY] agent_thought: {}".format(event))
            elif event_name == 'message_file':
                self._append_agent_message(accumulated_agent_message, merged_message)
                accumulated_agent_message = ''
                self._append_message_file(event, merged_message)
            elif event_name == 'message_replace':
                # TODO: handle message_replace
                pass
            elif event_name == 'error':
                logger.error("[DIFY] error: {}".format(event))
                raise Exception(event)
            elif event_name == 'message_end':
                self._append_agent_message(accumulated_agent_message, merged_message)
                logger.debug("[DIFY] message_end usage: {}".format(event['metadata']['usage']))
                break
            else:
                logger.warn("[DIFY] unknown event: {}".format(event))

        if not conversation_id:
            raise Exception("conversation_id not found")

        return merged_message, conversation_id

    def _append_agent_message(self, accumulated_agent_message, merged_message):
        if accumulated_agent_message:
            merged_message.append({
                'type': 'agent_message',
                'content': accumulated_agent_message,
            })

    def _append_message_file(self, event: dict, merged_message: list):
        if event.get('type') != 'image':
            logger.warn("[DIFY] unsupported message file type: {}".format(event))
        merged_message.append({
            'type': 'message_file',
            'content': event,
        })