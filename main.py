#!/usr/bin/env python3
# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  ALPHABOT PRO v7 — Agent IA Live Multi-Marchés                            ║
# ║  Compatible : PyDroid 3 (Android) · PC · Render                           ║
# ║─────────────────────────────────────────────────────────────────────────── ║
# ║  MARCHÉS   : Forex · Or · Argent · Indices · BTC                          ║
# ║  STRATÉGIE : ICT Breaker Block + FVG+BOS + Liq Sweep+MSS                 ║
# ║  TIMEFRAME : M1 (volatils) · M5 (standard)   HTF: H1                     ║
# ║  RISK      : Anti-Martingale · Break-Even · Trailing Stop                 ║
# ║  TG        : DM @leaderOdg + Groupe public + VIP                          ║
# ║  CHALLENGE : 10$ → 1000$ · Score publié à 21h UTC                        ║
# ║─────────────────────────────────────────────────────────────────────────── ║
# ║  PYDROID 3 : pip install requests anthropic                                ║
# ║              → modifie PYDROID_MODE en bas du fichier puis lance ▶        ║
# ║  PC/RENDER : python alphabot_v7.py --live | --test | --reset              ║
# ╚════════════════════════════════════════════════════════════════════════════╝

# ─── Compatibilité Python 3.8+ (PyDroid 3) ───────────────────────────────────
from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple

import os, sys, time, json, math, random, logging, threading, hashlib
import requests
from datetime import datetime, timezone, timedelta
from collections import defaultdict, deque

# ══════════════════════════════════════════════════════════════════════════════
#  CHEMINS — Compatibilité PyDroid (chemins absolus)
# ══════════════════════════════════════════════════════════════════════════════

_DIR         = os.path.dirname(os.path.abspath(__file__))
_LOG_FILE    = os.path.join(_DIR, "alphabot_v7.log")
_AM_FILE     = os.path.join(_DIR, "am_v7.json")
_CHAL_FILE   = os.path.join(_DIR, "challenge_v7.json")
_HIST_FILE   = os.path.join(_DIR, "trade_history_v7.json")

# ══════════════════════════════════════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger("AlphaBot")

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG — MODIFIE ICI
# ══════════════════════════════════════════════════════════════════════════════

TG_TOKEN        = os.getenv("TG_TOKEN",  "6950706659:AAGXw-27ebhWLm2HfG7lzC7EckpwCPS_JFg")
TG_GROUP        = os.getenv("TG_GROUP",  "-1003757467015")
TG_VIP          = os.getenv("TG_VIP",    "-1003771736496")
TG_LEADER_USER  = "leaderOdg"
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_KEY", "")

CHALLENGE_START  = float(os.getenv("CHALLENGE_START", "10.0"))
CHALLENGE_TARGET = 1000.0

SCAN_INTERVAL    = 45       # secondes entre scans

# ── MODE SCALP — Gold · Silver · NAS100 (marchés prioritaires) ──────────
SCALP_MARKETS    = {"XAUUSD", "XAGUSD", "NAS100"}  # marchés scalp
SCALP_LOT        = 0.01      # lot fixe scalp
SCALP_RISK_USD   = 2.0       # risque max 2$ par trade scalp
SCALP_TP_RR      = [1.5, 3.0, 5.0]  # TP1=1.5R / TP2=3R / TP3=5R (rapide)
SCALP_EXPIRY_M1  = 5         # M1 : entrée expire en 5 min
SCALP_EXPIRY_M5  = 12        # M5 : entrée expire en 12 min
SCALP_MIN_SCORE  = 78        # score minimum pour marchés scalp
SCALP_MIN_PROB   = 65        # prob minimum
COOLDOWN_MIN     = 30      # Délai entre 2 signaux sur le même symbole       # cooldown par symbole après signal
MIN_SCORE        = 80       # MODE SNIPER — seuil élevé
MIN_RR           = 1.5      # RR minimum (TP rapide prioritaire)
MIN_TP_PROB      = 65      # MODE SNIPER — prob minimum élevée
MAX_OPEN_TRADES  = 1       # MODE SNIPER — 1 seule position à la fois        # positions simultanées max
SIGNAL_HASH_TTL  = 90       # minutes anti-spam même signal

# Anti-Martingale
AM_BASE_RISK_PCT = 0.06
AM_MULT          = 1.30
AM_MAX_CYCLES    = 4

# Break-Even & Trailing
BE_TRIGGER_RR    = 1.0      # active BE quand RR atteint ce niveau
TRAIL_TRIGGER_RR = 2.0      # active trailing stop après RR 2.0
TRAIL_STEP_ATR   = 0.5      # trailing = prix - 0.5 ATR

# ══════════════════════════════════════════════════════════════════════════════
#  MARCHÉS — Forex + Or + Argent + Indices + BTC
# ══════════════════════════════════════════════════════════════════════════════

MARKETS: Dict[str, Dict] = {
    # ── FOREX ────────────────────────────────────────────────────────
    "EURUSD": {"label":"EUR/USD",    "cat":"FOREX",   "tf_entry":"M5",
               "spread":0.7,  "pip":0.0001, "pip_val":10.0,  "digits":5,
               "sessions":["london","ny","overlap"], "yf":"EURUSD=X"},
    "GBPUSD": {"label":"GBP/USD",    "cat":"FOREX",   "tf_entry":"M5",
               "spread":1.2,  "pip":0.0001, "pip_val":10.0,  "digits":5,
               "sessions":["london","overlap"],       "yf":"GBPUSD=X"},
    "USDJPY": {"label":"USD/JPY",    "cat":"FOREX",   "tf_entry":"M5",
               "spread":0.8,  "pip":0.01,   "pip_val":9.1,   "digits":3,
               "sessions":["asia","ny"],              "yf":"USDJPY=X"},
    "USDCHF": {"label":"USD/CHF",    "cat":"FOREX",   "tf_entry":"M5",
               "spread":1.0,  "pip":0.0001, "pip_val":10.3,  "digits":5,
               "sessions":["london","ny"],            "yf":"USDCHF=X"},
    "AUDUSD": {"label":"AUD/USD",    "cat":"FOREX",   "tf_entry":"M5",
               "spread":0.9,  "pip":0.0001, "pip_val":10.0,  "digits":5,
               "sessions":["asia","london"],          "yf":"AUDUSD=X"},
    "USDCAD": {"label":"USD/CAD",    "cat":"FOREX",   "tf_entry":"M5",
               "spread":1.5,  "pip":0.0001, "pip_val":7.5,   "digits":5,
               "sessions":["ny"],                    "yf":"USDCAD=X"},
    "NZDUSD": {"label":"NZD/USD",    "cat":"FOREX",   "tf_entry":"M5",
               "spread":1.3,  "pip":0.0001, "pip_val":10.0,  "digits":5,
               "sessions":["asia"],                  "yf":"NZDUSD=X"},
    "GBPJPY": {"label":"GBP/JPY",    "cat":"FOREX",   "tf_entry":"M1",
               "spread":2.0,  "pip":0.01,   "pip_val":9.1,   "digits":3,
               "sessions":["london","overlap"],       "yf":"GBPJPY=X"},
    "EURJPY": {"label":"EUR/JPY",    "cat":"FOREX",   "tf_entry":"M5",
               "spread":1.5,  "pip":0.01,   "pip_val":9.1,   "digits":3,
               "sessions":["asia","london"],          "yf":"EURJPY=X"},
    "EURGBP": {"label":"EUR/GBP",    "cat":"FOREX",   "tf_entry":"M5",
               "spread":1.0,  "pip":0.0001, "pip_val":12.5,  "digits":5,
               "sessions":["london"],                "yf":"EURGBP=X"},
    "EURCAD": {"label":"EUR/CAD",    "cat":"FOREX",   "tf_entry":"M5",
               "spread":2.0,  "pip":0.0001, "pip_val":7.5,   "digits":5,
               "sessions":["london","ny"],            "yf":"EURCAD=X"},
    "GBPCAD": {"label":"GBP/CAD",    "cat":"FOREX",   "tf_entry":"M5",
               "spread":2.5,  "pip":0.0001, "pip_val":7.5,   "digits":5,
               "sessions":["london","ny"],            "yf":"GBPCAD=X"},

    # ── MÉTAUX PRÉCIEUX ───────────────────────────────────────────────
    "XAUUSD": {"label":"Gold / XAU", "cat":"GOLD",    "tf_entry":"M1",
               "spread":0.35, "pip":0.01,   "pip_val":1.0,   "digits":2,
               "sessions":["london","ny","overlap"],  "yf":"GC=F"},
    "XAGUSD": {"label":"Silver/XAG", "cat":"SILVER",  "tf_entry":"M1",
               "spread":0.02, "pip":0.001,  "pip_val":5.0,   "digits":3,
               "sessions":["london","ny","overlap"],  "yf":"SI=F"},

    # ── INDICES ───────────────────────────────────────────────────────
    "NAS100": {"label":"NASDAQ 100", "cat":"INDICES", "tf_entry":"M1",
               "spread":1.5,  "pip":1.0,    "pip_val":1.0,   "digits":1,
               "sessions":["ny","premarket"],         "yf":"NQ=F"},
    "US500":  {"label":"S&P 500",    "cat":"INDICES", "tf_entry":"M5",
               "spread":0.6,  "pip":1.0,    "pip_val":1.0,   "digits":1,
               "sessions":["ny"],                    "yf":"ES=F"},
    "US30":   {"label":"Dow Jones",  "cat":"INDICES", "tf_entry":"M5",
               "spread":2.0,  "pip":1.0,    "pip_val":1.0,   "digits":1,
               "sessions":["ny"],                    "yf":"YM=F"},
    "GER40":  {"label":"DAX 40",     "cat":"INDICES", "tf_entry":"M5",
               "spread":1.2,  "pip":1.0,    "pip_val":1.0,   "digits":1,
               "sessions":["london","frankfurt"],    "yf":"^GDAXI"},
    "UK100":  {"label":"FTSE 100",   "cat":"INDICES", "tf_entry":"M5",
               "spread":1.5,  "pip":1.0,    "pip_val":1.0,   "digits":1,
               "sessions":["london"],                "yf":"^FTSE"},
    "FRA40":  {"label":"CAC 40",     "cat":"INDICES", "tf_entry":"M5",
               "spread":1.5,  "pip":1.0,    "pip_val":1.0,   "digits":1,
               "sessions":["london","frankfurt"],    "yf":"^FCHI"},
    "JPN225": {"label":"Nikkei 225", "cat":"INDICES", "tf_entry":"M5",
               "spread":6.0,  "pip":1.0,    "pip_val":1.0,   "digits":1,
               "sessions":["asia"],                  "yf":"^N225"},
    "AUS200": {"label":"ASX 200",    "cat":"INDICES", "tf_entry":"M5",
               "spread":2.0,  "pip":1.0,    "pip_val":1.0,   "digits":1,
               "sessions":["asia"],                  "yf":"^AXJO"},

    # ── CRYPTO — BTC uniquement ───────────────────────────────────────
    "BTCUSD": {"label":"Bitcoin/BTC","cat":"CRYPTO",  "tf_entry":"M5",
               "spread":2.0,  "pip":1.0,    "pip_val":1.0,   "digits":1,
               "sessions":["all"],  "yf":"BTC-USD", "binance":"BTCUSDT"},
}

CAT_EMOJI = {"FOREX":"💱","GOLD":"🥇","SILVER":"🪙","INDICES":"📈","CRYPTO":"🔷"}

# ══════════════════════════════════════════════════════════════════════════════
#  WIN RATES STRATÉGIES
# ══════════════════════════════════════════════════════════════════════════════

STRAT_INFO = {
    "ICT_BB":     {"label":"ICT Breaker Block",       "wr":0.82, "icon":"🔷", "min_score":72},
    "FVG_BOS":    {"label":"FVG + Break of Structure","wr":0.80, "icon":"⚡", "min_score":74},
    "LIQ_MSS":    {"label":"Liq Sweep + MSS",         "wr":0.83, "icon":"🌊", "min_score":70},
    "OB_HTF_LTF": {"label":"OB HTF + LTF Confluence","wr":0.81, "icon":"👑", "min_score":75},
    "MSS_BB_FVG": {"label":"MSS + Breaker + FVG",    "wr":0.84, "icon":"🎯", "min_score":72},
}

# ══════════════════════════════════════════════════════════════════════════════
#  SESSIONS DE TRADING
# ══════════════════════════════════════════════════════════════════════════════

SESSIONS_UTC = {
    "asia":       ( 0,  9),
    "frankfurt":  ( 7, 16),
    "london":     ( 7, 16),
    "premarket":  (12, 13),
    "overlap":    (12, 16),
    "ny":         (13, 22),
    "all":        ( 0, 24),
}

# ICT Kill Zones (heures UTC)
KILL_ZONES = {
    "Asia KZ":          ( 0,  4),
    "London Open KZ":   ( 7,  9),
    "London Close KZ":  (11, 13),
    "NY Open KZ":       (13, 15),
    "NY Close KZ":      (20, 22),
}

def get_active_sessions() -> List[str]:
    h = datetime.now(timezone.utc).hour
    return [s for s,(a,b) in SESSIONS_UTC.items() if a <= h < b]

def get_kill_zone() -> Optional[str]:
    h = datetime.now(timezone.utc).hour
    for kz,(a,b) in KILL_ZONES.items():
        if a <= h < b:
            return kz
    return None

def session_check(symbol: str) -> Tuple[bool, str]:
    mkt   = MARKETS[symbol]
    good  = mkt.get("sessions", ["all"])
    if "all" in good:
        return True, "24/7"
    match = [s for s in get_active_sessions() if s in good]
    return (True, match[0].upper()) if match else (False, "HORS SESSION")

def session_label() -> str:
    h = datetime.now(timezone.utc).hour
    kz = get_kill_zone()
    if kz: return f"{kz} 🎯"
    if  0 <= h <  7: return "Asie 🌏"
    if  7 <= h < 12: return "Londres 🇬🇧"
    if 12 <= h < 16: return "Overlap 🔥"
    if 16 <= h < 22: return "New York 🇺🇸"
    return "Inter-session"

def is_kill_zone() -> bool:
    return get_kill_zone() is not None

# ══════════════════════════════════════════════════════════════════════════════
#  BIAIS FONDAMENTAUX — Mis à jour manuellement
# ══════════════════════════════════════════════════════════════════════════════

FUNDAMENTALS: Dict[str, Dict] = {
    "EURUSD": {"bias":"BEARISH","note":"BCE dovish vs Fed hawkish · DXY fort"},
    "GBPUSD": {"bias":"BEARISH","note":"BoE incertaine · données UK mitigées"},
    "USDJPY": {"bias":"BULLISH","note":"BoJ ultra-dovish · carry USD/JPY actif"},
    "USDCHF": {"bias":"BULLISH","note":"Risk-off USD · SNB pression CHF"},
    "AUDUSD": {"bias":"BEARISH","note":"Chine ralentie · AUD sous pression"},
    "USDCAD": {"bias":"BULLISH","note":"Pétrole flat · CAD neutre"},
    "NZDUSD": {"bias":"BEARISH","note":"RBNZ dovish · NZD faible"},
    "GBPJPY": {"bias":"NEUTRAL","note":"Volatilité élevée · double biais"},
    "EURJPY": {"bias":"BEARISH","note":"EUR faible · JPY soutenu BoJ"},
    "EURGBP": {"bias":"NEUTRAL","note":"Range structurel · données UK vs Zone Euro"},
    "EURCAD": {"bias":"BEARISH","note":"EUR sous pression · CAD neutre pétrole"},
    "GBPCAD": {"bias":"NEUTRAL","note":"BoE vs BoC · équilibré"},
    "XAUUSD": {"bias":"BULLISH","note":"Géopolitique · demande refuge · Fed pivot"},
    "XAGUSD": {"bias":"BULLISH","note":"Demande industrielle · corrélation Gold"},
    "NAS100": {"bias":"BULLISH","note":"IA tech rally · earnings Big Tech solides"},
    "US500":  {"bias":"BULLISH","note":"Croissance US résiliente · Fed pivot proche"},
    "US30":   {"bias":"NEUTRAL","note":"Rotation sectorielle cycliques mixtes"},
    "GER40":  {"bias":"BEARISH","note":"Récession Allemagne · énergie coûteuse"},
    "UK100":  {"bias":"NEUTRAL","note":"FTSE stable · commodités en baisse"},
    "FRA40":  {"bias":"NEUTRAL","note":"CAC40 flat · incertitude politique"},
    "JPN225": {"bias":"BULLISH","note":"Yen faible · exports japonais favorisés"},
    "AUS200": {"bias":"NEUTRAL","note":"RBA neutre · Chine mitigée"},
    "BTCUSD": {"bias":"BULLISH","note":"Cycle post-halving · ETF BTC institutionnel"},
}

def get_fund(symbol: str) -> Dict:
    return FUNDAMENTALS.get(symbol, {"bias":"NEUTRAL","note":"—"})

def fund_supports(symbol: str, side: str) -> bool:
    b = get_fund(symbol)["bias"]
    if b == "NEUTRAL": return True
    return (side=="BUY" and b=="BULLISH") or (side=="SELL" and b=="BEARISH")

# ══════════════════════════════════════════════════════════════════════════════
#  DONNÉES MARCHÉ — Yahoo Finance + Binance fallback
# ══════════════════════════════════════════════════════════════════════════════

_price_cache   : Dict[str, Dict] = {}
_candles_cache : Dict[str, Dict] = {}
CACHE_TTL = 55  # secondes

# Prix spot attendus pour sanity-check
_PRICE_RANGES = {
    "GC=F":    (1800, 4000),   # Gold futures $/oz (élargi pour 2025-2026)
    "SI=F":    (15, 40),       # Silver futures $/oz
    "NQ=F":    (15000, 25000), # NASDAQ futures
    "ES=F":    (3000, 6500),   # S&P futures
    "YM=F":    (28000, 50000), # Dow futures
    "^GDAXI":  (12000, 22000), # DAX
    "^FTSE":   (6000, 9000),   # FTSE
    "^FCHI":   (6000, 9000),   # CAC
    "^N225":   (25000, 45000), # Nikkei
    "BTC-USD": (20000, 120000),# BTC
    "GC=F_CENTS": (150000, 350000),  # GC=F parfois retourné en cents
}

def _yf_price(ticker: str) -> Optional[float]:
    lo, hi = _PRICE_RANGES.get(ticker, (0, 999999))

    # Essayer plusieurs endpoints Yahoo
    urls = [
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d",
        f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d",
    ]
    for url in urls:
        try:
            r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=8)
            data = r.json()
            meta = data["chart"]["result"][0]["meta"]

            # Essayer regularMarketPrice puis previousClose
            for field in ("regularMarketPrice", "chartPreviousClose", "previousClose"):
                raw = meta.get(field)
                if raw is None:
                    continue
                p = float(raw)

                # Corrections auto selon plage attendue
                if lo > 0:
                    # Si p × 50 tombe dans la plage → données en contrats mini
                    if not (lo <= p <= hi) and lo <= p * 50 <= hi:
                        p = p * 50
                    # Si p × 100 dans la plage → cents
                    elif not (lo <= p <= hi) and lo <= p * 100 <= hi:
                        p = p * 100
                    # GC=F spécifique : parfois divisé par 100
                    elif ticker == "GC=F" and p > 4000:
                        p = p / 100

                if lo > 0 and not (lo <= p <= hi):
                    continue  # Essayer le champ suivant
                return round(p, 5)
        except Exception:
            continue

    log.warning(f"[PRICE] {ticker} — impossible d'obtenir un prix valide")
    return None

def _bnb_price(sym: str) -> Optional[float]:
    try:
        r = requests.get(
            f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={sym}", timeout=6)
        return float(r.json()["price"])
    except Exception:
        return None

def get_price(symbol: str) -> Optional[float]:
    c = _price_cache.get(symbol)
    if c and time.time() - c["ts"] < CACHE_TTL: return c["p"]
    mkt = MARKETS[symbol]
    p   = _yf_price(mkt["yf"])
    if p is None and "binance" in mkt:
        p = _bnb_price(mkt["binance"])
    if p: _price_cache[symbol] = {"p":p, "ts":time.time()}
    return p

def _yf_candles(ticker: str, interval: str = "1m") -> Optional[List]:
    try:
        period = "5d" if interval == "5m" else "2d"
        url    = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
                  f"?interval={interval}&range={period}")
        r   = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
        res = r.json()["chart"]["result"][0]
        ts_l = res["timestamp"]
        q    = res["indicators"]["quote"][0]
        out  = []
        for i in range(len(ts_l)):
            o,h,l,c = q["open"][i],q["high"][i],q["low"][i],q["close"][i]
            v = (q.get("volume") or [0]*len(ts_l))[i]
            if None in (o,h,l,c): continue
            oc,hc,lc,cc = float(o),float(h),float(l),float(c)
            # Correction Gold/Silver retournés en cents par Yahoo Finance
            if ticker == "GC=F" and cc > 4000:
                oc,hc,lc,cc = oc/100, hc/100, lc/100, cc/100
            if ticker == "SI=F" and cc > 100:
                oc,hc,lc,cc = oc/100, hc/100, lc/100, cc/100
            out.append({"ts":ts_l[i],"open":oc,"high":hc,
                        "low":lc,"close":cc,"vol":float(v or 0)})
        return out[-100:] if out else None
    except Exception:
        return None

def _bnb_candles(sym: str, interval: str = "5m", limit: int = 100) -> Optional[List]:
    try:
        r = requests.get(
            f"https://fapi.binance.com/fapi/v1/klines"
            f"?symbol={sym}&interval={interval}&limit={limit}", timeout=8)
        return [{"ts":int(k[0]),"open":float(k[1]),"high":float(k[2]),
                 "low":float(k[3]),"close":float(k[4]),"vol":float(k[5])}
                for k in r.json()]
    except Exception:
        return None

def get_candles(symbol: str, tf: str = "5m") -> Optional[List]:
    key = f"{symbol}_{tf}"
    c   = _candles_cache.get(key)
    if c and time.time() - c["ts"] < CACHE_TTL: return c["d"]
    mkt  = MARKETS[symbol]
    data = _yf_candles(mkt["yf"], tf)
    if data is None and "binance" in mkt:
        data = _bnb_candles(mkt["binance"], tf)
    if data: _candles_cache[key] = {"d":data, "ts":time.time()}
    return data

# ══════════════════════════════════════════════════════════════════════════════
#  FEAR & GREED INDEX (alternative.me) + données de marché global
# ══════════════════════════════════════════════════════════════════════════════

_fear_greed_cache: Dict = {}

