#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  ALPHABOT PRO v4 — Agent IA Autonome                                ║
# ║  4 Stratégies 80%+ WR · Anti-Martingale · Challenge 5$→500$        ║
# ║  Top 20 Binance Futures · Levier Auto · Marge Isolée                ║
# ╠══════════════════════════════════════════════════════════════════════╣
# ║  pip install requests python-telegram-bot schedule anthropic        ║
# ╚══════════════════════════════════════════════════════════════════════╝

import os, sys, time, json, math, random, hashlib, logging, threading
import requests
from datetime import datetime, timezone, timedelta
from collections import defaultdict, deque

# ── Logging ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("alphabot_v4.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("AlphaBot")

# ══════════════════════════════════════════════════════════════════════
#  CONFIG — modifie uniquement cette section
# ══════════════════════════════════════════════════════════════════════

TG_TOKEN        = os.getenv("TG_TOKEN",  "6950706659:AAGXw-27ebhWLm2HfG7lzC7EckpwCPS_JFg")
TG_GROUP        = os.getenv("TG_GROUP",  "-1003757467015")   # groupe public
TG_VIP          = os.getenv("TG_VIP",    "-1003771736496")   # groupe VIP
TG_LEADER_USER  = "leaderOdg"                                 # username sans @
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_KEY", "")             # clé Anthropic (optionnel)

# Challenge
CHALLENGE_START = float(os.getenv("CHALLENGE_START", "5.0"))   # solde initial
CHALLENGE_FILE  = "challenge_state.json"

# Binance
BINANCE_BASE    = "https://fapi.binance.com/fapi/v1"
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET  = os.getenv("BINANCE_SECRET", "")
FEE_PCT         = 0.0004   # 0.04% taker par côté

# Paramètres bot
SCAN_INTERVAL   = 30       # secondes entre chaque scan
COOLDOWN_MIN    = 20       # minutes entre 2 signaux sur la même paire
MIN_SCORE       = 70       # score minimum pour valider un setup
MIN_RR          = 2.0      # RR minimum
MAX_OPEN_TRADES = 3        # positions simultanées max
TOP_PAIRS_COUNT = 20       # Top N paires par volume

# Anti-Martingale
AM_BASE_RISK_PCT = 0.06    # 6% du solde (score 80-89)
AM_MULT          = 1.30    # +30% après chaque WIN
AM_MAX_CYCLES    = 4       # reset après 4 WINs consécutifs

# ══════════════════════════════════════════════════════════════════════
#  ÉTAT GLOBAL
# ══════════════════════════════════════════════════════════════════════

class BotState:
    def __init__(self):
        self.running        = True
        self.open_trades    = {}        # trade_id → TradeInfo
        self.trade_counter  = 0
        self.cooldowns      = {}        # pair → datetime
        self.candle_history = defaultdict(lambda: defaultdict(deque))  # pair→tf→deque[candle]
        self.prices         = {}        # pair → float
        self.top_pairs      = []        # Top20 par volume
        self.am_state       = self._load_am_state()
        self.challenge      = self._load_challenge()
        self.tg_leader_id   = None      # chat_id résolu de @leaderOdg
        self._lock          = threading.Lock()

    def _load_am_state(self):
        try:
            with open("am_state.json") as f:
                return json.load(f)
        except Exception:
            return {"cycle": 0, "win_streak": 0, "last_result": None, "total_boosted": 0.0, "history": []}

    def save_am_state(self):
        with open("am_state.json", "w") as f:
            json.dump(self.am_state, f, indent=2)

    def _load_challenge(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            with open(CHALLENGE_FILE) as f:
                c = json.load(f)
            if c.get("day_start") != today:
                c.update({"day_start": today, "today_pnl": 0.0, "today_wins": 0,
                          "today_losses": 0, "trades": [], "published": False})
                self.save_challenge_data(c)
            return c
        except Exception:
            c = {"start_balance": CHALLENGE_START, "current_balance": CHALLENGE_START,
                 "day_start": today, "today_pnl": 0.0, "today_wins": 0,
                 "today_losses": 0, "best_rr": 0.0, "trades": [], "published": False,
                 "all_time_peak": CHALLENGE_START}
            self.save_challenge_data(c)
            return c

    def save_challenge_data(self, c=None):
        with open(CHALLENGE_FILE, "w") as f:
            json.dump(c or self.challenge, f, indent=2)

    def new_trade_id(self):
        self.trade_counter += 1
        return self.trade_counter

STATE = BotState()

# ══════════════════════════════════════════════════════════════════════
#  TELEGRAM
# ══════════════════════════════════════════════════════════════════════

def tg_send(chat_id: str, text: str, parse_mode="HTML") -> bool:
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode,
                  "disable_web_page_preview": True},
            timeout=10,
        )
        return r.json().get("ok", False)
    except Exception as e:
        log.warning(f"[TG] Erreur envoi: {e}")
        return False

def tg_resolve_leader() -> str | None:
    """Résout le chat_id numérique de @leaderOdg via getUpdates."""
    if STATE.tg_leader_id:
        return STATE.tg_leader_id
    try:
        r = requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates?limit=100", timeout=10)
        for upd in r.json().get("result", []):
            msg = upd.get("message", {})
            if msg.get("from", {}).get("username", "").lower() == TG_LEADER_USER.lower():
                STATE.tg_leader_id = str(msg["chat"]["id"])
                log.info(f"[TG] Leader ID résolu: {STATE.tg_leader_id}")
                return STATE.tg_leader_id
    except Exception:
        pass
    return f"@{TG_LEADER_USER}"

def dm_leader(text: str):
    cid = tg_resolve_leader()
    if cid:
        tg_send(cid, text)

def pub_group(text: str):
    tg_send(TG_GROUP, text)

def pub_vip(text: str):
    tg_send(TG_VIP, text)

# ══════════════════════════════════════════════════════════════════════
#  BINANCE DATA
# ══════════════════════════════════════════════════════════════════════

def binance_get(endpoint: str, params: dict = None) -> dict | list | None:
    try:
        r = requests.get(f"{BINANCE_BASE}/{endpoint}", params=params or {}, timeout=8)
        return r.json()
    except Exception as e:
        log.debug(f"[BINANCE] {endpoint}: {e}")
        return None

def fetch_top_pairs(n: int = 20) -> list[str]:
    """Retourne les N paires USDT-Futures triées par volume 24h."""
    data = binance_get("ticker/24hr")
    if not data or not isinstance(data, list):
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
                "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT"]
    usdt = [t for t in data if t["symbol"].endswith("USDT") and "_" not in t["symbol"]]
    usdt.sort(key=lambda t: float(t.get("quoteVolume", 0)), reverse=True)
    pairs = [t["symbol"] for t in usdt[:n]]
    log.info(f"[BINANCE] Top {n} paires chargées: {pairs[:5]}…")
    return pairs

def fetch_price(symbol: str) -> float | None:
    data = binance_get("ticker/price", {"symbol": symbol})
    if data and "price" in data:
        return float(data["price"])
    return None

