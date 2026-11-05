# --coding:utf-8--
from aomaker.send_msg.dingtalk import DingTalkSend
from aomaker.send_msg.feishu import FeishuSend
from aomaker.send_msg.generic import GenericSend
from aomaker.send_msg.wechat import WeChatSend

__all__ = ['DingTalkSend', 'FeishuSend', 'GenericSend', 'WeChatSend']