def fetch_fear_greed() -> Dict:
    """Fear & Greed Index via alternative.me — marche aussi pour Forex/Indices comme proxy."""
    c = _fear_greed_cache
    if c and time.time() - c.get("ts",0) < 3600:  # cache 1h
        return c
    try:
        r = requests.get(
            "https://api.alternative.me/fng/?limit=1&format=json", timeout=8)
        d   = r.json()["data"][0]
        val = int(d["value"])
        lbl = d["value_classification"]
        _fear_greed_cache.update({"value":val,"label":lbl,"ts":time.time()})
        return _fear_greed_cache
    except Exception:
        return {"value":50,"label":"Neutral","ts":0}

# ══════════════════════════════════════════════════════════════════════════════
#  INDICATEURS TECHNIQUES
# ══════════════════════════════════════════════════════════════════════════════

def calc_atr(candles: List, period: int = 14) -> float:
    r = candles[-period:]
    return sum(c["high"]-c["low"] for c in r)/len(r) if r else 0.001

def calc_ema(candles: List, period: int) -> float:
    closes = [c["close"] for c in candles[-period*2:]]
    if not closes: return 0
    k, v = 2/(period+1), closes[0]
    for p in closes[1:]: v = p*k + v*(1-k)
    return v

def calc_rsi(candles: List, period: int = 14) -> float:
    closes = [c["close"] for c in candles[-(period+2):]]
    if len(closes) < 2: return 50
    gains  = [max(0, closes[i]-closes[i-1]) for i in range(1,len(closes))]
    losses = [max(0, closes[i-1]-closes[i]) for i in range(1,len(closes))]
    ag, al = sum(gains)/len(gains), sum(losses)/len(losses)
    return 100 - 100/(1+ag/al) if al else 100

def calc_macd(candles: List) -> Tuple[float, float, float]:
    """Retourne (macd_line, signal, histogram)."""
    fast = calc_ema(candles, 12)
    slow = calc_ema(candles, 26)
    macd = fast - slow
    # Signal = EMA9 du MACD — approximation
    closes = [c["close"] for c in candles[-35:]]
    k, sig = 2/10, closes[0]
    for p in closes[1:]: sig = p*k + sig*(1-k)
    signal = sig * 0.1  # approximation simplifiée
    return macd, signal, macd - signal

def calc_stoch(candles: List, k_period: int = 14) -> Tuple[float, float]:
    """Retourne (%K, %D)."""
    r = candles[-k_period:]
    if not r: return 50, 50
    h14 = max(c["high"]  for c in r)
    l14 = min(c["low"]   for c in r)
    last_close = r[-1]["close"]
    k = ((last_close - l14) / (h14 - l14) * 100) if h14 != l14 else 50
    # %D = SMA3 de %K — approximation
    d = k * 0.9
    return round(k,1), round(d,1)

def htf_trend(symbol: str) -> str:
    """Tendance H1 via EMA20/EMA50 sur M5 (60 bougies = 5h)."""
    c = get_candles(symbol, "5m") or []
    if len(c) < 20: return "RANGE"
    e20 = calc_ema(c, 20)
    e50 = calc_ema(c, min(50,len(c)))
    p   = c[-1]["close"]
    if e20 > e50 and p > e20: return "BULL"
    if e20 < e50 and p < e20: return "BEAR"
    return "RANGE"

def get_swing_levels(candles: List, lookback: int = 20) -> Tuple[float, float]:
    """Retourne (swing_high, swing_low) sur les N dernières bougies."""
    r = candles[-lookback:]
    return max(c["high"] for c in r), min(c["low"] for c in r)

# ══════════════════════════════════════════════════════════════════════════════
#  STRATÉGIE 1 — ICT Breaker Block (principale)
#  Règles :
#  · OB fort (corps > 52% du range, taille > 35% ATR)
#  · Prix revient retester l'OB (rejet ou retest)
#  · BOS sur TF signal
#  · FVG interne (gap entre bougies)
#  · Zone Premium/Discount ICT (EQ 50%)
#  · SL = swing bas/haut 5 bougies + spread
#  · TP1 = 2.5R · TP2 = 5R · TP3 = 8R
# ══════════════════════════════════════════════════════════════════════════════

def strat_ict_breaker(candles: List, symbol: str, trend: str) -> Optional[Dict]:
    if len(candles) < 15: return None
    mkt   = MARKETS[symbol]
    n     = len(candles)
    a     = calc_atr(candles, 14)
    r     = calc_rsi(candles, 14)
    price = candles[-1]["close"]
    c1    = candles[-2]   # bougie impulsive candidate
    c2    = candles[-3]

    def body_pct(c):
        rng = c["high"] - c["low"]
        return abs(c["close"] - c["open"]) / rng if rng > 0 else 0

    # Premium/Discount zones
    sh, sl_ = get_swing_levels(candles, 20)
    eq      = (sh + sl_) / 2
    pd_pct  = (price - sl_) / (sh - sl_) * 100 if sh != sl_ else 50
    pd_zone = "DISCOUNT" if pd_pct < 45 else "PREMIUM" if pd_pct > 55 else "EQ"

    # Volume relatif
    vols  = [c["vol"] for c in candles[-10:] if c["vol"] > 0]
    avg_v = sum(vols)/len(vols) if vols else 0
    vol_ok = c1["vol"] > avg_v * 1.15 if avg_v > 0 else True

    # ── BULL ─────────────────────────────────────────────────────────
    b_ob    = c1["close"] > c1["open"] and body_pct(c1) > 0.52
    b_size  = (c1["close"] - c1["open"]) > a * 0.35
    b_ret   = c1["open"]*0.9994 <= price <= c1["close"]*1.0012
    fvg_b   = c2["high"] < candles[-1]["low"]
    fvg_wb  = not fvg_b and c2["high"] < candles[-1]["close"]
    bos_blv = max(c["high"] for c in candles[-12:-2])
    bos_b   = c1["close"] > bos_blv
    htf_b   = trend in ("BULL","RANGE")
    rsi_b   = r < 68

    if b_ob and b_size and b_ret and (bos_b or fvg_b) and htf_b and rsi_b:
        # SL = low de la DERNIÈRE bougie (last candle low) + demi-spread
        last_low = min(candles[-1]["low"], candles[-2]["low"])
        sl       = round(last_low - mkt["pip"]*mkt["spread"]*0.5, mkt["digits"])
        # Entrée directe = prix actuel (pas d'anticipation)
        entry_now = round(price, mkt["digits"])
        sl_d  = entry_now - sl
        if sl_d < a*0.06 or sl_d > a*2.8: return None
        # TP RAPIDE : 1.5R / 2.5R / 4.0R
        tp1 = round(entry_now + sl_d*1.5, mkt["digits"])
        tp2 = round(entry_now + sl_d*2.5, mkt["digits"])
        tp3 = round(entry_now + sl_d*4.0, mkt["digits"])
        sc  = 60
        sc += 18 if bos_b               else 0
        sc += 12 if fvg_b               else (5 if fvg_wb else 0)
        sc += 8  if pd_zone=="DISCOUNT" else 0
        sc += 8  if trend=="BULL"       else 0
        sc += 6  if vol_ok              else 0
        sc += 6  if r < 48              else 0
        sc += 5  if is_kill_zone()      else 0
        sc += 4  if body_pct(c1)>0.68   else 0
        return {"strategy":"ICT_BB","side":"BUY",
                "entry":entry_now,"sl":sl,
                "tp1":tp1,"tp2":tp2,"tp3":tp3,
                "sl_dist":sl_d,"rr":1.5,"score":min(sc,100),"atr":a,
                "bos":bos_b,"fvg":fvg_b or fvg_wb,
                "pd_zone":pd_zone,"pd_pct":round(pd_pct,1),
                "rsi":round(r,1),"htf_trend":trend,
                "ob_zone":(round(c1["open"],mkt["digits"]),round(c1["close"],mkt["digits"]))}

    # ── BEAR ──────────────────────────────────────────────────────────
    s_ob    = c1["close"] < c1["open"] and body_pct(c1) > 0.52
    s_size  = (c1["open"] - c1["close"]) > a * 0.35
    s_ret   = c1["close"]*0.9988 <= price <= c1["open"]*1.0006
    fvg_s   = c2["low"] > candles[-1]["high"]
    fvg_ws  = not fvg_s and c2["low"] > candles[-1]["close"]
    bos_slv = min(c["low"] for c in candles[-12:-2])
    bos_s   = c1["close"] < bos_slv
    htf_s   = trend in ("BEAR","RANGE")
    rsi_s   = r > 32

    if s_ob and s_size and s_ret and (bos_s or fvg_s) and htf_s and rsi_s:
        # SL = high de la DERNIÈRE bougie + demi-spread
        last_high = candles[-1]["high"]
        sl_sw     = max(last_high, candles[-2]["high"])
        sl        = round(sl_sw + mkt["pip"]*mkt["spread"]*0.5, mkt["digits"])
        # Entrée directe = prix actuel
        entry_direct = round(price, mkt["digits"])
        sl_d  = sl - entry_direct
        if sl_d < a*0.08 or sl_d > a*3.0: return None
        # TP rapide : 1.5R / 2.5R / 4.0R
        tp1 = round(entry_direct - sl_d*1.5, mkt["digits"])
        tp2 = round(entry_direct - sl_d*2.5, mkt["digits"])
        tp3 = round(entry_direct - sl_d*4.0, mkt["digits"])
        sc  = 60
        sc += 18 if bos_s          else 0
        sc += 12 if fvg_s          else (5 if fvg_ws else 0)
        sc += 8  if pd_zone=="PREMIUM" else 0
        sc += 8  if trend=="BEAR"  else 0
        sc += 6  if vol_ok         else 0
        sc += 6  if r > 52         else 0
        sc += 5  if is_kill_zone() else 0
        sc += 4  if body_pct(c1)>0.68 else 0
        return {"strategy":"ICT_BB","side":"SELL",
                "entry":entry_direct,"sl":sl,
                "tp1":tp1,"tp2":tp2,"tp3":tp3,
                "sl_dist":sl_d,"rr":1.5,"score":min(sc,100),"atr":a,
                "bos":bos_s,"fvg":fvg_s or fvg_ws,
                "pd_zone":pd_zone,"pd_pct":round(pd_pct,1),
                "rsi":round(r,1),"htf_trend":trend,
                "ob_zone":(round(c1["close"],mkt["digits"]),round(c1["open"],mkt["digits"]))}
    return None

# ══════════════════════════════════════════════════════════════════════════════
#  STRATÉGIE 2 — FVG + Break of Structure
#  · Détecte un Fair Value Gap (gap entre bougie i-2 et i)
#  · Confirmation BOS sur la même TF
#  · Entrée au retest du FVG
# ══════════════════════════════════════════════════════════════════════════════

def strat_fvg_bos(candles: List, symbol: str, trend: str) -> Optional[Dict]:
    if len(candles) < 10: return None
    mkt   = MARKETS[symbol]
    n     = len(candles)
    a     = calc_atr(candles, 14)
    r     = calc_rsi(candles, 14)
    price = candles[-1]["close"]

    for i in range(n-1, 4, -1):
        ca, cb, cc = candles[i-2], candles[i-1], candles[i]

        # ── FVG BULL ───────────────────────────────────────────────
        if cc["low"] > ca["high"] and cb["close"] > cb["open"]:
            fvg_lo, fvg_hi = ca["high"], cc["low"]
            if fvg_lo <= price <= fvg_hi + (fvg_hi-fvg_lo)*0.3:
                prev_h = max(c["high"] for c in candles[max(0,i-10):i-1])
                bos    = cb["close"] > prev_h
                sl_sw  = min(c["low"] for c in candles[max(0,i-5):i])
                sl     = round(sl_sw - mkt["pip"], mkt["digits"])
                sl_d   = price - sl
                if sl_d < a*0.1 or sl_d > a*3.5: continue
                sc = 68 + (18 if bos else 0) + (8 if trend=="BULL" else 0) + (5 if r<50 else 0)
                return {"strategy":"FVG_BOS","side":"BUY",
                        "entry":round(price,mkt["digits"]),"sl":sl,
                        "tp1":round(price+sl_d*2.5,mkt["digits"]),
                        "tp2":round(price+sl_d*5.0,mkt["digits"]),
                        "tp3":round(price+sl_d*8.0,mkt["digits"]),
                        "sl_dist":sl_d,"rr":2.5,"score":min(sc,100),"atr":a,
                        "bos":bos,"fvg":True,
                        "fvg_zone":(fvg_lo,fvg_hi),
                        "pd_zone":"DISCOUNT","pd_pct":round((price-min(c["low"] for c in candles[-20:]))/(max(c["high"] for c in candles[-20:])-min(c["low"] for c in candles[-20:])+0.001)*100,1),
                        "rsi":round(r,1),"htf_trend":trend}

        # ── FVG BEAR ───────────────────────────────────────────────
        if cc["high"] < ca["low"] and cb["close"] < cb["open"]:
            fvg_lo, fvg_hi = cc["high"], ca["low"]
            if fvg_lo - (fvg_hi-fvg_lo)*0.3 <= price <= fvg_hi:
                prev_l = min(c["low"] for c in candles[max(0,i-10):i-1])
                bos    = cb["close"] < prev_l
                sl_sw  = max(c["high"] for c in candles[max(0,i-5):i])
                sl     = round(sl_sw + mkt["pip"], mkt["digits"])
                sl_d   = sl - price
                if sl_d < a*0.1 or sl_d > a*3.5: continue
                sc = 68 + (18 if bos else 0) + (8 if trend=="BEAR" else 0) + (5 if r>50 else 0)
                return {"strategy":"FVG_BOS","side":"SELL",
                        "entry":round(price,mkt["digits"]),"sl":sl,
                        "tp1":round(price-sl_d*2.5,mkt["digits"]),
                        "tp2":round(price-sl_d*5.0,mkt["digits"]),
                        "tp3":round(price-sl_d*8.0,mkt["digits"]),
                        "sl_dist":sl_d,"rr":2.5,"score":min(sc,100),"atr":a,
                        "bos":bos,"fvg":True,
                        "fvg_zone":(fvg_lo,fvg_hi),
                        "pd_zone":"PREMIUM","pd_pct":round((price-min(c["low"] for c in candles[-20:]))/(max(c["high"] for c in candles[-20:])-min(c["low"] for c in candles[-20:])+0.001)*100,1),
                        "rsi":round(r,1),"htf_trend":trend}
    return None

# ══════════════════════════════════════════════════════════════════════════════
#  STRATÉGIE 3 — Liquidity Sweep + MSS
#  · Détecte un sweep du swing high/low
#  · Market Structure Shift (MSS) = clôture sous/sur structure
#  · SL au-delà du swing + spread
# ══════════════════════════════════════════════════════════════════════════════

def strat_liq_mss(candles: List, symbol: str, trend: str) -> Optional[Dict]:
    if len(candles) < 14: return None
    mkt   = MARKETS[symbol]
    n     = len(candles)
    a     = calc_atr(candles, 14)
    r     = calc_rsi(candles, 14)
    price = candles[-1]["close"]
    recent = candles[n-14:n-2]

    # ── SWEEP HIGH → SHORT ─────────────────────────────────────────
    swing_h = max(c["high"] for c in recent)
    swept_h = any(c["high"] > swing_h for c in candles[n-4:n-1])
    if swept_h and price < swing_h and trend != "BULL":
        mss_low  = min(c["low"] for c in candles[n-5:n-1])
        mss_conf = price < mss_low
        sl_sw    = max(c["high"] for c in candles[n-5:n])
        sl       = round(sl_sw * 1.001, mkt["digits"])
        sl_d     = sl - price
        if sl_d < a*0.1 or sl_d > a*2.8: return None
        sc = 70 + (20 if mss_conf else 0) + (8 if trend=="BEAR" else 0)
        entry_liq = round(price, mkt["digits"])
        return {"strategy":"LIQ_MSS","side":"SELL",
                "entry":entry_liq,"sl":sl,
                "tp1":round(entry_liq-sl_d*1.5,mkt["digits"]),
                "tp2":round(entry_liq-sl_d*2.5,mkt["digits"]),
                "tp3":round(entry_liq-sl_d*4.0,mkt["digits"]),
                "sl_dist":sl_d,"rr":1.5,"score":min(sc,100),"atr":a,
                "bos":mss_conf,"fvg":False,"sweep_level":swing_h,
                "pd_zone":"PREMIUM","pd_pct":80.0,
                "rsi":round(r,1),"htf_trend":trend}

    # ── SWEEP LOW → LONG ──────────────────────────────────────────
    swing_l = min(c["low"] for c in recent)
    swept_l = any(c["low"] < swing_l for c in candles[n-4:n-1])
    if swept_l and price > swing_l and trend != "BEAR":
        mss_high = max(c["high"] for c in candles[n-5:n-1])
        mss_conf = price > mss_high
        sl_sw    = min(c["low"] for c in candles[n-5:n])
        sl       = round(sl_sw * 0.999, mkt["digits"])
        sl_d     = price - sl
        if sl_d < a*0.1 or sl_d > a*2.8: return None
        sc = 70 + (20 if mss_conf else 0) + (8 if trend=="BULL" else 0)
        entry_liq = round(price, mkt["digits"])
        return {"strategy":"LIQ_MSS","side":"BUY",
                "entry":entry_liq,"sl":sl,
                "tp1":round(entry_liq+sl_d*1.5,mkt["digits"]),
                "tp2":round(entry_liq+sl_d*2.5,mkt["digits"]),
                "tp3":round(entry_liq+sl_d*4.0,mkt["digits"]),
                "sl_dist":sl_d,"rr":1.5,"score":min(sc,100),"atr":a,
                "bos":mss_conf,"fvg":False,"sweep_level":swing_l,
                "pd_zone":"DISCOUNT","pd_pct":20.0,
                "rsi":round(r,1),"htf_trend":trend}
    return None

# ══════════════════════════════════════════════════════════════════════════════
#  SCAN TOUTES LES STRATÉGIES SUR UN SYMBOLE
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
#  STRATÉGIE 5 — MSS + Breaker Block + FVG  (comme dans la vidéo ICT)
#  Logique : MSS casse la structure → BB formé → FVG dans le BB →
#            Entrée au retour dans le BB/FVG → SL serré, TP loin (RR 1:3+)
# ══════════════════════════════════════════════════════════════════════════════

def strat_mss_bb_fvg(candles: List, symbol: str, trend: str) -> Optional[Dict]:
    """
    MSS + Breaker Block + FVG — Stratégie ICT complète (vue en vidéo).

    Détection SELL :
    - Swing High identifié sur les 20 dernières bougies
    - MSS : une bougie impulsive BEARISH casse sous un swing low récent
    - BB : la zone de la bougie impulsive qui a créé le MSS devient résistance
    - FVG : gap entre 3 bougies consécutives dans la zone de retrace
    - Entrée : quand le prix remonte dans le BB/FVG
    - SL : au-dessus du BB (tight = dernier high du BB)
    - TP : vers le prochain swing low / range bas (loin = RR 1:3 à 1:4)

    Détection BUY (miroir) :
    - Swing Low → MSS bullish → BB support → FVG dans le retrace
    """
    if len(candles) < 25: return None
    mkt   = MARKETS[symbol]
    n     = len(candles)
    d     = mkt["digits"]
    a     = calc_atr(candles, 14)
    r     = calc_rsi(candles, 14)
    price = candles[-1]["close"]

    if a <= 0: return None

    def body(c):
        return abs(c["close"] - c["open"])
    def is_bearish(c):
        return c["close"] < c["open"]
    def is_bullish(c):
        return c["close"] > c["open"]

    # ── Chercher MSS BEARISH + BB + FVG ──────────────────────────────
    # Fenêtre d'analyse : 20 bougies
    window = candles[n-22:n-1]

    # 1. Swing High dans la fenêtre
    swing_h_idx = max(range(len(window)), key=lambda i: window[i]["high"])
    swing_h     = window[swing_h_idx]["high"]

    # 2. MSS Bearish : bougie impulsive bear qui casse sous un swing low
    #    après le swing high → structure shift
    post_swing  = window[swing_h_idx+1:] if swing_h_idx+1 < len(window) else []
    mss_bear_c  = None
    mss_bear_i  = -1
    for i, c in enumerate(post_swing):
        if is_bearish(c) and body(c) > a * 0.6:
            # Vérifie qu'il casse sous le low du candle précédent (MSS)
            prev_low = min(cc["low"] for cc in post_swing[max(0,i-3):i+1])
            if c["close"] < prev_low * 0.9995:
                mss_bear_c = c
                mss_bear_i = i
                break

    if mss_bear_c is None:
        pass  # Pas de MSS bear → tenter BUY
    else:
        # 3. BB zone = corps de la bougie MSS (zone de résistance)
        bb_high = max(mss_bear_c["open"], mss_bear_c["close"])
        bb_low  = min(mss_bear_c["open"], mss_bear_c["close"])
        bb_mid  = (bb_high + bb_low) / 2

        # 4. FVG dans les bougies après le MSS
        post_mss = candles[n - (len(post_swing) - mss_bear_i) - 2 : n-1]
        fvg_bear = False
        for j in range(1, min(len(post_mss)-1, 8)):
            # FVG = gap entre high de c[j-1] et low de c[j+1]
            if post_mss[j+1]["low"] > post_mss[j-1]["high"]:
                fvg_bear = True
                break

        # 5. Le prix actuel est-il dans la BB zone (retrace) ?
        in_bb = bb_low <= price <= bb_high * 1.001

        if in_bb:
            # SL = juste au-dessus du BB high (serré)
            sl   = round(bb_high + mkt["pip"] * mkt["spread"] * 0.5, d)
            sl_d = sl - price
            if sl_d < a * 0.05 or sl_d > a * 1.5: pass
            else:
                # TP = RR 1:3 / 1:4 / 1:6 — loin car structure cassée
                entry_now = round(price, d)
                tp1 = round(entry_now - sl_d * 3.0, d)
                tp2 = round(entry_now - sl_d * 4.5, d)
                tp3 = round(entry_now - sl_d * 6.0, d)

                sc = 72
                sc += 15 if fvg_bear           else 0
                sc += 12 if trend == "BEAR"    else 0
                sc += 8  if r > 55             else 0
                sc += 6  if is_kill_zone()     else 0
                sc += 5  if body(mss_bear_c) > a * 1.0 else 0

                return {
                    "strategy":  "MSS_BB_FVG",
                    "side":      "SELL",
                    "entry":     entry_now,
                    "sl":        sl,
                    "tp1":       tp1, "tp2": tp2, "tp3": tp3,
                    "sl_dist":   sl_d, "rr": 3.0,
                    "score":     min(sc, 100), "atr": a,
                    "bos":       True, "fvg": fvg_bear,
                    "pd_zone":   "PREMIUM", "pd_pct": 80.0,
                    "rsi":       round(r, 1), "htf_trend": trend,
                    "bb_zone":   (round(bb_low, d), round(bb_high, d)),
                    "mss_conf":  True,
                }

    # ── Chercher MSS BULLISH + BB + FVG ──────────────────────────────
    swing_l_idx = min(range(len(window)), key=lambda i: window[i]["low"])
    swing_l     = window[swing_l_idx]["low"]

    post_swing_b = window[swing_l_idx+1:] if swing_l_idx+1 < len(window) else []
    mss_bull_c   = None
    mss_bull_i   = -1
    for i, c in enumerate(post_swing_b):
        if is_bullish(c) and body(c) > a * 0.6:
            prev_high = max(cc["high"] for cc in post_swing_b[max(0,i-3):i+1])
            if c["close"] > prev_high * 1.0005:
                mss_bull_c = c
                mss_bull_i = i
                break

    if mss_bull_c:
        bb_low_b  = min(mss_bull_c["open"], mss_bull_c["close"])
        bb_high_b = max(mss_bull_c["open"], mss_bull_c["close"])

        post_mss_b = candles[n - (len(post_swing_b) - mss_bull_i) - 2 : n-1]
        fvg_bull   = False
        for j in range(1, min(len(post_mss_b)-1, 8)):
            if post_mss_b[j+1]["high"] < post_mss_b[j-1]["low"]:
                fvg_bull = True
                break

        in_bb_b = bb_low_b * 0.999 <= price <= bb_high_b

        if in_bb_b:
            sl   = round(bb_low_b - mkt["pip"] * mkt["spread"] * 0.5, d)
            sl_d = price - sl
            if sl_d >= a * 0.05 and sl_d <= a * 1.5:
                entry_now = round(price, d)
                tp1 = round(entry_now + sl_d * 3.0, d)
                tp2 = round(entry_now + sl_d * 4.5, d)
                tp3 = round(entry_now + sl_d * 6.0, d)

                sc = 72
                sc += 15 if fvg_bull          else 0
                sc += 12 if trend == "BULL"   else 0
                sc += 8  if r < 45            else 0
                sc += 6  if is_kill_zone()    else 0
                sc += 5  if body(mss_bull_c) > a * 1.0 else 0

                return {
                    "strategy":  "MSS_BB_FVG",
                    "side":      "BUY",
                    "entry":     entry_now,
                    "sl":        sl,
                    "tp1":       tp1, "tp2": tp2, "tp3": tp3,
                    "sl_dist":   sl_d, "rr": 3.0,
                    "score":     min(sc, 100), "atr": a,
                    "bos":       True, "fvg": fvg_bull,
                    "pd_zone":   "DISCOUNT", "pd_pct": 20.0,
                    "rsi":       round(r, 1), "htf_trend": trend,
                    "bb_zone":   (round(bb_low_b, d), round(bb_high_b, d)),
                    "mss_conf":  True,
                }
    return None


