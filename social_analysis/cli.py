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


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