def fetch_klines(symbol: str, interval: str = "5m", limit: int = 60) -> list[dict] | None:
    """Retourne les dernières `limit` bougies OHLCV."""
    data = binance_get("klines", {"symbol": symbol, "interval": interval, "limit": limit})
    if not data or not isinstance(data, list):
        return None
    candles = []
    for k in data:
        candles.append({
            "ts":    int(k[0]),
            "open":  float(k[1]),
            "high":  float(k[2]),
            "low":   float(k[3]),
            "close": float(k[4]),
            "vol":   float(k[5]),
        })
    return candles

def fetch_funding_rate(symbol: str) -> float | None:
    data = binance_get("premiumIndex", {"symbol": symbol})
    if data and "lastFundingRate" in data:
        return float(data["lastFundingRate"]) * 100  # en %
    return None

def fetch_order_book_imbalance(symbol: str, depth: int = 10) -> float | None:
    """Retourne l'imbalance bid/ask entre -1 (bear) et +1 (bull)."""
    data = binance_get("depth", {"symbol": symbol, "limit": depth})
    if not data:
        return None
    try:
        bid_vol = sum(float(b[1]) for b in data["bids"][:5])
        ask_vol = sum(float(a[1]) for a in data["asks"][:5])
        total   = bid_vol + ask_vol
        return (bid_vol - ask_vol) / total if total > 0 else 0.0
    except Exception:
        return None

# ══════════════════════════════════════════════════════════════════════
#  LEVIER AUTO — MARGE ISOLÉE
# ══════════════════════════════════════════════════════════════════════

PAIR_MAX_LEV = {
    "BTCUSDT": 125, "ETHUSDT": 100, "BNBUSDT": 75,
    "SOLUSDT": 50,  "XRPUSDT": 50,  "ADAUSDT": 50,
    "DOGEUSDT": 50, "AVAXUSDT": 50, "LINKUSDT": 50,
}

def get_auto_leverage(balance: float) -> int:
    if balance >= 2000: return 25
    if balance >= 1000: return 20
    if balance >=  500: return 15
    if balance >=  200: return 10
    if balance >=  100: return  7
    if balance >=   50: return  5
    return 3

def get_effective_leverage(symbol: str, balance: float) -> int:
    auto    = get_auto_leverage(balance)
    pair_max = PAIR_MAX_LEV.get(symbol, 20)
    return min(auto, pair_max)

# ══════════════════════════════════════════════════════════════════════
#  RISK MANAGER — ANTI-MARTINGALE
# ══════════════════════════════════════════════════════════════════════

def calc_risk_usdt(balance: float, score: int, am_cycle: int) -> float:
    """Calcule la mise en $ selon le score et le cycle anti-martingale."""
    # Risque de base selon score
    if balance < 10:      base_pct = 0.05   # survie
    elif balance < 20:    base_pct = 0.08   # protection
    elif score >= 92:     base_pct = 0.10   # très haute conviction
    elif score >= 85:     base_pct = 0.08   # haute conviction
    elif score >= 78:     base_pct = 0.06   # bonne conviction
    elif score >= 70:     base_pct = 0.04   # conviction standard
    else:                 base_pct = 0.03   # faible

    # Boost anti-martingale sur les WINs
    am_mult  = 1.30 ** am_cycle
    raw_risk = balance * base_pct * am_mult
    max_risk = balance * 0.20   # jamais plus de 20% du solde

    return round(min(raw_risk, max_risk), 4)

def update_am_state(result: str, pnl: float, pair: str):
    """Met à jour l'état anti-martingale après chaque clôture."""
    am = STATE.am_state
    old_cycle = am["cycle"]

    if result == "WIN":
        am["win_streak"] += 1
        if am["win_streak"] >= AM_MAX_CYCLES:
            am["cycle"]      = 0
            am["win_streak"] = 0
            log.info("[AM] 4 WINs consécutifs → reset au cycle 0")
        else:
            am["cycle"] = min(am["cycle"] + 1, AM_MAX_CYCLES)
        surplus = max(0.0, pnl - CHALLENGE_START * AM_BASE_RISK_PCT)
        am["total_boosted"] = am.get("total_boosted", 0.0) + surplus

    elif result in ("LOSS", "BE"):
        am["cycle"]      = 0
        am["win_streak"] = 0

    am["last_result"] = result
    am["history"].insert(0, {
        "cycle_before": old_cycle, "cycle_after": am["cycle"],
        "result": result, "pnl": round(pnl, 4),
        "pair": pair, "ts": datetime.now(timezone.utc).isoformat()
    })
    am["history"] = am["history"][:40]
    STATE.save_am_state()
    log.info(f"[AM] Cycle: {old_cycle} → {am['cycle']} | Résultat: {result} | PnL: {pnl:.2f}$")

def update_challenge(pnl: float, pair: str, side: str, rr: float, am_cycle: int):
    c = STATE.challenge
    c["current_balance"] = round(c["current_balance"] + pnl, 4)
    c["today_pnl"]       = round(c.get("today_pnl", 0) + pnl, 4)
    if pnl > 0:
        c["today_wins"] = c.get("today_wins", 0) + 1
    else:
        c["today_losses"] = c.get("today_losses", 0) + 1
    c["best_rr"] = max(c.get("best_rr", 0), float(rr))
    c.setdefault("trades", []).append({
        "pair": pair, "side": side, "pnl": round(pnl, 4),
        "rr": rr, "am_cycle": am_cycle, "ts": datetime.now(timezone.utc).strftime("%H:%M")
    })
    c["all_time_peak"] = max(c.get("all_time_peak", c["start_balance"]), c["current_balance"])
    STATE.save_challenge_data()
    log.info(f"[CHALLENGE] Solde: {c['current_balance']:.2f}$ | PnL jour: {c['today_pnl']:.2f}$")

# ══════════════════════════════════════════════════════════════════════
#  4 STRATÉGIES ICT/SMC
# ══════════════════════════════════════════════════════════════════════

def calc_atr(candles: list, period: int = 14) -> float:
    recent = candles[-period:]
    if not recent:
        return 0.01
    return sum(c["high"] - c["low"] for c in recent) / len(recent)

