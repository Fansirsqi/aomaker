# --coding:utf-8--
import base64
import hashlib
import hmac
import os
import time

import requests

from aomaker.utils.gen_allure_report import CaseSummary
from aomaker.utils.utils import load_yaml
from aomaker.storage import Config
from aomaker.path import CONF_DIR
from aomaker._constants import Conf

utils_yaml_path = os.path.join(CONF_DIR, Conf.UTILS_CONF_NAME)


class FeishuSend:
    """
    飞书群机器人消息通知（interactive 卡片）

    配置在 conf/utils.yaml 的 feishu 段：
        feishu:
            webhook: https://open.feishu.cn/open-apis/bot/v2/hook/xxx
            secret:  xxxx        # 机器人开启「加签」时必填，关键词模式留空

    卡片主题色按结果自动取：有失败或阻塞 -> red，有跳过 -> orange，全通过 -> green。
    """

    # 飞书卡片 header.template 的取值
    _TEMPLATE_RED = 'red'
    _TEMPLATE_ORANGE = 'orange'
    _TEMPLATE_GREEN = 'green'

    def __init__(self, tester="古一", title="自动化测试通知", report_address=""):
        conf = load_yaml(utils_yaml_path) or {}
        self.feishu_conf = conf.get('feishu') or {}
        self.curl = (self.feishu_conf.get('webhook') or '').strip()
        self.secret = (self.feishu_conf.get('secret') or '').strip()
        if not self.curl:
            raise ValueError("conf/utils.yaml 缺少 feishu.webhook，无法发送飞书通知")

        self.headers = {"Content-Type": "application/json"}
        self.test_results = CaseSummary()
        self.total = str(self.test_results.total_count)
        self.passed = str(self.test_results.passed_count)
        self.failed = str(self.test_results.failed_count)
        self.skipped = str(self.test_results.skipped_count)
        self.broken = str(self.test_results.broken_count)
        self.passed_rate = self.test_results.passed_rate
        self.duration = self.test_results.duration
        self.config_db = Config()
        self.current_env = self.config_db.get('current_env')
        self.tester = tester
        self.title = title
        self.report_address = report_address

    def _template(self):
        """按失败/阻塞/跳过情况挑卡片主题色。"""
        if int(self.failed) > 0 or int(self.broken) > 0:
            return self._TEMPLATE_RED
        if int(self.skipped) > 0:
            return self._TEMPLATE_ORANGE
        return self._TEMPLATE_GREEN

    def _build_card(self):
        """组装飞书 interactive 卡片。"""
        content = '\n'.join([
            '**测试环境**：{}'.format(self.current_env),
            '**测试负责人**：{}'.format(self.tester),
            '',
            '**运行成功率**：{}'.format(self.passed_rate),
            '**用例总数**：{} 个'.format(self.total),
            '**成功用例数**：{} 个'.format(self.passed),
            '**失败用例数**：{} 个'.format(self.failed),
            '**阻塞用例数**：{} 个'.format(self.broken),
            '**跳过用例数**：{} 个'.format(self.skipped),
            '**执行时长**：{}'.format(self.duration),
        ])

        elements = [
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": content},
            }
        ]
        if self.report_address:
            elements.append({
                "tag": "action",
                "actions": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看测试报告"},
                    "url": self.report_address,
                    "type": "primary",
                }],
            })

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": self._template(),
                "title": {"tag": "plain_text", "content": self.title},
            },
            "elements": elements,
        }

    def _sign(self, timestamp):
        """飞书「加签」：以 "{timestamp}\n{secret}" 为密钥，对空串做 HMAC-SHA256 再 base64。"""
        key = '{}\n{}'.format(timestamp, self.secret).encode('utf-8')
        return base64.b64encode(hmac.new(key, b'', digestmod=hashlib.sha256).digest()).decode('utf-8')

    def send_msg(self):
        """发送飞书通知，返回飞书响应。

        飞书成功返回 {"code":0,...} 或 {"StatusCode":0,...}，非 0 视为失败。
        """
        json_data = {"msg_type": "interactive", "card": self._build_card()}
        if self.secret:
            timestamp = str(int(time.time()))
            json_data['timestamp'] = timestamp
            json_data['sign'] = self._sign(timestamp)

        res = requests.post(url=self.curl, json=json_data, headers=self.headers, timeout=10)
        res.raise_for_status()
        result = res.json()
        code = result.get('code', result.get('StatusCode'))
        if code not in (0, None):
            raise ValueError("飞书「interactive 卡片」消息发送失败：{}".format(result))
        return result


if __name__ == '__main__':
    FeishuSend().send_msg()