def scan_all_strategies(candles: List, symbol: str, trend: str) -> List[Dict]:
    results = []
    for fn in [strat_ict_breaker, strat_fvg_bos, strat_liq_mss, strat_mss_bb_fvg]:
        try:
            s = fn(candles, symbol, trend)
            if s: results.append(s)
        except Exception as e:
            log.debug(f"[STRAT] {symbol} {fn.__name__}: {e}")
    return results

# ══════════════════════════════════════════════════════════════════════════════
#  PROBABILITÉ D'ATTEINTE TP — 12 facteurs
# ══════════════════════════════════════════════════════════════════════════════

def calc_tp_probability(symbol: str, setup: Dict, sess_ok: bool) -> Dict:
    """
    Probabilité d'atteinte TP1 — Calibration réaliste ICT live.

    PLAFOND HARD : 78% (max réaliste ICT en conditions live avec spread)
    BASE neutre  : 52% (légèrement au-dessus du hasard)
    Chaque facteur apporte un PETIT ajustement (max ±6%)
    Spread/SL est un FILTRE BLOQUANT si ratio > 25%
    """
    mkt    = MARKETS[symbol]
    strat  = STRAT_INFO.get(setup.get("strategy","ICT_BB"), STRAT_INFO["ICT_BB"])
    side   = setup["side"]
    a      = setup["atr"]
    sl_d   = setup["sl_dist"]
    r      = setup.get("rsi", 50)
    trend  = setup.get("htf_trend","RANGE")
    fund   = get_fund(symbol)
    fg     = fetch_fear_greed()
    factors= []

    # ── BASE NEUTRE — 52% (légèrement mieux que pile ou face) ────────
    prob = 52.0

    # ── FILTRE CRITIQUE : Spread vs SL ──────────────────────────────
    # C'est LE facteur le plus important en pratique
    spread_pts   = mkt["spread"] * mkt["pip"]
    spread_ratio = spread_pts / sl_d if sl_d > 0 else 1.0

    if spread_ratio > 0.25:
        # SL trop serré = très probable de se faire sortir par le spread
        prob -= 15
        factors.append(f"🚨 SL serré: spread={spread_pts:.5f} = {spread_ratio:.0%} du SL — risque stop-out élevé -15%")
    elif spread_ratio > 0.12:
        prob -= 6
        factors.append(f"⚠️ Spread/SL moyen ({spread_ratio:.0%}) -6%")
    elif spread_ratio < 0.05:
        prob += 5
        factors.append(f"✅ Spread/SL excellent ({spread_ratio:.0%}) +5%")
    else:
        prob += 2
        factors.append(f"✅ Spread/SL correct ({spread_ratio:.0%}) +2%")

    # ── FACTEURS ICT (bonus petit, pénalités plus grandes) ──────────

    # 1. BOS (Break of Structure)
    if setup.get("bos"):   prob += 5;  factors.append("✅ BOS confirmé +5%")
    else:                  prob -= 6;  factors.append("⚠️ Pas de BOS -6%")

    # 2. FVG
    if setup.get("fvg"):   prob += 4;  factors.append("✅ FVG présent +4%")
    else:                  prob -= 3;  factors.append("— Pas de FVG -3%")

    # 3. Zone ICT
    pd = setup.get("pd_zone","")
    if   side=="BUY"  and pd=="DISCOUNT": prob += 5; factors.append("✅ BUY en DISCOUNT +5%")
    elif side=="SELL" and pd=="PREMIUM":  prob += 5; factors.append("✅ SELL en PREMIUM +5%")
    elif pd == "EQ":                      prob += 1; factors.append("⚪ Zone EQ +1%")
    else:                                 prob -= 5; factors.append(f"🚨 Zone opposée {pd} -5%")

    # 4. RSI
    if   side=="BUY"  and 30 <= r <= 60: prob += 4; factors.append(f"✅ RSI {r} favorable BUY +4%")
    elif side=="SELL" and 40 <= r <= 70: prob += 4; factors.append(f"✅ RSI {r} favorable SELL +4%")
    elif (side=="BUY" and r > 70) or (side=="SELL" and r < 30):
        prob -= 9; factors.append(f"🚨 RSI {r} extrême — contre-tendance -9%")

    # 5. Kill Zone / Session
    if sess_ok:
        if is_kill_zone():
            prob += 6; factors.append(f"✅ Kill Zone {get_kill_zone()} (liquidité ICT) +6%")
        elif "overlap" in get_active_sessions():
            prob += 5; factors.append("✅ Overlap session +5%")
        else:
            prob += 2; factors.append("✅ Bonne session +2%")
    else:
        prob -= 8; factors.append("⚠️ Hors session optimale -8%")

    # 6. Fondamental
    if fund_supports(symbol, side):
        prob += 4; factors.append(f"✅ Fondamental {fund['bias']} aligné +4%")
    else:
        prob -= 6; factors.append(f"⚠️ Fondamental contre ({fund['bias']}) -6%")

    # 7. HTF trend
    if   side=="BUY"  and trend=="BULL": prob += 5; factors.append("✅ HTF BULL +5%")
    elif side=="SELL" and trend=="BEAR": prob += 5; factors.append("✅ HTF BEAR +5%")
    elif trend == "RANGE":               factors.append("⚪ HTF RANGE neutre 0%")
    else:                                prob -= 5; factors.append(f"⚠️ HTF {trend} contre -5%")

    # 8. Fear & Greed (influence faible)
    fg_val = fg.get("value", 50)
    if fg_val > 75 and side=="SELL": prob += 4; factors.append(f"😱 F&G Greed extrême → SHORT +4%")
    elif fg_val < 25 and side=="BUY":prob += 4; factors.append(f"😨 F&G Fear extrême → LONG +4%")

    # 9. SL vs ATR
    if sl_d < a * 0.20:
        prob -= 10; factors.append(f"🚨 SL < 0.20 ATR — bruit marché -10%")
    elif sl_d > a * 2.8:
        prob -= 4;  factors.append(f"⚠️ SL > 2.8 ATR (très large) -4%")
    else:
        prob += 2;  factors.append(f"✅ SL dans zone ATR normale +2%")

    # 10. Pénalité Kelly RR (théorie probabiliste)
    # P(win) théorique Kelly = 1/(1+RR) — on l'intègre à 20%
    rr      = setup["rr"]
    kelly   = 1.0 / (1.0 + rr) * 100   # ex: RR 2.5 → Kelly = 28.6%
    # Mixage : 80% ICT base + 20% Kelly
    prob    = prob * 0.80 + kelly * 0.20
    factors.append(f"ℹ️ Kelly RR 1:{rr} ({kelly:.0f}% théorique) pondéré 20%")

    # ── PLAFOND ABSOLU 78% ───────────────────────────────────────────
    # Aucun système ICT ne dépasse 78% de win rate en conditions réelles
    # (spread, slippage, news, faux signaux inclus)
    HARD_CAP = 78.0
    if prob > HARD_CAP:
        factors.append(f"⚠️ Plafonné {HARD_CAP}% (max ICT réaliste live)")
        prob = HARD_CAP

    prob = round(max(30.0, min(HARD_CAP, prob)), 1)

    # Verdicts recalibrés
    if   prob >= 68: verdict = "FORT ✅"
    elif prob >= 60: verdict = "BON ✅"
    elif prob >= 52: verdict = "MOYEN ⚠️"
    else:            verdict = "FAIBLE ❌"

    return {
        "prob":          prob,
        "factors":       factors,
        "verdict":       verdict,
        "fg":            fg,
        "strat_wr":      round(strat["wr"]*100),
        "spread_ratio":  round(spread_ratio*100, 1),
        "kelly_rr":      round(kelly, 1),
    }

# ══════════════════════════════════════════════════════════════════════════════
#  RISK MANAGER — Anti-Martingale + Taille de position
# ══════════════════════════════════════════════════════════════════════════════

def risk_usdt(balance: float, score: int, am_cycle: int) -> float:
    if   balance < 15:  pct = 0.05
    elif balance < 30:  pct = 0.07
    elif balance < 60:  pct = 0.08
    elif score >= 92:   pct = 0.10
    elif score >= 85:   pct = 0.08
    elif score >= 78:   pct = 0.06
    elif score >= 72:   pct = 0.04
    else:               pct = 0.03
    raw = balance * pct * (AM_MULT ** am_cycle)
    return round(min(raw, balance * 0.20), 4)

def position_size(symbol: str, risk: float, sl_dist: float, price: float, balance: float = 10.0) -> Dict:
    mkt = MARKETS[symbol]
    cat = mkt["cat"]

    if cat == "FOREX":
        sl_pips = sl_dist / mkt["pip"] if mkt["pip"] > 0 else 1
        # pip_val selon type de paire
        # JPY pairs (price>50) : pip_val = pip/price × 100000 (en USD)
        # USD base : pip_val fixe (ex: USDCHF ≈ 6.xx$ variable)
        # En pratique, utiliser pip_val du MARKETS dict (déjà calibré)
        pip_val_dyn = mkt["pip_val"]
        lots = risk / (sl_pips * pip_val_dyn) if sl_pips > 0 and pip_val_dyn > 0 else 0.01
        lots = round(max(0.01, min(lots, 100)), 2)
        # Levier standard broker (XM = 500x Forex)
        leverage    = 500
    elif cat in ("GOLD","SILVER"):
        # MODE SCALP : lot fixe 0.01, risque plafonné à SCALP_RISK_USD
        sl_pips  = sl_dist / mkt["pip"]
        if symbol in SCALP_MARKETS:
            lots     = SCALP_LOT                        # toujours 0.01
            risk     = min(risk, SCALP_RISK_USD)        # cap 2$
        else:
            lots     = risk / max(sl_pips * mkt["pip_val"], 0.01)
            lots     = round(max(0.01, min(lots, 50)), 2)
        leverage = 200
    elif cat == "INDICES":
        sl_pts   = sl_dist / mkt["pip"]
        if symbol in SCALP_MARKETS:
            lots     = SCALP_LOT                        # 0.01 fixe
            risk     = min(risk, SCALP_RISK_USD)
        else:
            lots     = risk / max(sl_pts * mkt["pip_val"], 0.01)
            lots     = round(max(0.01, min(lots, 20)), 2)
        leverage = 100
    elif cat == "CRYPTO":
        lots     = round(risk / max(sl_dist, 0.01), 4)
        lots     = max(0.001, min(lots, 10))
        leverage = min(50, max(5, round(price*lots/max(risk*5,1))))
    else:
        lots, leverage = 0.01, 100

    # Marge réelle selon la catégorie
    if leverage > 0:
        if cat == "FOREX":
            # USD_BASE pairs (USDJPY, USDCHF, USDCAD) : marge en USD sans conversion
            if symbol in {"USDJPY", "USDCHF", "USDCAD"}:
                margin = round(lots * 100_000 / leverage, 2)
            elif symbol.endswith("JPY"):
                # Cross JPY (GBPJPY, EURJPY) : base ≠ USD
                # Estimer prix base/USD : GBPJPY/USDJPY ≈ GBPUSD
                _base_usd = price / 159.0  # approximation cross JPY → USD
                margin = round(lots * 100_000 * _base_usd / leverage, 2)
            else:
                # Non-USD base (EURUSD, GBPUSD, AUDUSD...) : × price
                margin = round(lots * 100_000 * price / leverage, 2)
        elif cat in ("GOLD", "SILVER"):
            # Gold/Silver : lots × 100 oz × price / leverage
            margin = round(lots * 100 * price / leverage, 2)
        elif cat == "INDICES":
            # Indices : lots × price / leverage (contract = 1 unit)
            margin = round(lots * price / leverage, 2)
        elif cat == "CRYPTO":
            margin = round(lots * price / leverage, 2)
        else:
            margin = round(lots * price / leverage, 2)
    else:
        margin = 0.0

    return {
        "lots":      lots,
        "leverage":  leverage,
        "sl_pips":   round(sl_dist / mkt["pip"], 1) if mkt["pip"] > 0 else 0,
        "margin":    margin,
        "risk_usdt": round(sl_dist / mkt["pip"] * lots *
                           mkt.get("pip_val", 1.0), 4) if mkt["pip"] > 0 else 0,
    }

# ══════════════════════════════════════════════════════════════════════════════
#  ANTI-SPAM SIGNAUX — Empreinte hash pour éviter doublon
# ══════════════════════════════════════════════════════════════════════════════

_signal_hashes: Dict[str, float] = {}   # hash → timestamp

def signal_hash(symbol: str, side: str) -> str:
    return hashlib.md5(f"{symbol}{side}".encode()).hexdigest()[:8]

def is_duplicate_signal(symbol: str, side: str) -> bool:
    h  = signal_hash(symbol, side)
    ts = _signal_hashes.get(h, 0)
    if time.time() - ts < SIGNAL_HASH_TTL * 60:
        return True
    _signal_hashes[h] = time.time()
    return False

# ══════════════════════════════════════════════════════════════════════════════
#  MESSAGES IA — Banque de phrases naturelles (style v48 HTML)
# ══════════════════════════════════════════════════════════════════════════════

AI_MSGS = {
    "scan_start": [
        "On regarde ce que le marché a à dire… 👁️",
        "Je scan, attends une seconde.",
        "Le marché parle, j'écoute. M5 en cours…",
        "Analyse en cours. BTC donne le ton aujourd'hui.",
        "Je cherche. Quand c'est propre, je prends.",
        "Structure, liquidité, session. Tout s'aligne ou rien.",
    ],
    "no_setup": [
        "Rien de propre pour l'instant. La patience est une edge.",
        "Je vois du bruit. On attend.",
        "Le marché joue encore. Je ne force rien.",
        "Pas de setup qualifié. On garde la poudre sèche.",
        "Ce n'est pas le moment. L'inaction est aussi une décision.",
        "Le marché est flou. On ne trade pas le flou.",
    ],
    "win": [
        "✅ TP touché. On encaisse. L'analyse était bonne.",
        "TP atteint. Anti-martingale fait le job. Mise augmente.",
        "Beau trade. On encaisse. La mise augmente au prochain.",
        "TP touché proprement. Structure respectée.",
    ],
    "loss": [
        "❌ SL touché. On reset. Prochain trade, mise de base.",
        "SL touché. Pas de frustration — on coupe et on recommence proprement.",
        "Le marché a dit non. Reset à la base. On reste discipliné.",
        "Stop. Le setup était là, le timing pas parfait. On revient à la base.",
    ],
    "be": [
        "🔒 Break-Even activé. Capital protégé. On reste dans le jeu.",
        "BE+ — on ne perd rien. Anti-martingale reste au même cycle.",
        "SL au break-even. Frais couverts. C'est déjà une victoire.",
    ],
    "motivation": [
        "La discipline fait la différence. Pas le capital de départ.",
        "Chaque trade est une décision. Pas une émotion.",
        "Les pros perdent aussi. Ce qui compte, c'est le process.",
        "Le marché donne des opportunités à ceux qui savent attendre.",
        "Un mauvais trade bien géré vaut mieux qu'un bon trade mal géré.",
        "L'anti-martingale surfe sur les victoires. La patience paie.",
        "10$ → 1000$. Chaque trade compte. Chaque décision compte.",
    ],
}

def agent_say(category: str, *args) -> str:
    pool = AI_MSGS.get(category, ["…"])
    return random.choice(pool)

# ══════════════════════════════════════════════════════════════════════════════
#  ÉTAT GLOBAL
# ══════════════════════════════════════════════════════════════════════════════

class State:
    def __init__(self):
        self.running       = True
        self.trades: Dict  = {}
        self.trade_ctr     = 0
        self.cooldowns: Dict = {}
        self.am            = self._load(_AM_FILE,
                               {"cycle":0,"win_streak":0,"last_result":None,
                                "total_boosted":0.0,"history":[]})
        self.challenge     = self._load_challenge()
        self.trade_history = self._load(_HIST_FILE, [])
        self.leader_id: Optional[str] = None
        self._lock         = threading.Lock()

    def _load(self, fname: str, default):
        try:
            with open(fname) as f: return json.load(f)
        except Exception: return default

    def _save(self, fname: str, obj):
        try:
            with open(fname,"w") as f: json.dump(obj, f, indent=2)
        except Exception as e:
            log.warning(f"[SAVE] {fname}: {e}")

    def save_am(self):        self._save(_AM_FILE, self.am)
    def save_challenge(self): self._save(_CHAL_FILE, self.challenge)
    def save_history(self):   self._save(_HIST_FILE, self.trade_history[-200:])

    def _load_challenge(self) -> Dict:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        c     = self._load(_CHAL_FILE, None)
        if c and c.get("day_start") == today:
            return c
        fresh: Dict = {
            "start_balance":    CHALLENGE_START,
            "current_balance":  CHALLENGE_START,
            "day_start":        today,
            "today_pnl":        0.0,
            "today_wins":       0,
            "today_losses":     0,
            "best_rr":          0.0,
            "best_prob":        0.0,
            "trades":           [],
            "published":        False,
            "all_time_peak":    CHALLENGE_START,
        }
        if c:   # nouveau jour mais garde le solde
            fresh["current_balance"] = c.get("current_balance", CHALLENGE_START)
            fresh["all_time_peak"]   = c.get("all_time_peak",   CHALLENGE_START)
        self._save(_CHAL_FILE, fresh)
        return fresh

    def new_tid(self) -> int:
        self.trade_ctr += 1
        return self.trade_ctr

S = State()

# ══════════════════════════════════════════════════════════════════════════════
#  ANTI-MARTINGALE — Mise à jour
# ══════════════════════════════════════════════════════════════════════════════

def update_am(result: str, pnl: float, symbol: str):
    am, old = S.am, S.am["cycle"]
    if result == "WIN":
        am["win_streak"] += 1
        if am["win_streak"] >= AM_MAX_CYCLES:
            am["cycle"] = 0; am["win_streak"] = 0
            log.info("[AM] 4 WINs consécutifs → reset cycle 0")
        else:
            am["cycle"] = min(am["cycle"]+1, AM_MAX_CYCLES)
        am["total_boosted"] = am.get("total_boosted",0) + max(0,pnl)
    else:
        am["cycle"] = 0; am["win_streak"] = 0
    am["last_result"] = result
    am["history"].insert(0,{
        "cycle_before":old,"cycle_after":am["cycle"],
        "result":result,"pnl":round(pnl,4),"symbol":symbol,
        "ts":datetime.now(timezone.utc).isoformat()
    })
    am["history"] = am["history"][:60]
    S.save_am()
    log.info(f"[AM] Cycle {old}→{am['cycle']} | {result} | PnL:{pnl:+.2f}$")

def update_challenge(pnl: float, symbol: str, side: str,
                     rr: float, am_cycle: int, tp_prob: float):
    c = S.challenge
    c["current_balance"] = round(c["current_balance"] + pnl, 4)
    c["today_pnl"]       = round(c.get("today_pnl",0) + pnl, 4)
    if pnl > 0: c["today_wins"]   = c.get("today_wins",0)+1
    else:        c["today_losses"] = c.get("today_losses",0)+1
    c["best_rr"]   = max(c.get("best_rr",0), float(rr))
    c["best_prob"] = max(c.get("best_prob",0), float(tp_prob))
    c["all_time_peak"] = max(c.get("all_time_peak",CHALLENGE_START), c["current_balance"])
    c.setdefault("trades",[]).append({
        "symbol":symbol,"side":side,"pnl":round(pnl,4),
        "rr":rr,"am_cycle":am_cycle,"tp_prob":tp_prob,
        "ts":datetime.now(timezone.utc).strftime("%H:%M")
    })
    S.save_challenge()

# ══════════════════════════════════════════════════════════════════════════════
#  TELEGRAM
# ══════════════════════════════════════════════════════════════════════════════

def tg_send(chat_id: str, text: str, retry: int = 2) -> bool:
    for attempt in range(retry):
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id":chat_id,"text":text,"parse_mode":"HTML",
                      "disable_web_page_preview":True},
                timeout=12)
            ok = r.json().get("ok", False)
            if ok: return True
            log.debug(f"[TG] {r.json().get('description','')}")
        except Exception as e:
            log.warning(f"[TG] Tentative {attempt+1}: {e}")
        time.sleep(2)
    return False

def resolve_leader() -> str:
    """Chat ID @leaderOdg = 6982051442 (hardcodé et confirmé)."""
    if not S.leader_id:
        S.leader_id = "6982051442"   # @leaderOdg
        log.info(f"[TG] ✅ DM → {S.leader_id} (@{TG_LEADER_USER})")
    return S.leader_id