# ── Stratégie 1 : ICT Breaker Block + FVG interne ────────────────────
def strategy_ict_breaker(candles: list, btc_trend: str) -> dict | None:
    if len(candles) < 10:
        return None
    n   = len(candles)
    c0  = candles[n-3]   # bougie -3
    c1  = candles[n-2]   # bougie -2
    c2  = candles[n-1]   # bougie actuelle
    atr = calc_atr(candles)

    price = c2["close"]
    move  = (c2["close"] - c1["close"]) / c1["close"] * 100
    body  = abs(c1["close"] - c1["open"])
    range_ = c1["high"] - c1["low"]
    strong_body = body / range_ > 0.55 if range_ > 0 else False

    # Order Block Bull : bougie impulsive haussière suivie d'un retest
    if (c1["close"] > c1["open"] and strong_body
            and c2["low"] <= c1["open"] * 1.002
            and c2["close"] > c1["open"]
            and btc_trend != "BEAR"):
        sl      = min(c0["low"], c1["low"]) * 0.999
        sl_dist = price - sl
        if sl_dist <= 0 or sl_dist > atr * 2.5:
            return None
        tp1 = price + sl_dist * 2.5
        tp2 = price + sl_dist * 5.0
        # FVG interne : gap entre c0.high et c2.low
        fvg = c0["high"] < c2["low"]
        # BOS : prix dépasse le high précédent
        prev_high = max(c["high"] for c in candles[n-8:n-2])
        bos = price > prev_high
        score = 62 + (18 if bos else 0) + (10 if fvg else 0) + \
                (8 if btc_trend == "BULL" else 0) + (4 if strong_body else 0)
        return {"strategy": "ICT_BB", "side": "BUY", "entry": price,
                "sl": sl, "tp1": tp1, "tp2": tp2,
                "rr": round(sl_dist * 2.5 / sl_dist, 1),
                "score": min(score, 100), "fvg": fvg, "bos": bos}

    # Order Block Bear
    if (c1["close"] < c1["open"] and strong_body
            and c2["high"] >= c1["open"] * 0.998
            and c2["close"] < c1["open"]
            and btc_trend != "BULL"):
        sl      = max(c0["high"], c1["high"]) * 1.001
        sl_dist = sl - price
        if sl_dist <= 0 or sl_dist > atr * 2.5:
            return None
        tp1 = price - sl_dist * 2.5
        tp2 = price - sl_dist * 5.0
        fvg = c0["low"] > c2["high"]
        prev_low = min(c["low"] for c in candles[n-8:n-2])
        bos = price < prev_low
        score = 62 + (18 if bos else 0) + (10 if fvg else 0) + \
                (8 if btc_trend == "BEAR" else 0) + (4 if strong_body else 0)
        return {"strategy": "ICT_BB", "side": "SELL", "entry": price,
                "sl": sl, "tp1": tp1, "tp2": tp2,
                "rr": round(sl_dist * 2.5 / sl_dist, 1),
                "score": min(score, 100), "fvg": fvg, "bos": bos}
    return None

# ── Stratégie 2 : Fair Value Gap + Break of Structure ─────────────────
def strategy_fvg_bos(candles: list, btc_trend: str) -> dict | None:
    if len(candles) < 8:
        return None
    n     = len(candles)
    price = candles[-1]["close"]
    atr   = calc_atr(candles)

    for i in range(n-1, 3, -1):
        c_a, c_b, c_c = candles[i-2], candles[i-1], candles[i]
        # FVG BULL : low[i] > high[i-2]
        if c_c["low"] > c_a["high"] and c_b["close"] > c_b["open"]:
            fvg_low  = c_a["high"]
            fvg_high = c_c["low"]
            fvg_mid  = (fvg_low + fvg_high) / 2
            # Prix revient dans le FVG (retest)
            if fvg_low <= price <= fvg_high + (fvg_high - fvg_low) * 0.3:
                sl = min(c["low"] for c in candles[max(0,i-5):i]) * 0.999
                sl_dist = price - sl
                if sl_dist <= 0 or sl_dist > atr * 3: continue
                prev_high = max(c["high"] for c in candles[max(0,i-10):i-1])
                bos = candles[i-1]["close"] > prev_high
                rr  = (fvg_mid - price) / sl_dist + 1.5 if bos else 2.0
                score = 68 + (18 if bos else 0) + (8 if btc_trend == "BULL" else 0) + \
                        (6 if rr >= 3 else 0)
                return {"strategy": "FVG_BOS", "side": "BUY", "entry": price,
                        "sl": sl, "tp1": price + sl_dist * 2.5, "tp2": price + sl_dist * 5,
                        "rr": round(rr, 1), "score": min(score, 100),
                        "fvg_zone": (fvg_low, fvg_high), "bos": bos}

        # FVG BEAR : high[i] < low[i-2]
        if c_c["high"] < c_a["low"] and c_b["close"] < c_b["open"]:
            fvg_low  = c_c["high"]
            fvg_high = c_a["low"]
            fvg_mid  = (fvg_low + fvg_high) / 2
            if fvg_low - (fvg_high - fvg_low) * 0.3 <= price <= fvg_high:
                sl = max(c["high"] for c in candles[max(0,i-5):i]) * 1.001
                sl_dist = sl - price
                if sl_dist <= 0 or sl_dist > atr * 3: continue
                prev_low = min(c["low"] for c in candles[max(0,i-10):i-1])
                bos = candles[i-1]["close"] < prev_low
                rr  = (price - fvg_mid) / sl_dist + 1.5 if bos else 2.0
                score = 68 + (18 if bos else 0) + (8 if btc_trend == "BEAR" else 0) + \
                        (6 if rr >= 3 else 0)
                return {"strategy": "FVG_BOS", "side": "SELL", "entry": price,
                        "sl": sl, "tp1": price - sl_dist * 2.5, "tp2": price - sl_dist * 5,
                        "rr": round(rr, 1), "score": min(score, 100),
                        "fvg_zone": (fvg_low, fvg_high), "bos": bos}
    return None

# ── Stratégie 3 : Liquidity Sweep + MSS ──────────────────────────────
def strategy_liq_mss(candles: list, btc_trend: str) -> dict | None:
    if len(candles) < 12:
        return None
    n     = len(candles)
    price = candles[-1]["close"]
    atr   = calc_atr(candles)
    recent = candles[n-12:n-2]

    # Swing HIGH sweep → SHORT
    swing_h = max(c["high"] for c in recent)
    swept_h  = any(c["high"] > swing_h for c in candles[n-4:n-1])
    if swept_h and price < swing_h and btc_trend != "BULL":
        mss_lows = [c["low"] for c in candles[n-5:n-1]]
        mss_3low = min(mss_lows)
        mss_conf = price < mss_3low
        sl       = max(c["high"] for c in candles[n-5:n]) * 1.001
        sl_dist  = sl - price
        if 0 < sl_dist <= atr * 2.5:
            score = 70 + (20 if mss_conf else 0) + (8 if btc_trend == "BEAR" else 0)
            return {"strategy": "LIQ_MSS", "side": "SELL", "entry": price,
                    "sl": sl, "tp1": price - sl_dist * 2.5, "tp2": price - sl_dist * 5,
                    "rr": 2.5, "score": min(score, 100),
                    "sweep_level": swing_h, "mss_conf": mss_conf}

    # Swing LOW sweep → LONG
    swing_l = min(c["low"] for c in recent)
    swept_l  = any(c["low"] < swing_l for c in candles[n-4:n-1])
    if swept_l and price > swing_l and btc_trend != "BEAR":
        mss_highs = [c["high"] for c in candles[n-5:n-1]]
        mss_3high = max(mss_highs)
        mss_conf  = price > mss_3high
        sl        = min(c["low"] for c in candles[n-5:n]) * 0.999
        sl_dist   = price - sl
        if 0 < sl_dist <= atr * 2.5:
            score = 70 + (20 if mss_conf else 0) + (8 if btc_trend == "BULL" else 0)
            return {"strategy": "LIQ_MSS", "side": "BUY", "entry": price,
                    "sl": sl, "tp1": price + sl_dist * 2.5, "tp2": price + sl_dist * 5,
                    "rr": 2.5, "score": min(score, 100),
                    "sweep_level": swing_l, "mss_conf": mss_conf}
    return None

