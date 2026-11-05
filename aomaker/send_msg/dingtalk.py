# --coding:utf-8--
import base64
import hashlib
import hmac
import os
import time
import urllib.parse

import requests

from aomaker.utils.gen_allure_report import CaseSummary
from aomaker.utils.utils import load_yaml
from aomaker.storage import Config
from aomaker.path import CONF_DIR
from aomaker._constants import Conf

utils_yaml_path = os.path.join(CONF_DIR, Conf.UTILS_CONF_NAME)


class DingTalkSend:
    """
    钉钉群机器人消息通知（markdown 类型）

    配置在 conf/utils.yaml 的 dingtalk 段：
        dingtalk:
            webhook: https://oapi.dingtalk.com/robot/send?access_token=xxx
            secret:  SECxxx          # 机器人开启「加签」时必填，未开启留空
    """

    def __init__(self, tester="古一", title="自动化测试通知", report_address=""):
        conf = load_yaml(utils_yaml_path) or {}
        self.dingtalk_conf = conf.get('dingtalk') or {}
        self.webhook = (self.dingtalk_conf.get('webhook') or '').strip()
        self.secret = (self.dingtalk_conf.get('secret') or '').strip()
        if not self.webhook:
            raise ValueError("conf/utils.yaml 缺少 dingtalk.webhook，无法发送钉钉通知")

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

    def _signed_url(self):
        """开启加签时，把 timestamp 与 sign 拼到 webhook 上。

        钉钉规则：stringToSign = "{timestamp}\n{secret}"，
        以 secret 为密钥做 HMAC-SHA256，再 base64 并 urlencode。
        """
        if not self.secret:
            return self.webhook
        timestamp = str(round(time.time() * 1000))
        string_to_sign = '{}\n{}'.format(timestamp, self.secret)
        hmac_code = hmac.new(
            self.secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256,
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        joiner = '&' if '?' in self.webhook else '?'
        return '{}{}timestamp={}&sign={}'.format(self.webhook, joiner, timestamp, sign)

    def _build_markdown(self):
        """组装 markdown 正文：尽量一屏看完，失败数用粗体突出。"""
        lines = [
            '### {}'.format(self.title),
            '',
            '- **测试环境**：{}'.format(self.current_env),
            '- **测试负责人**：{}'.format(self.tester),
            '',
            '**执行结果**',
            '',
            '- 运行成功率：{}'.format(self.passed_rate),
            '- 用例总数：{} 个'.format(self.total),
            '- 成功用例数：{} 个'.format(self.passed),
            '- 失败用例数：**{} 个**'.format(self.failed),
            '- 阻塞用例数：**{} 个**'.format(self.broken),
            '- 跳过用例数：{} 个'.format(self.skipped),
            '- 执行时长：{}'.format(self.duration),
        ]
        if self.report_address:
            lines.extend(['', '[查看测试报告]({})'.format(self.report_address)])
        return '\n'.join(lines)

    def send_msg(self):
        """发送钉钉通知，返回钉钉响应。"""
        json_data = {
            "msgtype": "markdown",
            "markdown": {
                "title": self.title,
                "text": self._build_markdown(),
            },
        }
        res = requests.post(url=self._signed_url(), json=json_data, headers=self.headers, timeout=10)
        res.raise_for_status()
        result = res.json()
        if result.get('errcode') != 0:
            raise ValueError("钉钉「MarkDown类型」消息发送失败：{}".format(result))
        return result


if __name__ == '__main__':
    DingTalkSend().send_msg()
