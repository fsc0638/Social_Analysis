"""統一入口 CLI。

範例:
  python -m social_analysis.cli collect --keyword "AI" --platforms mock
  python -m social_analysis.cli analyze --keyword "AI"
  python -m social_analysis.cli report --keyword "AI"
  python -m social_analysis.cli run-all --keyword "AI" --platforms mock,x
  python -m social_analysis.cli schedule --keyword "AI" --interval-hours 6
"""
import argparse
from .collectors import get_collector
from .storage import init_db, save_posts, save_analyses, save_article, fetch_posts, fetch_analyses_joined
from .analysis import analyze_posts, compute_trends
from .generator import generate_article, publish


def cmd_collect(args):
    init_db()
    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    total = 0
    for plat in platforms:
        try:
            c = get_collector(plat)
            posts = c.search(args.keyword, limit=args.limit)
            saved = save_posts(posts)
            print(f"[{plat}] 抓到 {len(posts)} 則,新增 {saved} 筆")
            total += saved
        except Exception as e:
            print(f"[{plat}] 錯誤: {e}")
    print(f"共新增 {total} 筆貼文")


def cmd_analyze(args):
    init_db()
    posts = fetch_posts(keyword=args.keyword, limit=args.limit)
    print(f"分析 {len(posts)} 則貼文...")
    analyses = analyze_posts(posts)
    n = save_analyses(analyses)
    print(f"儲存 {n} 筆分析結果")


def cmd_report(args):
    init_db()
    df = fetch_analyses_joined(keyword=args.keyword)
    trends = compute_trends(df)
    print(f"總筆數: {trends.get('total', 0)}, 平均情感: {trends.get('avg_sentiment', 0):.2f}")
    title, body = generate_article(
        args.keyword, trends,
        fmt=args.format,
        critique=args.critique,
    )
    where = publish(title, body, target=args.publish)
    save_article(args.keyword, title, body, published_to=where)
    print(f"已產出文章: {title}\n推送目標: {where}")


def cmd_run_all(args):
    cmd_collect(args)
    cmd_analyze(args)
    cmd_report(args)


def cmd_schedule(args):
    from apscheduler.schedulers.blocking import BlockingScheduler
    sched = BlockingScheduler()

    def job():
        print(f"[scheduler] 跑 keyword={args.keyword}")
        cmd_run_all(args)

    sched.add_job(job, "interval", hours=args.interval_hours, next_run_time=None)
    print(f"排程已啟動,每 {args.interval_hours} 小時跑一次 keyword={args.keyword}")
    sched.start()


def build_parser():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp):
        sp.add_argument("--keyword", required=True)
        sp.add_argument("--limit", type=int, default=50)

    sp = sub.add_parser("collect"); add_common(sp)
    sp.add_argument("--platforms", default="mock")
    sp.set_defaults(func=cmd_collect)

    sp = sub.add_parser("analyze"); add_common(sp)
    sp.set_defaults(func=cmd_analyze)

    sp = sub.add_parser("report"); add_common(sp)
    sp.add_argument("--publish", default=None, help="file|webhook|email,預設讀 .env")
    sp.add_argument("--format", default="analysis", choices=["analysis", "brief", "social"])
    sp.add_argument("--critique", action="store_true", help="啟用 LLM self-critique 二次潤稿")
    sp.set_defaults(func=cmd_report)

    sp = sub.add_parser("run-all"); add_common(sp)
    sp.add_argument("--platforms", default="mock")
    sp.add_argument("--publish", default=None)
    sp.add_argument("--format", default="analysis", choices=["analysis", "brief", "social"])
    sp.add_argument("--critique", action="store_true")
    sp.set_defaults(func=cmd_run_all)

    sp = sub.add_parser("schedule"); add_common(sp)
    sp.add_argument("--platforms", default="mock")
    sp.add_argument("--interval-hours", type=int, default=6)
    sp.add_argument("--publish", default=None)
    sp.add_argument("--format", default="analysis", choices=["analysis", "brief", "social"])
    sp.add_argument("--critique", action="store_true")
    sp.set_defaults(func=cmd_schedule)

    return p