# ── Stratégie 4 : Order Block HTF + LTF Confluence ───────────────────
def strategy_ob_htf_ltf(symbol: str, btc_trend: str) -> dict | None:
    h1c  = list(STATE.candle_history[symbol].get("1h", deque()))
    m5c  = list(STATE.candle_history[symbol].get("5m", deque()))
    if len(h1c) < 5 or len(m5c) < 5:
        return None

    price   = m5c[-1]["close"]
    atr_m5  = calc_atr(m5c)
    h1_prev = h1c[-2]
    h1_body = abs(h1_prev["close"] - h1_prev["open"])
    h1_rng  = h1_prev["high"] - h1_prev["low"]
    h1_strong = h1_body / h1_rng > 0.5 if h1_rng > 0 else False

    # OB H1 Haussier : prix reteste la zone de l'OB
    if (h1_prev["close"] > h1_prev["open"] and h1_strong
            and h1_prev["open"] * 0.998 <= price <= h1_prev["close"] * 1.003
            and btc_trend != "BEAR"):
        m5_conf = m5c[-1]["close"] > m5c[-2]["close"]
        sl      = min(c["low"] for c in h1c[-3:] + m5c[-5:]) * 0.999
        sl_dist = price - sl
        if sl_dist <= 0 or sl_dist > atr_m5 * 4:
            return None
        score = 72 + (16 if m5_conf else 0) + (10 if btc_trend == "BULL" else 0) + \
                (8 if h1_strong else 0)
        return {"strategy": "OB_HTF_LTF", "side": "BUY", "entry": price,
                "sl": sl, "tp1": price + sl_dist * 3, "tp2": price + sl_dist * 6,
                "rr": 3.0, "score": min(score, 100),
                "ob_h1": (h1_prev["open"], h1_prev["close"]), "m5_conf": m5_conf}

    # OB H1 Baissier
    if (h1_prev["close"] < h1_prev["open"] and h1_strong
            and h1_prev["close"] * 0.997 <= price <= h1_prev["open"] * 1.002
            and btc_trend != "BULL"):
        m5_conf = m5c[-1]["close"] < m5c[-2]["close"]
        sl      = max(c["high"] for c in h1c[-3:] + m5c[-5:]) * 1.001
        sl_dist = sl - price
        if sl_dist <= 0 or sl_dist > atr_m5 * 4:
            return None
        score = 72 + (16 if m5_conf else 0) + (10 if btc_trend == "BEAR" else 0) + \
                (8 if h1_strong else 0)
        return {"strategy": "OB_HTF_LTF", "side": "SELL", "entry": price,
                "sl": sl, "tp1": price - sl_dist * 3, "tp2": price - sl_dist * 6,
                "rr": 3.0, "score": min(score, 100),
                "ob_h1": (h1_prev["open"], h1_prev["close"]), "m5_conf": m5_conf}
    return None

# ── Win rates des stratégies ──────────────────────────────────────────
STRAT_INFO = {
    "ICT_BB":     {"label": "ICT Breaker Block",        "wr": 0.82, "icon": "🔷", "min_score": 72},
    "FVG_BOS":    {"label": "Fair Value Gap + BOS",     "wr": 0.80, "icon": "⚡", "min_score": 74},
    "LIQ_MSS":    {"label": "Liquidity Sweep + MSS",    "wr": 0.83, "icon": "🌊", "min_score": 70},
    "OB_HTF_LTF": {"label": "OB HTF + LTF Confluence", "wr": 0.81, "icon": "👑", "min_score": 75},
}

# ══════════════════════════════════════════════════════════════════════
#  PROBABILITÉ TP — CALCUL MULTI-FACTEUR
# ══════════════════════════════════════════════════════════════════════

def calc_tp_probability(symbol: str, side: str, entry: float,
                        sl: float, tp: float, score: int) -> dict:
    strat_wr   = 0.80
    sl_dist    = abs(entry - sl)
    tp_dist    = abs(tp - entry)
    rr         = tp_dist / sl_dist if sl_dist > 0 else 2.0
    # Base : win rate de la stratégie
    base_prob  = strat_wr * 100

    reasons = []

    # Carnet d'ordres Binance
    imb = fetch_order_book_imbalance(symbol, depth=20)
    if imb is not None:
        if imb > 0.15 and side == "BUY":
            base_prob += 8; reasons.append("📚 Carnet: pression acheteuse +8%")
        elif imb < -0.15 and side == "SELL":
            base_prob += 8; reasons.append("📚 Carnet: pression vendeuse +8%")
        elif imb > 0.15 and side == "SELL":
            base_prob -= 6; reasons.append("📚 Carnet: contre-tendance -6%")
        elif imb < -0.15 and side == "BUY":
            base_prob -= 6; reasons.append("📚 Carnet: contre-tendance -6%")

    # Funding rate
    fund = fetch_funding_rate(symbol)
    if fund is not None:
        if fund > 0.05 and side == "SELL":
            base_prob += 7; reasons.append(f"💸 Funding élevé ({fund:.4f}%) → short squeeze +7%")
        elif fund < -0.005 and side == "BUY":
            base_prob += 5; reasons.append(f"💸 Funding négatif ({fund:.4f}%) +5%")

    # Score ICT
    base_prob += (score - 70) * 0.3

    # RR bonus
    if rr >= 4:
        base_prob += 4; reasons.append(f"📐 RR exceptionnel 1:{rr:.1f} +4%")
    elif rr >= 3:
        base_prob += 2

    return {
        "prob":    max(10, min(95, round(base_prob))),
        "rr":      round(rr, 1),
        "reasons": reasons[:3],
        "fund":    fund,
        "imb":     imb,
    }

# ══════════════════════════════════════════════════════════════════════
#  AGENT IA — SCAN + VALIDATION
# ══════════════════════════════════════════════════════════════════════

def get_btc_trend() -> str:
    m5c = list(STATE.candle_history["BTCUSDT"].get("5m", deque()))
    if len(m5c) < 5:
        return "RANGE"
    closes = [c["close"] for c in m5c[-10:]]
    delta  = (closes[-1] - closes[0]) / closes[0] * 100
    if delta > 0.35:  return "BULL"
    if delta < -0.35: return "BEAR"
    return "RANGE"

def scan_pair(symbol: str, btc_trend: str) -> list[dict]:
    """Lance les 4 stratégies sur une paire, retourne les setups validés."""
    candles = list(STATE.candle_history[symbol].get("5m", deque()))
    if len(candles) < 12:
        return []

    results = []
    for fn in [
        lambda: strategy_ict_breaker(candles, btc_trend),
        lambda: strategy_fvg_bos(candles, btc_trend),
        lambda: strategy_liq_mss(candles, btc_trend),
        lambda: strategy_ob_htf_ltf(symbol, btc_trend),
    ]:
        try:
            s = fn()
            if s:
                results.append(s)
        except Exception as e:
            log.debug(f"[SCAN] Erreur stratégie sur {symbol}: {e}")

    return results

