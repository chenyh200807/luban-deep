"""B6 Gate: both miniprogram apps must implement WeChat Privacy Framework.

WeChat base lib >= 2.32.3 enforces __usePrivacyCheck__ for apps collecting
personal data (phone number, profile, login). Missing it causes review rejection
or forced offline.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent

WX_MP = REPO_ROOT / "wx_miniprogram"
YOUSEN = REPO_ROOT / "yousenwebview"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_wx_miniprogram_app_json_has_privacy_check_flag():
    cfg = _load_json(WX_MP / "app.json")
    assert cfg.get("__usePrivacyCheck__") is True, (
        'wx_miniprogram/app.json must have "__usePrivacyCheck__": true '
        "(WeChat base lib >= 2.32.3 requirement for apps using personal data APIs)"
    )


def test_yousenwebview_app_json_has_privacy_check_flag():
    cfg = _load_json(YOUSEN / "app.json")
    assert cfg.get("__usePrivacyCheck__") is True, (
        'yousenwebview/app.json must have "__usePrivacyCheck__": true'
    )


def test_wx_miniprogram_app_js_registers_privacy_handler():
    src = (WX_MP / "app.js").read_text(encoding="utf-8")
    assert "onNeedPrivacyAuthorization" in src, (
        "wx_miniprogram/app.js must register wx.onNeedPrivacyAuthorization "
        "before any personal-data API call"
    )
    assert re.search(r'resolve\(\s*\{\s*event\s*:\s*[\'"]agree[\'"]', src), (
        "wx_miniprogram/app.js privacy handler must call resolve({event:'agree'}) on consent"
    )


def test_yousenwebview_app_js_registers_privacy_handler():
    src = (YOUSEN / "app.js").read_text(encoding="utf-8")
    assert "onNeedPrivacyAuthorization" in src, (
        "yousenwebview/app.js must register wx.onNeedPrivacyAuthorization"
    )
    assert re.search(r'resolve\(\s*\{\s*event\s*:\s*[\'"]agree[\'"]', src), (
        "yousenwebview/app.js privacy handler must call resolve({event:'agree'}) on consent"
    )