def _load_accounts(account_arg: str) -> list:
    from .photo_agent.account_config import AccountConfig
    if account_arg:
        return [AccountConfig.load(account_arg)]
    names = AccountConfig.list_all()
    if not names:
        print("找不到任何帳號設定。請先執行 photo-init --account <帳號名稱>")
        return []
    return [AccountConfig.load(n) for n in names]


def cmd_photo_setup(args):
    """互動式帳號設定精靈：只需帳號 + 密碼，自動登入並完成所有設定。"""
    import getpass
    from pathlib import Path
    from .photo_agent.account_config import AccountConfig

    print("┌─────────────────────────────────────┐")
    print("│   Photo Agent 帳號設定精靈           │")
    print("└─────────────────────────────────────┘\n")

    # ── 基本資料 ──────────────────────────────────────
    username = input("Instagram 帳號名稱: ").strip()
    if not username:
        print("錯誤：帳號不能為空")
        return

    config_path = Path("accounts") / username / "config.yaml"
    if config_path.exists():
        confirm = input(f"帳號 {username} 已存在，重新設定？(y/N): ").strip().lower()
        if confirm != "y":
            print("已取消")
            return

    try:
        password = getpass.getpass("Instagram 密碼（輸入時不顯示）: ")
    except Exception:
        password = input("Instagram 密碼: ")

    schedule_input = input("排程時間（直接 Enter 使用預設 08:00,20:00）: ").strip()
    schedule = schedule_input if schedule_input else "08:00,20:00"

    # ── 帳號風格設定 ──────────────────────────────────
    _STYLE_PRESETS = {
        "1": (
            "攝影 / 生活記錄",
            "- 帳號定位：日常生活攝影記錄\n"
            "- 語言：繁體中文\n"
            "- 語氣：直接自然，像在跟朋友說話，不要詩情畫意\n"
            "- 文字量：精簡，說重點就好",
        ),
        "2": (
            "車輛 / 改裝",
            "- 帳號定位：車輛攝影與改裝紀錄\n"
            "- 語言：繁體中文，可混入英文車款名稱\n"
            "- 語氣：理性、直接，像在跟車友交流\n"
            "- 重點：車型、規格細節、拍攝場景",
        ),
        "3": (
            "美食 / 餐廳",
            "- 帳號定位：美食探店記錄\n"
            "- 語言：繁體中文\n"
            "- 語氣：輕鬆活潑，帶點食慾感\n"
            "- 重點：食物外觀、口感描述、店名地點",
        ),
        "4": (
            "旅遊 / 風景",
            "- 帳號定位：旅遊與風景攝影\n"
            "- 語言：繁體中文\n"
            "- 語氣：輕描淡寫，分享實際感受，不誇大\n"
            "- 重點：地點、天氣、旅行小細節",
        ),
        "5": (
            "時尚 / 穿搭",
            "- 帳號定位：日常穿搭記錄\n"
            "- 語言：繁體中文，可適度混入英文單字\n"
            "- 語氣：簡潔有型，不囉嗦\n"
            "- 重點：服裝品牌、搭配邏輯、場合",
        ),
    }

    print("\n帳號風格（決定 AI 如何寫文案）：")
    for k, (label, _) in _STYLE_PRESETS.items():
        print(f"  {k}. {label}")
    print("  6. 自定義")

    style_choice = input("選擇風格（輸入數字）: ").strip()

    if style_choice in _STYLE_PRESETS:
        _, caption_style = _STYLE_PRESETS[style_choice]
        print(f"已套用：{_STYLE_PRESETS[style_choice][0]}")
    else:
        print("請描述這個帳號的風格（語言、語氣、內容重點，可多行，輸入空行結束）：")
        lines = []
        while True:
            line = input()
            if not line:
                break
            lines.append(f"- {line}")
        caption_style = "\n".join(lines) if lines else ""

    # ── 自動登入取得 session ───────────────────────────
    print("\n登入中...", end="", flush=True)
    try:
        from instagrapi import Client

        cl = Client()
        try:
            cl.login(username, password)
        except Exception as e:
            if "two_factor" in str(e).lower() or "challenge" in str(e).lower():
                print()
                code = input("需要雙重驗證碼: ").strip()
                cl.login(username, password, verification_code=code)
            else:
                raise

        sessionid = cl.sessionid or cl.cookie_dict.get("sessionid", "")
        csrftoken = cl.cookie_dict.get("csrftoken", "")
        user_id = str(cl.user_id)
        print(f" 成功（user_id: {user_id}）")

    except Exception as e:
        print(f" 失敗：{e}")
        return

    # ── 寫入設定 ──────────────────────────────────────
    acc = AccountConfig(
        name=username,
        ig_username=username,
        ig_password=password,
        ig_session_id=sessionid,
        ig_csrftoken=csrftoken,
        threads_sessionid=sessionid,
        threads_csrftoken=csrftoken,
        threads_ds_user_id=user_id,
        ig_post_feed=True,
        ig_post_story=True,
        threads_post=True,
        schedule=schedule,
        caption_style=caption_style,
    )
    acc.init_dirs()
    cl.dump_settings(str(acc.session_file))
    acc.save()

    print(f"\n設定完成！")
    print(f"  設定檔  : accounts/{username}/config.yaml")
    print(f"  照片佇列: accounts/{username}/queue/")
    print(f"  排程    : {schedule}")
    print(f"\n下一步：把照片丟入 accounts/{username}/queue/，然後執行：")
    print(f"  python -m social_analysis.cli photo-post --account {username}")