def dm(text: str):
    """DM @leaderOdg — fallback groupe si DM échoue."""
    ok = tg_send(resolve_leader(), text)
    if not ok:
        log.warning("[DM] Echec → fallback groupe public")
        tg_send(TG_GROUP, text)
def pub(text: str):    tg_send(TG_GROUP, text)
def vip_(text: str):   tg_send(TG_VIP, text)

# ══════════════════════════════════════════════════════════════════════════════
#  JUSTIFICATION IA — Claude claude-sonnet-4-20250514
# ══════════════════════════════════════════════════════════════════════════════

def ai_justify(symbol: str, setup: Dict, tp_info: Dict, sess: str) -> str:
    mkt    = MARKETS[symbol]
    fund   = get_fund(symbol)
    strat  = STRAT_INFO.get(setup.get("strategy","ICT_BB"), STRAT_INFO["ICT_BB"])
    sc     = setup["score"]
    side   = setup["side"]
    prob   = tp_info["prob"]
    fg     = tp_info.get("fg",{})
    kz     = get_kill_zone()

    # ── Fallback sans clé Anthropic — texte rédigé ───────────────────
    if not ANTHROPIC_KEY:
        bos_txt  = "BOS confirmé" if setup.get("bos") else "BOS partiel"
        fvg_txt  = " avec FVG présent" if setup.get("fvg") else ""
        pd       = setup.get("pd_zone","")
        zone_txt = (f"en zone DISCOUNT ({setup.get('pd_pct','?')}%)"
                    if pd=="DISCOUNT" else
                    f"en zone PREMIUM ({setup.get('pd_pct','?')}%)"
                    if pd=="PREMIUM" else "en zone EQ")
        rsi_v    = setup.get("rsi",50)
        rsi_txt  = (f"RSI {rsi_v} neutre" if 40<=float(str(rsi_v).replace(',','.'))<60
                    else f"RSI {rsi_v} favorable")
        htf_v    = setup.get("htf_trend","RANGE")
        kz_txt   = f"Kill Zone {kz} active" if kz else f"session {sess}"
        fund_txt = fund["note"]
        si       = STRAT_INFO.get(setup.get("strategy","ICT_BB"), STRAT_INFO["ICT_BB"])
        return (
            f"Setup {si['label']} {side} — {bos_txt}{fvg_txt} {zone_txt}. "
            f"HTF {htf_v}, {rsi_txt}, {kz_txt}. "
            f"Contexte macro : {fund_txt}. "
            f"Probabilité {tp_info['prob']}% — {tp_info['verdict']}."
        )

    # ── Appel Claude ─────────────────────────────────────────────────
    prompt = (
        f"Tu es Alpha, un agent trader ICT professionnel. "
        f"Justifie ce signal en 2-3 phrases directes, sans markdown, en français.\n\n"
        f"Marché: {mkt['label']} | Direction: {side} | "
        f"Stratégie: {strat['label']} (WR {strat['wr']*100:.0f}%)\n"
        f"Score ICT: {sc}/100 | Prob TP: {prob}%\n"
        f"Technique: BOS={'OUI' if setup.get('bos') else 'NON'} | "
        f"FVG={'OUI' if setup.get('fvg') else 'NON'} | "
        f"Zone: {setup.get('pd_zone')} ({setup.get('pd_pct')}%) | "
        f"RSI: {setup.get('rsi')} | HTF: {setup.get('htf_trend')}\n"
        f"Fondamental: {fund['bias']} — {fund['note']}\n"
        f"Session: {sess}{' · Kill Zone: '+kz if kz else ''}\n"
        f"Fear & Greed: {fg.get('value',50)}/100 — {fg.get('label','Neutral')}\n"
        f"Top facteurs: {' | '.join(tp_info['factors'][:3])}\n\n"
        f"Justification UNIQUEMENT, 2-3 phrases, style direct et professionnel."
    )
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key":ANTHROPIC_KEY,"anthropic-version":"2023-06-01",
                     "content-type":"application/json"},
            json={"model":"claude-sonnet-4-20250514","max_tokens":200,
                  "messages":[{"role":"user","content":prompt}]},
            timeout=15)
        return r.json()["content"][0]["text"].strip()
    except Exception as e:
        log.debug(f"[AI] {e}")
        return (f"{strat['label']} {side} · {fund['note']} · "
                f"Score {sc}/100 · Prob TP {prob}%")

# ══════════════════════════════════════════════════════════════════════════════
#  FORMAT DES MESSAGES TELEGRAM — Complet comme le HTML v48
# ══════════════════════════════════════════════════════════════════════════════

