from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
import json
import os
import re
import time

BASE_URL = "https://openapi.sosovalue.com/openapi/v1"
ROOT = Path(__file__).resolve().parent
CURRENCY_CACHE = {"expires": 0, "data": None}
SNAPSHOT_CACHE = {}
NEWS_CACHE = {}
KLINE_CACHE = {}

ALIASES = {
    "BTC": ["BTC", "BITCOIN", "比特币", "大饼"],
    "ETH": ["ETH", "ETHEREUM", "以太坊"],
    "SOL": ["SOL", "SOLANA"],
    "DOGE": ["DOGE", "DOGECOIN", "狗狗币"],
    "BNB": ["BNB", "BINANCE"],
    "XRP": ["XRP", "RIPPLE"],
    "ADA": ["ADA", "CARDANO"],
    "AVAX": ["AVAX", "AVALANCHE"],
    "LINK": ["LINK", "CHAINLINK"],
    "TON": ["TON", "TONCOIN"],
    "PEPE": ["PEPE"],
    "SHIB": ["SHIB", "SHIBA"],
    "WIF": ["WIF", "DOGWIFHAT"],
}
STOP_TOKENS = {"THE", "AND", "ETF", "FOMO", "NEWS", "TODAY", "BUY", "SELL", "USD", "USDT", "IS", "UP", "DOWN", "BEFORE", "MISS", "SHOULD", "EVERYONE", "LOOKS", "BULLISH", "BEARISH", "NOW", "JUMP", "TRENDING", "SOCIAL", "MEDIA", "WANT"}
RECOMMENDATIONS = {
    "cool_down": {"en": "Cool down", "zh": "先冷静"},
    "watch_only": {"en": "Watch only", "zh": "只观察"},
    "plan_first": {"en": "Plan first", "zh": "先写计划"},
}
PROFILE = {"beginner": {"limit": 2, "offset": -4}, "curious": {"limit": 3, "offset": 0}, "active": {"limit": 4, "offset": 5}}


def load_env():
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.strip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def unwrap(payload):
    return payload.get("data", payload) if isinstance(payload, dict) else payload