def cmd_photo_refresh(args):
    """重新登入並更新指定帳號的 session（session 過期時使用）。"""
    import getpass
    from .photo_agent.account_config import AccountConfig

    acc = AccountConfig.load(args.account)
    print(f"重新登入帳號: {acc.ig_username}")

    try:
        password = getpass.getpass("Instagram 密碼: ")
    except Exception:
        password = input("Instagram 密碼: ")

    print("登入中...", end="", flush=True)
    try:
        from instagrapi import Client
        cl = Client()
        try:
            cl.login(acc.ig_username, password)
        except Exception as e:
            if "two_factor" in str(e).lower() or "challenge" in str(e).lower():
                print()
                code = input("雙重驗證碼: ").strip()
                cl.login(acc.ig_username, password, verification_code=code)
            else:
                raise

        sessionid = cl.sessionid or cl.cookie_dict.get("sessionid", "")
        csrftoken = cl.cookie_dict.get("csrftoken", "")
        user_id = str(cl.user_id)
        print(f" 成功（user_id: {user_id}）")

        acc.ig_password = password
        acc.ig_session_id = sessionid
        acc.ig_csrftoken = csrftoken
        acc.threads_sessionid = sessionid
        acc.threads_csrftoken = csrftoken
        acc.threads_ds_user_id = user_id
        acc.init_dirs()
        cl.dump_settings(str(acc.session_file))
        acc.save()
        print(f"Session 已更新: {acc.base_dir}/config.yaml")

    except Exception as e:
        print(f" 失敗：{e}")


def cmd_photo_accounts(args):
    """列出所有已設定的帳號。"""
    from .photo_agent.account_config import AccountConfig
    names = AccountConfig.list_all()
    if not names:
        print("尚無任何帳號（accounts/ 目錄下找不到 config.yaml）")
        return
    print(f"共 {len(names)} 個帳號：")
    for name in names:
        acc = AccountConfig.load(name)
        pending_count = len(acc.queue_dir.glob("*")) if acc.queue_dir.exists() else 0
        platforms = ", ".join(filter(None, [
            "IG Feed" if acc.ig_post_feed else "",
            "IG Story" if acc.ig_post_story else "",
            "Threads" if acc.threads_post else "",
        ]))
        print(f"  {name:20s}  佇列: {pending_count} 張  排程: {acc.schedule}  平台: {platforms}")