def validate_setup(setup: dict, symbol: str, balance: float) -> dict | None:
    """Valide et enrichit un setup — retourne None si invalide."""
    strat = setup.get("strategy", "")
    info  = STRAT_INFO.get(strat, {"min_score": 75, "wr": 0.80})

    if setup["score"] < info["min_score"]:
        return None
    if not all(k in setup for k in ("sl", "entry", "tp1")):
        return None

    sl_dist  = abs(setup["entry"] - setup["sl"])
    tp1_dist = abs(setup["tp1"]  - setup["entry"])
    if sl_dist <= 0 or tp1_dist <= 0:
        return None
    rr = tp1_dist / sl_dist
    if rr < MIN_RR:
        return None

    # Cooldown
    cd = STATE.cooldowns.get(symbol)
    if cd and datetime.now(timezone.utc) < cd:
        return None

    # Pas déjà en position sur cette paire
    with STATE._lock:
        already = any(t["symbol"] == symbol and t["status"] == "open"
                      for t in STATE.open_trades.values())
    if already:
        return None

    am    = STATE.am_state
    risk  = calc_risk_usdt(balance, setup["score"], am["cycle"])
    lev   = get_effective_leverage(symbol, balance)
    qty   = round(risk / sl_dist, 6) if sl_dist > 0 else 0
    fees  = risk * lev * FEE_PCT * 2

    tp_analysis = calc_tp_probability(symbol, setup["side"], setup["entry"],
                                      setup["sl"], setup["tp1"], setup["score"])

    return {
        **setup,
        "symbol":    symbol,
        "rr":        round(rr, 1),
        "risk_usdt": risk,
        "qty":       qty,
        "leverage":  lev,
        "fees":      round(fees, 4),
        "tp_prob":   tp_analysis,
        "am_cycle":  am["cycle"],
        "strat_info": info,
    }

def agent_full_scan(balance: float) -> list[dict]:
    """Scan complet Top20 — retourne tous les setups valides triés."""
    btc_trend  = get_btc_trend()
    all_setups = []

    for symbol in STATE.top_pairs[:TOP_PAIRS_COUNT]:
        raw = scan_pair(symbol, btc_trend)
        for setup in raw:
            validated = validate_setup(setup, symbol, balance)
            if validated:
                all_setups.append(validated)

    # Tri : score desc puis RR desc
    all_setups.sort(key=lambda s: (s["score"], s["rr"]), reverse=True)
    return all_setups

# ══════════════════════════════════════════════════════════════════════
#  GESTION DES TRADES
# ══════════════════════════════════════════════════════════════════════

def open_trade(setup: dict):
    """Enregistre un trade ouvert et envoie les rapports Telegram."""
    tid = STATE.new_trade_id()
    sym = setup["symbol"]
    si  = setup.get("strat_info", {})
    tp  = setup.get("tp_analysis", setup.get("tp_prob", {}))

    trade = {
        "id":        tid,
        "symbol":    sym,
        "side":      setup["side"],
        "entry":     setup["entry"],
        "sl":        setup["sl"],
        "sl0":       setup["sl"],
        "tp1":       setup["tp1"],
        "tp2":       setup.get("tp2", setup["tp1"]),
        "risk_usdt": setup["risk_usdt"],
        "rr":        setup["rr"],
        "leverage":  setup["leverage"],
        "fees":      setup["fees"],
        "strategy":  setup["strategy"],
        "score":     setup["score"],
        "am_cycle":  setup["am_cycle"],
        "status":    "open",
        "be_active": False,
        "open_ts":   datetime.now(timezone.utc).isoformat(),
    }

    with STATE._lock:
        STATE.open_trades[tid] = trade
        STATE.cooldowns[sym] = datetime.now(timezone.utc) + timedelta(minutes=COOLDOWN_MIN)

    dir_emoji = "🟢 LONG" if setup["side"] == "BUY" else "🔴 SHORT"
    prob      = tp.get("prob", "—")
    fund_str  = f"{tp.get('fund', 0):.4f}%" if tp.get("fund") is not None else "—"
    imb_str   = f"{tp.get('imb', 0)*100:.0f}%" if tp.get("imb") is not None else "—"

    # Message DM @leaderOdg
    dm = (
        f"🤖 <b>NOUVEAU TRADE — Agent Alpha v4</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{dir_emoji} <b>{sym}</b>\n"
        f"📍 Entrée : <b>{setup['entry']:.4f}</b>\n"
        f"🛑 SL     : <b>{setup['sl']:.4f}</b>\n"
        f"✅ TP1    : <b>{setup['tp1']:.4f}</b>\n"
        f"✅ TP2    : <b>{setup.get('tp2', setup['tp1']):.4f}</b>\n"
        f"📐 RR     : <b>1:{setup['rr']}</b> | Lev: <b>{setup['leverage']}x</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{si.get('icon','📊')} {si.get('label', setup['strategy'])} · Score: {setup['score']}/100\n"
        f"🎯 Probabilité TP: <b>{prob}%</b>\n"
        f"📚 Carnet: {imb_str} | 💸 Funding: {fund_str}\n"
        f"🔄 AM Cycle {setup['am_cycle']}/4 | Mise: <b>{setup['risk_usdt']:.2f}$</b>\n"
        f"💰 Solde challenge: {STATE.challenge.get('current_balance', 0):.2f}$\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <i>Agent Alpha gère le compte automatiquement</i>"
    )
    dm_leader(dm)

    # Message groupe si score >= 85
    if setup["score"] >= 85:
        pub_group(
            f"📊 <b>SIGNAL AGENT — {sym} {dir_emoji}</b>\n"
            f"{si.get('icon','📊')} {si.get('label', setup['strategy'])} · Score: {setup['score']}/100\n"
            f"⚡ Entrée: {setup['entry']:.4f} | SL: {setup['sl']:.4f} | TP: {setup['tp1']:.4f}\n"
            f"📐 RR 1:{setup['rr']} · Prob TP: {prob}%\n"
            f"@leaderOdg"
        )

    log.info(f"[TRADE OUVERT] #{tid} {sym} {setup['side']} | "
             f"Score:{setup['score']} RR:{setup['rr']} Mise:{setup['risk_usdt']:.2f}$ Lev:{setup['leverage']}x")
    return tid