def soso_get(path, params=None):
    key = os.environ.get("SOSO_API_KEY")
    if not key:
        raise RuntimeError("Missing SOSO_API_KEY")
    query = f"?{urlencode(params)}" if params else ""
    request = Request(
        f"{BASE_URL}{path}{query}",
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
            "Origin": "https://sosovalue.com",
            "Referer": "https://sosovalue.com/",
            "x-soso-api-key": key,
        },
    )
    try:
        with urlopen(request, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
            body = payload.get("message") or body
        except json.JSONDecodeError:
            pass
        raise RuntimeError(f"SoSoValue API HTTP {exc.code}: {body}") from exc


def cached(cache, key, ttl, path, params=None):
    now = time.time()
    hit = cache.get(key)
    if hit and hit["expires"] > now:
        return hit["data"]
    data = soso_get(path, params)
    cache[key] = {"expires": now + ttl, "data": data}
    return data


def currencies():
    now = time.time()
    if CURRENCY_CACHE["data"] is not None and CURRENCY_CACHE["expires"] > now:
        return CURRENCY_CACHE["data"]
    data = unwrap(soso_get("/currencies"))
    CURRENCY_CACHE["data"] = data
    CURRENCY_CACHE["expires"] = now + 900
    return data


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def item_id(item):
    return item.get("currency_id") or item.get("id")


def item_name(item):
    return str(item.get("name") or item.get("full_name") or item.get("symbol") or "")


def item_symbol(item):
    return str(item.get("symbol") or item.get("ticker") or item_name(item) or "UNKNOWN").upper()


def coin_url(item):
    base = item_name(item) or item_symbol(item)
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    return f"https://sosovalue.com/coins/{slug}" if slug else "https://sosovalue.com"


def tokens(text):
    return {t for t in re.findall(r"\b[A-Za-z0-9]{2,20}\b", text.upper()) if t not in STOP_TOKENS}


def known_asset(text):
    upper = text.upper()
    for asset, aliases in ALIASES.items():
        if any(alias.upper() in upper for alias in aliases):
            return asset
    return "UNKNOWN"


def find_currency(text):
    query_tokens = tokens(text)
    upper = text.upper()
    for item in walk(currencies()):
        if not isinstance(item, dict) or not item_id(item):
            continue
        values = [str(item.get(k, "")) for k in ("name", "symbol", "ticker", "full_name") if item.get(k)]
        upper_values = {v.upper() for v in values}
        if query_tokens.intersection(upper_values):
            return item_symbol(item), str(item_id(item)), item
        for value in values:
            if len(value) >= 4 and value.upper() in upper:
                return item_symbol(item), str(item_id(item)), item
    fallback = known_asset(text)
    if fallback != "UNKNOWN":
        for item in walk(currencies()):
            vals = {str(item.get(k, "")).upper() for k in ("name", "symbol", "ticker", "full_name")}
            if fallback in vals and item_id(item):
                return fallback, str(item_id(item)), item
    raise RuntimeError("No supported currency could be detected from the user input")


def search_items(query, limit=8):
    q = query.strip().lower()
    if not q:
        return []
    found = []
    for item in walk(currencies()):
        if not isinstance(item, dict) or not item_id(item):
            continue
        symbol = item_symbol(item)
        name = item_name(item)
        haystack = f"{symbol} {name}".lower()
        if q not in haystack:
            continue
        score = 0 if symbol.lower() == q else 1 if symbol.lower().startswith(q) else 2 if name.lower().startswith(q) else 3
        found.append((score, len(symbol), {"asset": symbol, "symbol": symbol, "name": name, "currency_id": str(item_id(item)), "url": coin_url(item)}))
    found.sort(key=lambda row: (row[0], row[1], row[2]["name"]))
    return [row[2] for row in found[:limit]]


def as_float(value, fallback=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def as_percent(value):
    number = as_float(value)
    return number * 100 if abs(number) <= 1 else number


def fmt_usd(value):
    number = as_float(value)
    if number >= 1_000_000_000:
        return f"${number / 1_000_000_000:.2f}B"
    if number >= 1_000_000:
        return f"${number / 1_000_000:.2f}M"
    if number >= 1:
        return f"${number:,.2f}"
    return f"${number:.4f}"


def compact_news(payload):
    items = payload.get("list", payload) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    titles = []
    for item in items[:3]:
        if not isinstance(item, dict):
            continue
        title = item.get("title") or item.get("highlight", {}).get("title")
        if title:
            titles.append(re.sub(r"<[^>]+>", "", str(title)).replace("&amp;", "&"))
    return titles


def trend_from_klines(payload, limit=14):
    data = payload[-limit:] if isinstance(payload, list) else []
    points = []
    for item in data:
        if not isinstance(item, dict):
            continue
        close = as_float(item.get("close"), None)
        if close is not None:
            points.append({"timestamp": item.get("timestamp"), "close": close, "volume": as_float(item.get("volume"), None)})
    return points


def coverage(snapshot, news, trend):
    return [
        {"key": "price", "label": "Price", "ok": snapshot.get("price") is not None},
        {"key": "volume", "label": "Volume", "ok": snapshot.get("turnover_24h") is not None},
        {"key": "marketcap", "label": "Market cap", "ok": snapshot.get("marketcap") is not None},
        {"key": "news", "label": "News", "ok": bool(news)},
        {"key": "trend", "label": "K-line", "ok": bool(trend)},
    ]


def strength(items):
    ok = sum(1 for item in items if item.get("ok"))
    return "high" if ok >= 4 else "medium" if ok >= 2 else "low"


def score_report(thought, change, volume, rank, news):
    text = thought.lower()
    points = [
        {"key": "priceMove", "label": "Price move", "points": min(30, round(abs(change) * 2))},
        {"key": "newsPressure", "label": "News pressure", "points": 12 if news else 0},
        {"key": "socialPressure", "label": "Social pressure", "points": 18 if any(w in text for w in ("twitter", "social", "trending", "朋友", "群里", "大家")) else 0},
        {"key": "urgency", "label": "Urgency", "points": 16 if any(w in text for w in ("now", "immediately", "马上", "现在", "冲", "miss")) else 0},
        {"key": "liquidityRisk", "label": "Liquidity risk", "points": 14 if as_float(volume) < 100_000_000 else 7 if as_float(volume) < 1_000_000_000 else 0},
        {"key": "marketCapRisk", "label": "Market-cap risk", "points": 10 if str(rank).isdigit() and int(rank) > 50 else -5 if str(rank).isdigit() and int(rank) <= 10 else 0},
        {"key": "missingPlan", "label": "Missing plan", "points": 2 if any(w in text for w in ("stop", "止损", "计划", "仓位")) else 12},
    ]
    return max(0, min(95, 35 + sum(item["points"] for item in points))), points


def shape(report, profile):
    cfg = PROFILE.get(profile, PROFILE["beginner"])
    if report.get("riskKey") not in ("noAssetRisk", "dataUnavailableRisk"):
        report["score"] = max(0, min(99, int(report["score"]) + cfg["offset"]))
    else:
        report["score"] = 0
    limit = cfg["limit"]
    report["evidence"] = report["evidence"][:limit]
    report["counter"] = report["counter"][:limit]
    report["actions"] = report["actions"][:limit]
    return report


def live_report(thought, lang, profile):
    asset, cid, citem = find_currency(thought)
    snapshot = unwrap(cached(SNAPSHOT_CACHE, cid, 20, f"/currencies/{cid}/market-snapshot"))
    news_payload = unwrap(cached(NEWS_CACHE, asset, 60, "/news/search", {"keyword": asset, "page": 1, "page_size": 5}))
    news = compact_news(news_payload)
    try:
        trend = trend_from_klines(unwrap(cached(KLINE_CACHE, f"{cid}:1d", 60, f"/currencies/{cid}/klines", {"interval": "1d"})))
    except Exception:
        trend = []
    change = as_percent(snapshot.get("change_pct_24h"))
    volume = snapshot.get("turnover_24h")
    rank = snapshot.get("marketcap_rank")
    score, breakdown = score_report(thought, change, volume, rank, news)
    rec = "cool_down" if score >= 78 else "plan_first"
    zh = lang == "zh"
    direction = "上涨" if change > 0 and zh else "下跌" if change < 0 and zh else "up" if change > 0 else "down" if change < 0 else "flat"
    evidence = [
        f"{asset} 24h {direction} {change:.2f}%，当前价格约 {fmt_usd(snapshot.get('price'))}。" if zh else f"{asset} is {direction} {change:.2f}% over 24h; current price is about {fmt_usd(snapshot.get('price'))}.",
        f"24h 成交额约 {fmt_usd(volume)}，市值约 {fmt_usd(snapshot.get('marketcap'))}，市值排名 #{rank or '--'}。" if zh else f"24h turnover is about {fmt_usd(volume)}; market cap is about {fmt_usd(snapshot.get('marketcap'))}; rank is #{rank or '--'}.",
    ]
    if news:
        evidence.append(("SoSoValue 相关新闻：" if zh else "SoSoValue related headline: ") + news[0])
    counter = [
        "价格变化本身还不足以构成交易理由。" if zh else "The price move alone is not enough to justify a trade.",
        "技术面：先看下一段 K 线是否确认，不要追在第一根情绪线上。" if zh else "Technical: wait for the next candle to confirm; do not chase the first emotional candle.",
        "没有入场价、失效条件和仓位上限时，仍然不是完整交易计划。" if zh else "Without entry, invalidation, and position size, this is not a complete trade plan.",
    ]
    actions = [
        "写下交易理由，以及什么情况说明你判断错了。" if zh else "Write the trade reason and what would prove it wrong.",
        "如果没有止损、止盈和持有时间，就不要执行。" if zh else "Do not execute unless stop, target, and holding time are defined.",
        "打开 SoSoValue 页面复核更多细节。" if zh else "Open the SoSoValue coin page for more detail.",
    ]
    cov = coverage(snapshot, news, trend)
    report = {
        "source": "live",
        "asset": asset,
        "market": {"price": as_float(snapshot.get("price"), None), "change_24h": change, "volume_24h": as_float(volume, None), "marketcap": as_float(snapshot.get("marketcap"), None)},
        "score": score,
        "riskKey": "highRisk" if score >= 80 else "mediumRisk",
        "triggerKey": "triggerPrice" if abs(change) >= 5 else "triggerNews",
        "cooldownKey": "cooldown30",
        "fomoTypes": ["Price chase" if change >= 5 else "Market curiosity"] + (["News FOMO"] if news else []),
        "recommendation": RECOMMENDATIONS[rec][lang],
        "decisionReasons": [
            f"FOMO 分数 {score}，先补齐交易计划。" if zh else f"FOMO score is {score}; complete the trade plan first.",
            f"24h 波动 {change:.2f}% 需要冷静复核。" if zh else f"The 24h move is {change:.2f}%, so review calmly.",
            "新闻只能作为线索，不能单独作为买入理由。" if zh else "A headline is a lead, not a complete thesis.",
        ],
        "scoreBreakdown": breakdown,
        "trend": trend,
        "apiEvidence": {"asset": asset, "links": {"coin": coin_url(citem)}, "coverage": cov, "strength": strength(cov), "generated_at": datetime.now(timezone.utc).isoformat(), "endpoints": ["GET /currencies", "GET /currencies/{currency_id}/market-snapshot", "GET /currencies/{currency_id}/klines", "GET /news/search"], "fields": {"currency_id": cid, "currency_name": item_name(citem), "price": snapshot.get("price"), "change_pct_24h": change, "turnover_24h": volume, "marketcap": snapshot.get("marketcap"), "marketcap_rank": rank, "news_headline": news[0] if news else None}},
        "evidence": evidence,
        "counter": counter,
        "actions": actions,
    }
    return shape(report, profile)


def fallback(asset, lang, profile, reason):
    zh = lang == "zh"
    report = {
        "source": "unavailable",
        "asset": asset or "UNKNOWN",
        "market": {"price": None, "change_24h": None, "volume_24h": None, "marketcap": None},
        "score": 0,
        "riskKey": "dataUnavailableRisk",
        "triggerKey": "triggerNews",
        "cooldownKey": "cooldown30",
        "fomoTypes": [],
        "recommendation": RECOMMENDATIONS["watch_only"][lang],
        "decisionReasons": ["实时数据不可用，先不要交易。" if zh else "Live data is unavailable; do not trade from this state."],
        "scoreBreakdown": [],
        "trend": [],
        "apiEvidence": {"asset": asset, "coverage": [], "strength": "low", "generated_at": datetime.now(timezone.utc).isoformat(), "endpoints": ["POST /api/fomo-check"], "fields": {"error": reason}},
        "evidence": [f"{asset} 已识别，但无法读取 SoSoValue 实时行情。" if zh else f"{asset} was detected, but SoSoValue live data could not be loaded."],
        "counter": ["没有实时价格、成交量和市值时，不应该形成强结论。" if zh else "Without live price, volume, and market cap, do not form a strong conclusion."],
        "actions": ["检查 API Key 后重试。" if zh else "Check the API key and retry."],
    }
    return shape(report, profile)


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/search-assets":
            query = parse_qs(parsed.query).get("q", [""])[0]
            try:
                body = {"results": search_items(query)}
            except Exception as exc:
                body = {"results": [], "error": str(exc)}
            self.send_json(body)
            return
        super().do_GET()

    def do_POST(self):
        if self.path != "/api/fomo-check":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        thought = str(payload.get("thought") or payload.get("asset") or "")
        lang = "zh" if payload.get("lang") == "zh" else "en"
        profile = payload.get("profile") if payload.get("profile") in PROFILE else "beginner"
        asset = known_asset(thought)
        try:
            report = live_report(thought, lang, profile)
        except Exception as exc:
            report = fallback(asset, lang, profile, str(exc))
        self.send_json(report)

    def send_json(self, value):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    load_env()
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"FOMO Firewall running at http://127.0.0.1:{port}")
    server.serve_forever()