def cmd_photo_post(args):
    from .photo_agent.agent import PhotoAgent
    accounts = _load_accounts(args.account)
    for acc in accounts:
        PhotoAgent(acc).run_once(dry_run=args.dry_run)


def cmd_photo_status(args):
    from .photo_agent.account_config import AccountConfig
    from .photo_agent.queue import PhotoQueue
    accounts = _load_accounts(args.account)
    for acc in accounts:
        q = PhotoQueue(str(acc.queue_dir), str(acc.posted_dir), str(acc.failed_dir))
        pending = q.list_pending()
        print(f"\n[{acc.name}] 佇列: {len(pending)} 張")
        for p in pending:
            print(f"  {p.name}")


def cmd_photo_engage(args):
    """手動觸發一次互動巡迴。"""
    from .photo_agent.engager import run_session
    accounts = _load_accounts(args.account)
    for acc in accounts:
        run_session(acc)


# 互動巡迴時段設定（每個時段在區間內隨機選一個時間點觸發）
_ENGAGE_WINDOWS = [
    (9, 30, 10, 0),    # 09:30–10:00
    (12, 30, 13, 30),  # 12:30–13:30
    (17, 0, 18, 0),    # 17:00–18:00
    (21, 30, 22, 30),  # 21:30–22:30
]


def _random_time_in_window(h_start, m_start, h_end, m_end):
    """在時段內隨機選一個 (hour, minute)。"""
    import random
    start_total = h_start * 60 + m_start
    end_total = h_end * 60 + m_end
    chosen = random.randint(start_total, end_total)
    return chosen // 60, chosen % 60


def cmd_photo_schedule(args):
    from apscheduler.schedulers.blocking import BlockingScheduler
    from .photo_agent.agent import PhotoAgent
    from .photo_agent.engager import run_session
    import random
    import threading
    from datetime import datetime as _dt

    accounts = _load_accounts(args.account)
    if not accounts:
        return

    sched = BlockingScheduler()

    # ── 發文排程 ──────────────────────────────────────
    for acc in accounts:
        agent = PhotoAgent(acc)
        for t in [t.strip() for t in acc.schedule.split(",") if t.strip()]:
            hour, minute = map(int, t.split(":"))
            sched.add_job(
                agent.run_once, "cron",
                hour=hour, minute=minute,
                id=f"post_{acc.name}_{t}",
            )
            print(f"[scheduler] {acc.name} 每天 {t} 發文")

    # ── 互動巡迴排程（四個時段，每天重新隨機化時間點）──
    def _schedule_engage_jobs(catchup: bool = False):
        """移除舊的 engage jobs 並重新以隨機時間點排入今天的巡迴。
        catchup=True 時，對今天已過的時段立刻在背景補跑一次。"""
        now = _dt.now()
        now_total = now.hour * 60 + now.minute

        for acc in accounts:
            if not acc.engage_hashtags:
                continue
            for i, (hs, ms, he, me) in enumerate(_ENGAGE_WINDOWS):
                job_id = f"engage_{acc.name}_w{i}"
                try:
                    sched.remove_job(job_id)
                except Exception:
                    pass
                h, m = _random_time_in_window(hs, ms, he, me)
                sched.add_job(
                    run_session, "cron",
                    args=[acc],
                    hour=h, minute=m,
                    id=job_id,
                )
                print(f"[scheduler] {acc.name} 互動巡迴 時段{i+1} → {h:02d}:{m:02d}")

                # 補跑：排程器啟動時若該時段已過，立刻在背景執行一次
                if catchup:
                    window_end = he * 60 + me
                    if now_total > window_end:
                        print(f"[scheduler] {acc.name} 時段{i+1} 已過，立刻補跑")
                        threading.Thread(
                            target=run_session, args=[acc], daemon=True
                        ).start()

    # 每天 00:01 重新隨機化各時段時間點
    sched.add_job(_schedule_engage_jobs, "cron", hour=0, minute=1, id="daily_reschedule")
    # 啟動時先跑一次，並補跑已過的時段
    _schedule_engage_jobs(catchup=True)

    print("[scheduler] 啟動，按 Ctrl+C 停止")
    try:
        sched.start()
    except KeyboardInterrupt:
        print("\n[scheduler] 已停止")


