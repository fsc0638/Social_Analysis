"""競品帳號分析：自動搜尋風格相似帳號、抽取 15% 貼文、GPT-4o 統整分析、記憶結果。

設計原則：
- 每次最多分析 10 個帳號
- 每帳號隨機抽取 15% 貼文
- 7 天內不重複分析同一帳號
- 結果存入 memory/competitor_analysis/
"""
from __future__ import annotations

import base64
import json
import math
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

import re

import httpx

from .account_config import AccountConfig
from ..config import settings

# ── 常數 ─────────────────────────────────────────────────────────────────────
_MEMORY_DIR        = Path("memory/competitor_analysis")
_INDEX_FILE        = _MEMORY_DIR / "_index.json"
_MIN_FOLLOWERS     = 3000        # 最低粉絲門檻
_SAMPLE_RATIO      = 0.15        # 抽取 15% 貼文
_MIN_SAMPLE        = 5           # 至少抽幾篇
_MAX_SAMPLE        = 50          # 最多抽幾篇（避免太貴）
_MAX_ACCOUNTS      = 10          # 每次執行最多分析幾個帳號
_COOLDOWN_DAYS     = 7           # 同帳號冷卻天數
_HASHTAG_FETCH     = 20          # 每個 hashtag 取幾個帳號候選
_REQUEST_DELAY     = 2           # 請求間隔（秒）


# ── 索引管理 ─────────────────────────────────────────────────────────────────