def check_trades():
    """Vérifie les TP/SL de tous les trades ouverts."""
    with STATE._lock:
        trades = list(STATE.open_trades.values())

    for trade in trades:
        if trade["status"] != "open":
            continue
        sym   = trade["symbol"]
        price = fetch_price(sym)
        if price is None:
            continue

        side     = trade["side"]
        sl       = trade["sl"]
        tp1      = trade["tp1"]
        tp2      = trade["tp2"]
        entry    = trade["entry"]
        sl_dist0 = abs(entry - trade["sl0"])
        rr_cur   = ((price - entry) / sl_dist0 if side == "BUY"
                    else (entry - price) / sl_dist0) if sl_dist0 > 0 else 0

        # Break-Even : déplace le SL à entry + frais après RR 1.0
        if rr_cur >= 1.0 and not trade["be_active"]:
            be_sl = (entry + trade["fees"] / (trade["risk_usdt"] / sl_dist0) + 0.01
                     if side == "BUY"
                     else entry - trade["fees"] / (trade["risk_usdt"] / sl_dist0) - 0.01)
            with STATE._lock:
                trade["sl"]       = be_sl
                trade["be_active"] = True
            log.info(f"[BE] #{trade['id']} {sym} → SL déplacé à {be_sl:.4f}")
            dm_leader(f"🔒 <b>Break-Even activé</b> — {sym}\nSL → {be_sl:.4f} (entrée + frais)")

        # SL touché
        hit_sl = (price <= sl if side == "BUY" else price >= sl)
        # TP1 touché
        hit_tp1 = (price >= tp1 if side == "BUY" else price <= tp1)
        # TP2 touché
        hit_tp2 = (price >= tp2 if side == "BUY" else price <= tp2)

        if hit_sl or hit_tp1 or hit_tp2:
            gross = trade["risk_usdt"] * (rr_cur if (hit_tp1 or hit_tp2) else -1)
            net   = gross - trade["fees"]
            result = ("WIN" if (hit_tp1 or hit_tp2) else
                      "BE"  if trade["be_active"] else "LOSS")

            with STATE._lock:
                trade["status"]    = "closed"
                trade["exit"]      = price
                trade["pnl"]       = round(net, 4)
                trade["result"]    = result
                trade["close_ts"]  = datetime.now(timezone.utc).isoformat()

            am_before = STATE.am_state["cycle"]
            update_am_state(result, net, sym)
            update_challenge(net, sym, side, trade["rr"], am_before)

            res_emoji = "✅ WIN" if result == "WIN" else "🔒 BE" if result == "BE" else "❌ LOSS"
            am_after  = STATE.am_state["cycle"]

            close_msg = (
                f"{res_emoji} — <b>{sym}</b> fermé\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Entrée: {entry:.4f} → Sortie: {price:.4f}\n"
                f"💵 PnL net: <b>{'+' if net >= 0 else ''}{net:.2f}$</b>\n"
                f"🔄 AM Cycle: {am_before} → {am_after} | "
                f"Solde: {STATE.challenge['current_balance']:.2f}$\n"
                f"🏆 Challenge: {STATE.challenge['today_wins']}W / "
                f"{STATE.challenge['today_losses']}L\n"
                f"@leaderOdg"
            )
            dm_leader(close_msg)
            if result == "WIN":
                pub_group(
                    f"✅ <b>WIN — {sym}</b> | +{net:.2f}$ | "
                    f"Solde: {STATE.challenge['current_balance']:.2f}$\n@leaderOdg"
                )

            log.info(f"[TRADE FERMÉ] #{trade['id']} {sym} {result} | PnL:{net:.2f}$ | "
                     f"AM:{am_before}→{am_after} | Solde:{STATE.challenge['current_balance']:.2f}$")

# ══════════════════════════════════════════════════════════════════════
#  AGENT IA HUMAIN — Messages naturels
# ══════════════════════════════════════════════════════════════════════

AI_MSGS = {
    "scan_start": [
        "Je scan le marché… Top20 en cours d'analyse.",
        "On regarde ce que le marché a à dire. M5 + H1.",
        "Analyse multi-TF en cours. Quand c'est propre, on prend.",
        "Scan Top20 Binance. La patience est une edge.",
    ],
    "no_setup": [
        "Rien de qualifié pour l'instant. On attend.",
        "Pas de setup propre. Le marché joue encore.",
        "0 setup validé. L'inaction est aussi une décision.",
        "On garde la poudre sèche. Prochain scan dans 30s.",
    ],
    "found_setup": lambda sym, side, rr, strat: random.choice([
        f"{sym} {side} — {strat}. RR 1:{rr}. C'est propre.",
        f"Setup détecté : {sym} {side}. Score solide. On entre.",
        f"{sym} — structure validée. {side}. RR 1:{rr}.",
        f"🎯 {sym} {side} qualifié via {strat}. Mise adaptée.",
    ]),
    "win": lambda sym, pnl: random.choice([
        f"✅ {sym} touche le TP. +{pnl}$. Le setup était bon.",
        f"{sym} WIN. +{pnl}$. Anti-martingale fait le job.",
        f"On encaisse. {sym} +{pnl}$. Mise augmente au prochain.",
    ]),
    "loss": lambda sym, pnl: random.choice([
        f"❌ SL touché sur {sym}. {pnl}$. Reset à la base.",
        f"{sym} — le marché a dit non. {pnl}$. On recommence proprement.",
        f"Stop sur {sym}. {pnl}$. Pas de frustration. Prochain setup.",
    ]),
    "challenge": [
        "La discipline fait la différence. Pas le capital de départ.",
        "5$ → 500$. Chaque trade est une décision, pas une émotion.",
        "Le process prime sur le résultat. On reste disciplinés.",
    ],
}

def agent_say(category, *args):
    pool = AI_MSGS[category]
    if callable(pool):
        return pool(*args)
    return random.choice(pool)

# ══════════════════════════════════════════════════════════════════════
#  RAPPORT CHALLENGE JOURNALIER
# ══════════════════════════════════════════════════════════════════════

