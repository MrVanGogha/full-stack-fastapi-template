from __future__ import annotations

import logging
from dataclasses import dataclass
import json

from alibabacloud_dysmsapi20170525.client import Client as DysmsapiClient
from alibabacloud_dysmsapi20170525.models import SendSmsRequest
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_util import models as util_models
from alibabacloud_tea_util.client import Client as UtilClient

from app.core.config import settings

logger = logging.getLogger(__name__)


def _mask_phone(phone: str) -> str:
    digits = ''.join(ch for ch in phone if ch.isdigit())
    if len(digits) < 7:
        return digits
    return digits[:3] + '****' + digits[-4:]


class SMSProvider:
    async def send_login_code(self, phone_number: str, code: str) -> None:
        raise NotImplementedError


@dataclass
class ConsoleSMSProvider(SMSProvider):
    async def send_login_code(self, phone_number: str, code: str) -> None:
        masked = _mask_phone(phone_number)
        logger.info(f"[SMS:console] Send login code {code} to {masked}")


@dataclass
class AliyunSMSProvider(SMSProvider):
    access_key_id: str
    access_key_secret: str
    sign_name: str
    template_code_login: str
    region_id: str = "cn-hangzhou"
    template_param_code_key: str = "code"

    def _create_client(self) -> DysmsapiClient:
        config = open_api_models.Config(
            access_key_id=self.access_key_id,
            access_key_secret=self.access_key_secret,
        )
        config.region_id = self.region_id
        config.endpoint = "dysmsapi.aliyuncs.com"
        return DysmsapiClient(config)

    async def send_login_code(self, phone_number: str, code: str) -> None:
        client = self._create_client()
        template_param = json.dumps({self.template_param_code_key: code}, ensure_ascii=False)
        req = SendSmsRequest(
            phone_numbers=phone_number,
            sign_name=self.sign_name,
            template_code=self.template_code_login,
            template_param=template_param,
        )
        runtime = util_models.RuntimeOptions()
        runtime.readTimeout = 15000  # ms
        runtime.connectTimeout = 5000  # ms
        runtime.maxAttempts = 3
        try:
            resp = client.send_sms_with_options(req, runtime)
            body = resp.body
            code_val = getattr(body, "code", None)
            msg_val = getattr(body, "message", None)
            req_id = getattr(body, "request_id", None)
            masked = _mask_phone(phone_number)
            if code_val != "OK":
                logger.error(f"Aliyun SMS failed for {masked}: Code={code_val}, Message={msg_val}, RequestId={req_id}")
                raise RuntimeError(f"Aliyun SMS failed: {code_val} {msg_val}")
        except Exception as e:
            masked = _mask_phone(phone_number)
            try:
                UtilClient.assert_as_string(e)
            except Exception:
                pass
            logger.exception(f"Aliyun SDK error for {masked}")
            raise


@dataclass
class TencentSMSProvider(SMSProvider):
    secret_id: str
    secret_key: str
    sdk_app_id: str
    sign_name: str
    template_id_login: str

    async def send_login_code(self, phone_number: str, code: str) -> None:
        logger.warning("[SMS:tencent] Placeholder implementation in use. Falling back to console log.")
        masked = _mask_phone(phone_number)
        logger.info(f"[SMS:tencent] Would send login code {code} to {masked} with sign '{self.sign_name}', template '{self.template_id_login}'")


def get_sms_provider() -> SMSProvider:
    provider = settings.SMS_PROVIDER

    # 本地环境统一使用 ConsoleProvider，避免误发短信
    # if settings.ENVIRONMENT == "local":
    #     return ConsoleSMSProvider()

    if provider == "aliyun":
        if not (settings.ALIYUN_ACCESS_KEY_ID and settings.ALIYUN_ACCESS_KEY_SECRET and settings.ALIYUN_SIGN_NAME and settings.ALIYUN_TEMPLATE_CODE_LOGIN):
            logger.error("Aliyun SMS configuration incomplete. Falling back to console provider.")
            return ConsoleSMSProvider()
        return AliyunSMSProvider(
            access_key_id=settings.ALIYUN_ACCESS_KEY_ID,
            access_key_secret=settings.ALIYUN_ACCESS_KEY_SECRET,
            sign_name=settings.ALIYUN_SIGN_NAME,
            template_code_login=settings.ALIYUN_TEMPLATE_CODE_LOGIN,
            region_id=settings.ALIYUN_REGION_ID,
            template_param_code_key=settings.ALIYUN_TEMPLATE_PARAM_CODE_KEY,
        )

    if provider == "tencent":
        if not (settings.TENCENT_SECRET_ID and settings.TENCENT_SECRET_KEY and settings.TENCENT_SDK_APP_ID and settings.TENCENT_SIGN_NAME and settings.TENCENT_TEMPLATE_ID_LOGIN):
            logger.error("Tencent SMS configuration incomplete. Falling back to console provider.")
            return ConsoleSMSProvider()
        return TencentSMSProvider(
            secret_id=settings.TENCENT_SECRET_ID,
            secret_key=settings.TENCENT_SECRET_KEY,
            sdk_app_id=settings.TENCENT_SDK_APP_ID,
            sign_name=settings.TENCENT_SIGN_NAME,
            template_id_login=settings.TENCENT_TEMPLATE_ID_LOGIN,
        )

    return ConsoleSMSProvider()


async def send_login_code(phone_number: str, code: str) -> None:
    provider = get_sms_provider()
    try:
        await provider.send_login_code(phone_number, code)
    except Exception:
        logger.exception("Failed to send SMS login code")