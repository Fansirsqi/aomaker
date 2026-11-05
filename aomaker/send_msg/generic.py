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

# 只允许能把 JSON 放在请求体里的方法。GET/HEAD 之类会把摘要丢掉且不报错，
# 与其静默失败，不如在配置阶段就拒绝。
_ALLOWED_METHODS = ('POST', 'PUT', 'PATCH')


class GenericSend:
    """
    通用 webhook 通知：把测试结果摘要按 JSON 请求体发到任意平台。

    适合对接自建服务、Slack/Teams 中转、或尚未内置适配的平台。
    注意：这里产出的是「摘要字段」协议（见 build_payload），
    面向的是能直接消费该结构的服务；若目标平台要求 text/blocks/卡片等专有结构，
    请用 payload_template 覆盖，或自己写一个适配器，而不是指望默认字段直接兼容。

    配置在 conf/utils.yaml 的 generic 段：
        generic:
            webhook: https://your-endpoint/hook
            method: POST                 # 可选，默认 POST，仅支持 POST/PUT/PATCH
            headers:                     # 可选，必须为字典；值为 None 的键会被跳过
                Authorization: Bearer xxx
            payload_template: {}         # 可选，必须为字典；与默认摘要做浅合并（同名覆盖）
    """

    def __init__(self, tester="古一", title="自动化测试通知", report_address=""):
        conf = load_yaml(utils_yaml_path) or {}
        generic_conf = conf.get('generic') or {}
        if not isinstance(generic_conf, dict):
            raise ValueError("conf/utils.yaml 的 generic 段应为字典，实际是 {}".format(type(generic_conf).__name__))
        self.generic_conf = generic_conf

        self.webhook = str(generic_conf.get('webhook') or '').strip()
        if not self.webhook:
            raise ValueError("conf/utils.yaml 缺少 generic.webhook，无法发送通用 webhook 通知")

        method = generic_conf.get('method') or 'POST'
        if not isinstance(method, str):
            raise ValueError("conf/utils.yaml 的 generic.method 应为字符串，实际是 {}".format(type(method).__name__))
        self.method = method.strip().upper()
        if self.method not in _ALLOWED_METHODS:
            raise ValueError(
                "conf/utils.yaml 的 generic.method 只支持 {}，实际配置为 {}".format(
                    '/'.join(_ALLOWED_METHODS), self.method))

        self.extra_headers = self._dict_or_raise(generic_conf.get('headers'), 'generic.headers')
        self.payload_template = self._dict_or_raise(generic_conf.get('payload_template'), 'generic.payload_template')

        self.test_results = CaseSummary()
        # 只用来读一次环境名，读掉就关连接（与 wechat.py 用完即关的口径一致，但更早释放）
        self.config_db = Config()
        try:
            self.current_env = self.config_db.get('current_env')
        finally:
            self.config_db.close()
        self.tester = tester
        self.title = title
        self.report_address = report_address

    @staticmethod
    def _dict_or_raise(value, key):
        """只接受 None 或字典；None 归一化为空字典，其它类型直接报错。

        写成字符串/列表时若静默忽略，会表现为「发送成功但平台没收到所需字段」，
        比直接报错难排查得多。
        """
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("conf/utils.yaml 的 {} 应为字典或留空，实际是 {}".format(key, type(value).__name__))
        return value

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
        payload.update(self.payload_template)
        return payload

    def send_msg(self):
        """发送通用 webhook，返回解析后的响应（响应不是 JSON 时返回原始文本）。"""
        headers = {"Content-Type": "application/json"}
        # 值为 None 的 header 直接跳过，避免变成字面量字符串 "None"
        headers.update({str(k): str(v) for k, v in self.extra_headers.items() if v is not None})

        payload = self.build_payload()
        res = requests.request(
            method=self.method,
            url=self.webhook,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers=headers,
            timeout=10,
        )
        if not 200 <= res.status_code < 300:
            raise ValueError("通用 webhook 发送失败：HTTP {}，响应摘要：{}".format(res.status_code, res.text[:200]))
        try:
            return res.json()
        except (json.JSONDecodeError, requests.exceptions.JSONDecodeError):
            # 用 requests 的异常类型兜底：安装了 simplejson 时解码异常不一定是标准库那个
            return res.text


if __name__ == '__main__':
    GenericSend().send_msg()