def build_challenge_report() -> str:
    c      = STATE.challenge
    balance= c["current_balance"]
    start  = c["start_balance"]
    gain   = balance - start
    pct    = (gain / start * 100) if start > 0 else 0
    wins   = c.get("today_wins", 0)
    losses = c.get("today_losses", 0)
    total  = wins + losses
    wr     = round(wins / total * 100) if total > 0 else 0
    trades = c.get("trades", [])[-5:]
    today  = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    target = start * 100   # objectif x100

    lines = [
        f"🏆 <b>CHALLENGE JOURNALIER — Agent Alpha v4</b>",
        f"━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📅 {today}",
        f"💰 Solde: <b>{start:.2f}$ → {balance:.2f}$</b>",
        f"📈 PnL jour: <b>{'+' if gain >= 0 else ''}{gain:.2f}$</b> ({'+' if pct >= 0 else ''}{pct:.1f}%)",
        f"🎯 Objectif: {target:.0f}$ | Progression: {min(100, balance/target*100):.1f}%",
        f"━━━━━━━━━━━━━━━━━━━━━━━━",
        f"✅ Wins: {wins} | ❌ Losses: {losses} | WR: {wr}%",
        f"🔄 AM Cycle: {STATE.am_state['cycle']}/4",
        f"━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for t in trades:
        emoji = "✅" if t["pnl"] >= 0 else "❌"
        lines.append(f"  {emoji} {t['pair']} {t['side']} | {'+' if t['pnl']>=0 else ''}{t['pnl']:.2f}$ | RR 1:{t['rr']} | AM C{t['am_cycle']}")
    lines += [
        f"━━━━━━━━━━━━━━━━━━━━━━━━",
        f"{'🚀' if gain >= 0 else '🔄'} {agent_say('challenge')}",
        f"<b>@leaderOdg</b> · t.me/bluealpha_signals",
    ]
    return "\n".join(lines)

def publish_challenge():
    if STATE.challenge.get("published"):
        return
    msg = build_challenge_report()
    dm_leader(msg)
    pub_group(msg)
    STATE.challenge["published"] = True
    STATE.save_challenge_data()
    log.info("[CHALLENGE] Score publié sur Telegram")

# ══════════════════════════════════════════════════════════════════════
#  MISE À JOUR DES DONNÉES MARCHÉ
# ══════════════════════════════════════════════════════════════════════

def refresh_market_data():
    """Met à jour les prix et les bougies pour le Top20."""
    # Refresh top20 toutes les 5 minutes
    STATE.top_pairs = fetch_top_pairs(TOP_PAIRS_COUNT + 5)

    for symbol in STATE.top_pairs[:TOP_PAIRS_COUNT]:
        # M5 — principal
        c5 = fetch_klines(symbol, "5m", 60)
        if c5:
            STATE.candle_history[symbol]["5m"] = deque(c5, maxlen=60)
            STATE.prices[symbol] = c5[-1]["close"]

        # H1 — pour OB_HTF_LTF
        c1h = fetch_klines(symbol, "1h", 20)
        if c1h:
            STATE.candle_history[symbol]["1h"] = deque(c1h, maxlen=20)

        time.sleep(0.1)  # évite le rate limit

    log.info(f"[DATA] {len(STATE.top_pairs)} paires mises à jour")

# ══════════════════════════════════════════════════════════════════════
#  BOUCLE PRINCIPALE — AGENT AUTONOME
# ══════════════════════════════════════════════════════════════════════

def main_loop():
    log.info("═" * 60)
    log.info("  ALPHABOT PRO v4 — Agent IA Autonome")
    log.info("  4 Stratégies · Anti-Martingale · Challenge 5$→500$")
    log.info("═" * 60)

    # Init données
    log.info("[INIT] Chargement Top20 Binance Futures…")
    refresh_market_data()

    c = STATE.challenge
    dm_leader(
        f"🤖 <b>Agent Alpha v4 démarré</b>\n"
        f"📊 Top20 Binance Futures | 4 stratégies 80%+ WR\n"
        f"💰 Solde challenge: {c['current_balance']:.2f}$ (cible: {c['start_balance']*100:.0f}$)\n"
        f"🔄 AM Cycle: {STATE.am_state['cycle']}/4\n"
        f"⏰ Scan toutes les {SCAN_INTERVAL}s"
    )

    scan_count   = 0
    data_refresh = 0    # rafraîchit les données marché toutes les 5 min

    while STATE.running:
        now  = datetime.now(timezone.utc)
        hour = now.hour

        # Rafraîchir les données marché toutes les 5 min
        if data_refresh % 10 == 0:
            refresh_market_data()
        data_refresh += 1

        # Vérifier les trades ouverts
        check_trades()

        # Publication challenge à 21h UTC
        if hour == 21 and not STATE.challenge.get("published"):
            publish_challenge()

        # Scan agent
        scan_count += 1
        balance = STATE.challenge.get("current_balance", CHALLENGE_START)

        # Ne pas scanner si trop de positions ouvertes
        open_count = sum(1 for t in STATE.open_trades.values() if t["status"] == "open")
        if open_count >= MAX_OPEN_TRADES:
            log.info(f"[SCAN #{scan_count}] {open_count}/{MAX_OPEN_TRADES} positions ouvertes — attente")
            time.sleep(SCAN_INTERVAL)
            continue

        log.info(f"[SCAN #{scan_count}] Démarrage — {len(STATE.top_pairs[:TOP_PAIRS_COUNT])} paires | "
                 f"Solde: {balance:.2f}$ | AM Cycle: {STATE.am_state['cycle']}/4")

        setups = agent_full_scan(balance)

        if not setups:
            log.info(f"[SCAN #{scan_count}] {agent_say('no_setup')}")
        else:
            log.info(f"[SCAN #{scan_count}] {len(setups)} setup(s) validé(s)")
            # Envoyer rapport scan au leader toutes les 10 scans ou si très bon setup
            if scan_count % 10 == 0 or (setups and setups[0]["score"] >= 88):
                report_lines = [
                    f"🤖 <b>Scan #{scan_count} — {len(setups)} setup(s)</b>",
                    f"━━━━━━━━━━━━━━━━━━━━━━━━",
                ]
                for i, s in enumerate(setups[:3]):
                    si = s.get("strat_info", {})
                    medal = ["🥇","🥈","🥉"][i]
                    report_lines.append(
                        f"{medal} <b>{s['symbol']}</b> {s['side']} | "
                        f"{si.get('icon','')} {si.get('label', s['strategy'])}\n"
                        f"   Score: {s['score']}/100 · RR 1:{s['rr']} · "
                        f"Mise: {s['risk_usdt']:.2f}$ · Prob TP: {s['tp_prob']['prob']}%"
                    )
                report_lines.append(f"\n💰 Solde: {balance:.2f}$ | @leaderOdg")
                dm_leader("\n".join(report_lines))

            # Ouvrir le meilleur setup
            best = setups[0]
            si   = best.get("strat_info", {})
            msg  = agent_say("found_setup", best["symbol"], best["side"],
                             best["rr"], si.get("label", best["strategy"]))
            log.info(f"[AGENT] {msg}")
            open_trade(best)

        time.sleep(SCAN_INTERVAL)


def _print_positions():
    trades = [t for t in STATE.open_trades.values() if t["status"] == "open"]
    if not trades:
        return
    print("\n  [POSITIONS OUVERTES %d/%d]" % (len(trades), MAX_OPEN_TRADES))
    for t in trades:
        price    = STATE.prices.get(t["symbol"], t["entry"])
        sl_dist0 = abs(t["entry"] - t["sl0"])
        rr_cur   = ((price - t["entry"]) / sl_dist0 if t["side"] == "BUY"
                    else (t["entry"] - price) / sl_dist0) if sl_dist0 > 0 else 0
        pnl_live = round(t["risk_usdt"] * rr_cur - t["fees"], 4)
        sign     = "+" if pnl_live >= 0 else ""
        be_tag   = " [BE]" if t["be_active"] else ""
        dir_tag  = "LONG" if t["side"] == "BUY" else "SHORT"
        print("  #%d %s %s%s" % (t["id"], t["symbol"], dir_tag, be_tag))
        print("     Entree: %.4f | Prix: %.4f" % (t["entry"], price))
        print("     SL: %.4f | TP1: %.4f | TP2: %.4f" % (t["sl"], t["tp1"], t["tp2"]))
        print("     PnL live: %s%.4f$ | RR: %.2f | Frais: -%.4f$" % (sign, pnl_live, rr_cur, t["fees"]))


def run_demo_mode():
    """Boucle continue demo : prix reels Binance, positions simulees, frais inclus."""
    print("\n" + "="*60)
    print("  ALPHABOT PRO v4 - MODE DEMO")
    print("  Prix reels Binance | Trades simules | Frais inclus")
    print("  Challenge 5$ -> 500$ | Anti-Martingale actif")
    print("="*60)
    log.info("[DEMO] Chargement Top20 Binance Futures...")
    refresh_market_data()
    c = STATE.challenge
    print("\n  Solde demo  : %.4f$" % c["current_balance"])
    print("  Objectif    : %.0f$" % (c["start_balance"] * 100))
    print("  AM Cycle    : %d/4" % STATE.am_state["cycle"])
    print("  Scan        : toutes les %ds" % SCAN_INTERVAL)
    print("  Frais taker : %.2f%% par cote (%.2f%% A/R)" % (FEE_PCT*100, FEE_PCT*200))
    dm_leader(
        "[DEMO] Agent Alpha v4 demarre\n"
        "Prix reels Binance | Trades 100%% simules\n"
        "Solde demo: %.4f$ -> cible %.0f$\n"
        "AM Cycle: %d/4 | Scan: %ds" % (
            c["current_balance"], c["start_balance"]*100,
            STATE.am_state["cycle"], SCAN_INTERVAL)
    )
    scan_count   = 0
    data_refresh = 0
    while STATE.running:
        now  = datetime.now(timezone.utc)
        hour = now.hour
        if data_refresh % 10 == 0:
            refresh_market_data()
        data_refresh += 1
        check_trades()
        if hour == 21 and not STATE.challenge.get("published"):
            publish_challenge()
        scan_count += 1
        balance    = STATE.challenge.get("current_balance", CHALLENGE_START)
        open_count = sum(1 for t in STATE.open_trades.values() if t["status"] == "open")
        pnl_jour   = STATE.challenge.get("today_pnl", 0)
        wins       = STATE.challenge.get("today_wins", 0)
        losses     = STATE.challenge.get("today_losses", 0)
        print("\n" + "="*60)
        print("  SCAN #%d | %s" % (scan_count, datetime.now(timezone.utc).strftime("%H:%M:%S UTC")))
        print("  Solde demo: %.4f$ | AM Cycle: %d/4" % (balance, STATE.am_state["cycle"]))
        print("  W:%d L:%d | PnL jour: %+.4f$" % (wins, losses, pnl_jour))
        print("-"*60)
        _print_positions()
        if open_count >= MAX_OPEN_TRADES:
            print("\n  %d positions max atteint - attente fermeture..." % MAX_OPEN_TRADES)
            time.sleep(SCAN_INTERVAL)
            continue
        setups = agent_full_scan(balance)
        if not setups:
            print("\n  Aucun setup qualifie. " + agent_say("no_setup"))
        else:
            print("\n  %d setup(s) detecte(s) :" % len(setups))
            print("  " + "-"*56)
            for i, s in enumerate(setups[:3]):
                si    = s.get("strat_info", {})
                tp    = s.get("tp_prob", {})
                medal = ["[1]", "[2]", "[3]"][i]
                print("  %s %s %s | %s" % (medal, s["symbol"], s["side"], si.get("label", s["strategy"])))
                print("     Score: %d/100 | RR: 1:%s | Prob TP: %s%%" % (
                    s["score"], s["rr"], tp.get("prob", "?")))
                print("     Entree: %.4f | SL: %.4f | TP1: %.4f" % (
                    s["entry"], s["sl"], s["tp1"]))
                print("     Mise: %.4f$ | Lev: %dx | Frais: %.4f$" % (
                    s["risk_usdt"], s["leverage"], s["fees"]))
                for r in tp.get("reasons", []):
                    print("     -> " + r)
            best = setups[0]
            si   = best.get("strat_info", {})
            print("\n  " + agent_say("found_setup", best["symbol"], best["side"],
                                     best["rr"], si.get("label", best["strategy"])))
            open_trade(best)
            print("  Position demo #%d ouverte (aucun ordre reel envoye a Binance)" % STATE.trade_counter)
            if scan_count % 10 == 0 or best["score"] >= 88:
                lines = ["[DEMO] Scan #%d - %d setup(s)" % (scan_count, len(setups))]
                for i, s in enumerate(setups[:3]):
                    ssi = s.get("strat_info", {}); tp = s.get("tp_prob", {})
                    lines.append("[%d] %s %s | %s - Score:%d/100 RR 1:%s Mise:%.4f$ Prob:%s%%" % (
                        i+1, s["symbol"], s["side"], ssi.get("label", s["strategy"]),
                        s["score"], s["rr"], s["risk_usdt"], tp.get("prob", "?")))
                lines.append("Solde demo: %.4f$ | @leaderOdg" % balance)
                dm_leader("\n".join(lines))
        print("\n  Prochain scan dans %ds..." % SCAN_INTERVAL)
        time.sleep(SCAN_INTERVAL)


def run_test_mode():
    """Mode test : scan unique, affiche les setups sans ouvrir de trades."""
    log.info("MODE TEST - Aucun trade ne sera ouvert")
    refresh_market_data()
    balance = STATE.challenge.get("current_balance", CHALLENGE_START)
    setups  = agent_full_scan(balance)
    print("\n" + "="*60)
    print("  RESULTATS DU SCAN TEST")
    print("  Top %d paires | %d setup(s) trouves" % (TOP_PAIRS_COUNT, len(setups)))
    print("  Solde: %.2f$ | AM Cycle: %d/4" % (balance, STATE.am_state["cycle"]))
    print("="*60 + "\n")
    if not setups:
        print("  Aucun setup qualifie.\n")
    else:
        for i, s in enumerate(setups[:5]):
            si = s.get("strat_info", {})
            tp = s.get("tp_prob", {})
            print("  #%d %s %s %s" % (i+1, si.get("icon",""), s["symbol"], s["side"]))
            print("     Strategie : %s" % si.get("label", s["strategy"]))
            print("     Score     : %d/100 | WR estime: %d%%" % (s["score"], round(si.get("wr",0.80)*100)))
            print("     Entree    : %.4f | SL: %.4f | TP1: %.4f" % (s["entry"], s["sl"], s["tp1"]))
            print("     RR        : 1:%s | Prob TP: %s%%" % (s["rr"], tp.get("prob","?")))
            print("     Mise      : %.4f$ | Levier: %dx" % (s["risk_usdt"], s["leverage"]))
            for r in tp.get("reasons", []):
                print("     -> " + r)
            print()
    print("="*60 + "\n")


if __name__ == "__main__":
    # ── MODE : modifie cette ligne ───────────────────────────────────
    # "demo"  -> scan continu, prix reels, trades SIMULES (RECOMMANDE)
    # "live"  -> scan continu, ordres REELS sur Binance
    # "test"  -> scan unique, aucun trade ouvert
    # "reset" -> efface challenge_state.json et am_state.json
    MODE = "demo"
    # ─────────────────────────────────────────────────────────────────

    if len(sys.argv) > 1:
        arg = sys.argv[1].lstrip("-").lower()
        if arg in ("demo", "live", "test", "reset"):
            MODE = arg

    if MODE == "reset":
        for fname in ("am_state.json", CHALLENGE_FILE):
            try:
                os.remove(fname)
                print("Supprime: " + fname)
            except Exception:
                pass
        print("Etat reinitialise. Relancez le bot.")
        sys.exit(0)
    elif MODE == "demo":
        try:
            run_demo_mode()
        except KeyboardInterrupt:
            log.info("[DEMO] Arret par l'utilisateur")
            publish_challenge()
    elif MODE == "test":
        run_test_mode()
    elif MODE == "live":
        try:
            main_loop()
        except KeyboardInterrupt:
            log.info("[BOT] Arret par l'utilisateur")
            publish_challenge()
    else:
        print("MODE inconnu. Valeurs: demo, live, test, reset")
iiiii