def _load_index() -> dict:
    _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if _INDEX_FILE.exists():
        with open(_INDEX_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_index(index: dict) -> None:
    with open(_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def _is_cooldown(username: str, index: dict) -> bool:
    if username not in index:
        return False
    last = datetime.fromisoformat(index[username]["analyzed_at"])
    return datetime.now(timezone.utc) - last < timedelta(days=_COOLDOWN_DAYS)


def _mark_analyzed(username: str, index: dict, report_path: str) -> None:
    index[username] = {
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "report": report_path,
    }


# ── 帳號發現 ─────────────────────────────────────────────────────────────────

def _discover_candidates(cl, hashtags: list[str], index: dict, account_name: str) -> list:
    """從 hashtag 搜尋符合條件的帳號候選。"""
    seen_users: set[str] = set()
    candidates = []

    random.shuffle(hashtags)
    for tag in hashtags:
        if len(candidates) >= _MAX_ACCOUNTS * 3:
            break
        try:
            medias = cl.hashtag_medias_recent_v1(tag, amount=_HASHTAG_FETCH)
            for m in medias:
                uid = str(m.user.pk)
                username = m.user.username
                if uid in seen_users or username == account_name:
                    continue
                seen_users.add(uid)
                if _is_cooldown(username, index):
                    print(f"  [discover] @{username} 冷卻中（7天內已分析），跳過")
                    continue
                # 取完整用戶資料確認粉絲數
                try:
                    user_info = cl.user_info(uid)
                    if user_info.follower_count >= _MIN_FOLLOWERS and not user_info.is_private:
                        candidates.append(user_info)
                        print(f"  [discover] 候選 @{username}（粉絲 {user_info.follower_count:,}）")
                except Exception:
                    pass
                time.sleep(_REQUEST_DELAY)
        except Exception as e:
            print(f"  [discover] #{tag} 搜尋失敗: {e}")
        time.sleep(_REQUEST_DELAY)

    # 依粉絲數排序，保留最多 MAX_ACCOUNTS 個
    candidates.sort(key=lambda u: u.follower_count, reverse=True)
    return candidates[:_MAX_ACCOUNTS]


# ── 貼文抽樣 ─────────────────────────────────────────────────────────────────

def _sample_medias(cl, user_pk: str, total_posts: int) -> list:
    """隨機抽取 15% 貼文，數量限制在 MIN_SAMPLE ~ MAX_SAMPLE 之間。"""
    n = max(_MIN_SAMPLE, min(_MAX_SAMPLE, math.ceil(total_posts * _SAMPLE_RATIO)))
    # 多取一些再隨機抽樣
    fetch_amount = min(total_posts, n * 3)
    try:
        medias = cl.user_medias_v1(user_pk, amount=fetch_amount)
        if len(medias) <= n:
            return medias
        return random.sample(medias, n)
    except Exception as e:
        print(f"  [sample] 取貼文失敗: {e}")
        return []


# ── 圖片下載 ─────────────────────────────────────────────────────────────────

def _fetch_image_b64(url: str) -> str | None:
    try:
        r = httpx.get(str(url), timeout=10, follow_redirects=True)
        if r.status_code == 200:
            return base64.b64encode(r.content).decode()
    except Exception:
        pass
    return None


# ── GPT-4o 統整分析 ──────────────────────────────────────────────────────────

_ANALYSIS_PROMPT = """\
你是社群媒體策略分析師。以下是 Instagram 帳號 @{username} 的基本資料與隨機抽樣的 {n} 篇貼文。

【帳號基本資料】
- 粉絲數：{followers:,}
- 追蹤數：{following:,}
- 總貼文數：{media_count:,}
- Bio：{bio}

【抽樣貼文（共 {n} 篇）】
{posts_text}

【分析任務】
請針對這個帳號進行深度分析，輸出以下內容（繁體中文）：

1. **帳號定位**（一句話）
2. **內容特徵**：主題分布、視覺風格、拍攝手法
3. **文案風格**：語氣、長度、結構、語言
4. **Hashtag 策略**：常用標籤類型、數量、選擇邏輯
5. **互動率分析**：哪類貼文互動最高？為什麼？
6. **人氣關鍵原因**（列出 TOP 3）
7. **可借鑑的關鍵字清單**（10–20 個，可直接用於 hashtag 或文案）
8. **對目標帳號的具體啟示**：{our_account} 可以學習哪些具體做法

請以結構化 Markdown 輸出，不要輸出 JSON。"""


def _gpt_analyze(username: str, user_info, medias: list, our_account: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key)

    posts_lines = []
    images_content = []

    for i, m in enumerate(medias, 1):
        caption = (m.caption_text or "（無文案）").replace("\n", " ").strip()[:200]
        likes = getattr(m, "like_count", 0) or 0
        comments = getattr(m, "comment_count", 0) or 0
        posts_lines.append(
            f"[{i}] 讚:{likes} 留言:{comments}\n    文案：{caption}"
        )
        # 加入前 5 張圖片做視覺分析
        if i <= 5:
            thumb = getattr(m, "thumbnail_url", None)
            if thumb:
                b64 = _fetch_image_b64(str(thumb))
                if b64:
                    images_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"},
                    })

    posts_text = "\n".join(posts_lines)
    prompt = _ANALYSIS_PROMPT.format(
        username=username,
        followers=user_info.follower_count,
        following=user_info.following_count,
        media_count=user_info.media_count,
        bio=(user_info.biography or "").replace("\n", " "),
        n=len(medias),
        posts_text=posts_text,
        our_account=our_account,
    )

    content: list = [{"type": "text", "text": prompt}] + images_content

    resp = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=2000,
        messages=[{"role": "user", "content": content}],
    )
    return resp.choices[0].message.content.strip()


# ── 儲存報告 ─────────────────────────────────────────────────────────────────

