from __future__ import annotations

import requests

from .config import Settings


class PushError(RuntimeError):
    pass


def push_markdown(title: str, markdown: str, settings: Settings) -> None:
    channel = settings.push_channel
    if channel in {"", "none", "off", "false"}:
        raise PushError("PUSH_CHANNEL is not configured for a real push.")
    if channel == "serverchan":
        _push_serverchan(title, markdown, settings)
        print("微信推送成功")
        return
    if channel == "pushplus":
        _push_pushplus(title, markdown, settings)
        print("微信推送成功")
        return
    raise PushError(f"Unsupported PUSH_CHANNEL: {channel}")


def _push_serverchan(title: str, markdown: str, settings: Settings) -> None:
    if not settings.serverchan_sendkey:
        raise PushError("SERVERCHAN_SENDKEY is required for ServerChan.")
    print("准备推送到 Server酱")
    url = f"https://sctapi.ftqq.com/{settings.serverchan_sendkey}.send"
    response = requests.post(url, data={"title": title, "desp": markdown}, timeout=20)
    _raise_for_response(response, "ServerChan")


def _push_pushplus(title: str, markdown: str, settings: Settings) -> None:
    if not settings.pushplus_token:
        raise PushError("PUSHPLUS_TOKEN is required for PushPlus.")
    print("准备推送到 PushPlus")
    response = requests.post(
        "https://www.pushplus.plus/send",
        json={
            "token": settings.pushplus_token,
            "title": title,
            "content": markdown,
            "template": "markdown",
        },
        timeout=20,
    )
    _raise_for_response(response, "PushPlus")


def _raise_for_response(response: requests.Response, channel_name: str) -> None:
    if response.status_code >= 400:
        raise PushError(f"{channel_name} HTTP {response.status_code}: {response.text[:200]}")
    try:
        payload = response.json()
    except ValueError:
        return
    code = payload.get("code")
    if code not in (0, 200, "0", "200", None):
        raise PushError(f"{channel_name} rejected message: {payload}")