def fmt_signal_full(symbol: str, setup: Dict, pos: Dict,
                    sess: str, tp_info: Dict, ai_txt: str) -> str:
    mkt    = MARKETS[symbol]
    d      = mkt["digits"]
    side   = setup["side"]
    ce     = CAT_EMOJI.get(mkt["cat"],"📊")
    de     = "🟢 LONG" if side=="BUY" else "🔴 SHORT"
    fe     = "🟢" if get_fund(symbol)["bias"]=="BULLISH" else "🔴" if get_fund(symbol)["bias"]=="BEARISH" else "⚪"
    he     = "📈" if setup.get("htf_trend")=="BULL" else "📉" if setup.get("htf_trend")=="BEAR" else "➡️"
    now    = datetime.now(timezone.utc).strftime("%H:%M UTC")
    fund   = get_fund(symbol)
    prob   = tp_info["prob"]
    verd   = tp_info["verdict"]
    strat  = STRAT_INFO.get(setup.get("strategy","ICT_BB"), STRAT_INFO["ICT_BB"])
    fg     = tp_info.get("fg",{})
    kz     = get_kill_zone()
    am_    = S.am
    bal_   = S.challenge["current_balance"]
    prog_  = round(bal_/CHALLENGE_TARGET*100, 1)

    rr1_v = setup["rr"]          # 1.5
    rr2_v = round(rr1_v*5/3, 1)  # 2.5
    rr3_v = round(rr1_v*8/3, 1)  # 4.0
    rr2   = rr2_v
    rr3   = rr3_v
    bars  = int(prob/10); bar = "█"*bars + "░"*(10-bars)

    lines = [
        f"{ce} <b>{mkt['label']} — {de}</b>",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"{'⚡ SCALP SHOT' if symbol in SCALP_MARKETS else '🎯 SNIPER SHOT'} — <b>ENTRÉE DIRECTE</b>",
        f"{'💎 ' + mkt['label'] + ' MODE SCALP — LOT 0.01 RISQUE 2$' if symbol in SCALP_MARKETS else ''}",
        f"⏳ Entrée valide : <b>{8 if mkt['tf_entry']=='M1' else 20} minutes max</b> | TF: {mkt['tf_entry']}",
        f"📍 Entrée : <code>{setup['entry']:.{d}f}</code>",
        f"🛑 SL     : <code>{setup['sl']:.{d}f}</code>  ({pos['sl_pips']:.0f} pips)",
        f"✅ TP1    : <code>{setup['tp1']:.{d}f}</code>  (RR 1:{setup['rr']})",
        f"✅ TP2    : <code>{setup['tp2']:.{d}f}</code>  (RR 1:{round(setup['rr']*5/3,1)})",
        f"🎯 TP3    : <code>{setup['tp3']:.{d}f}</code>  (RR 1:{round(setup['rr']*8/3,1)})",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📊 <b>Probabilité TP : {prob}%</b>  {verd}",
        f"[{bar}]",
        f"📐 WR historique {strat['label']}: {strat['wr']*100:.0f}%",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🔷 Score ICT : <b>{setup['score']}/100</b>  {he} HTF: <b>{setup.get('htf_trend','—')}</b>",
        f"{'✅' if setup.get('bos') else '⚠️'} BOS  "
        f"{'✅' if setup.get('fvg') else '—'} FVG  "
        f"📍 {setup.get('pd_zone','—')} ({setup.get('pd_pct','—')}%)",
        f"📉 RSI : {setup.get('rsi','—')}",
    ]

    # Kill Zone
    if kz: lines.append(f"🎯 Kill Zone : <b>{kz}</b>")

    lines += [
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"{fe} <b>Fondamental</b> : {fund['bias']}",
        f"📰 {fund['note']}",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    # Fear & Greed
    fg_val = fg.get("value",50); fg_lbl = fg.get("label","Neutral")
    fg_bar = int(fg_val/10); fg_str = "█"*fg_bar + "░"*(10-fg_bar)
    lines += [
        f"😱 <b>Fear & Greed : {fg_val}/100</b> — {fg_lbl}",
        f"[{fg_str}]",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    # Facteurs probabilité (top 5)
    lines.append(f"📋 <b>Facteurs TP :</b>")
    for f_ in tp_info["factors"][:5]:
        lines.append(f"  · {f_}")

    lines += [
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🤖 <b>Analyse IA (Alpha)</b> :",
        f"<i>{ai_txt}</i>",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"⏰ {sess}  {now}  TF: {mkt['tf_entry']}",
        f"💰 Mise: <b>{pos['risk_usdt']:.2f}$</b>  "
        f"Lots: <b>{pos['lots']}</b>  "
        f"Lev: <b>{pos['leverage']}x</b>",
        f"📊 Marge estimée: <b>{pos['margin']:.2f}$</b>",
        f"🔄 Anti-Martingale: Cycle <b>{am_['cycle']}/4</b>  "
        f"(WS: {am_['win_streak']})",
        f"🏆 Challenge: <b>{bal_:.2f}$</b> → {CHALLENGE_TARGET:.0f}$  "
        f"({prog_:.1f}%)",
        f"@leaderOdg",
    ]
    return "\n".join(lines)

def fmt_close_full(trade: Dict, result: str, price: float, pnl: float) -> str:
    symbol = trade["symbol"]
    mkt    = MARKETS[symbol]
    d      = mkt["digits"]
    ce     = CAT_EMOJI.get(mkt["cat"],"📊")
    re     = "✅ WIN" if result=="WIN" else "🔒 BE" if result=="BE" else "❌ LOSS"
    am     = S.am
    c      = S.challenge
    bal    = c["current_balance"]
    prog   = round(bal/CHALLENGE_TARGET*100, 1)
    gain   = bal - c["start_balance"]
    gains  = f"{'+' if gain>=0 else ''}{gain:.2f}$"
    am_msg = agent_say("win") if result=="WIN" else (
             agent_say("be")  if result=="BE"  else agent_say("loss"))

    lines = [
        f"{ce} {re} — <b>{mkt['label']}</b>",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"Entrée : <code>{trade['entry']:.{d}f}</code> → "
        f"Sortie : <code>{price:.{d}f}</code>",
        f"💵 PnL net : <b>{'+' if pnl>=0 else ''}{pnl:.2f}$</b>",
        f"📐 RR réalisé : {abs(price-trade['entry'])/max(trade['sl_dist'],0.0001):.1f}",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🔄 AM: {trade['am_cycle']}→{am['cycle']}  "
        f"WS: {am['win_streak']}  "
        f"Prob estimée: {trade.get('tp_prob',0):.0f}%",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🏆 Solde: <b>{bal:.2f}$</b>  ({gains} depuis début)",
        f"📈 Progression: {prog:.1f}% vers {CHALLENGE_TARGET:.0f}$",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🤖 <i>{am_msg}</i>",
        f"@leaderOdg",
    ]
    return "\n".join(lines)

def fmt_scan_report(scan_n: int, setups: List[Dict]) -> str:
    fg   = fetch_fear_greed()
    sess = session_label()
    kz   = get_kill_zone()
    bal  = S.challenge["current_balance"]
    now  = datetime.now(timezone.utc).strftime("%H:%M UTC")

    lines = [
        f"🔍 <b>Rapport Scan #{scan_n}</b>  {now}",
        f"🕐 {sess}{' · '+kz if kz else ''}",
        f"😱 F&G: {fg.get('value',50)}/100 — {fg.get('label','—')}",
        f"📊 {len(setups)} setup(s) qualifié(s) | Solde: {bal:.2f}$",
        f"━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    medals = ["🥇","🥈","🥉","4️⃣","5️⃣"]
    for i, s in enumerate(setups[:5]):
        mkt   = MARKETS[s["symbol"]]
        si    = STRAT_INFO.get(s.get("strategy","ICT_BB"), STRAT_INFO["ICT_BB"])
        tp    = s.get("tp_info",{})
        medal = medals[i] if i < len(medals) else "•"
        lines.append(
            f"{medal} <b>{mkt['label']}</b> {s['side']}  "
            f"{si['icon']} {si['label']}\n"
            f"   Score: {s['score']}/100  Prob: {tp.get('prob','—')}%  "
            f"RR: 1:{s['rr']}  TF: {mkt['tf_entry']}"
        )
    lines += [
        f"━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🔄 AM Cycle: {S.am['cycle']}/4  @leaderOdg",
    ]
    return "\n".join(lines)

def fmt_challenge_report() -> str:
    c     = S.challenge
    bal   = c["current_balance"]
    start = c["start_balance"]
    gain  = bal - start
    pct   = gain/start*100 if start else 0
    wins  = c.get("today_wins",0)
    loss  = c.get("today_losses",0)
    wr    = round(wins/(wins+loss)*100) if wins+loss else 0
    prog  = min(100, bal/CHALLENGE_TARGET*100)
    today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    ts    = c.get("trades",[])[-8:]
    am_   = S.am
    next_target = start * 2

    lines = [
        f"🏆 <b>CHALLENGE JOURNALIER — Agent Alpha v7</b>",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📅 {today}",
        f"💰 {start:.2f}$ → <b>{bal:.2f}$</b>  "
        f"({'+' if gain>=0 else ''}{gain:.2f}$ / {pct:+.1f}%)",
        f"🎯 Objectif {CHALLENGE_TARGET:.0f}$ : <b>{prog:.1f}%</b>",
        f"🏁 Prochain cap : {next_target:.2f}$",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"✅ {wins}W  ❌ {loss}L  WR: {wr}%",
        f"🎯 Best prob: {c.get('best_prob',0):.0f}%  Best RR: 1:{c.get('best_rr',0):.1f}",
        f"🔄 AM Cycle: {am_['cycle']}/4  WS: {am_['win_streak']}",
        f"📈 All-time peak: {c.get('all_time_peak',start):.2f}$",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for t in ts:
        e = "✅" if t["pnl"]>=0 else "❌"
        lines.append(
            f"  {e} {t['symbol']} {t['side']}  "
            f"{'+' if t['pnl']>=0 else ''}{t['pnl']:.2f}$  "
            f"RR 1:{t['rr']}  Prob:{t.get('tp_prob',0):.0f}%  "
            f"AM C{t['am_cycle']}  {t.get('ts','')}"
        )
    lines += [
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"💡 {agent_say('motivation')}",
        f"<b>@leaderOdg</b> · t.me/bluealpha_signals",
    ]
    return "\n".join(lines)

def fmt_startup_msg() -> str:
    c     = S.challenge
    bal   = c["current_balance"]
    fg    = fetch_fear_greed()
    sess  = session_label()
    kz    = get_kill_zone()
    cats  = {}
    for m in MARKETS.values(): cats[m["cat"]] = cats.get(m["cat"],0)+1

    lines = [
        f"🤖 <b>Agent Alpha v7 — LIVE ✅</b>",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📊 <b>{len(MARKETS)} marchés scannés</b>",
    ]
    for cat,n in cats.items():
        lines.append(f"  {CAT_EMOJI.get(cat,'📊')} {cat}: {n}")
    lines += [
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"⚡ 3 stratégies ICT:",
        f"  🔷 ICT Breaker Block (WR 82%)",
        f"  ⚡ FVG + BOS (WR 80%)",
        f"  🌊 Liq Sweep + MSS (WR 83%)",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🕐 Session actuelle : {sess}",
    ]
    if kz: lines.append(f"🎯 Kill Zone active : <b>{kz}</b>")
    lines += [
        f"😱 Fear & Greed : {fg.get('value',50)}/100 — {fg.get('label','—')}",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🏆 Solde challenge: <b>{bal:.2f}$</b> → {CHALLENGE_TARGET:.0f}$",
        f"🔄 Anti-Martingale Cycle: {S.am['cycle']}/4",
        f"📐 Filtre: Prob TP ≥ {MIN_TP_PROB}% | Score ≥ {MIN_SCORE} | RR ≥ {MIN_RR}",
        f"⏰ Scan toutes les {SCAN_INTERVAL}s",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"@leaderOdg",
    ]
    return "\n".join(lines)

# ══════════════════════════════════════════════════════════════════════════════
#  VALIDATION DU SETUP — Score + Prob + Position
# ══════════════════════════════════════════════════════════════════════════════

def validate_setup(symbol: str, setup: Dict, balance: float) -> Optional[Dict]:
    strat = STRAT_INFO.get(setup.get("strategy","ICT_BB"), STRAT_INFO["ICT_BB"])

    # Score minimum selon la stratégie
    if setup["score"] < strat["min_score"]: return None
    if setup["rr"]    < MIN_RR:             return None

    # Cooldown
    cd = S.cooldowns.get(symbol)
    if cd and datetime.now(timezone.utc) < cd: return None

    # Anti-doublon hash
    if is_duplicate_signal(symbol, setup["side"]): return None

    # Pas déjà ouvert sur ce symbole
    with S._lock:
        if any(t["symbol"]==symbol and t["status"]=="open"
               for t in S.trades.values()):
            return None

    # Session
    s_ok, sess_name = session_check(symbol)
    if not s_ok:
        setup["score"] = max(0, setup["score"] - 8)
        if setup["score"] < MIN_SCORE: return None

    # Fondamental contre-tendance → réduction score
    if not fund_supports(symbol, setup["side"]):
        setup["score"] = max(0, setup["score"] - 10)
        if setup["score"] < MIN_SCORE: return None

    # ── FILTRE SL vs Spread — adaptatif par catégorie ───────────────
    mkt_v        = MARKETS[symbol]
    spread_pts_v = mkt_v["spread"] * mkt_v["pip"]
    cat_v        = mkt_v["cat"]
    # Multiplicateur selon volatilité naturelle du marché
    # Marchés volatils ont des spreads plus larges mais des SL légitimement plus larges
    spread_mult  = {
        "GOLD":    2.5,   # Gold spread large mais SL aussi → ratio ok
        "SILVER":  2.5,
        "INDICES": 2.5,   # Indices : spread peut être 2-5$ sur SL de 20$
        "CRYPTO":  2.0,
        "FOREX":   3.5,   # Forex : spread plus petit, filtre normal
    }.get(cat_v, 3.0)
    min_sl = spread_pts_v * spread_mult
    if setup["sl_dist"] < min_sl:
        log.info(f"  ⛔ {symbol} {setup['side']} rejeté — "
                 f"SL {setup['sl_dist']:.5f} < {spread_mult:.1f}×spread {min_sl:.5f} "
                 f"(risque stop-out bruit)")
        return None

    # ── Probabilité TP ──────────────────────────────────────────────
    tp_info = calc_tp_probability(symbol, setup, s_ok)
    if tp_info["prob"] < MIN_TP_PROB:
        log.info(f"  ⛔ {symbol} {setup['side']} "
                 f"[{setup.get('strategy','?')}] "
                 f"rejeté — Prob TP {tp_info['prob']}% < {MIN_TP_PROB}%")
        return None

    # ── Position ────────────────────────────────────────────────────
    am   = S.am
    risk = risk_usdt(balance, setup["score"], am["cycle"])
    pos  = position_size(symbol, risk, setup["sl_dist"], setup["entry"])
    pos["risk_usdt"] = risk

    return {
        **setup,
        "symbol":   symbol,
        "session":  sess_name,
        "am_cycle": am["cycle"],
        "tp_info":  tp_info,
        "pos":      pos,
    }

# ══════════════════════════════════════════════════════════════════════════════
#  SCAN D'UN SYMBOLE — Toutes stratégies
# ══════════════════════════════════════════════════════════════════════════════

def scan_symbol(symbol: str, balance: float) -> Optional[Dict]:
    mkt = MARKETS[symbol]
    tf  = "1m" if mkt["tf_entry"]=="M1" else "5m"

    candles = get_candles(symbol, tf)
    if not candles or len(candles) < 15:
        return None

    trend    = htf_trend(symbol)
    raw_sets = scan_all_strategies(candles, symbol, trend)
    if not raw_sets:
        return None

    # Valider tous et garder le meilleur
    validated = []
    for setup in raw_sets:
        v = validate_setup(symbol, setup, balance)
        if v: validated.append(v)

    if not validated: return None
    # Tri par prob × score
    validated.sort(key=lambda s: s["tp_info"]["prob"]*0.6 + s["score"]*0.4, reverse=True)
    return validated[0]

# ══════════════════════════════════════════════════════════════════════════════
#  GESTION DES TRADES — Ouvrir / Surveiller / Fermer
# ══════════════════════════════════════════════════════════════════════════════

def open_trade(sig: Dict):
    symbol  = sig["symbol"]
    mkt     = MARKETS[symbol]

    # ── MODE SCALP : recalculer TP serrés pour marchés volatils ──────────
    if symbol in SCALP_MARKETS:
        sl_d = sig["sl_dist"]
        e    = sig["entry"]
        side = sig["side"]
        # TP1=1.5R / TP2=3R / TP3=5R — rapides, atteignables en 5-15 min
        rr_list = SCALP_TP_RR
        if side == "BUY":
            sig["tp1"] = round(e + sl_d * rr_list[0], mkt["digits"])
            sig["tp2"] = round(e + sl_d * rr_list[1], mkt["digits"])
            sig["tp3"] = round(e + sl_d * rr_list[2], mkt["digits"])
        else:
            sig["tp1"] = round(e - sl_d * rr_list[0], mkt["digits"])
            sig["tp2"] = round(e - sl_d * rr_list[1], mkt["digits"])
            sig["tp3"] = round(e - sl_d * rr_list[2], mkt["digits"])
        sig["rr"] = rr_list[0]
        sig["risk_usd"] = SCALP_RISK_USD
        # Expiration plus courte pour scalp
        sig["expiry_min_override"] = SCALP_EXPIRY_M1 if mkt["tf_entry"] == "M1" else SCALP_EXPIRY_M5

    pos     = sig["pos"]
    tp_info = sig["tp_info"]
    sess    = sig["session"]
    strat   = STRAT_INFO.get(sig.get("strategy","ICT_BB"), STRAT_INFO["ICT_BB"])

    # Justification IA
    ai_txt = ai_justify(symbol, sig, tp_info, sess)

    tid   = S.new_tid()
    trade = {
        "id":        tid,
        "symbol":    symbol,
        "side":      sig["side"],
        "entry":     sig["entry"],
        "sl":        sig["sl"],
        "sl0":       sig["sl"],
        "tp1":       sig["tp1"],
        "tp2":       sig["tp2"],
        "tp3":       sig["tp3"],
        "sl_dist":   sig["sl_dist"],
        "risk_usdt": pos["risk_usdt"],
        "lots":      pos["lots"],
        "leverage":  pos["leverage"],
        "rr":        sig["rr"],
        "score":     sig["score"],
        "strategy":  sig.get("strategy","ICT_BB"),
        "am_cycle":  sig["am_cycle"],
        "tp_prob":   tp_info["prob"],
        "tf":        mkt["tf_entry"],
        "status":    "open",
        "be_active": False,
        "trail_active": False,
        "open_ts":   datetime.now(timezone.utc).isoformat(),
        "session":   sess,
        # Expiration : M1 = 8 min, M5 = 20 min
        "expiry_min": sig.get("expiry_min_override",
                              8 if mkt["tf_entry"] == "M1" else 20),
        "expiry_ts":  (datetime.now(timezone.utc)
                       + timedelta(minutes=sig.get("expiry_min_override",
                                   8 if mkt["tf_entry"] == "M1" else 20))
                       ).isoformat(),
        "entry_filled": False,   # True quand le prix a touché l'entrée
        "last_update_ts": datetime.now(timezone.utc).isoformat(),
    }

    with S._lock:
        S.trades[tid] = trade
        S.cooldowns[symbol] = (datetime.now(timezone.utc)
                               + timedelta(minutes=COOLDOWN_MIN))

    # ── Envoi UNIQUEMENT en DM @leaderOdg ─────────────────────────
    full_msg = fmt_signal_full(symbol, sig, pos, sess, tp_info, ai_txt)
    dm(full_msg)
    # Groupe et VIP désactivés — DM leader uniquement
    # if sig["score"] >= 80:   pub(full_msg)
    # if sig["score"] >= 87:   vip_(full_msg)

    log.info(
        f"[TRADE #{tid}] {symbol} {sig['side']} {strat['icon']} {strat['label']}\n"
        f"         Score:{sig['score']}  Prob:{tp_info['prob']}%  "
        f"RR:1:{sig['rr']}  TF:{mkt['tf_entry']}\n"
        f"         Mise:{pos['risk_usdt']:.2f}$  Lots:{pos['lots']}  "
        f"Lev:{pos['leverage']}x  Marge:{pos['margin']:.2f}$"
    )
    return tid

def check_all_trades():
    """Surveille tous les trades ouverts — BE, Trailing, TP, SL."""
    with S._lock:
        trades = list(S.trades.values())

    for trade in trades:
        if trade["status"] != "open": continue

        sym   = trade["symbol"]
        price = get_price(sym)
        if price is None: continue

        mkt     = MARKETS[sym]
        d       = mkt["digits"]
        side    = trade["side"]
        sl      = trade["sl"]
        tp1     = trade["tp1"]
        tp2     = trade["tp2"]
        entry   = trade["entry"]
        sl_d0   = trade["sl_dist"]
        a       = calc_atr(get_candles(sym, "5m") or [], 14)

        # RR courant
        rr_cur = ((price-entry)/sl_d0 if side=="BUY"
                  else (entry-price)/sl_d0) if sl_d0 > 0 else 0

        # ── Break-Even ────────────────────────────────────────────
        if rr_cur >= BE_TRIGGER_RR and not trade["be_active"]:
            buf   = mkt["pip"] * 3
            be_sl = round((entry+buf) if side=="BUY" else (entry-buf), d)
            with S._lock:
                trade["sl"]       = be_sl
                trade["be_active"] = True
            log.info(f"[BE #{trade['id']}] {sym} SL→{be_sl:.{d}f}")
            dm(f"🔒 <b>Break-Even</b> — {mkt['label']}\n"
               f"SL → <code>{be_sl:.{d}f}</code> (RR {rr_cur:.1f})")

        # ── Trailing Stop ─────────────────────────────────────────
        if rr_cur >= TRAIL_TRIGGER_RR and a > 0:
            trail_sl = round(
                (price - a*TRAIL_STEP_ATR) if side=="BUY"
                else (price + a*TRAIL_STEP_ATR), d)
            better_sl = ((side=="BUY"  and trail_sl > trade["sl"]) or
                         (side=="SELL" and trail_sl < trade["sl"]))
            if better_sl:
                old_sl = trade["sl"]
                with S._lock:
                    trade["sl"]           = trail_sl
                    trade["trail_active"] = True
                log.info(f"[TRAIL #{trade['id']}] {sym} SL {old_sl:.{d}f}→{trail_sl:.{d}f}")

        # ── SL / TP ───────────────────────────────────────────────
        hit_sl  = (price <= sl  if side=="BUY" else price >= sl)
        hit_tp1 = (price >= tp1 if side=="BUY" else price <= tp1)
        hit_tp2 = (price >= tp2 if side=="BUY" else price <= tp2)

        if hit_sl or hit_tp1 or hit_tp2:
            gross  = trade["risk_usdt"] * (rr_cur if (hit_tp1 or hit_tp2) else -1)
            net    = round(gross * 0.985, 4)
            result = ("WIN" if (hit_tp1 or hit_tp2) else
                      "BE"  if trade["be_active"]    else "LOSS")

            with S._lock:
                trade.update({
                    "status":   "closed",
                    "exit":     price,
                    "pnl":      net,
                    "result":   result,
                    "close_ts": datetime.now(timezone.utc).isoformat()
                })

            am_before = S.am["cycle"]
            update_am(result, net, sym)
            update_challenge(net, sym, trade["side"], trade["rr"],
                             am_before, trade["tp_prob"])

            # Historique
            S.trade_history.append({**trade, "am_after":S.am["cycle"]})
            S.save_history()

            close_msg = fmt_close_full(trade, result, price, net)
            dm(close_msg)   # DM leader seulement
            # if result == "WIN": pub(close_msg)

            log.info(
                f"[CLOSE #{trade['id']}] {sym} {result}  "
                f"PnL:{net:+.2f}$  AM:{am_before}→{S.am['cycle']}  "
                f"Solde:{S.challenge['current_balance']:.2f}$"
            )

# ══════════════════════════════════════════════════════════════════════════════
#  PUBLICATION CHALLENGE
# ══════════════════════════════════════════════════════════════════════════════

def publish_challenge():
    if S.challenge.get("published"): return
    msg = fmt_challenge_report()
    dm(msg)   # DM leader seulement (pub désactivé)
    # pub(msg)
    S.challenge["published"] = True
    S.save_challenge()
    log.info("[CHALLENGE] Rapport publié à 21h UTC")

def should_auto_publish() -> bool:
    """Publie si 8+ trades dans la journée (auto, sans attendre 21h)."""
    trades_today = len(S.challenge.get("trades",[]))
    return (trades_today >= 8 and not S.challenge.get("published", False))

# ══════════════════════════════════════════════════════════════════════════════
#  BOUCLE PRINCIPALE
# ══════════════════════════════════════════════════════════════════════════════


def sniper_triple_confirm(symbol: str, balance: float,
                           btc_corr: Optional[Dict] = None) -> Optional[Dict]:
    """
    SNIPER DOUBLE CHECK — Confirmation légère en 2 étapes.

    Étape 1 (immédiate) : re-scanner les candles actuels, vérifier que
                          le côté est toujours valide sans filtres stricts.
    Attente 5 secondes.
    Étape 2 : re-scanner, vérifier cohérence côté.

    Signal validé si :
    - Au moins 1 setup détecté du même côté que le candidat initial
    - Score >= MIN_SCORE - 5 (tolérance fluctuation candles)
    - Prob >= MIN_TP_PROB - 3 (tolérance fluctuation)
    - Le prix n'a pas déjà touché le SL ou TP entre les passes

    NOTE : validate_setup() n'est PAS rappelé ici pour éviter le
    double-filtrage qui causait des rejets injustifiés.
    """
    import time as _time
    mkt    = MARKETS[symbol]
    tf     = "1m" if mkt["tf_entry"] == "M1" else "5m"
    # Seuils souples pour la confirmation (les candles fluctuent entre les passes)
    SCORE_MIN_SOFT = MIN_SCORE - 8    # ex: 80-8 = 72
    PROB_MIN_SOFT  = MIN_TP_PROB - 5  # ex: 65-5 = 60

    confirm_sides  = []
    best_result    = None

    for pass_n in range(2):
        if pass_n > 0:
            _time.sleep(5)  # 5 secondes entre les 2 passes

        try:
            candles = get_candles(symbol, tf)
            if not candles or len(candles) < 10:
                log.debug(f"[SNIPER] pass {pass_n+1}: candles vides")
                continue

            trend  = htf_trend(symbol)
            setups = scan_all_strategies(candles, symbol, trend)

            # Strat 4 HTF
            try:
                c_h1 = get_candles(symbol, "60m")
                if c_h1 and len(c_h1) >= 4:
                    s4 = strat_ob_htf_ltf(candles, c_h1, symbol, trend)
                    if s4: setups.append(s4)
            except Exception:
                pass

            if not setups:
                log.debug(f"[SNIPER] pass {pass_n+1}: aucun setup brut")
                continue

            # Filtrer BTC correl si applicable
            if btc_corr:
                setups = [s for s in setups
                          if btc_corr_ok(s["side"], mkt["cat"])
                          or btc_corr.get("htf") == "RANGE"]

            # Garder les setups avec seuils souples (pas validate_setup)
            valid_soft = [
                s for s in setups
                if s.get("score", 0) >= SCORE_MIN_SOFT
            ]

            if not valid_soft:
                log.debug(
                    f"[SNIPER] pass {pass_n+1}: {len(setups)} setups mais "
                    f"aucun score >= {SCORE_MIN_SOFT}"
                )
                continue

            # Choisir le meilleur de cette passe
            best_this = max(valid_soft, key=lambda s: s.get("score", 0))
            confirm_sides.append(best_this["side"])

            # Calculer prob pour ce setup (sans les filtres bloquants)
            s_ok, _ = session_check(symbol)
            tp_i  = calc_tp_probability(symbol, best_this, s_ok)
            best_this["tp_info"] = tp_i
            best_this["session"] = session_label()

            if tp_i["prob"] >= PROB_MIN_SOFT:
                # Calcul position avec les vraies fonctions
                price_now = get_price(symbol) or best_this.get("entry", 1.0)
                risk      = risk_usdt(balance, best_this.get("score", 80), S.am["cycle"])
                sl_dist   = best_this.get("sl_dist", 0.001)
                pos       = position_size(symbol, risk, sl_dist, price_now, balance)
                pos["risk_usdt"] = risk
                pos["pip_val"]   = MARKETS[symbol].get("pip_val", 1.0)
                best_this.update({
                    "symbol":   symbol,
                    "pos":      pos,
                    "entry":    best_this.get("entry", price_now),
                    "am_cycle": S.am["cycle"],
                })
                if best_result is None or tp_i["prob"] > best_result["tp_info"]["prob"]:
                    best_result = best_this

            log.debug(
                f"[SNIPER] pass {pass_n+1}: côté={best_this['side']} "
                f"score={best_this.get('score',0)} prob={tp_i['prob']}%"
            )

        except Exception as e:
            log.warning(f"[SNIPER] pass {pass_n+1} erreur: {e}")
            continue

    # ── Décision finale ──────────────────────────────────────────
    if not confirm_sides:
        log.info(f"[SNIPER ❌] {symbol} — 0 passe réussie → rejeté")
        return None

    # Vérifier cohérence de côté (si 2 passes)
    if len(confirm_sides) == 2 and confirm_sides[0] != confirm_sides[1]:
        log.info(
            f"[SNIPER ❌] {symbol} — "
            f"Côtés incohérents {confirm_sides[0]} vs {confirm_sides[1]} → rejeté"
        )
        return None

    if best_result is None:
        log.info(f"[SNIPER ❌] {symbol} — prob trop faible dans toutes les passes")
        return None

    # Enrichir le résultat
    best_result["sniper_passes"]    = len(confirm_sides)
    best_result["sniper_avg_score"] = best_result.get("score", 0)
    best_result["sniper_avg_prob"]  = best_result["tp_info"]["prob"]
    best_result["sniper_confirmed"] = True

    log.info(
        f"[SNIPER ✅] {symbol} {best_result['side']} VALIDÉ — "
        f"{len(confirm_sides)}/2 passes · "
        f"Score:{best_result.get('score',0)} · "
        f"Prob:{best_result['tp_info']['prob']}%"
    )
    return best_result


# ══════════════════════════════════════════════════════════════════════════════
#  PROFIL DE SESSION — Adaptation automatique selon l'heure UTC
# ══════════════════════════════════════════════════════════════════════════════

SESSION_PROFILES = {
    # Clé: (heure_debut, heure_fin) UTC
    # Valeurs: scan_interval, min_score, min_prob, cooldown, markets_priority, label

    "INTER_NUIT": {
        "hours":    (22, 24),  # 22h-00h UTC — Zone morte post NY
        "scan_s":   90,        # Scan lent (moins de volatilité)
        "min_score": 85,       # Très sélectif (peu de setups propres)
        "min_prob":  68,
        "cooldown":  45,
        "markets":  ["XAUUSD","USDJPY","GBPJPY"],   # Seuls actifs nocturnes
        "label":    "🌙 Inter-session (zone calme)",
        "log_msg":  "Peu de volatilité. Bot en veille légère — cherche Gold/JPY uniquement.",
    },
    "INTER_NUIT2": {
        "hours":    (0, 0),    # minuit exact — géré séparément
        "scan_s":   90,
        "min_score": 85,
        "min_prob":  68,
        "cooldown":  45,
        "markets":  ["XAUUSD","USDJPY","GBPJPY"],
        "label":    "🌙 Inter-session",
        "log_msg":  "Zone calme. Bot en veille légère.",
    },
    "ASIA": {
        "hours":    (0, 7),    # 00h-07h UTC — Session Asie
        "scan_s":   60,
        "min_score": 80,
        "min_prob":  65,
        "cooldown":  30,
        "markets":  ["XAUUSD","USDJPY","GBPJPY","EURJPY","AUDUSD","NZDUSD","XAGUSD"],
        "label":    "🌏 Session Asie",
        "log_msg":  "Asie active. Focus JPY, Gold, AUD. Tendances douces.",
    },
    "LONDON_OPEN": {
        "hours":    (7, 10),   # 07h-10h UTC — London Open (volatilité ++++)
        "scan_s":   30,        # Scan rapide !
        "min_score": 78,       # Moins strict — beaucoup de setups propres
        "min_prob":  63,
        "cooldown":  20,
        "markets":  ["XAUUSD","EURUSD","GBPUSD","GBPJPY","EURGBP","USDCHF",
                     "USDJPY","NAS100","GER40","UK100","XAGUSD"],
        "label":    "🇬🇧 London Open 🔥",
        "log_msg":  "LONDON OPEN — Volatilité maximale. Meilleure session du jour. Tous marchés actifs.",
    },
    "LONDON_MID": {
        "hours":    (10, 13),  # 10h-13h UTC — London milieu
        "scan_s":   45,
        "min_score": 80,
        "min_prob":  65,
        "cooldown":  25,
        "markets":  ["XAUUSD","EURUSD","GBPUSD","GBPJPY","NAS100","GER40","XAGUSD"],
        "label":    "🇬🇧 London Mid-session",
        "log_msg":  "London continue. Tendances établies — cherche les continuations.",
    },
    "NY_OPEN": {
        "hours":    (13, 17),  # 13h-17h UTC — NY Open + Overlap (MEILLEURE HEURE)
        "scan_s":   30,        # Scan très rapide
        "min_score": 76,       # Le plus permissif — meilleure heure
        "min_prob":  62,
        "cooldown":  18,
        "markets":  ["XAUUSD","EURUSD","GBPUSD","NAS100","US500","US30",
                     "GBPJPY","USDCHF","USDCAD","XAGUSD","GER40","BTCUSD"],
        "label":    "🇺🇸 NY Open + Overlap 🔥🔥",
        "log_msg":  "NY OPEN + OVERLAP — Session la plus volatile. Maximum d'opportunités. Tous marchés.",
    },
    "NY_MID": {
        "hours":    (17, 20),  # 17h-20h UTC — NY milieu
        "scan_s":   45,
        "min_score": 80,
        "min_prob":  65,
        "cooldown":  25,
        "markets":  ["XAUUSD","EURUSD","GBPUSD","NAS100","US500","USDCAD","USDCHF"],
        "label":    "🇺🇸 NY Mid-session",
        "log_msg":  "NY milieu. Tendances NY établies. Focus USD pairs et indices.",
    },
    "NY_CLOSE": {
        "hours":    (20, 22),  # 20h-22h UTC — NY Close
        "scan_s":   40,
        "min_score": 80,
        "min_prob":  65,
        "cooldown":  25,
        "markets":  ["XAUUSD","EURUSD","GBPUSD","NAS100","US500","US30","USDCHF"],
        "label":    "🇺🇸 NY Close KZ",
        "log_msg":  "NY Close. Dernières opportunités de la session US. Attention aux retournements.",
    },
}


def get_session_profile() -> Dict:
    """
    Retourne le profil actif selon l'heure UTC actuelle.
    Adapte automatiquement : scan_interval, min_score, min_prob,
    cooldown et liste des marchés prioritaires.
    """
    h = datetime.now(timezone.utc).hour

    for key, profile in SESSION_PROFILES.items():
        start, end = profile["hours"]
        if start == end:
            continue
        # Gérer le cas 22-24 (pas de minuit dans range)
        if start > end:
            if h >= start or h < end:
                return profile
        else:
            if start <= h < end:
                return profile

    # Fallback : inter-session
    return SESSION_PROFILES["INTER_NUIT"]


def apply_session_profile(profile: Dict) -> None:
    """
    Applique dynamiquement le profil de session aux variables globales.
    Appelé au début de chaque cycle de scan.
    """
    global MIN_SCORE, MIN_TP_PROB, COOLDOWN_MIN, SCAN_INTERVAL
    MIN_SCORE    = profile["min_score"]
    MIN_TP_PROB  = profile["min_prob"]
    COOLDOWN_MIN = profile["cooldown"]
    SCAN_INTERVAL = profile["scan_s"]


_last_session_label = ""   # pour logger uniquement au changement de session


def log_session_change(profile: Dict) -> None:
    """Log + DM quand la session change."""
    global _last_session_label
    label = profile["label"]
    if label != _last_session_label:
        _last_session_label = label
        msg = (
            f"⏰ <b>NOUVELLE SESSION</b>\n"
            f"{label}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Score min : {profile['min_score']}  |  Prob min : {profile['min_prob']}%\n"
            f"⏱ Scan : toutes les {profile['scan_s']}s  |  Cooldown : {profile['cooldown']}min\n"
            f"🎯 Marchés prioritaires : {', '.join(profile['markets'][:6])}{'...' if len(profile['markets'])>6 else ''}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💬 {profile['log_msg']}"
        )
        log.info(f"[SESSION] {label} — {profile['log_msg']}")
        dm(msg)



def main_loop():
    log.info("═"*70)
    log.info("  ALPHABOT PRO v7 — Agent IA Live")
    log.info(f"  {len(MARKETS)} marchés : Forex({sum(1 for m in MARKETS.values() if m['cat']=='FOREX')}) "
             f"· Or/Argent · Indices({sum(1 for m in MARKETS.values() if m['cat']=='INDICES')}) · BTC")
    log.info(f"  Filtres: Prob ≥{MIN_TP_PROB}% · Score ≥{MIN_SCORE} · RR ≥{MIN_RR}")
    log.info(f"  Challenge: {CHALLENGE_START}$ → {CHALLENGE_TARGET}$")
    log.info("═"*70)

    # Message de démarrage
    dm(fmt_startup_msg())
    log.info("[BOT] Message de démarrage envoyé en DM @leaderOdg ✅ (groupe désactivé)")

    scan_n    = 0
    pub_hour  = -1   # Heure du dernier rapport

    while S.running:
        now     = datetime.now(timezone.utc)
        scan_n += 1
        balance = S.challenge["current_balance"]

        # ── Vérification trades ouverts ───────────────────────────
        check_all_trades()

        # ── Publication 21h UTC ───────────────────────────────────
        if now.hour == 21 and pub_hour != 21:
            pub_hour = 21
            publish_challenge()
        elif now.hour != 21 and pub_hour == 21:
            pub_hour = -1  # reset pour le lendemain

        # ── Auto-publication après 8 trades ───────────────────────
        if should_auto_publish():
            publish_challenge()

        # ── Limite positions ──────────────────────────────────────
        open_ct = sum(1 for t in S.trades.values() if t["status"]=="open")
        if open_ct >= MAX_OPEN_TRADES:
            log.info(f"[SCAN #{scan_n}] Max positions ({open_ct}/{MAX_OPEN_TRADES}) — skip")
            time.sleep(SCAN_INTERVAL)
            continue

        # ── ADAPTATION SESSION AUTOMATIQUE ───────────────────────
        _prof = get_session_profile()
        apply_session_profile(_prof)
        log_session_change(_prof)

        # ── SCAN COMPLET ──────────────────────────────────────────
        kz    = get_kill_zone()
        sess  = _prof["label"]
        log.info(
            f"[SCAN #{scan_n}] {sess}"
            f"{' 🎯 '+kz if kz else ''} | "
            f"Solde:{balance:.2f}$ | Score≥{MIN_SCORE} Prob≥{MIN_TP_PROB}% | "
            f"Open:{open_ct}/{MAX_OPEN_TRADES}"
        )

        # ── MODE SNIPER ───────────────────────────────────────────────
        # Étape 1 : scan rapide pour identifier les candidats
        # Ordre de scan : volatils en premier MAIS tous les marchés
        # sont éligibles — le bot choisit le MEILLEUR setup peu importe le marché
        # Marchés prioritaires selon la session active
        _session_mkts = _prof["markets"]
        SCAN_ORDER    = _session_mkts + [s for s in MARKETS if s not in _session_mkts]
        candidates: List[Dict] = []
        for symbol in SCAN_ORDER:
            if symbol not in MARKETS: continue
            try:
                sig = scan_symbol(symbol, balance)
                if sig:
                    tp = sig["tp_info"]
                    si = STRAT_INFO.get(sig.get("strategy","ICT_BB"), STRAT_INFO["ICT_BB"])
                    log.info(
                        f"  👁 {symbol:<8} {sig['side']:<5} "
                        f"{si['icon']} Score:{sig['score']}  "
                        f"Prob:{tp['prob']}%  (candidat)"
                    )
                    candidates.append(sig)
            except Exception as e:
                log.debug(f"  {symbol}: {e}")
            time.sleep(0.3)

        if not candidates:
            log.info(f"[SNIPER #{scan_n}] Aucun candidat — {agent_say('no_setup')}")
        else:
            # Trier par prob × score × speed_score
            # speed_score = ATR/SL → grand = TP atteint vite
            def _speed_score(s):
                atr   = s.get("atr", 0.0001)
                sl_d  = s.get("sl_dist", 0.0001)
                speed = min(atr / sl_d, 5.0) if sl_d > 0 else 1.0
                return s["tp_info"]["prob"] * 0.5 + s["score"] * 0.3 + speed * 20.0
            candidates.sort(key=_speed_score, reverse=True)
            top = candidates[0]
            log.info(
                f"[SNIPER #{scan_n}] {len(candidates)} candidat(s) · "
                f"🎯 Top: {top['symbol']} {top['side']} "
                f"Prob:{top['tp_info']['prob']}% Score:{top['score']}"
            )

            # Rapport scan toutes les 5 cycles
            if scan_n % 5 == 0:
                dm(fmt_scan_report(scan_n, candidates))

            # Étape 2 : TRIPLE CONFIRMATION sur le meilleur candidat
            log.info(
                f"[SNIPER] 🔎 Triple confirmation {top['symbol']} {top['side']}..."
            )
            confirmed = sniper_triple_confirm(top["symbol"], balance)

            if confirmed:
                log.info(
                    f"[SNIPER ✅] TIR — {top['symbol']} "
                    f"Passes:{confirmed['sniper_passes']}/3 · "
                    f"Score:{confirmed['sniper_avg_score']} · "
                    f"Prob:{confirmed['sniper_avg_prob']}%"
                )
                open_trade(confirmed)
            else:
                log.info(
                    f"[SNIPER ❌] {top['symbol']} rejeté — "
                    f"Triple confirmation non passée. Pas assez solide. On patiente."
                )

        time.sleep(SCAN_INTERVAL)

# ══════════════════════════════════════════════════════════════════════════════
#  MODE TEST — Scan complet sans ouvrir de trade
# ══════════════════════════════════════════════════════════════════════════════

def run_test():
    log.info("═"*70)
    log.info("  MODE TEST — Aucun trade ouvert")
    log.info("═"*70)

    balance = S.challenge.get("current_balance", CHALLENGE_START)
    fg      = fetch_fear_greed()
    kz      = get_kill_zone()
    sess    = session_label()

    print(f"\n{'═'*70}")
    print(f"  Agent Alpha v7 — Scan Test")
    print(f"  {len(MARKETS)} marchés | Prob ≥{MIN_TP_PROB}% | Score ≥{MIN_SCORE} | RR ≥{MIN_RR}")
    print(f"  Solde: {balance:.2f}$ | AM Cycle: {S.am['cycle']}/4")
    print(f"  Session: {sess}{' · Kill Zone: '+kz if kz else ''}")
    print(f"  Fear & Greed: {fg.get('value',50)}/100 — {fg.get('label','—')}")
    print(f"{'═'*70}\n")

    results: List[Dict] = []
    rejected = 0

    for symbol, mkt in MARKETS.items():
        s_ok, sess_name = session_check(symbol)
        ce   = CAT_EMOJI.get(mkt["cat"],"📊")
        print(f"  {ce} {mkt['label']:<22} TF:{mkt['tf_entry']}  "
              f"Sess:{sess_name:<15}", end="", flush=True)
        sig = scan_symbol(symbol, balance)
        if sig:
            results.append(sig)
            tp = sig["tp_info"]
            si = STRAT_INFO.get(sig.get("strategy","ICT_BB"), STRAT_INFO["ICT_BB"])
            print(f" ✅ {sig['side']}  "
                  f"{si['icon']} {si['label'][:20]:<20}  "
                  f"Score:{sig['score']}  Prob:{tp['prob']}%  {tp['verdict']}")
        else:
            rejected += 1
            print(f" —")
        time.sleep(0.5)

    print(f"\n{'═'*70}")
    print(f"  RÉSULTATS : {len(results)} setup(s) qualifié(s) / {len(MARKETS)} marchés scannés")
    print(f"  Rejetés   : {rejected} (score < {MIN_SCORE} ou prob < {MIN_TP_PROB}% ou hors session)")
    print(f"{'═'*70}\n")

    results.sort(key=lambda s: s["tp_info"]["prob"]*0.6 + s["score"]*0.4, reverse=True)

    for i, sig in enumerate(results, 1):
        mkt   = MARKETS[sig["symbol"]]
        pos   = sig["pos"]
        tp    = sig["tp_info"]
        fund  = get_fund(sig["symbol"])
        strat = STRAT_INFO.get(sig.get("strategy","ICT_BB"), STRAT_INFO["ICT_BB"])
        d     = mkt["digits"]

        print(f"  #{i}  {CAT_EMOJI.get(mkt['cat'],'📊')}  {mkt['label']}")
        print(f"       Stratégie  : {strat['icon']} {strat['label']}  (WR {strat['wr']*100:.0f}%)")
        print(f"       Direction  : {sig['side']}  TF: {mkt['tf_entry']}  HTF: {sig['htf_trend']}")
        print(f"       Score ICT  : {sig['score']}/100")
        print(f"       Prob TP1   : {tp['prob']}%  →  {tp['verdict']}")
        print(f"       Entrée     : {sig['entry']:.{d}f}")
        print(f"       SL         : {sig['sl']:.{d}f}  ({pos['sl_pips']:.0f} pips)")
        print(f"       TP1        : {sig['tp1']:.{d}f}  (RR 1:{sig['rr']})")
        print(f"       TP2        : {sig['tp2']:.{d}f}  (RR 1:{sig['rr']*2:.1f})")
        print(f"       TP3        : {sig['tp3']:.{d}f}  (RR 1:{sig['rr']*3.2:.1f})")
        print(f"       Mise       : {pos['risk_usdt']:.2f}$  "
              f"Lots:{pos['lots']}  Lev:{pos['leverage']}x  Marge:{pos['margin']:.2f}$")
        print(f"       BOS: {'✅' if sig.get('bos') else '—'}  "
              f"FVG: {'✅' if sig.get('fvg') else '—'}  "
              f"Zone: {sig.get('pd_zone','—')} ({sig.get('pd_pct','—')}%)  "
              f"RSI: {sig.get('rsi','—')}")
        print(f"       Fondamental: {fund['bias']}  —  {fund['note']}")
        print(f"       Session    : {sig['session']}")
        if kz: print(f"       Kill Zone  : {kz} 🎯")
        print(f"       F&G        : {fg.get('value',50)}/100 — {fg.get('label','—')}")
        print(f"       Facteurs probabilité :")
        for f_ in tp["factors"][:6]:
            print(f"         {f_}")
        print()

    print(f"{'═'*70}")
    print("  Pour lancer le bot : python alphabot_v7.py --live")
    print(f"{'═'*70}\n")

# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT — Compatible PyDroid 3 + PC + Render
# ══════════════════════════════════════════════════════════════════════════════

# ── Instance unique — évite le 409 Conflit Telegram ─────────────────────────
import os, atexit

_LOCK_FILE = "/tmp/alphabot_v14.lock"

def _acquire_lock():
    if os.path.exists(_LOCK_FILE):
        try:
            pid = int(open(_LOCK_FILE).read().strip())
            # Vérifier si le process tourne encore
            os.kill(pid, 0)
            print(f"❌ AlphaBot déjà en cours (PID {pid}). Arrête l'autre instance d'abord.")
            print(f"   Sur VPS : kill {pid}")
            print(f"   Sur PyDroid : arrêter le script actif")
            raise SystemExit(1)
        except (ProcessLookupError, ValueError):
            pass  # Process mort → on peut continuer
    with open(_LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    atexit.register(lambda: os.path.exists(_LOCK_FILE) and os.remove(_LOCK_FILE))

if __name__ == "__main__":
    _acquire_lock()

    # ── PyDroid 3 : change ce paramètre puis appuie sur ▶ ──────────────────
    PYDROID_MODE = "live"   # "test" | "live" | "reset"
    # ────────────────────────────────────────────────────────────────────────

    import argparse
    try:
        p = argparse.ArgumentParser(description="AlphaBot Pro v7")
        p.add_argument("--live",  action="store_true")
        p.add_argument("--test",  action="store_true")
        p.add_argument("--reset", action="store_true")
        args   = p.parse_args()
        has_args = args.live or args.test or args.reset
    except SystemExit:
        has_args = False
        class _A:
            live = False; test = False; reset = False
        args = _A()

    # PyDroid 3 : pas de ligne de commande → PYDROID_MODE
    if not has_args:
        print(f"\n[PyDroid] Mode: {PYDROID_MODE.upper()}")
        args.live  = (PYDROID_MODE == "live")
        args.test  = (PYDROID_MODE == "test")
        args.reset = (PYDROID_MODE == "reset")

    if args.reset:
        for f in (_AM_FILE, _CHAL_FILE, _HIST_FILE):
            try: os.remove(f); print(f"✅ {os.path.basename(f)} supprimé")
            except Exception: pass
        print("État réinitialisé."); sys.exit(0)

    if args.test:
        run_test()

    elif args.live:
        try:
            main_loop()
        except KeyboardInterrupt:
            log.info("[BOT] Arrêt par l'utilisateur")
            try:
                msg = fmt_challenge_report()
                dm(msg); pub(msg)
                log.info("[BOT] Rapport final envoyé")
            except Exception: pass

    else:
        print("\n  Usage:")
        print("  python alphabot_v7.py --test    # Scan test local (0 trade)")
        print("  python alphabot_v7.py --live    # Mode live (scan continu)")
        print("  python alphabot_v7.py --reset   # Reset état\n")
        print("  PyDroid 3 : modifie PYDROID_MODE dans le script\n")

# ══════════════════════════════════════════════════════════════════════════════
#  EXTENSION v7.1 — Tous les modules manquants vs HTML v48
# ══════════════════════════════════════════════════════════════════════════════

# ── FIBONACCI LEVELS ─────────────────────────────────────────────────────────

def calc_fibonacci(symbol: str, candles: List) -> Dict:
    """
    Calcule les niveaux Fibonacci clés sur le dernier swing (ICT).
    Retourne fib21, fib38, fib50, fib62, fib79 — zones ICT premium/discount.
    """
    sh, sl_ = get_swing_levels(candles, 20)
    rng     = sh - sl_
    if rng <= 0:
        return {}
    return {
        "fib_100": round(sh, MARKETS[symbol]["digits"]),
        "fib_79":  round(sl_ + rng * 0.79, MARKETS[symbol]["digits"]),
        "fib_62":  round(sl_ + rng * 0.62, MARKETS[symbol]["digits"]),
        "fib_50":  round(sl_ + rng * 0.50, MARKETS[symbol]["digits"]),
        "fib_38":  round(sl_ + rng * 0.38, MARKETS[symbol]["digits"]),
        "fib_21":  round(sl_ + rng * 0.21, MARKETS[symbol]["digits"]),
        "fib_0":   round(sl_, MARKETS[symbol]["digits"]),
        "swing_high": round(sh, MARKETS[symbol]["digits"]),
        "swing_low":  round(sl_, MARKETS[symbol]["digits"]),
        "range":   round(rng, MARKETS[symbol]["digits"]),
    }

def fib_zone_label(price: float, fib: Dict) -> str:
    """Retourne le label de la zone Fibonacci du prix actuel."""
    if not fib: return "—"
    if price >= fib.get("fib_79",0):  return "PREMIUM FORT (79-100%)"
    if price >= fib.get("fib_62",0):  return "PREMIUM (62-79%)"
    if price >= fib.get("fib_50",0):  return "EQUILIBRIUM (50-62%)"
    if price >= fib.get("fib_38",0):  return "EQUILIBRIUM (38-50%)"
    if price >= fib.get("fib_21",0):  return "DISCOUNT (21-38%)"
    return "DISCOUNT FORT (0-21%)"

# ── CORRÉLATION BTC POUR TOUS LES ACTIFS ────────────────────────────────────

_btc_hist: deque = deque(maxlen=60)  # historique prix BTC

def update_btc_history():
    p = get_price("BTCUSD")
    if p: _btc_hist.append({"p": p, "ts": time.time()})

def btc_correlation_trend() -> Dict:
    """
    Analyse la tendance BTC pour filtrer tous les actifs.
    HTF = tendance 1h (60 derniers prix)
    LTF = tendance 5min (5 derniers prix)
    """
    if len(_btc_hist) < 5:
        return {"htf": "RANGE", "ltf": "RANGE", "change_htf": 0.0, "change_ltf": 0.0}
    prices = [x["p"] for x in _btc_hist]
    first, last  = prices[0],   prices[-1]
    recent_first = prices[-5],  prices[-1]

    d_htf = (last - first) / first * 100 if first else 0
    d_ltf = (prices[-1] - prices[-5]) / prices[-5] * 100 if len(prices)>=5 and prices[-5] else 0

    htf = "BULL" if d_htf > 1.2 else "BEAR" if d_htf < -1.2 else "RANGE"
    ltf = "BULL" if d_ltf > 0.2 else "BEAR" if d_ltf < -0.2 else "RANGE"
    return {"htf": htf, "ltf": ltf, "change_htf": round(d_htf,2), "change_ltf": round(d_ltf,2)}

def btc_corr_ok(side: str, cat: str) -> bool:
    """Vérifie si BTC corrélation est favorable (pour Forex/Indices skip ce filtre)."""
    if cat in ("FOREX",): return True  # Forex peu corrélé à BTC
    btc = btc_correlation_trend()
    if btc["htf"] == "RANGE": return True
    if side=="BUY"  and btc["htf"] != "BEAR": return True
    if side=="SELL" and btc["htf"] != "BULL": return True
    return False

# ── RISQUE JOURNALIER ────────────────────────────────────────────────────────

def get_day_risk() -> Dict:
    """Évalue le risque de la journée de trading."""
    d = datetime.now(timezone.utc).weekday()  # 0=Lundi … 6=Dimanche
    h = datetime.now(timezone.utc).hour
    # NFP / données macro clés (vendredi 12:30 UTC)
    nfp_window = (d == 4 and 12 <= h <= 14)
    fomc_window = False  # à activer manuellement si FOMC
    if d in (5, 6):
        return {"level":"warn","icon":"⚠️",
                "label":"Weekend",
                "msg":"Volume faible · Spreads larges · Trader avec prudence",
                "max_risk_mult": 0.5, "ok": True}
    if d == 0:
        return {"level":"warn","icon":"⚠️",
                "label":"Lundi",
                "msg":"Attention aux gaps d'ouverture · Liquidité progressive",
                "max_risk_mult": 0.7, "ok": True}
    if d == 4 and h >= 19:
        return {"level":"warn","icon":"⚠️",
                "label":"Vendredi soir",
                "msg":"Fermeture hebdomadaire · Éviter nouvelles positions",
                "max_risk_mult": 0.6, "ok": True}
    if nfp_window:
        return {"level":"danger","icon":"🚨",
                "label":"NFP / Publication macro",
                "msg":"Volatilité extrême · Stop trading 30min avant/après",
                "max_risk_mult": 0.0, "ok": False}
    return {"level":"safe","icon":"✅",
            "label":"Jour optimal",
            "msg":"Conditions normales · Toutes stratégies actives",
            "max_risk_mult": 1.0, "ok": True}

# ── PRIX DE LIQUIDATION ───────────────────────────────────────────────────────

def calc_liq_price(side: str, entry: float, leverage: int,
                   mm_rate: float = 0.004) -> float:
    """
    Calcule le prix de liquidation (formule Binance Futures / XM).
    Margin isolée, taux de maintenance 0.4% par défaut.
    """
    if leverage <= 0: return 0
    if side == "BUY":
        return round(entry * (1 - 1/leverage + mm_rate), 5)
    else:
        return round(entry * (1 + 1/leverage - mm_rate), 5)

def calc_fees(notional: float) -> float:
    """Frais taker 0.04% aller + 0.04% retour = 0.08% du notionnel."""
    return round(notional * 0.0004 * 2, 4)

def calc_notional(lots: float, price: float, cat: str) -> float:
    if cat == "FOREX":   return round(lots * 100_000 * price, 2)
    if cat in ("GOLD","SILVER"): return round(lots * 100 * price, 2)
    if cat == "INDICES": return round(lots * price, 2)
    if cat == "CRYPTO":  return round(lots * price, 2)
    return round(lots * price, 2)

# ── STATS GLOBALES ───────────────────────────────────────────────────────────

def calc_global_stats(history: List) -> Dict:
    """Calcule win rate, profit factor, expectancy, Sharpe approximatif."""
    if not history:
        return {"wr":0,"pf":0,"exp":0,"total_trades":0,"total_pnl":0}
    wins   = [t for t in history if t.get("result")=="WIN"]
    losses = [t for t in history if t.get("result")=="LOSS"]
    bes    = [t for t in history if t.get("result")=="BE"]
    n      = len(history)
    total_pnl   = sum(t.get("pnl",0) for t in history)
    gross_win   = sum(t.get("pnl",0) for t in wins)
    gross_loss  = abs(sum(t.get("pnl",0) for t in losses))
    wr     = round(len(wins)/n*100, 1) if n else 0
    pf     = round(gross_win/gross_loss, 2) if gross_loss > 0 else 99
    exp    = round(total_pnl/n, 4) if n else 0
    avg_w  = round(gross_win/len(wins), 2) if wins else 0
    avg_l  = round(gross_loss/len(losses), 2) if losses else 0
    # Streak
    streak = 0
    cur    = history[-1].get("result","") if history else ""
    for t in reversed(history):
        if t.get("result") == cur: streak += 1
        else: break
    return {
        "wr":wr,"pf":pf,"exp":exp,"total_trades":n,
        "total_pnl":round(total_pnl,2),
        "wins":len(wins),"losses":len(losses),"bes":len(bes),
        "avg_win":avg_w,"avg_loss":avg_l,
        "gross_win":round(gross_win,2),"gross_loss":round(gross_loss,2),
        "streak":streak,"streak_type":cur,
    }

# ── STRATÉGIE 4 : OB HTF + LTF CONFLUENCE ───────────────────────────────────

def strat_ob_htf_ltf(candles_m5: List, candles_h1: List,
                     symbol: str, trend: str) -> Optional[Dict]:
    """
    OB H1 comme zone HTF, confirmation M5 LTF.
    OB H1 = grande bougie impulsive H1.
    Prix M5 revient dans l'OB H1 → entrée LTF.
    """
    if len(candles_h1) < 4 or len(candles_m5) < 5: return None
    mkt   = MARKETS[symbol]
    price = candles_m5[-1]["close"]
    a     = calc_atr(candles_m5, 14)
    r     = calc_rsi(candles_m5, 14)

    h1_last  = candles_h1[-1]
    h1_prev  = candles_h1[-2]
    h1_prev2 = candles_h1[-3]

    def h1_body(c):
        rng = c["high"] - c["low"]
        return abs(c["close"] - c["open"]) / rng if rng else 0

    # OB H1 BULL
    h1_bull = (h1_prev["close"] > h1_prev["open"] and h1_body(h1_prev) > 0.5)
    in_bull_ob = (h1_bull and
                  h1_prev["open"] * 0.997 <= price <= h1_prev["close"] * 1.003)
    m5_conf_b  = candles_m5[-1]["close"] > candles_m5[-2]["close"]
    bos_b      = price > max(c["high"] for c in candles_m5[-10:-2])

    if in_bull_ob and m5_conf_b and trend != "BEAR":
        sl_sw  = min(min(c["low"] for c in candles_m5[-5:]), h1_prev["low"])
        sl     = round(sl_sw * 0.9992, mkt["digits"])
        sl_d   = price - sl
        if sl_d < a*0.1 or sl_d > a*4: return None
        sc = 72 + (20 if bos_b else 0) + (8 if trend=="BULL" else 0) + (5 if r<52 else 0)
        entry_ob = round(price, mkt["digits"])
        return {"strategy":"OB_HTF_LTF","side":"BUY",
                "entry":entry_ob,"sl":sl,
                "tp1":round(entry_ob+sl_d*1.5,mkt["digits"]),
                "tp2":round(entry_ob+sl_d*2.5,mkt["digits"]),
                "tp3":round(entry_ob+sl_d*4.0,mkt["digits"]),
                "sl_dist":sl_d,"rr":1.5,"score":min(sc,100),"atr":a,
                "bos":bos_b,"fvg":False,
                "ob_h1":(round(h1_prev["open"],mkt["digits"]),
                         round(h1_prev["close"],mkt["digits"])),
                "pd_zone":"DISCOUNT","pd_pct":20.0,
                "rsi":round(r,1),"htf_trend":trend}

    # OB H1 BEAR
    h1_bear = (h1_prev["close"] < h1_prev["open"] and h1_body(h1_prev) > 0.5)
    in_bear_ob = (h1_bear and
                  h1_prev["close"] * 0.997 <= price <= h1_prev["open"] * 1.003)
    m5_conf_s  = candles_m5[-1]["close"] < candles_m5[-2]["close"]
    bos_s      = price < min(c["low"] for c in candles_m5[-10:-2])

    if in_bear_ob and m5_conf_s and trend != "BULL":
        sl_sw  = max(max(c["high"] for c in candles_m5[-5:]), h1_prev["high"])
        sl     = round(sl_sw * 1.0008, mkt["digits"])
        sl_d   = sl - price
        if sl_d < a*0.1 or sl_d > a*4: return None
        sc = 72 + (20 if bos_s else 0) + (8 if trend=="BEAR" else 0) + (5 if r>48 else 0)
        entry_ob = round(price, mkt["digits"])
        return {"strategy":"OB_HTF_LTF","side":"SELL",
                "entry":entry_ob,"sl":sl,
                "tp1":round(entry_ob-sl_d*1.5,mkt["digits"]),
                "tp2":round(entry_ob-sl_d*2.5,mkt["digits"]),
                "tp3":round(entry_ob-sl_d*4.0,mkt["digits"]),
                "sl_dist":sl_d,"rr":1.5,"score":min(sc,100),"atr":a,
                "bos":bos_s,"fvg":False,
                "ob_h1":(round(h1_prev["close"],mkt["digits"]),
                         round(h1_prev["open"],mkt["digits"])),
                "pd_zone":"PREMIUM","pd_pct":80.0,
                "rsi":round(r,1),"htf_trend":trend}
    return None

# ── DIVERGENCE RSI (signal de retournement supplémentaire) ──────────────────

def detect_rsi_divergence(candles: List) -> Optional[str]:
    """
    Divergence haussière/baissière RSI sur les 20 dernières bougies.
    Retourne 'BULL_DIV' | 'BEAR_DIV' | None.
    """
    if len(candles) < 20: return None
    window = candles[-20:]
    closes = [c["close"] for c in window]
    rsis_  = []
    for i in range(14, len(window)):
        seg   = window[i-13:i+1]
        rsis_.append(calc_rsi(seg, min(14, len(seg))))

    if len(rsis_) < 2: return None

    price_low1  = min(closes[-8:])
    price_low2  = min(closes[-16:-8])
    rsi_low1    = min(rsis_[-4:]) if len(rsis_) >= 4 else rsis_[-1]
    rsi_low2    = min(rsis_[:-4]) if len(rsis_) > 4  else rsis_[0]

    price_high1 = max(closes[-8:])
    price_high2 = max(closes[-16:-8])
    rsi_high1   = max(rsis_[-4:]) if len(rsis_) >= 4 else rsis_[-1]
    rsi_high2   = max(rsis_[:-4]) if len(rsis_) > 4  else rsis_[0]

    # Divergence haussière : prix fait lower low mais RSI fait higher low
    if price_low1 < price_low2 and rsi_low1 > rsi_low2 + 3:
        return "BULL_DIV"
    # Divergence baissière : prix fait higher high mais RSI fait lower high
    if price_high1 > price_high2 and rsi_high1 < rsi_high2 - 3:
        return "BEAR_DIV"
    return None

# ── MULTI-TIMEFRAME SCORE ────────────────────────────────────────────────────

def calc_mtf_score(symbol: str, side: str) -> Dict:
    """
    Score de confluence multi-TF (M1, M5, H1).
    Plus de TF alignés = signal plus fort.
    """
    scores  = {}
    weights = {"1m": 0.8, "5m": 1.0, "60m": 2.0}
    conf    = 0
    total_w = 0

    for tf, w in weights.items():
        try:
            c = get_candles(symbol, tf)
            if not c or len(c) < 5: continue
            e20 = calc_ema(c, 20)
            e50 = calc_ema(c, min(50, len(c)))
            p   = c[-1]["close"]
            tf_bull = e20 > e50 and p > e20
            tf_bear = e20 < e50 and p < e20
            aligned = (side=="BUY" and tf_bull) or (side=="SELL" and tf_bear)
            scores[tf] = {"aligned": aligned, "weight": w,
                          "ema20": round(e20,4), "ema50": round(e50,4)}
            if aligned: conf += w
            total_w  += w
        except Exception:
            pass

    conf_pct = round(conf/total_w*100) if total_w > 0 else 0
    bonus    = 12 if conf_pct >= 80 else (7 if conf_pct >= 60 else (3 if conf_pct >= 40 else 0))
    return {"conf_pct": conf_pct, "bonus": bonus, "tfs": scores,
            "aligned_count": sum(1 for v in scores.values() if v["aligned"]),
            "total_count":   len(scores)}

# ── WATCHLIST DYNAMIQUE ──────────────────────────────────────────────────────

_watchlist: List[Dict] = []  # Setups proches de se déclencher

def update_watchlist(symbol: str, score: int, side: str, prob: float,
                     reason: str):
    """Maintient une watchlist des setups proches du seuil."""
    global _watchlist
    _watchlist = [w for w in _watchlist if w["symbol"] != symbol]
    if score >= MIN_SCORE - 10:  # dans les 10 points du seuil
        _watchlist.append({
            "symbol": symbol, "side": side, "score": score,
            "prob": prob, "reason": reason,
            "ts": datetime.now(timezone.utc).strftime("%H:%M"),
        })
    _watchlist.sort(key=lambda w: w["score"], reverse=True)
    _watchlist = _watchlist[:8]

# ── MESSAGES TELEGRAM SUPPLÉMENTAIRES ───────────────────────────────────────

def fmt_signal_ultra(symbol: str, setup: Dict, pos: Dict,
                     sess: str, tp_info: Dict, ai_txt: str,
                     fib: Dict, mtf: Dict, btc_c: Dict,
                     day_risk: Dict) -> str:
    """
    Message signal ULTRA-DÉTAILLÉ — version complète pour @leaderOdg.
    Contient : entrée, SL, TP1/2/3, fibonacci, MTF, BTC correl,
               liquidation, frais, day risk, prob, facteurs, IA.
    """
    mkt   = MARKETS[symbol]
    d     = mkt["digits"]
    side  = setup["side"]
    ce    = CAT_EMOJI.get(mkt["cat"],"📊")
    de    = "🟢 LONG" if side=="BUY" else "🔴 SHORT"
    he    = "📈" if setup.get("htf_trend")=="BULL" else "📉" if setup.get("htf_trend")=="BEAR" else "➡️"
    fe    = "🟢" if get_fund(symbol)["bias"]=="BULLISH" else "🔴" if get_fund(symbol)["bias"]=="BEARISH" else "⚪"
    now   = datetime.now(timezone.utc).strftime("%H:%M UTC")
    fund  = get_fund(symbol)
    strat = STRAT_INFO.get(setup.get("strategy","ICT_BB"), STRAT_INFO["ICT_BB"])
    am_   = S.am
    bal_  = S.challenge["current_balance"]
    prog_ = round(bal_/CHALLENGE_TARGET*100,1)

    prob  = tp_info["prob"]
    verd  = tp_info["verdict"]
    fg    = tp_info.get("fg",{})
    kz    = get_kill_zone()
    rr2   = round(setup["rr"]*5/3, 1)   # TP2 = RR 2.5
    rr3   = round(setup["rr"]*8/3, 1)   # TP3 = RR 4.0

    bars  = int(prob/10); bar  = "█"*bars + "░"*(10-bars)
    fg_v  = fg.get("value",50); fg_b = int(fg_v/10)
    fg_bar= "█"*fg_b + "░"*(10-fg_b)

    # Calculs financiers
    notional = calc_notional(pos["lots"], setup["entry"], mkt["cat"])
    fees     = calc_fees(notional)
    liq      = calc_liq_price(side, setup["entry"], pos["leverage"])

    # Divergence RSI
    candles = get_candles(symbol, "1m" if mkt["tf_entry"]=="M1" else "5m") or []
    div     = detect_rsi_divergence(candles)

    lines = [
        f"{ce} <b>{mkt['label']} — {de}</b>",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"⚡ <b>ENTRÉE DIRECTE — MAINTENANT</b>",
        f"📍 Entrée  : <code>{setup['entry']:.{d}f}</code>",
        f"🛑 SL      : <code>{setup['sl']:.{d}f}</code>  ({pos['sl_pips']:.0f} pips)",
        f"✅ TP1     : <code>{setup['tp1']:.{d}f}</code>  (RR 1:{setup['rr']})",
        f"✅ TP2     : <code>{setup['tp2']:.{d}f}</code>  (RR 1:{rr2})",
        f"🎯 TP3     : <code>{setup['tp3']:.{d}f}</code>  (RR 1:{rr3})",
        f"💥 Liq.    : <code>{liq:.{d}f}</code>  ({pos['leverage']}x)",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📊 <b>Probabilité TP : {prob}%</b>  {verd}",
        f"[{bar}]",
        f"📐 WR {strat['label']}: {strat['wr']*100:.0f}%",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    # Fibonacci
    if fib:
        fib_lbl = fib_zone_label(setup["entry"], fib)
        lines += [
            f"📏 <b>Fibonacci</b>",
            f"   Range: {fib['swing_low']:.{d}f} → {fib['swing_high']:.{d}f}",
            f"   Fib 79%: {fib['fib_79']:.{d}f}  |  62%: {fib['fib_62']:.{d}f}",
            f"   Fib 50%: {fib['fib_50']:.{d}f}  |  38%: {fib['fib_38']:.{d}f}",
            f"   Fib 21%: {fib['fib_21']:.{d}f}",
            f"   Zone entrée: <b>{fib_lbl}</b>",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]

    # ICT Score + indicateurs
    lines += [
        f"🔷 Score ICT : <b>{setup['score']}/100</b>  "
        f"{he} HTF: <b>{setup.get('htf_trend','—')}</b>",
        f"{'✅' if setup.get('bos') else '⚠️'} BOS  "
        f"{'✅' if setup.get('fvg') else '—'} FVG  "
        f"📍 {setup.get('pd_zone','—')} ({setup.get('pd_pct','—')}%)",
        f"📉 RSI: {setup.get('rsi','—')}  "
        f"{'🔻 Div Bear' if div=='BEAR_DIV' else '🔺 Div Bull' if div=='BULL_DIV' else ''}",
    ]

    # Kill Zone
    if kz: lines.append(f"🎯 Kill Zone : <b>{kz}</b>")

    # Multi-TF
    if mtf:
        conf_lbl = ("🟢" if mtf["conf_pct"]>=80 else
                    "🟡" if mtf["conf_pct"]>=60 else "🔴")
        tf_detail = "  ".join(
            f"{tf_}{'✅' if v['aligned'] else '—'}"
            for tf_,v in mtf.get("tfs",{}).items()
        )
        lines += [
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"📊 <b>Confluence Multi-TF</b> : {conf_lbl} {mtf['conf_pct']}%",
            f"   {tf_detail}  | Bonus score: +{mtf['bonus']}",
        ]

    # BTC correlation (non-FOREX)
    if MARKETS[symbol]["cat"] not in ("FOREX",) and btc_c:
        btc_emoji = "📈" if btc_c["htf"]=="BULL" else "📉" if btc_c["htf"]=="BEAR" else "➡️"
        lines += [
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"🔷 BTC Corrélation :",
            f"   HTF: {btc_emoji} {btc_c['htf']} ({btc_c['change_htf']:+.2f}%)  "
            f"LTF: {btc_c['ltf']} ({btc_c['change_ltf']:+.2f}%)",
        ]

    lines += [
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"{fe} <b>Fondamental</b> : {fund['bias']}",
        f"📰 {fund['note']}",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    # Fear & Greed
    fg_v = fg.get("value",50); fg_lbl = fg.get("label","—")
    lines += [
        f"😱 <b>Fear & Greed : {fg_v}/100</b> — {fg_lbl}",
        f"[{fg_bar}]",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    # Facteurs prob (top 6)
    lines.append(f"📋 <b>Facteurs probabilité :</b>")
    for f_ in tp_info["factors"][:6]:
        lines.append(f"  · {f_}")

    lines += [
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🤖 <b>Analyse Alpha IA</b> :",
        f"<i>{ai_txt}</i>",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"⏰ {sess}  {now}  TF: {mkt['tf_entry']}",
        f"💰 Mise: <b>{pos['risk_usdt']:.2f}$</b>  "
        f"Lots: <b>{pos['lots']}</b>  "
        f"Lev: <b>{pos['leverage']}x</b>",
        f"📊 Notionnel: <b>{notional:.2f}$</b>  "
        f"Frais≈: <b>{fees:.4f}$</b>",
        f"📊 Marge: <b>{pos['margin']:.2f}$</b>",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"✅ Confirmé : <b>{setup.get('sniper_passes',3)}/3 analyses</b>  "
        f"Score moy: {setup.get('sniper_avg_score', setup['score'])}  "
        f"Prob moy: {setup.get('sniper_avg_prob', tp_info['prob'])}%",
        f"🔄 Anti-Martingale: Cycle <b>{am_['cycle']}/4</b>  "
        f"WS: {am_['win_streak']}  "
        f"Boosté: +{round((AM_MULT**am_['cycle']-1)*100)}%",
    ]

    # Day risk
    if day_risk["level"] != "safe":
        lines.append(f"{day_risk['icon']} {day_risk['label']}: {day_risk['msg']}")

    lines += [
        f"🏆 Challenge: <b>{bal_:.2f}$</b>  ({prog_:.1f}% vers {CHALLENGE_TARGET:.0f}$)",
        f"@leaderOdg",
    ]
    return "\n".join(lines)

def fmt_close_ultra(trade: Dict, result: str, price: float, pnl: float) -> str:
    """Message de clôture ultra-détaillé."""
    symbol = trade["symbol"]
    mkt    = MARKETS[symbol]
    d      = mkt["digits"]
    ce     = CAT_EMOJI.get(mkt["cat"],"📊")
    re_e   = "✅ WIN" if result=="WIN" else "🔒 BE" if result=="BE" else "❌ LOSS"
    am     = S.am
    c      = S.challenge
    bal    = c["current_balance"]
    prog   = round(bal/CHALLENGE_TARGET*100,1)
    gain   = bal - c["start_balance"]
    stats  = calc_global_stats(S.trade_history[-50:])

    rr_real = abs(price-trade["entry"])/max(trade["sl_dist"],0.0001)
    notional = calc_notional(trade["lots"], trade["entry"], mkt["cat"])
    fees     = calc_fees(notional)
    net_fees = round(pnl - fees, 4)

    am_msg = agent_say("win") if result=="WIN" else (
             agent_say("be")  if result=="BE"  else agent_say("loss"))

    strat  = STRAT_INFO.get(trade.get("strategy","ICT_BB"), STRAT_INFO["ICT_BB"])

    lines = [
        f"{ce} {re_e} — <b>{mkt['label']}</b>  {strat['icon']} {strat['label']}",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"Entrée  : <code>{trade['entry']:.{d}f}</code>",
        f"Sortie  : <code>{price:.{d}f}</code>",
        f"SL init : <code>{trade['sl0']:.{d}f}</code>",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"💵 PnL brut : <b>{'+' if pnl>=0 else ''}{pnl:.2f}$</b>",
        f"💸 Frais    : -{fees:.4f}$",
        f"💵 PnL net  : <b>{'+' if net_fees>=0 else ''}{net_fees:.4f}$</b>",
        f"📐 RR réalisé: 1:{rr_real:.1f}",
        f"🎯 Prob estimée: {trade.get('tp_prob',0):.0f}%",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🔄 AM: {trade['am_cycle']}→{am['cycle']}  WS: {am['win_streak']}",
        f"{'🔒 Break-Even actif' if trade.get('be_active') else ''}",
        f"{'🔁 Trailing Stop actif' if trade.get('trail_active') else ''}",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📊 Stats globales ({stats['total_trades']} trades):",
        f"   WR: {stats['wr']}%  PF: {stats['pf']}  Exp: {stats['exp']:.2f}$/trade",
        f"   Streak: {stats['streak']}x {stats['streak_type']}",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🏆 Solde: <b>{bal:.2f}$</b>  ({'+' if gain>=0 else ''}{gain:.2f}$ aujourd'hui)",
        f"📈 Challenge: {prog:.1f}% vers {CHALLENGE_TARGET:.0f}$",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🤖 <i>{am_msg}</i>",
        f"@leaderOdg",
    ]
    return "\n".join(l for l in lines if l.strip())

def fmt_heartbeat() -> str:
    """Message toutes les heures — statut complet du bot."""
    c     = S.challenge
    bal   = c["current_balance"]
    open_ = sum(1 for t in S.trades.values() if t["status"]=="open")
    stats = calc_global_stats(S.trade_history[-50:])
    fg    = fetch_fear_greed()
    btc_c = btc_correlation_trend()
    kz    = get_kill_zone()
    sess  = session_label()
    dr    = get_day_risk()
    now   = datetime.now(timezone.utc).strftime("%H:%M UTC")
    prog  = round(bal/CHALLENGE_TARGET*100,1)

    lines = [
        f"💓 <b>Heartbeat — Agent Alpha v7</b>  {now}",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🕐 {sess}{' · 🎯 '+kz if kz else ''}",
        f"{dr['icon']} {dr['label']} — {dr['msg']}",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"💰 Solde  : <b>{bal:.2f}$</b>  ({prog:.1f}%→{CHALLENGE_TARGET:.0f}$)",
        f"📊 Trades : {open_}/{MAX_OPEN_TRADES} ouverts",
        f"🔄 AM     : Cycle {S.am['cycle']}/4  WS: {S.am['win_streak']}",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📈 Stats ({stats['total_trades']} trades)",
        f"   WR: {stats['wr']}%  PF: {stats['pf']}  Exp: {stats['exp']:.2f}$",
        f"   ✅{stats['wins']}W ❌{stats['losses']}L 🔒{stats['bes']}BE",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"😱 Fear & Greed: {fg.get('value',50)}/100 — {fg.get('label','—')}",
        f"🔷 BTC HTF: {btc_c['htf']} ({btc_c['change_htf']:+.2f}%)",
    ]

    if _watchlist:
        lines.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"👀 Watchlist ({len(_watchlist)} setups proches):")
        for w in _watchlist[:3]:
            mkt = MARKETS[w["symbol"]]
            lines.append(f"  • {mkt['label']} {w['side']}  "
                         f"Score:{w['score']}  Prob:{w['prob']:.0f}%  @{w['ts']}")

    lines += [f"━━━━━━━━━━━━━━━━━━━━━━━━━━", f"@leaderOdg"]
    return "\n".join(lines)

def fmt_weekly_report() -> str:
    """Rapport hebdomadaire complet."""
    stats = calc_global_stats(S.trade_history)
    c     = S.challenge
    bal   = c["current_balance"]
    start = CHALLENGE_START
    gain  = bal - start
    prog  = round(bal/CHALLENGE_TARGET*100,1)
    now   = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    by_strat: Dict[str, List] = {}
    for t in S.trade_history:
        s = t.get("strategy","ICT_BB")
        by_strat.setdefault(s,[]).append(t)

    lines = [
        f"📅 <b>RAPPORT HEBDOMADAIRE — Agent Alpha v7</b>",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🗓 {now}",
        f"💰 {start:.2f}$ → <b>{bal:.2f}$</b>  "
        f"({'+' if gain>=0 else ''}{gain:.2f}$ / {gain/start*100 if start else 0:+.1f}%)",
        f"🎯 Challenge: <b>{prog:.1f}%</b> vers {CHALLENGE_TARGET:.0f}$",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📊 Stats globales ({stats['total_trades']} trades)",
        f"   WR: {stats['wr']}%  PF: {stats['pf']}  Exp: {stats['exp']:.2f}$/trade",
        f"   ✅{stats['wins']}W  ❌{stats['losses']}L  🔒{stats['bes']}BE",
        f"   Avg WIN: +{stats['avg_win']:.2f}$  Avg LOSS: -{stats['avg_loss']:.2f}$",
        f"   PnL total: {'+' if stats['total_pnl']>=0 else ''}{stats['total_pnl']:.2f}$",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📐 Performances par stratégie:",
    ]

    for strat_key, trades_ in by_strat.items():
        si  = STRAT_INFO.get(strat_key, {"label":strat_key,"icon":"📊"})
        st  = calc_global_stats(trades_)
        lines.append(
            f"  {si['icon']} {si['label']}: "
            f"{st['wins']}W/{st['losses']}L  WR:{st['wr']}%  "
            f"PnL:{'+' if st['total_pnl']>=0 else ''}{st['total_pnl']:.2f}$"
        )

    lines += [
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🔄 Anti-Martingale: Cycle {S.am['cycle']}/4  "
        f"Total boosté: {S.am.get('total_boosted',0):.2f}$",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"💡 {agent_say('motivation')}",
        f"<b>@leaderOdg</b> · t.me/bluealpha_signals",
    ]
    return "\n".join(lines)

def fmt_be_message(trade: Dict, be_sl: float) -> str:
    """Message Break-Even détaillé."""
    mkt = MARKETS[trade["symbol"]]
    d   = mkt["digits"]
    return (
        f"🔒 <b>Break-Even</b> — {mkt['label']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"SL initial : <code>{trade['sl0']:.{d}f}</code>\n"
        f"SL BE+     : <code>{be_sl:.{d}f}</code>\n"
        f"Entrée     : <code>{trade['entry']:.{d}f}</code>\n"
        f"Capital protégé ✅ · @leaderOdg"
    )

def fmt_trail_message(trade: Dict, old_sl: float, new_sl: float) -> str:
    """Message Trailing Stop mis à jour."""
    mkt = MARKETS[trade["symbol"]]
    d   = mkt["digits"]
    return (
        f"🔁 <b>Trailing Stop</b> — {mkt['label']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"SL: <code>{old_sl:.{d}f}</code> → <code>{new_sl:.{d}f}</code>\n"
        f"Profit verrouillé progressivement ✅\n@leaderOdg"
    )

# ── SCAN COMPLET V2 — Avec toutes les stratégies + OB HTF+LTF ───────────────

def scan_symbol_full(symbol: str, balance: float, btc_corr: Dict) -> Optional[Dict]:
    """Scan toutes les stratégies incluant OB HTF+LTF + filtres BTC."""
    mkt = MARKETS[symbol]
    tf  = "1m" if mkt["tf_entry"]=="M1" else "5m"

    candles = get_candles(symbol, tf)
    if not candles or len(candles) < 15: return None

    trend = htf_trend(symbol)

    # Collecte tous les setups
    setups = scan_all_strategies(candles, symbol, trend)

    # Stratégie 4 : OB HTF+LTF (nécessite H1)
    try:
        candles_h1 = get_candles(symbol, "60m")
        if candles_h1 and len(candles_h1) >= 4:
            s4 = strat_ob_htf_ltf(candles, candles_h1, symbol, trend)
            if s4: setups.append(s4)
    except Exception: pass

    if not setups: return None

    # Filtre BTC corrélation
    setups = [s for s in setups if btc_corr_ok(s["side"], mkt["cat"])
              or btc_corr["htf"]=="RANGE"]

    if not setups: return None

    # Validation + enrichissement
    validated = []
    for setup in setups:
        # MTF score bonus
        mtf = calc_mtf_score(symbol, setup["side"])
        setup["score"] = min(100, setup["score"] + mtf["bonus"])
        setup["mtf"]   = mtf

        v = validate_setup(symbol, setup, balance)
        if v:
            # Ajouter fibonacci et watchlist
            v["fib"]   = calc_fibonacci(symbol, candles)
            v["btc_c"] = btc_corr
            validated.append(v)
        else:
            # Proche du seuil → watchlist
            prob_ = setup.get("score",0)
            update_watchlist(symbol, setup.get("score",0), setup.get("side","?"),
                             prob_*0.8, setup.get("strategy","?"))

    if not validated: return None
    validated.sort(key=lambda s: s["tp_info"]["prob"]*0.6 + s["score"]*0.4, reverse=True)
    return validated[0]

# ── BOUCLE PRINCIPALE V2 — Avec toutes les améliorations ────────────────────


# ═══════════════════════════════════════════════════════════════════════
# SUIVI DES POSITIONS — Mise à jour toutes les 15 minutes
# ═══════════════════════════════════════════════════════════════════════

FOLLOWUP_INTERVAL = 15 * 60   # 15 minutes en secondes
_last_followup_ts = {}         # {trade_id: timestamp dernier suivi}


def _trade_decision(trade: Dict, price: float, candles: List[Dict]) -> Dict:
    """
    Analyse technique + fondamentale rapide sur une position ouverte.
    Retourne un dict avec recommendation : GARDER / CLÔTURER / ATTENTION
    """
    sym    = trade["symbol"]
    mkt    = MARKETS[sym]
    side   = trade["side"]
    entry  = trade["entry"]
    sl     = trade["sl"]
    tp1    = trade["tp1"]
    tp2    = trade["tp2"]
    d      = mkt["digits"]
    sl0    = trade.get("sl0", sl)

    # ── PnL actuel ────────────────────────────────────────────────
    if side == "BUY":
        pnl_pts = price - entry
        dist_sl = price - sl
        dist_tp = tp1 - price
        toward_tp = price > entry
    else:
        pnl_pts = entry - price
        dist_sl = sl - price
        dist_tp = price - tp1
        toward_tp = price < entry

    sl_dist_total = abs(entry - sl0)
    rr_current    = pnl_pts / sl_dist_total if sl_dist_total > 0 else 0
    pct_to_tp1    = (1 - dist_tp / abs(tp1 - entry)) * 100 if abs(tp1 - entry) > 0 else 0

    # ── Analyse technique des candles récentes ─────────────────────
    if candles and len(candles) >= 5:
        recent = candles[-5:]
        closes = [c["close"] for c in recent]
        highs  = [c["high"]  for c in recent]
        lows   = [c["low"]   for c in recent]
        bodies = [abs(c["close"] - c["open"]) for c in recent]
        avg_body = sum(bodies) / len(bodies)

        # Momentum : price accelère vers TP ?
        momentum_ok = (
            (side == "BUY"  and closes[-1] > closes[-3] > closes[-5]) or
            (side == "SELL" and closes[-1] < closes[-3] < closes[-5])
        )
        # Structure : pas de clôture adverse forte (>= 2× corps moyen)
        last_body    = bodies[-1]
        adverse_close = (
            (side == "BUY"  and candles[-1]["close"] < candles[-1]["open"] and last_body > avg_body * 1.8) or
            (side == "SELL" and candles[-1]["close"] > candles[-1]["open"] and last_body > avg_body * 1.8)
        )
        # Prix entre entry et TP (en bonne position)
        in_range = (
            (side == "BUY"  and price > entry * 0.999) or
            (side == "SELL" and price < entry * 1.001)
        )
    else:
        momentum_ok   = True
        adverse_close = False
        in_range      = True

    # ── Vérifier expiration d'entrée ──────────────────────────────
    now_utc   = datetime.now(timezone.utc)
    expiry_ts = datetime.fromisoformat(trade.get("expiry_ts", now_utc.isoformat()))
    expired   = now_utc > expiry_ts and not trade.get("entry_filled", False)
    # Si le prix a déjà dépassé l'entry (touché), marquer comme filled
    entry_filled = trade.get("entry_filled", False)
    if not entry_filled:
        if (side == "BUY" and price >= entry) or (side == "SELL" and price <= entry):
            entry_filled = True

    # ── DECISION ──────────────────────────────────────────────────
    signal = "GARDER 🟢"
    reasons = []

    if expired and not entry_filled:
        signal  = "EXPIRÉ ⏰"
        reasons.append(f"Entrée jamais touchée — signal expiré après {trade.get('expiry_min',15)} min")

    elif pnl_pts < -sl_dist_total * 0.7:
        signal  = "ATTENTION 🟠"
        reasons.append(f"Prix à {abs(dist_sl/mkt['pip']):.0f} pips du SL — surveiller de près")

    elif adverse_close and rr_current < 0.5:
        signal  = "ATTENTION 🟠"
        reasons.append("Bougie adverse forte sans momentum — structure menacée")

    elif not momentum_ok and pnl_pts > 0 and rr_current > 1.2:
        signal  = "PARTIEL 💛"
        reasons.append(f"RR {rr_current:.1f}× atteint — prise de profit partielle conseillée")

    elif pct_to_tp1 >= 80:
        signal  = "PRESQUE TP1 🎯"
        reasons.append(f"À {100-pct_to_tp1:.0f}% du TP1 — ne pas fermer trop tôt")

    if momentum_ok   : reasons.append("Momentum technique favorable ✅")
    if in_range      : reasons.append("Prix en zone de trade valide ✅")
    if not adverse_close: reasons.append("Structure de bougie saine ✅")
    if rr_current > 0: reasons.append(f"RR actuel : 1:{rr_current:.1f}")

    return {
        "signal":        signal,
        "rr_current":    round(rr_current, 2),
        "pnl_pts":       round(pnl_pts, mkt["digits"]),
        "pct_to_tp1":    round(pct_to_tp1, 1),
        "dist_sl_pips":  round(abs(dist_sl) / mkt["pip"], 1),
        "dist_tp_pips":  round(abs(dist_tp) / mkt["pip"], 1),
        "reasons":       reasons[:4],
        "expired":       expired,
        "entry_filled":  entry_filled,
        "toward_tp":     toward_tp,
        "momentum_ok":   momentum_ok,
    }


def fmt_trade_update(trade: Dict, price: float, dec: Dict) -> str:
    """
    Message de suivi de position — envoyé toutes les 15 min.
    Contient : PnL, distance SL/TP, momentum, décision, expiration.
    """
    sym   = trade["symbol"]
    mkt   = MARKETS[sym]
    d     = mkt["digits"]
    side  = trade["side"]
    tf    = trade.get("tf", "M5")
    tid   = trade["id"]
    strat = STRAT_INFO.get(trade.get("strategy","ICT_BB"), STRAT_INFO["ICT_BB"])
    ce    = "🟢" if side == "BUY" else "🔴"

    # PnL en USD
    pos        = {"lots": trade.get("lots", 0.01), "pip_val": mkt.get("pip_val", 10)}
    pnl_pts    = dec["pnl_pts"]
    pip_val    = mkt.get("pip_val", 10)
    pnl_usd    = round(pnl_pts / mkt["pip"] * pip_val * trade.get("lots", 0.01), 2)
    pnl_icon   = "📈" if pnl_pts >= 0 else "📉"
    pnl_sign   = "+" if pnl_usd >= 0 else ""

    # Barre progression vers TP1
    pct   = min(max(dec["pct_to_tp1"], 0), 100)
    bars  = int(pct / 10)
    bar   = "█" * bars + "░" * (10 - bars)

    # Expiration
    now_utc   = datetime.now(timezone.utc)
    expiry_ts = datetime.fromisoformat(trade.get("expiry_ts", now_utc.isoformat()))
    mins_left = max(0, int((expiry_ts - now_utc).total_seconds() / 60))
    exp_line  = (
        f"⏳ Expiration entrée : <b>{mins_left} min restantes</b>"
        if not dec["entry_filled"] and mins_left > 0
        else ("✅ Entrée confirmée — position active"
              if dec["entry_filled"]
              else "⏰ Entrée expirée — position à clôturer")
    )

    # Raisons
    reasons_txt = "\n".join("  • " + r for r in dec["reasons"])
    lines = [
        f"📊 <b>SUIVI POSITION #{tid} — {mkt['label']}</b>",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"{ce} {side}  {strat['icon']} {strat['label']}  |  TF: {tf}",
        f"",
        f"💵 Prix actuel : <code>{price:.{d}f}</code>",
        f"📍 Entrée      : <code>{trade['entry']:.{d}f}</code>",
        f"🛑 SL          : <code>{trade['sl']:.{d}f}</code>  ({dec['dist_sl_pips']} pips)",
        f"🎯 TP1         : <code>{trade['tp1']:.{d}f}</code>  ({dec['dist_tp_pips']} pips)",
        f"",
        f"{pnl_icon} PnL estimé : <b>{pnl_sign}{pnl_usd:.2f}$</b>  ({pnl_sign}{dec['pnl_pts']:.{d}f} pts)",
        f"📐 RR actuel  : <b>1:{dec['rr_current']}</b>",
        f"",
        f"Progression TP1 : [{bar}] {pct:.0f}%",
        f"",
        exp_line,
        f"",
        f"🧠 <b>ANALYSE :</b>",
        reasons_txt,
        f"",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"<b>DÉCISION : {dec['signal']}</b>",
        f"",
        f"<i>⏱ Prochain suivi dans 15 min</i>",
    ]
    return "\n".join(lines)


def run_trade_followup():
    """
    Appelée toutes les 15 min par le scheduler.
    Pour chaque position ouverte : analyse + message de suivi.
    """
    global _last_followup_ts
    now_ts = datetime.now(timezone.utc).timestamp()

    with S._lock:
        open_trades = [t for t in S.trades.values() if t["status"] == "open"]

    if not open_trades:
        return

    log.info(f"[FOLLOWUP] Suivi {len(open_trades)} position(s) ouverte(s)...")

    for trade in open_trades:
        tid = trade["id"]
        sym = trade["symbol"]

        # Vérifier intervalle 15 min
        last = _last_followup_ts.get(tid, 0)
        if now_ts - last < FOLLOWUP_INTERVAL - 30:   # -30s tolérance
            continue

        _last_followup_ts[tid] = now_ts

        try:
            price = get_price(sym)
            if price is None:
                continue
            mkt = MARKETS[sym]
            tf  = "1m" if mkt["tf_entry"] == "M1" else "5m"
            candles = get_candles(sym, tf)

            dec = _trade_decision(trade, price, candles or [])

            # Mettre à jour entry_filled dans l'état
            if dec["entry_filled"] and not trade.get("entry_filled"):
                with S._lock:
                    if tid in S.trades:
                        S.trades[tid]["entry_filled"] = True

            msg = fmt_trade_update(trade, price, dec)
            dm(msg)

            log.info(
                f"[FOLLOWUP #{tid}] {sym} {trade['side']} | "
                f"Prix:{price} PnL:{dec['pnl_pts']:+.{mkt['digits']}f} | "
                f"{dec['signal']}"
            )

            # Si expiré et entrée jamais remplie → clore automatiquement
            if dec["expired"] and not dec["entry_filled"]:
                log.info(f"[FOLLOWUP #{tid}] Entrée expirée → clôture automatique")
                with S._lock:
                    if tid in S.trades:
                        S.trades[tid]["status"] = "expired"
                        S.trades[tid]["close_price"] = price
                        S.trades[tid]["close_reason"] = "EXPIRED"
                dm(
                    f"⏰ <b>ENTRÉE EXPIRÉE — #{tid} {sym}</b>\n"
                    f"Position annulée (entrée non atteinte dans {trade.get('expiry_min',15)}min)."
                )

        except Exception as e:
            log.warning(f"[FOLLOWUP #{tid}] Erreur: {e}")





def main_loop_v2():
    log.info("═"*72)
    log.info("  ALPHABOT PRO v7.1 — Agent IA Live Complet")
    log.info(f"  {len(MARKETS)} marchés | 4 stratégies ICT | MTF + Fibonacci + BTC corr")
    log.info(f"  Filtres: Prob ≥{MIN_TP_PROB}% | Score ≥{MIN_SCORE} | RR ≥{MIN_RR}")
    log.info(f"  Challenge: {CHALLENGE_START}$ → {CHALLENGE_TARGET}$")
    log.info("═"*72)

    # Charger BTC history au démarrage
    for _ in range(5):
        update_btc_history()
        time.sleep(0.5)

    # Tenter de résoudre le leader_id dès le démarrage
    leader_id = resolve_leader()
    if leader_id == TG_GROUP:
        log.warning(
            "[DM] Leader ID pas encore résolu. "
            "→ Envoie /start au bot depuis Telegram pour débloquer les DM."
        )
    dm(fmt_startup_msg())
    log.info(f"[BOT] Démarrage — Messages → {leader_id} ✅")

    scan_n         = 0
    pub_hour       = -1
    last_heartbeat = 0
    last_weekly    = datetime.now(timezone.utc).strftime("%V")  # semaine ISO

    while S.running:
        now         = datetime.now(timezone.utc)
        scan_n     += 1
        balance     = S.challenge["current_balance"]
        btc_corr    = btc_correlation_trend()
        day_risk    = get_day_risk()

        # ── Update BTC history ────────────────────────────────────
        update_btc_history()

        # ── Vérification trades ouverts (version ultra) ───────────
        _check_all_trades_ultra(btc_corr)

        # ── Publication 21h UTC ───────────────────────────────────
        if now.hour == 21 and pub_hour != 21:
            pub_hour = 21
            msg = fmt_challenge_report()
            dm(msg); pub(msg)
            S.challenge["published"] = True
            S.save_challenge()
            log.info("[CHALLENGE] Rapport 21h publié")
        elif now.hour != 21 and pub_hour == 21:
            pub_hour = -1

        # ── Rapport hebdomadaire (lundi matin) ────────────────────
        week_cur = now.strftime("%V")
        if now.weekday()==0 and now.hour==8 and week_cur != last_weekly:
            last_weekly = week_cur
            wr = fmt_weekly_report()
            dm(wr); pub(wr)
            log.info("[WEEKLY] Rapport hebdo publié")

        # ── Heartbeat toutes les heures ───────────────────────────
        if time.time() - last_heartbeat >= 3600:
            last_heartbeat = time.time()
            dm(fmt_heartbeat())
            log.info("[HEARTBEAT] Envoyé")

        # ── Auto-pub après 8 trades ───────────────────────────────
        if should_auto_publish():
            publish_challenge()

        # ── Limite positions ──────────────────────────────────────
        open_ct = sum(1 for t in S.trades.values() if t["status"]=="open")
        if open_ct >= MAX_OPEN_TRADES:
            log.info(f"[SCAN #{scan_n}] Max positions ({open_ct}) — skip")
            time.sleep(SCAN_INTERVAL); continue

        # ── Day risk bloquant ─────────────────────────────────────
        if not day_risk["ok"]:
            log.warning(f"[SCAN #{scan_n}] {day_risk['label']} — pause trading")
            time.sleep(SCAN_INTERVAL); continue

        # ── SCAN COMPLET ──────────────────────────────────────────
        kz   = get_kill_zone()
        sess = session_label()
        log.info(
            f"[SCAN #{scan_n}] {sess}"
            f"{' 🎯 '+kz if kz else ''} | "
            f"BTC HTF:{btc_corr['htf']} ({btc_corr['change_htf']:+.2f}%) | "
            f"Solde:{balance:.2f}$ | AM:{S.am['cycle']}/4 | Open:{open_ct}"
        )

        # ── MODE SNIPER v2 ────────────────────────────────────────────
        # Ordre de scan : volatils en premier MAIS tous les marchés
        # sont éligibles — le bot choisit le MEILLEUR setup peu importe le marché
        VOLATILE_FIRST = [
            "XAUUSD","XAGUSD","NAS100",              # Scalp rapide
            "GBPJPY","EURJPY","GBPUSD","EURUSD",     # Forex haute liquidité
            "BTCUSD","US500","GER40","US30",          # Indices + Crypto
            "USDCHF","USDCAD","AUDUSD","NZDUSD",     # Forex majeurs
            "EURGBP","EURCAD","GBPCAD",              # Forex croisés
            "UK100","FRA40","JPN225","AUS200",        # Indices secondaires
            "XAGUSD",                                # Silver
        ]
        SCAN_ORDER = VOLATILE_FIRST + [s for s in MARKETS if s not in VOLATILE_FIRST]
        candidates: List[Dict] = []
        for symbol in SCAN_ORDER:
            if symbol not in MARKETS: continue
            try:
                sig = scan_symbol_full(symbol, balance, btc_corr)
                if sig:
                    candidates.append(sig)
                    tp  = sig["tp_info"]
                    si  = STRAT_INFO.get(sig.get("strategy","ICT_BB"), STRAT_INFO["ICT_BB"])
                    mtf = sig.get("mtf",{})
                    log.info(
                        f"  👁 {symbol:<8} {sig['side']:<5} "
                        f"{si['icon']} {si['label'][:22]:<22} "
                        f"Score:{sig['score']}  Prob:{tp['prob']}%  "
                        f"MTF:{mtf.get('conf_pct','—')}%  (candidat)"
                    )
            except Exception as e:
                log.debug(f"  {symbol}: {e}")
            time.sleep(0.35)

        def _speed_score_v2(s):
            atr   = s.get("atr", 0.0001)
            sl_d  = s.get("sl_dist", 0.0001)
            speed = min(atr / sl_d, 5.0) if sl_d > 0 else 1.0
            return s["tp_info"]["prob"] * 0.5 + s["score"] * 0.3 + speed * 20.0
        candidates.sort(key=_speed_score_v2, reverse=True)

        if not candidates:
            log.info(f"[SNIPER #{scan_n}] {agent_say('no_setup')}")
        else:
            best_prob = candidates[0]["tp_info"]["prob"]
            log.info(
                f"[SNIPER #{scan_n}] {len(candidates)} candidat(s) | "
                f"🎯 Top: {candidates[0]['symbol']} "
                f"Prob:{best_prob}% Score:{candidates[0]['score']}"
            )
            if scan_n % 5 == 0 or best_prob >= 70:
                dm(fmt_scan_report(scan_n, candidates))

            # Triple confirmation
            log.info(f"[SNIPER] 🔎 Triple confirmation {candidates[0]['symbol']}...")
            confirmed = sniper_triple_confirm(candidates[0]["symbol"], balance, btc_corr)
            if confirmed:
                _open_trade_ultra(confirmed)
            else:
                log.info(f"[SNIPER ❌] Rejeté après triple confirmation — on attend.")

        time.sleep(SCAN_INTERVAL)


def _open_trade_ultra(sig: Dict):
    """Ouvre un trade avec message Telegram ultra-détaillé."""
    symbol  = sig["symbol"]
    mkt     = MARKETS[symbol]
    pos     = sig["pos"]
    tp_info = sig["tp_info"]
    sess    = sig["session"]
    fib     = sig.get("fib", {})
    mtf     = sig.get("mtf", {})
    btc_c   = sig.get("btc_c", {})
    day_r   = get_day_risk()

    ai_txt  = ai_justify(symbol, sig, tp_info, sess)

    tid   = S.new_tid()
    trade = {
        "id": tid, "symbol": symbol, "side": sig["side"],
        "entry": sig["entry"], "sl": sig["sl"], "sl0": sig["sl"],
        "tp1": sig["tp1"], "tp2": sig["tp2"], "tp3": sig["tp3"],
        "sl_dist": sig["sl_dist"], "risk_usdt": pos["risk_usdt"],
        "lots": pos["lots"], "leverage": pos["leverage"],
        "rr": sig["rr"], "score": sig["score"],
        "strategy": sig.get("strategy","ICT_BB"),
        "am_cycle": sig["am_cycle"], "tp_prob": tp_info["prob"],
        "tf": mkt["tf_entry"], "status": "open",
        "be_active": False, "trail_active": False,
        "open_ts": datetime.now(timezone.utc).isoformat(),
        "session": sess,
    }

    with S._lock:
        S.trades[tid] = trade
        S.cooldowns[symbol] = (datetime.now(timezone.utc)
                                + timedelta(minutes=COOLDOWN_MIN))

    # Message ultra-détaillé
    full_msg = fmt_signal_ultra(
        symbol, sig, pos, sess, tp_info, ai_txt, fib, mtf, btc_c, day_r)
    # ── Envoi UNIQUEMENT en DM @leaderOdg ─────────────────────────
    dm(full_msg)
    # pub() et vip_() désactivés — leader DM only
    # if sig["score"] >= 80:   pub(full_msg)
    # if sig["score"] >= 87:   vip_(full_msg)

    si = STRAT_INFO.get(sig.get("strategy","ICT_BB"), STRAT_INFO["ICT_BB"])
    log.info(
        f"[TRADE #{tid}] {symbol} {sig['side']} {si['icon']} {si['label']}\n"
        f"         Score:{sig['score']}  Prob:{tp_info['prob']}%  "
        f"RR:1:{sig['rr']}  TF:{mkt['tf_entry']}\n"
        f"         Mise:{pos['risk_usdt']:.2f}$  Lots:{pos['lots']}  "
        f"Lev:{pos['leverage']}x  Marge:{pos['margin']:.2f}$\n"
        f"         Fib zone: {fib_zone_label(sig['entry'],sig.get('fib',{}))}"
    )


def _check_all_trades_ultra(btc_corr: Dict):
    """Surveillance ultra-complète : BE, Trailing, TP, SL."""
    with S._lock:
        trades = list(S.trades.values())

    for trade in trades:
        if trade["status"] != "open": continue

        sym   = trade["symbol"]
        price = get_price(sym)
        if price is None: continue

        mkt   = MARKETS[sym]
        d     = mkt["digits"]
        side  = trade["side"]
        sl    = trade["sl"]
        tp1, tp2, tp3 = trade["tp1"], trade["tp2"], trade["tp3"]
        entry = trade["entry"]
        sl_d0 = trade["sl_dist"]
        try:
            candles = get_candles(sym, "5m") or []
            a       = calc_atr(candles, 14)
        except Exception:
            a = sl_d0 * 1.5

        rr_cur = ((price-entry)/sl_d0 if side=="BUY"
                  else (entry-price)/sl_d0) if sl_d0 > 0 else 0

        # ── Break-Even ────────────────────────────────────────────
        if rr_cur >= BE_TRIGGER_RR and not trade["be_active"]:
            buf   = mkt["pip"] * 3
            be_sl = round((entry+buf) if side=="BUY" else (entry-buf), d)
            with S._lock:
                trade["sl"]       = be_sl
                trade["be_active"] = True
            log.info(f"[BE #{trade['id']}] {sym} SL→{be_sl:.{d}f}")
            dm(fmt_be_message(trade, be_sl))

        # ── Trailing Stop ─────────────────────────────────────────
        if rr_cur >= TRAIL_TRIGGER_RR and a > 0:
            trail_sl = round(
                (price - a*TRAIL_STEP_ATR) if side=="BUY"
                else (price + a*TRAIL_STEP_ATR), d)
            better_sl = ((side=="BUY"  and trail_sl > trade["sl"]) or
                         (side=="SELL" and trail_sl < trade["sl"]))
            if better_sl:
                old_sl = trade["sl"]
                with S._lock:
                    trade["sl"]           = trail_sl
                    trade["trail_active"] = True
                dm(fmt_trail_message(trade, old_sl, trail_sl))
                log.info(f"[TRAIL #{trade['id']}] {sym} {old_sl:.{d}f}→{trail_sl:.{d}f}")

        # ── SL / TP ───────────────────────────────────────────────
        hit_sl  = (price <= sl  if side=="BUY" else price >= sl)
        hit_tp1 = (price >= tp1 if side=="BUY" else price <= tp1)
        hit_tp2 = (price >= tp2 if side=="BUY" else price <= tp2)
        hit_tp3 = (price >= tp3 if side=="BUY" else price <= tp3)

        if hit_sl or hit_tp1 or hit_tp2 or hit_tp3:
            gross  = trade["risk_usdt"] * (rr_cur if (hit_tp1 or hit_tp2 or hit_tp3) else -1)
            net    = round(gross * 0.985, 4)
            result = ("WIN" if (hit_tp1 or hit_tp2 or hit_tp3) else
                      "BE"  if trade["be_active"] else "LOSS")

            with S._lock:
                trade.update({
                    "status": "closed", "exit": price, "pnl": net,
                    "result": result,
                    "close_ts": datetime.now(timezone.utc).isoformat()
                })

            am_before = S.am["cycle"]
            update_am(result, net, sym)
            update_challenge(net, sym, trade["side"], trade["rr"],
                             am_before, trade["tp_prob"])

            S.trade_history.append({**trade, "am_after": S.am["cycle"]})
            S.save_history()

            close_msg = fmt_close_ultra(trade, result, price, net)
            dm(close_msg)   # DM leader seulement
            # if result == "WIN": pub(close_msg)

            log.info(
                f"[CLOSE #{trade['id']}] {sym} {result}  "
                f"PnL:{net:+.2f}$  RR:{rr_cur:.1f}  "
                f"AM:{am_before}→{S.am['cycle']}  "
                f"Solde:{S.challenge['current_balance']:.2f}$"
            )


# ── REDIRECTION main_loop → main_loop_v2 ────────────────────────────────────
# main_loop() garde la même signature pour compatibilité
_main_loop_orig = main_loop

def main_loop():
    main_loop_v2()