def _save_report(username: str, analysis: str, user_info, n_sampled: int) -> Path:
    _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    filename = f"{username}_{date_str}.md"
    path = _MEMORY_DIR / filename

    header = (
        f"# @{username} 競品分析報告\n\n"
        f"**分析日期**：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"**粉絲數**：{user_info.follower_count:,}\n"
        f"**總貼文數**：{user_info.media_count:,}\n"
        f"**本次抽樣**：{n_sampled} 篇（約 {_SAMPLE_RATIO:.0%}）\n\n---\n\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + analysis)

    print(f"  [report] 已儲存：{path}")
    return path


# ── 主流程 ───────────────────────────────────────────────────────────────────

def _make_client(account: AccountConfig):
    """建立並驗證 instagrapi Client，處理 GraphQL 被封鎖的備用登入流程。"""
    from instagrapi import Client

    cl = Client()
    session_file = Path("accounts") / account.name / "session.json"
    if session_file.exists():
        cl.load_settings(str(session_file))

    sid = unquote(account.ig_session_id)
    try:
        cl.login_by_sessionid(sid)
    except Exception as e:
        # 備用路徑：Instagram 封鎖 user_info_v1 / GraphQL 驗證時，
        # 手動建立 session（跳過 API 驗證），讓後續 feed/hashtag API 自行決定是否有效。
        print(f"  [login] login_by_sessionid 失敗（{type(e).__name__}），切換無驗證登入...")
        user_id = re.search(r"^\d+", sid).group()
        cl.settings["cookies"] = {"sessionid": sid}
        cl.init()                                     # 設定 HTTP session 與 device headers
        cl.authorization_data = {
            "ds_user_id": user_id,
            "sessionid": sid,
            "should_use_header_over_cookies": True,
        }
        cl.private.cookies.set("ds_user_id", user_id)
        cl.private.headers.update(cl.base_headers)
        cl.private.headers.update({"Authorization": cl.authorization})
        cl.username = account.ig_username
        print(f"  [login] session 建立完成（@{cl.username}，略過 API 驗證）")

    # 儲存 session 供下次使用（保留 device headers，避免重複被擋）
    session_file.parent.mkdir(parents=True, exist_ok=True)
    cl.dump_settings(str(session_file))
    return cl


def run_competitor_analysis(
    account: AccountConfig,
    target_username: str | None = None,
) -> list[str]:
    """執行競品分析，回傳本次分析的帳號名稱列表。"""
    cl = _make_client(account)
    print(f"[analyzer] @{account.ig_username} 登入成功")

    index = _load_index()
    analyzed = []

    # 指定帳號模式
    if target_username:
        targets_info = []
        try:
            ui = cl.user_info_by_username_v1(target_username)
            if _is_cooldown(target_username, index):
                print(f"[analyzer] @{target_username} 7 天內已分析，略過")
                return []
            targets_info = [ui]
        except Exception as e:
            print(f"[analyzer] 找不到 @{target_username}: {e}")
            return []
    else:
        print(f"[analyzer] 從 {len(account.engage_hashtags)} 個 hashtag 搜尋候選帳號...")
        targets_info = _discover_candidates(cl, account.engage_hashtags, index, account.ig_username)

    if not targets_info:
        print("[analyzer] 無符合條件的帳號可分析")
        return []

    print(f"\n[analyzer] 本次將分析 {len(targets_info)} 個帳號\n{'='*50}")

    for user_info in targets_info:
        username = user_info.username
        print(f"\n[analyzer] 分析 @{username}（粉絲 {user_info.follower_count:,}，共 {user_info.media_count} 篇）")

        # 抽樣貼文
        medias = _sample_medias(cl, str(user_info.pk), user_info.media_count)
        if not medias:
            print(f"[analyzer] @{username} 取不到貼文，跳過")
            continue
        print(f"[analyzer] 抽樣 {len(medias)} 篇，開始 AI 分析...")

        # GPT-4o 分析
        try:
            analysis = _gpt_analyze(username, user_info, medias, account.ig_username)
        except Exception as e:
            print(f"[analyzer] @{username} AI 分析失敗: {e}")
            continue

        # 儲存報告
        report_path = _save_report(username, analysis, user_info, len(medias))
        _mark_analyzed(username, index, str(report_path))
        _save_index(index)
        analyzed.append(username)

        print(f"[analyzer] ✓ @{username} 分析完成")
        time.sleep(_REQUEST_DELAY)

    print(f"\n[analyzer] 完成，共分析 {len(analyzed)} 個帳號：{analyzed}")
    return analyzed
