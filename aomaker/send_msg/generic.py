# --coding:utf-8--
import json
import os

import requests

from aomaker.utils.gen_allure_report import CaseSummary
from aomaker.utils.utils import load_yaml
from aomaker.storage import Config
from aomaker.path import CONF_DIR
from aomaker._constants import Conf

utils_yaml_path = os.path.join(CONF_DIR, Conf.UTILS_CONF_NAME)


class GenericSend:
    """
    通用 webhook 通知：把测试结果摘要按 JSON POST 到任意平台。

    适合对接自建服务、Slack/Teams 中转、或尚未内置适配的平台。
    配置在 conf/utils.yaml 的 generic 段：
        generic:
            webhook: https://your-endpoint/hook
            method: POST                 # 可选，默认 POST
            headers:                     # 可选，会与默认的 Content-Type 合并
                Authorization: Bearer xxx
            payload_template: {}         # 可选，与默认摘要字段做浅合并（同名以模板为准）
    """

    def __init__(self, tester="古一", title="自动化测试通知", report_address=""):
        conf = load_yaml(utils_yaml_path) or {}
        self.generic_conf = conf.get('generic') or {}
        self.webhook = (self.generic_conf.get('webhook') or '').strip()
        if not self.webhook:
            raise ValueError("conf/utils.yaml 缺少 generic.webhook，无法发送通用 webhook 通知")
        self.method = (self.generic_conf.get('method') or 'POST').upper()
        self.extra_headers = self.generic_conf.get('headers') or {}
        self.payload_template = self.generic_conf.get('payload_template') or {}

        self.test_results = CaseSummary()
        self.config_db = Config()
        self.current_env = self.config_db.get('current_env')
        self.tester = tester
        self.title = title
        self.report_address = report_address

    def build_payload(self):
        """组装标准摘要 payload；模板里的同名字段会覆盖默认值。"""
        payload = {
            "title": self.title,
            "tester": self.tester,
            "environment": self.current_env,
            "passed_rate": self.test_results.passed_rate,
            "total": self.test_results.total_count,
            "passed": self.test_results.passed_count,
            "failed": self.test_results.failed_count,
            "broken": self.test_results.broken_count,
            "skipped": self.test_results.skipped_count,
            "duration": self.test_results.duration,
            "report_address": self.report_address,
            "report_url": self.report_address,
        }
        if isinstance(self.payload_template, dict):
            payload.update(self.payload_template)
        return payload

    def send_msg(self):
        """发送通用 webhook，返回解析后的响应（非 JSON 响应返回原始文本）。"""
        headers = {"Content-Type": "application/json"}
        if isinstance(self.extra_headers, dict):
            headers.update({str(k): str(v) for k, v in self.extra_headers.items()})

        payload = self.build_payload()
        res = requests.request(
            method=self.method,
            url=self.webhook,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers=headers,
            timeout=10,
        )
        if not 200 <= res.status_code < 300:
            raise ValueError("通用 webhook 发送失败：HTTP {} {}".format(res.status_code, res.text[:200]))
        try:
            return res.json()
        except json.JSONDecodeError:
            return res.text


if __name__ == '__main__':
    GenericSend().send_msg()
