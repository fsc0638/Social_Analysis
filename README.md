# Social Analysis

跨平台(Instagram / Threads / X)關鍵字輿情蒐集與分析系統。

## 功能

1. **多平台 collector**:依關鍵字蒐集 IG / Threads / X 公開貼文
2. **分析 pipeline**:情感、主題、熱度趨勢
3. **Dashboard**:Streamlit 互動式儀表板
4. **自動產文**:用 LLM 根據趨勢生成文章
5. **排程推送**:定期蒐集 → 分析 → 產文 → 發送

## 架構

```
social_analysis/
├── collectors/        # 各平台抓取模組 (相同介面)
│   ├── base.py        # Collector 抽象基底
│   ├── instagram.py
│   ├── threads.py
│   ├── x_twitter.py
│   └── mock.py        # 假資料,用於 PoC pipeline 驗證
├── storage/           # SQLite 持久化
├── analysis/          # 情感 / 主題 / 趨勢
├── generator/         # LLM 文章生成
├── publisher/         # 推送 (Email/Webhook/Slack)
├── dashboard/         # Streamlit app
├── scheduler/         # 排程入口
└── config.py
```

## 快速開始

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 填入 API keys
python -m social_analysis.cli collect --keyword "AI" --platforms mock
python -m social_analysis.cli analyze
streamlit run social_analysis/dashboard/app.py
```

## 資料源說明

| 平台 | 方案 | 狀態 |
|---|---|---|
| Mock | 假資料 | 預設,用於 pipeline 驗證 |
| X | twscrape / X API v2 | 需 cookie 或付費 key |
| Threads | 非官方爬蟲 | 不穩定,需 cookie |
| Instagram | instaloader hashtag | 受頻率限制 |

合規提醒:爬蟲使用受各平台 ToS 約束,僅供研究用途,商業使用請改用官方/付費 API。