def build_parser():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp):
        sp.add_argument("--keyword", required=True)
        sp.add_argument("--limit", type=int, default=50)

    sp = sub.add_parser("collect"); add_common(sp)
    sp.add_argument("--platforms", default="mock")
    sp.set_defaults(func=cmd_collect)

    sp = sub.add_parser("analyze"); add_common(sp)
    sp.set_defaults(func=cmd_analyze)

    sp = sub.add_parser("report"); add_common(sp)
    sp.add_argument("--publish", default=None, help="file|webhook|email,預設讀 .env")
    sp.add_argument("--format", default="analysis", choices=["analysis", "brief", "social"])
    sp.add_argument("--critique", action="store_true", help="啟用 LLM self-critique 二次潤稿")
    sp.set_defaults(func=cmd_report)

    sp = sub.add_parser("run-all"); add_common(sp)
    sp.add_argument("--platforms", default="mock")
    sp.add_argument("--publish", default=None)
    sp.add_argument("--format", default="analysis", choices=["analysis", "brief", "social"])
    sp.add_argument("--critique", action="store_true")
    sp.set_defaults(func=cmd_run_all)

    sp = sub.add_parser("schedule"); add_common(sp)
    sp.add_argument("--platforms", default="mock")
    sp.add_argument("--interval-hours", type=int, default=6)
    sp.add_argument("--publish", default=None)
    sp.add_argument("--format", default="analysis", choices=["analysis", "brief", "social"])
    sp.add_argument("--critique", action="store_true")
    sp.set_defaults(func=cmd_schedule)

    # Photo Agent 指令
    sp = sub.add_parser("photo-setup", help="互動式帳號設定精靈（自動登入，一鍵完成）")
    sp.set_defaults(func=cmd_photo_setup)

    sp = sub.add_parser("photo-refresh", help="重新登入並更新指定帳號的 session")
    sp.add_argument("--account", required=True, help="帳號名稱")
    sp.set_defaults(func=cmd_photo_refresh)

    sp = sub.add_parser("photo-accounts", help="列出所有已設定的帳號")
    sp.set_defaults(func=cmd_photo_accounts)

    sp = sub.add_parser("photo-post", help="從佇列取下一張照片並發文")
    sp.add_argument("--account", default="", help="指定帳號，不填則執行所有帳號")
    sp.add_argument("--dry-run", action="store_true", help="只顯示文案，不實際發文")
    sp.set_defaults(func=cmd_photo_post)

    sp = sub.add_parser("photo-status", help="顯示照片佇列狀態")
    sp.add_argument("--account", default="", help="指定帳號，不填則顯示所有帳號")
    sp.set_defaults(func=cmd_photo_status)

    sp = sub.add_parser("photo-schedule", help="啟動排程自動發文 + 互動巡迴")
    sp.add_argument("--account", default="", help="指定帳號，不填則執行所有帳號")
    sp.set_defaults(func=cmd_photo_schedule)

    sp = sub.add_parser("photo-engage", help="手動觸發一次互動巡迴（按愛心）")
    sp.add_argument("--account", default="", help="指定帳號，不填則執行所有帳號")
    sp.set_defaults(func=cmd_photo_engage)

    return p


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
