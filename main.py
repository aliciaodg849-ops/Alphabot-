#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  ALPHABOT PRO v7 — AGENT IA SUPRA-INTELLIGENT                          ║
# ║                                                                          ║
# ║  Cerveau adaptatif multi-couches :                                       ║
# ║  • IA Décisionnelle : raisonne sur le contexte complet avant d'agir     ║
# ║  • Mémoire Episodique : apprend de chaque trade (WR par config)         ║
# ║  • Gestion Challenge dynamique : risque recalculé à chaque scan        ║
# ║  • Régime de marché auto-détecté : Trending/Ranging/Crisis/Volatile     ║
# ║  • Anti-krach multi-niveaux : drawdown + streak + volatilité             ║
# ║  • Calcul lots Binance exact (stepSize/minNotional)                      ║
# ║  • Frais réels déduits sur chaque PnL                                    ║
# ║  • Rapports Telegram ultra-détaillés                                     ║
# ║                                                                          ║
# ║  pip install requests                                                    ║
# ╚══════════════════════════════════════════════════════════════════════════╝
import os, sys, time, json, math, random, logging, threading, hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
from datetime import datetime, timezone, timedelta
from collections import defaultdict, deque

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("alphabot_v7.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("AlphaBot")

# ══════════════════════════════════════════════════════════════════════════
#  SESSION HTTP AVEC RETRY AUTOMATIQUE
# ══════════════════════════════════════════════════════════════════════════
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def _build_http_session() -> requests.Session:
    """
    Crée une session requests avec retry automatique :
    - 5 tentatives max
    - Backoff exponentiel : 1s, 2s, 4s, 8s, 16s
    - Retry sur erreurs réseau + codes HTTP 429/500/502/503/504
    """
    s = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],  # 429 géré manuellement, 409 ne doit pas retrier
        allowed_methods=["GET", "POST", "DELETE"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://",  adapter)
    return s

HTTP = _build_http_session()


def http_get(url, params=None, timeout=12, **kwargs):
    """GET robuste avec retry. Retourne la réponse brute (le caller gère le status)."""
    try:
        r = HTTP.get(url, params=params or {}, timeout=timeout, **kwargs)
        # On ne raise PAS sur les 4xx — le caller vérifie r.status_code si besoin
        if r.status_code >= 500:
            log.warning(f"[NET] Erreur serveur {r.status_code} → {url.split('/')[2]}")
        return r
    except requests.exceptions.ConnectionError as e:
        log.warning(f"[NET] Connexion impossible → {url.split('/')[2]} | {type(e).__name__}")
        return None
    except requests.exceptions.Timeout:
        log.warning(f"[NET] Timeout → {url}")
        return None
    except Exception as e:
        log.warning(f"[NET] Erreur inattendue → {url} : {e}")
        return None


def http_post(url, data=None, json_data=None, headers=None, timeout=12):
    """POST robuste avec retry. Retourne la réponse brute."""
    try:
        r = HTTP.post(url, data=data, json=json_data,
                      headers=headers or {}, timeout=timeout)
        if r.status_code >= 500:
            log.warning(f"[NET] POST Erreur serveur {r.status_code} → {url.split('/')[2]}")
        return r
    except requests.exceptions.ConnectionError as e:
        log.warning(f"[NET] POST Connexion impossible → {url.split('/')[2]} | {type(e).__name__}")
        return None
    except requests.exceptions.Timeout:
        log.warning(f"[NET] POST Timeout → {url}")
        return None
    except Exception as e:
        log.warning(f"[NET] POST Erreur → {url} : {e}")
        return None

# ══════════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════════
TG_TOKEN        = os.getenv("TG_TOKEN",  "6950706659:AAGXw-27ebhWLm2HfG7lzC7EckpwCPS_JFg")
TG_GROUP        = os.getenv("TG_GROUP",  "-1003757467015")
TG_VIP          = os.getenv("TG_VIP",    "-1003771736496")
TG_LEADER       = "leaderOdg"
# ── Chat ID direct (prioritaire sur la recherche automatique) ─────────
# Mets ton ID Telegram ici ou via: export TG_LEADER_ID="123456789"
# Pour trouver ton ID : envoie un message à @userinfobot sur Telegram
TG_LEADER_ID    = os.getenv("TG_LEADER_ID", "6982051442")
CHALLENGE_START = float(os.getenv("CHALLENGE_START", "5.0"))
CHALLENGE_FILE  = "challenge_v7.json"
BINANCE_BASE    = "https://fapi.binance.com/fapi/v1"
# ── Clés API Binance Futures (obligatoires pour ordres réels) ──────────
BN_API_KEY      = os.getenv("BINANCE_API_KEY", "")
BN_SECRET       = os.getenv("BINANCE_SECRET",  "")
LIVE_ORDERS     = bool(BN_API_KEY and BN_SECRET)
LIVE_MIN_BALANCE = 50.0   # Minimum viable pour ordres réels Binance Futures (min notional ~100$)
FEE_TAKER       = 0.0004    # 0.04% taker (Binance Futures)
FEE_MAKER       = 0.0002    # 0.02% maker
# ── Coûts réels simulés ────────────────────────────────────────────────
SIM_SLIPPAGE    = 0.0003    # 0.03% slippage moyen à l'entrée (market order)
SIM_SPREAD      = 0.0002    # 0.02% spread bid/ask moyen
SIM_FUNDING_8H  = 0.0001    # 0.01% frais de financement / 8h (moyen)

# ── Fear & Greed Index (VIX Crypto) ────────────────────────────────────
FG_CACHE        = {"value": 50, "label": "Neutral", "ts": 0}
FG_TTL          = 3600   # refresh toutes les heures
# Impact sur le risque :
# Extreme Fear (0-25)   : risque ×1.20 (opportunité contrariante)
# Fear (26-45)          : risque ×1.10
# Neutral (46-55)       : risque ×1.00
# Greed (56-75)         : risque ×0.85
# Extreme Greed (76-100): risque ×0.70 (marché trop euphorique)
# Total coût réel estimé par trade aller-retour :
# (FEE_TAKER×2) + SIM_SLIPPAGE + SIM_SPREAD + éventuel funding
# = 0.04%×2 + 0.03% + 0.02% = ~0.13% du notional
SCAN_INTERVAL   = 20
TOP_N           = 100
ORDER_WATCH_SEC = 8         # intervalle watchdog ordres

# ── Limites de sécurité du compte ──────────────────────────────────────
FLOOR_USD            = 2.0   # plancher absolu
DD_DAY_LIMIT         = 0.35  # drawdown journalier max 35%
DD_WEEK_LIMIT        = 0.50  # drawdown hebdo max 50%
MAX_RISK_PCT         = 0.20  # jamais plus de 20% sur un seul trade
MAX_OPEN             = 3     # positions simultanées max
COOLDOWN_MIN         = 15    # cooldown par paire
# ── Exposition totale vs solde par phase ──────────────────────────────
MAX_NOTIONAL_MULT    = {"SEED":3,"GROW":5,"BUILD":8,"BOOST":10,"FINAL":12}
# ── Corrélation BTC ──────────────────────────────────────────────────
BTC_CORR_THRESHOLD   = 0.65  # paire considérée BTC-liée au-dessus
BTC_CORR_BLOCK       = 0.80  # corrélation forte → bloque si contre BTC

# ── Martingale Intelligente ──────────────────────────────────────────────
# Après un WIN  : on augmente la mise (on profite du momentum)
# Après un LOSS : on réduit (on protège le capital)
AM_WIN_MULT     = 1.50   # +50% par win consécutif
AM_LOSS_MULT    = 0.60   # -40% après un loss
AM_MAX          = 4      # max 4 cycles de boost
AM_MULT         = 1.50   # compat legacy

# ── Trailing Stop Loss (SL suiveur) ───────────────────────────────────
TRAIL_ACTIVATE_RR   = 0.8    # trail actif à RR 0.8 — sécurise tôt
BE_ACTIVATE_RR      = 0.65   # breakeven à RR 0.65 — jamais perdre si proche du TP
PARTIAL_CLOSE_RR    = 1.0    # fermeture partielle 50% à RR 1:1 (sécurise gains)
MIN_PROFIT_CLOSE    = True   # fermer à petit gain si on peut éviter le SL
TRAIL_ATR_MULT      = 0.6    # trail = 0.6 × ATR sous/sur le prix
TRAIL_ATR_TIGHT     = 0.35   # après TP1 : trail plus serré
TRAIL_MIN_STEP_PCT  = 0.002  # ne monte le SL que si gain > 0.2%

# ── Détection de pièges de marché (anti-fakeout/whipsaw) ──────────────
TRAP_MAX_BODY_RATIO  = 0.25  # mèche > 75% de la bougie → piège potentiel
TRAP_SPIKE_MULT      = 2.5   # volume spike > 2.5× moyenne → manipulation
TRAP_WHIPSAW_N       = 6     # alternances de direction sur N bougies
TRAP_SCORE_PENALTY   = 20    # pénalité de score si piège détecté

# ══════════════════════════════════════════════════════════════════════════
#  MODULE 1 — RÉGIME DE MARCHÉ (Market Regime Detector)
# ══════════════════════════════════════════════════════════════════════════
# L'agent adapte TOUTE sa logique au régime actuel du marché.
# Un agent stupide utilise les mêmes règles dans tous les contextes.
# Un agent intelligent sait quand NE PAS trader.

REGIME_PARAMS = {
    # Régime → min_score, max_risk_mult, preferred_strategies, leverage_cap
    "TRENDING_BULL": {"min_score": 80, "risk_mult": 1.20, "lev_cap": 20,
                      "strats": ["LIQ_SWEEP","ICT_OB","FVG_BOS","OB_HTF"],
                      "label": "Tendance haussière forte"},
    "TRENDING_BEAR": {"min_score": 80, "risk_mult": 1.20, "lev_cap": 20,
                      "strats": ["LIQ_SWEEP","ICT_OB","FVG_BOS","OB_HTF"],
                      "label": "Tendance baissière forte"},
    "RANGING":       {"min_score": 83, "risk_mult": 0.80, "lev_cap": 10,
                      "strats": ["LIQ_SWEEP","CHoCH","AMD_REV"],
                      "label": "Range — prudence"},
    "VOLATILE":      {"min_score": 92, "risk_mult": 0.60, "lev_cap": 7,
                      "strats": ["LIQ_SWEEP","AMD_REV"],
                      "label": "Volatile — seuil élevé"},
    "CRISIS":        {"min_score": 95, "risk_mult": 0.30, "lev_cap": 3,
                      "strats": [],
                      "label": "Crise — quasi stop"},
    "ACCUMULATION":  {"min_score": 82, "risk_mult": 1.0,  "lev_cap": 15,
                      "strats": ["ICT_OB","FVG_BOS","OB_HTF","CHoCH"],
                      "label": "Accumulation — attente breakout"},
}

def detect_market_regime(candles_btc_4h: list, candles_btc_1h: list) -> dict:
    """
    Détecte le régime macro du marché crypto en analysant BTC.
    Retourne le régime actuel et adapte les paramètres de trading.
    """
    if len(candles_btc_4h) < 20:
        return {"regime": "RANGING", **REGIME_PARAMS["RANGING"]}

    c4h = candles_btc_4h[-20:]
    c1h = candles_btc_1h[-24:] if len(candles_btc_1h) >= 24 else candles_btc_1h

    closes_4h = [c["close"] for c in c4h]
    highs_4h  = [c["high"]  for c in c4h]
    lows_4h   = [c["low"]   for c in c4h]
    vols_4h   = [c["vol"]   for c in c4h]

    # ATR normalisé = mesure de volatilité
    atr_raw   = sum(h - l for h, l in zip(highs_4h, lows_4h)) / len(c4h)
    atr_pct   = atr_raw / closes_4h[-1] * 100 if closes_4h[-1] > 0 else 0

    # Momentum 20 périodes
    mom_20    = (closes_4h[-1] - closes_4h[0]) / closes_4h[0] * 100 if closes_4h[0] > 0 else 0

    # Range ratio : étendue relative
    rng       = max(highs_4h) - min(lows_4h)
    mid       = sum(closes_4h) / len(closes_4h)
    rng_pct   = rng / mid * 100 if mid > 0 else 0

    # Volume trend
    avg_vol   = sum(vols_4h[:-5]) / max(len(vols_4h) - 5, 1)
    last_vol  = sum(vols_4h[-3:]) / 3
    vol_ratio = last_vol / avg_vol if avg_vol > 0 else 1

    # Détection crash / spike extrême
    max_candle_move = max(abs(c["close"] - c["open"]) / c["open"] * 100
                          for c in c4h[-5:] if c["open"] > 0)

    # Décision regime
    if atr_pct > 5.0 or max_candle_move > 8.0:
        regime = "CRISIS"
    elif atr_pct > 3.0:
        regime = "VOLATILE"
    elif abs(mom_20) > 8.0 and vol_ratio > 1.2:
        regime = "TRENDING_BULL" if mom_20 > 0 else "TRENDING_BEAR"
    elif abs(mom_20) > 3.0:
        regime = "TRENDING_BULL" if mom_20 > 0 else "TRENDING_BEAR"
    elif rng_pct < 3.0:
        regime = "ACCUMULATION"
    else:
        regime = "RANGING"

    params = REGIME_PARAMS[regime]
    return {
        "regime":    regime,
        "label":     params["label"],
        "atr_pct":   round(atr_pct, 2),
        "mom_20":    round(mom_20, 2),
        "vol_ratio": round(vol_ratio, 2),
        "min_score": params["min_score"],
        "risk_mult": params["risk_mult"],
        "lev_cap":   params["lev_cap"],
        "strats":    params["strats"],
    }

# ══════════════════════════════════════════════════════════════════════════
#  MODULE 2 — SESSIONS BANCAIRES & KILL ZONES
# ══════════════════════════════════════════════════════════════════════════
SESSIONS = {
    "ASIA_OPEN":  (0,  3,  0.3, "Tokyo Open"),
    "ASIA_MID":   (3,  7,  0.1, "Asie range"),
    "LONDON_KZ":  (7,  10, 1.0, "London Kill Zone 🔥"),
    "LONDON_AM":  (10, 12, 0.8, "Londres AM"),
    "PRE_NY":     (12, 13, 0.5, "Pre-New York"),
    "NY_KZ":      (13, 16, 1.0, "New York Kill Zone 🔥"),
    "NY_AM":      (16, 19, 0.7, "New York AM"),
    "NY_LUNCH":   (19, 20, 0.0, "NY Lunch ⛔"),
    "NY_PM":      (20, 22, 0.4, "New York PM"),
    "DEAD":       (22, 24, 0.0, "Zone morte ⛔"),
}
MANIP_HOURS = {2, 3, 7, 8, 9, 13, 14, 15}
AVOID_HOURS = {19, 22, 23, 0, 1}

def get_session() -> dict:
    h = datetime.now(timezone.utc).hour
    m = datetime.now(timezone.utc).minute
    name, quality, label = "DEAD", 0.0, "Zone morte"
    for n, (s, e, q, l) in SESSIONS.items():
        if s <= h < e:
            name, quality, label = n, q, l; break
    in_kz    = name in ("LONDON_KZ", "NY_KZ")
    overlap  = 13 <= h < 16
    avoid    = h in AVOID_HOURS or name in ("NY_LUNCH", "DEAD")
    bonus = 0
    if in_kz:             bonus += 15
    if h in MANIP_HOURS:  bonus += 10
    if overlap:           bonus += 8
    if avoid:             bonus -= 25
    return {"name": name, "label": label, "quality": quality,
            "bonus": bonus, "in_kz": in_kz, "avoid": avoid,
            "hour": h, "minute": m, "overlap": overlap}

# ══════════════════════════════════════════════════════════════════════════
#  MODULE 3 — ANALYSE TECHNIQUE COMPLÈTE
# ══════════════════════════════════════════════════════════════════════════

def calc_atr(c, p=14):
    r = c[-p:]
    return sum(x["high"]-x["low"] for x in r)/len(r) if r else 0.01

def calc_rsi(c, p=14):
    if len(c) < p+1: return 50.0
    cl = [x["close"] for x in c[-(p+1):]]
    g = [max(0, cl[i]-cl[i-1]) for i in range(1, len(cl))]
    l = [max(0, cl[i-1]-cl[i]) for i in range(1, len(cl))]
    ag, al = sum(g)/p, sum(l)/p
    return round(100-100/(1+ag/al), 1) if al > 0 else 100.0

def calc_ema(c, p):
    if len(c) < p: return c[-1]["close"] if c else 0
    k = 2/(p+1)
    ema = sum(x["close"] for x in c[:p])/p
    for x in c[p:]: ema = x["close"]*k + ema*(1-k)
    return ema

def detect_structure(c) -> dict:
    if len(c) < 15: return {"type":"UNKNOWN","bias":"N","bonus":0,"label":"?"}
    recent = c[-15:]
    SH, SL = [], []
    for i in range(2, len(recent)-2):
        x = recent[i]
        if x["high"] > recent[i-1]["high"] and x["high"] > recent[i+1]["high"]: SH.append(x["high"])
        if x["low"]  < recent[i-1]["low"]  and x["low"]  < recent[i+1]["low"]:  SL.append(x["low"])
    if not SH or not SL: return {"type":"RANGE","bias":"N","bonus":0,"label":"Range"}
    p = recent[-1]["close"]
    bull = len(SH)>=2 and SH[-1]>SH[-2] and len(SL)>=2 and SL[-1]>SL[-2]
    bear = len(SH)>=2 and SH[-1]<SH[-2] and len(SL)>=2 and SL[-1]<SL[-2]
    if p > SH[-1] and bear: return {"type":"CHoCH_BULL","bias":"BULL","bonus":20,"label":"CHoCH Haussier"}
    if p < SL[-1] and bull: return {"type":"CHoCH_BEAR","bias":"BEAR","bonus":20,"label":"CHoCH Baissier"}
    if p > SH[-1] and bull: return {"type":"BOS_BULL",  "bias":"BULL","bonus":12,"label":"BOS Haussier"}
    if p < SL[-1] and bear: return {"type":"BOS_BEAR",  "bias":"BEAR","bonus":12,"label":"BOS Baissier"}
    if bull: return {"type":"TREND_BULL","bias":"BULL","bonus":6,"label":"Tendance haussiere"}
    if bear: return {"type":"TREND_BEAR","bias":"BEAR","bonus":6,"label":"Tendance baissiere"}
    return {"type":"RANGE","bias":"N","bonus":0,"label":"Range"}

def detect_amd(c) -> dict:
    if len(c) < 20: return {"phase":"?","conf":0,"label":"Inconnu","dir":None}
    vols  = [x["vol"]   for x in c[-20:]]
    cl    = [x["close"] for x in c[-20:]]
    hi    = [x["high"]  for x in c[-20:]]
    lo    = [x["low"]   for x in c[-20:]]
    avg_v = sum(vols[:-5])/15 if len(vols)>5 else 1
    v_rat = vols[-1]/avg_v if avg_v > 0 else 1
    rng   = max(hi)-min(lo); mid = sum(cl)/len(cl)
    rp    = rng/mid*100 if mid > 0 else 0
    mom   = (cl[-1]-cl[-5])/cl[-5]*100 if cl[-5] > 0 else 0
    spike = (max(hi[-5:])-min(lo[-5:]))/(max(hi[:-5])-min(lo[:-5])+1e-9)
    if rp < 1.5 and v_rat < 1.3:
        return {"phase":"ACC","conf":0.75,"label":"Accumulation bancaire","dir":None}
    if spike > 2.0 and v_rat > 1.6:
        d = "UP" if cl[-1] > cl[-6] else "DOWN"
        return {"phase":"MANIP","conf":0.85,"label":f"Manipulation {d}","dir":d}
    if abs(mom) > 0.8 and v_rat < 1.0:
        d = "BULL" if mom > 0 else "BEAR"
        return {"phase":"DIST","conf":0.70,"label":f"Distribution {d}","dir":d}
    return {"phase":"TRANS","conf":0.40,"label":"Transition","dir":None}

def detect_liq(c) -> dict:
    if len(c) < 20: return {"buy":[],"sell":[]}
    recent = c[-20:]
    buy_l, sell_l = [], []
    tol = 0.0007
    for i in range(2, len(recent)-2):
        x = recent[i]
        eq_h = (abs(x["high"]-recent[i-1]["high"])/x["high"]<tol or
                abs(x["high"]-recent[i+1]["high"])/x["high"]<tol)
        eq_l = (abs(x["low"]-recent[i-1]["low"])/x["low"]<tol or
                abs(x["low"]-recent[i+1]["low"])/x["low"]<tol)
        sh = (x["high"]>recent[i-1]["high"] and x["high"]>recent[i+1]["high"] and
              x["high"]>recent[i-2]["high"] and x["high"]>recent[i+2]["high"])
        sl = (x["low"]<recent[i-1]["low"] and x["low"]<recent[i+1]["low"] and
              x["low"]<recent[i-2]["low"] and x["low"]<recent[i+2]["low"])
        if eq_h or sh: sell_l.append(x["high"])
        if eq_l or sl: buy_l.append(x["low"])
    return {"buy": sorted(set(round(v,8) for v in buy_l))[-5:],
            "sell": sorted(set(round(v,8) for v in sell_l))[-5:]}

def detect_sweep(c, liq) -> dict:
    if len(c) < 3: return {"swept":False}
    last, prev = c[-1], c[-2]
    for lvl in liq.get("sell",[]):
        if prev["high"] <= lvl <= last["high"] and last["close"] < lvl:
            return {"swept":True,"dir":"SHORT","lvl":lvl,"bonus":22,
                    "label":f"Sweep SHORT {lvl:.5f}"}
    for lvl in liq.get("buy",[]):
        if prev["low"] >= lvl >= last["low"] and last["close"] > lvl:
            return {"swept":True,"dir":"LONG","lvl":lvl,"bonus":22,
                    "label":f"Sweep LONG {lvl:.5f}"}
    return {"swept":False}

def detect_ob(c, bias) -> list:
    if len(c) < 8: return []
    obs, n = [], len(c)
    for i in range(2, n-3):
        x, xn, xn2 = c[i], c[i+1], c[i+2]
        body = abs(x["close"]-x["open"]); rng = x["high"]-x["low"]
        if rng == 0: continue
        bull_i = xn["close"]>xn["open"] and xn2["close"]>xn2["open"] and (xn["close"]-xn["open"])>body*0.7
        bear_i = xn["close"]<xn["open"] and xn2["close"]<xn2["open"] and (xn["open"]-xn["close"])>body*0.7
        price = c[-1]["close"]
        if x["close"]<x["open"] and bull_i and body/rng>0.35 and x["low"]<=price<=x["high"]*1.004:
            obs.append({"side":"BUY","low":x["low"],"high":x["high"],
                        "mid":(x["low"]+x["high"])/2,"age":n-i,
                        "bonus":20 if bias=="BULL" else 10,"label":"OB Haussier"})
        if x["close"]>x["open"] and bear_i and body/rng>0.35 and x["low"]*0.996<=price<=x["high"]:
            obs.append({"side":"SELL","low":x["low"],"high":x["high"],
                        "mid":(x["low"]+x["high"])/2,"age":n-i,
                        "bonus":20 if bias=="BEAR" else 10,"label":"OB Baissier"})
    obs.sort(key=lambda x: x["age"])
    return obs[:3]

def detect_fvg(c) -> list:
    fvgs, n = [], len(c)
    if n < 5: return fvgs
    price = c[-1]["close"]
    for i in range(2, n-1):
        a, b, d = c[i-2], c[i-1], c[i]
        if d["low"] > a["high"] and b["close"] > b["open"] and a["high"] <= price <= d["low"]*1.003:
            fvgs.append({"side":"BUY","low":a["high"],"high":d["low"],
                         "mid":(a["high"]+d["low"])/2,"age":n-i,
                         "size":d["low"]-a["high"],"label":"FVG Bull"})
        if d["high"] < a["low"] and b["close"] < b["open"] and d["high"]*0.997 <= price <= a["low"]:
            fvgs.append({"side":"SELL","low":d["high"],"high":a["low"],
                         "mid":(d["high"]+a["low"])/2,"age":n-i,
                         "size":a["low"]-d["high"],"label":"FVG Bear"})
    fvgs.sort(key=lambda x: x["age"])
    return fvgs[:3]

def get_mtf(symbol) -> dict:
    biases = {}
    for tf in ["4h","1h","15m","5m"]:
        c = list(STATE.candles[symbol].get(tf, deque()))
        if len(c) < 10: biases[tf] = "N"; continue
        cl = [x["close"] for x in c[-10:]]
        hi = [x["high"]  for x in c[-10:]]
        lo = [x["low"]   for x in c[-10:]]
        ef = sum(cl[-3:])/3; es = sum(cl)/10
        if ef>es and hi[-1]>hi[-5] and lo[-1]>lo[-5]: biases[tf]="BULL"
        elif ef<es and hi[-1]<hi[-5] and lo[-1]<lo[-5]: biases[tf]="BEAR"
        else: biases[tf]="N"
    b = sum(1 for v in biases.values() if v=="BULL")
    s = sum(1 for v in biases.values() if v=="BEAR")
    if b>=3: overall,score="BULL",min(b*7,25)
    elif s>=3: overall,score="BEAR",min(s*7,25)
    elif b>=2: overall,score="BULL_W",b*4
    elif s>=2: overall,score="BEAR_W",s*4
    else: overall,score="N",0
    return {"overall":overall,"score":score,"aligned":b>=3 or s>=3,
            "h4":biases.get("4h","N"),"h1":biases.get("1h","N"),
            "m15":biases.get("15m","N"),"m5":biases.get("5m","N")}

# ══════════════════════════════════════════════════════════════════════════
#  MODULE 3b — DÉTECTEUR DE PIÈGES DE MARCHÉ
# ══════════════════════════════════════════════════════════════════════════
def detect_market_trap(c5: list) -> dict:
    """
    Détecte les conditions dangereuses avant d'entrer :
    1. Fakeout : grosse mèche + fermeture en corps minuscule (manipulation)
    2. Whipsaw : alternances de direction rapides → pas de tendance claire
    3. Volume spike : volume anormal → news ou liquidation en cours
    4. Candle trop étendue : ATR × 3 → don't chase
    Retourne {"trap": bool, "score_penalty": int, "reasons": list}
    """
    if len(c5) < 10:
        return {"trap": False, "score_penalty": 0, "reasons": []}

    reasons = []
    penalty = 0
    last3 = c5[-3:]

    # ── 1. Fakeout (mèche dominante) ────────────────────────────────
    for c in last3:
        rng = c["high"] - c["low"]
        if rng <= 0: continue
        body = abs(c["close"] - c["open"])
        if body / rng < TRAP_MAX_BODY_RATIO:
            wick_pct = (rng - body) / rng
            if wick_pct > 0.80:
                penalty += 12
                reasons.append(f"Fakeout mèche {wick_pct*100:.0f}% -12")
                break

    # ── 2. Whipsaw : alternances de direction ────────────────────────
    dirs = []
    for c in c5[-TRAP_WHIPSAW_N:]:
        dirs.append(1 if c["close"] > c["open"] else -1)
    alternances = sum(1 for i in range(1, len(dirs)) if dirs[i] != dirs[i-1])
    if alternances >= TRAP_WHIPSAW_N - 1:
        penalty += 15
        reasons.append(f"Whipsaw {alternances} alternances -15")

    # ── 3. Volume spike ──────────────────────────────────────────────
    vols = [c["vol"] for c in c5[-20:] if c.get("vol",0) > 0]
    if len(vols) >= 5:
        avg_vol = sum(vols[:-1]) / (len(vols)-1) if len(vols) > 1 else 1
        if vols[-1] > avg_vol * TRAP_SPIKE_MULT:
            penalty += 10
            reasons.append(f"Volume spike ×{vols[-1]/avg_vol:.1f} -10")

    # ── 4. Bougie trop étendue (don't chase) ─────────────────────────
    atr = calc_atr(c5)
    last_range = c5[-1]["high"] - c5[-1]["low"]
    if atr > 0 and last_range > atr * 3.0:
        penalty += 8
        reasons.append(f"Bougie extended {last_range/atr:.1f}×ATR -8")

    # ── 5. Déjà en mouvement (too late to enter) ─────────────────────
    closes = [c["close"] for c in c5[-6:]]
    move = abs(closes[-1] - closes[0]) / closes[0] * 100 if closes[0] > 0 else 0
    if move > 3.0:
        penalty += 8
        reasons.append(f"Move déjà {move:.1f}% -8")

    trap = penalty >= TRAP_SCORE_PENALTY
    return {"trap": trap, "score_penalty": penalty, "reasons": reasons}

# ══════════════════════════════════════════════════════════════════════════
#  MODULE 4 — MÉMOIRE ÉPISODIQUE & APPRENTISSAGE
# ══════════════════════════════════════════════════════════════════════════
# L'agent mémorise chaque trade et apprend quels contextes sont gagnants.
# Avec le temps, son edge s'améliore automatiquement.

class Memory:
    """
    Mémoire épisodique de l'agent.
    Chaque trade est encodé comme un épisode avec son contexte complet.
    L'agent consulte cette mémoire pour pondérer ses décisions.
    """
    def __init__(self):
        self.episodes = self._load()

    def _load(self):
        try:
            with open("memory_v7.json") as f: return json.load(f)
        except: return {"episodes": [], "stats": {}}

    def _save(self):
        # Garder les 500 derniers épisodes
        self.episodes["episodes"] = self.episodes["episodes"][-500:]
        with open("memory_v7.json", "w") as f:
            json.dump(self.episodes, f, indent=2)

    def record(self, context: dict, result: str, pnl: float):
        """Enregistre un épisode avec son contexte."""
        episode = {
            "ts":        datetime.now(timezone.utc).isoformat(),
            "strategy":  context.get("strategy", "?"),
            "session":   context.get("session", "?"),
            "regime":    context.get("regime", "?"),
            "score":     context.get("score", 0),
            "rr_target": context.get("rr", 0),
            "side":      context.get("side", "?"),
            "amd":       context.get("amd", "?"),
            "struct":    context.get("struct", "?"),
            "hour":      datetime.now(timezone.utc).hour,
            "result":    result,
            "pnl":       round(pnl, 4),
        }
        self.episodes["episodes"].append(episode)
        # Mise à jour stats
        key = f"{context.get('strategy','?')}|{context.get('session','?')}|{context.get('regime','?')}"
        s = self.episodes["stats"].setdefault(key, {"w":0,"l":0,"pnl":0.0})
        if result == "WIN": s["w"] += 1
        else: s["l"] += 1
        s["pnl"] = round(s["pnl"] + pnl, 4)
        self._save()

    def query_wr(self, strategy: str, session: str, regime: str) -> float:
        """Retourne le WR historique pour ce contexte précis."""
        key = f"{strategy}|{session}|{regime}"
        s = self.episodes["stats"].get(key, {})
        t = s.get("w",0) + s.get("l",0)
        if t >= 3: return s.get("w",0) / t
        # Fallback : stratégie seule
        for k, v in self.episodes["stats"].items():
            if k.startswith(strategy+"|"):
                tt = v.get("w",0)+v.get("l",0)
                if tt >= 5: return v.get("w",0)/tt
        return 0.80  # prior par défaut

    def get_best_context(self) -> list:
        """Retourne les 3 meilleurs contextes par WR (pour le rapport)."""
        results = []
        for key, v in self.episodes["stats"].items():
            t = v.get("w",0)+v.get("l",0)
            if t >= 3:
                results.append({"key": key, "wr": v["w"]/t, "total": t, "pnl": v["pnl"]})
        results.sort(key=lambda x: (x["wr"], x["total"]), reverse=True)
        return results[:3]

    def get_losing_context(self) -> list:
        """Retourne les contextes à éviter."""
        results = []
        for key, v in self.episodes["stats"].items():
            t = v.get("w",0)+v.get("l",0)
            if t >= 3 and v["w"]/t < 0.40:
                results.append({"key": key, "wr": v["w"]/t, "total": t})
        return results[:3]

# ══════════════════════════════════════════════════════════════════════════
#  MODULE 5 — GESTIONNAIRE DE CHALLENGE DYNAMIQUE
# ══════════════════════════════════════════════════════════════════════════
# Le challenge 5$→500$ est géré comme un jeu avec 4 phases.
# Chaque phase a ses propres règles de risque, levier, et critères.

class ChallengeManager:
    """
    Gère le challenge 5$→500$ de façon dynamique.
    Recalcule la phase à chaque scan et adapte la stratégie.
    """
    PHASES = {
        # nom      min$    max$    risk%  lev_max label
        # SEED agressif : nécessaire pour croître depuis 5$ (sim uniquement)
        # En live Binance Futures, minimum viable ~50$ (min notional 100$)
        "SEED":   (0,     15,    0.10,   20, "Phase Graine (5-15$)"),
        "GROW":   (15,    50,    0.08,   15, "Phase Croissance (15-50$)"),
        "BUILD":  (50,    150,   0.05,   12, "Phase Construction (50-150$)"),
        "BOOST":  (150,   300,   0.03,   10, "Phase Boost (150-300$)"),
        "FINAL":  (300,   10000, 0.02,   8,  "Phase Finale (300$+)"),
    }

    def __init__(self, state):
        self.state = state

    def get_phase(self, balance: float) -> dict:
        for name, (mn, mx, rp, lm, label) in self.PHASES.items():
            if mn <= balance < mx:
                return {"name": name, "label": label, "risk_pct": rp,
                        "lev_max": lm, "min": mn, "max": mx}
        return {"name": "FINAL", "label": "Phase Finale", "risk_pct": 0.05,
                "lev_max": 25, "min": 300, "max": 10000}

    def calc_risk(self, balance: float, score: int, am_cycle: int,
                  regime: dict, sess: dict) -> float:
        """
        Martingale Intelligente sur base fixe 0.50$
        ─────────────────────────────────────────────
        Principe : on surfe les séries gagnantes, on coupe quand ça coince.
        La mise monte APRÈS un win, descend APRÈS un loss.
        Jamais l'inverse (≠ martingale classique suicidaire).

        Win streak  → on appuie (momentum réel)
        Loss streak → on réduit (protection capital)
        Cap dur     → jamais plus de 25% du solde
        """
        BASE      = 0.50   # mise de base — risque fixe 0.50$
        WIN_MULT  = 1.50   # ×1.5 par win consécutif
        LOSS_MULT = 0.65   # ×0.65 après loss
        WIN_CAP   = 3      # max 3 paliers de boost
        LOSS_FLOOR= 0.25   # plancher absolu en $

        win_streak  = STATE.am.get("win_streak",  0)
        loss_streak = STATE.am.get("loss_streak", 0)

        if win_streak > 0:
            # Série gagnante : on monte progressivement
            paliers = min(win_streak, WIN_CAP)
            risk = BASE * (WIN_MULT ** paliers)
        elif loss_streak > 0:
            # Série perdante : on réduit pour survivre
            risk = BASE * (LOSS_MULT ** loss_streak)
            risk = max(risk, LOSS_FLOOR)
        else:
            risk = BASE

        # Ajustement Fear & Greed (VIX Crypto)
        fg_mult = fg_risk_mult()
        risk *= fg_mult

        # Ajustement série perdante : réduire progressivement
        loss_streak = STATE.challenge.get("loss_streak_today", 0)
        if loss_streak >= 3:
            risk *= 0.60   # -40% après 3 pertes consécutives
            log.debug(f"[RISK] Série perdante {loss_streak} → risque réduit ×0.6")
        elif loss_streak >= 2:
            risk *= 0.80   # -20% après 2 pertes

        # Ajustement série gagnante : augmenter progressivement (max ×1.5)
        win_streak = STATE.am.get("win_streak", 0)
        if win_streak >= 4:
            risk *= min(1.0 + win_streak * 0.08, 1.50)
            log.debug(f"[RISK] Série gagnante {win_streak} → risque ×{min(1+win_streak*0.08,1.5):.2f}")

        # Marge Binance : vérifier que la marge dispo est suffisante
        # Ne jamais utiliser plus de 80% de la marge disponible
        open_margin = sum(t.get("notional",0)/t.get("leverage",1)
                         for t in STATE.open_trades.values() if t["status"]=="open")
        max_risk_by_margin = max((balance * 0.80 - open_margin) * 0.15, 0.10)
        risk = min(risk, max_risk_by_margin)

        # Cap dur : jamais plus de 20% du solde par trade
        risk = min(risk, balance * 0.20)
        risk = max(risk, 0.10)  # minimum absolu

        return round(risk, 2)

    def get_leverage(self, symbol: str, balance: float,
                     score: int, regime: dict) -> int:
        phase   = self.get_phase(balance)
        lev_max = min(phase["lev_max"], regime.get("lev_cap", 20))

        # Levier de base progressif — agressif en SEED pour croître vite
        if balance < 8:     base = 15
        elif balance < 15:  base = 20
        elif balance < 30:  base = 15
        elif balance < 75:  base = 12
        elif balance < 150: base = 10
        elif balance < 300: base = 10
        else:               base = 8

        # Bonus score (haute conviction = plus de levier)
        if score >= 93: base = min(base + 3, lev_max)
        elif score >= 87: base = min(base + 2, lev_max)
        elif score >= 80: base = min(base + 1, lev_max)

        pair_max = PAIR_MAX_LEV.get(symbol, 20)
        return min(base, lev_max, pair_max)

    def check_safety(self, c: dict) -> dict:
        """Vérifie toutes les conditions de sécurité du compte."""
        bal       = c.get("current_balance", CHALLENGE_START)
        day_open  = c.get("day_open_balance", CHALLENGE_START)
        start_bal = c.get("start_balance", CHALLENGE_START)

        # Plancher absolu
        if bal < FLOOR_USD:
            return {"ok": False, "reason": f"Solde < plancher {FLOOR_USD}$",
                    "action": "STOP_ABSOLUTE"}

        # Drawdown journalier
        dd_day = (day_open - bal) / day_open if day_open > 0 else 0
        if dd_day >= DD_DAY_LIMIT:
            return {"ok": False, "reason": f"DD journalier {dd_day*100:.1f}% >= {DD_DAY_LIMIT*100:.0f}%",
                    "action": "PAUSE_DAY"}

        # Streak de pertes → réduire la taille
        am     = STATE.am
        streak = am.get("loss_streak", 0)
        warn   = streak >= 3

        return {"ok": True, "dd_day": round(dd_day*100, 1),
                "streak_loss": streak, "warn": warn, "bal": bal}

    def progress_report(self, c: dict) -> str:
        bal    = c.get("current_balance", CHALLENGE_START)
        start  = c.get("start_balance", CHALLENGE_START)
        target = start * 100
        phase  = self.get_phase(bal)
        prog   = min(100, bal / target * 100) if target > 0 else 0
        gain   = bal - start
        pct    = gain / start * 100 if start > 0 else 0

        # Barre de progression
        filled = int(prog / 5)
        bar    = "█" * filled + "░" * (20 - filled)
        return (f"[{bar}] {prog:.1f}%\n"
                f"{start:.2f}$ → {bal:.4f}$ ({pct:+.1f}%)\n"
                f"Objectif: {target:.0f}$ | {phase['label']}")

# ══════════════════════════════════════════════════════════════════════════
#  MODULE 6 — EXCHANGE INFO & LOTS BINANCE
# ══════════════════════════════════════════════════════════════════════════
PAIR_MAX_LEV = {
    "BTCUSDT":125,"ETHUSDT":100,"BNBUSDT":75,"SOLUSDT":50,
    "XRPUSDT":50,"ADAUSDT":50,"DOGEUSDT":50,"AVAXUSDT":50,
    "LINKUSDT":50,"DOTUSDT":25,"MATICUSDT":50,"LTCUSDT":75,
}
EXCH_CACHE = {}
EXCH_TS    = 0

def refresh_exchange_info():
    global EXCH_TS
    try:
        resp = http_get(f"{BINANCE_BASE}/exchangeInfo", timeout=15)
        if resp is None:
            log.warning("[EXCH] exchangeInfo indisponible — nouvelle tentative au prochain cycle")
            return
        d = resp.json()
        for sym in d.get("symbols", []):
            s = sym["symbol"]
            info = {"step":1.0,"minQty":0.0,"minNot":5.0,"tick":0.01}
            for f in sym.get("filters",[]):
                if f["filterType"] == "LOT_SIZE":
                    info["step"]   = float(f["stepSize"])
                    info["minQty"] = float(f["minQty"])
                elif f["filterType"] == "MIN_NOTIONAL":
                    info["minNot"] = float(f.get("notional",5.0))
                elif f["filterType"] == "PRICE_FILTER":
                    info["tick"]   = float(f["tickSize"])
            EXCH_CACHE[s] = info
        EXCH_TS = time.time()
        log.debug(f"[EXCH] {len(EXCH_CACHE)} paires chargees")
    except Exception as e:
        log.warning(f"[EXCH] {e}")

def sym_info(symbol):
    if not EXCH_CACHE or time.time()-EXCH_TS > 3600:
        refresh_exchange_info()
    return EXCH_CACHE.get(symbol, {"step":0.001,"minQty":0.001,"minNot":100.0,"tick":0.01})

def round_step(q, step):
    if step <= 0: return q
    p = max(0, round(-math.log10(step)))
    return round(math.floor(q/step)*step, p)

def calc_lot(symbol, risk_usdt, sl_dist, entry, leverage) -> dict:
    info    = sym_info(symbol)
    step    = info["step"]
    min_qty = info["minQty"]
    min_not = info["minNot"]
    # ── Calcul du lot à partir du SL (logique correcte) ────────────────
    # Principe : SL placé sur structure marché → lot = risk / sl_dist
    # On intègre les frais dans sl_dist effectif pour que perte SL = risk exact
    total_cost_pct = FEE_TAKER * 2 + SIM_SLIPPAGE + SIM_SPREAD
    effective_sl = sl_dist + entry * total_cost_pct if sl_dist > 0 else sl_dist
    qty     = round_step(risk_usdt / effective_sl if effective_sl > 0 else 0, step)
    qty     = max(qty, min_qty)
    notional = qty * entry

    # ── Si notionnel trop faible : augmenter levier (plafonné au max phase)
    # plutôt que de forcer une qty arbitraire qui fausse le risque
    if notional < min_not and leverage > 0:
        # On calcule le levier nécessaire pour que marge = risk_usdt
        # notional_cible = min_not → qty_cible = min_not / entry
        # Le levier n'affecte pas la qty ni le risque SL, juste la marge
        # Ici on ajuste uniquement si le min notionnel est Binance (live)
        # En simulation on garde la qty exacte calculée depuis le risque
        if LIVE_ORDERS:
            qty = round_step(min_not / entry * 1.01, step)
            qty = max(qty, min_qty)
            notional = qty * entry
            # Recalcul risque réel avec cette qty forcée
            # (en live, le risque sera légèrement différent — on l'affiche)
    fee_open  = notional * FEE_TAKER
    fee_close = notional * FEE_TAKER
    fee_total = fee_open + fee_close
    # Marge isolée nécessaire = notionnel / levier
    margin_needed = notional / leverage if leverage > 0 else notional
    real_risk = qty * sl_dist + fee_total

    # ── Vérification finale : lot valide pour Binance ────────────────
    # 1. Quantité doit être multiple du stepSize
    # 2. Notionnel doit être ≥ minNotional (en LIVE)
    # 3. Marge ne doit pas dépasser le solde
    valid = (qty >= min_qty and qty == round_step(qty, step))

    return {"qty": qty, "notional": round(notional,4),
            "fee_open": round(fee_open,6), "fee_close": round(fee_close,6),
            "fee_total": round(fee_total,6), "real_risk": round(real_risk,4),
            "margin_needed": round(margin_needed, 4),
            "valid": valid,
            "min_qty": min_qty, "step": step}

# ══════════════════════════════════════════════════════════════════════════
#  ÉTAT GLOBAL
# ══════════════════════════════════════════════════════════════════════════
class BotState:
    def __init__(self):
        self.running      = True
        self.open_trades  = {}
        self.trade_ctr    = 0
        self.cooldowns    = {}
        self.candles      = defaultdict(lambda: defaultdict(deque))
        self.prices       = {}
        self.top_pairs    = []
        self.tg_id        = None
        self._lock        = threading.Lock()
        # SL rejetés par Binance : {tid: {sym, sl_price, side, qty}}
        self.rejected_sls = {}
        self.am          = self._load("am_v7.json",
                            {"cycle":0,"win_streak":0,"loss_streak":0,
                             "last":None,"total_boosted":0.0,"history":[]})
        self.challenge   = self._load_challenge()
        self.regime      = {"regime":"RANGING","label":"Init","min_score":72,
                            "risk_mult":1.0,"lev_cap":15,"strats":[]}
        self.memory      = Memory()
        self.challenge_mgr = None
        # Restaurer état volatile depuis state_v7.json
        self._restore_state()

    def _load(self, fname, default):
        try:
            with open(fname) as f: return json.load(f)
        except: return default

    def _save(self, fname, data):
        with open(fname,"w") as f: json.dump(data, f, indent=2)

    def _load_challenge(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            c = self._load(CHALLENGE_FILE, None)
            if c is None: raise Exception("no file")
            # Si le solde sauvegardé est inférieur au solde de départ du challenge → reset
            if c.get("current_balance", 0) < CHALLENGE_START:
                log.warning(f"[CHALLENGE] Solde sauvegardé {c.get('current_balance',0):.4f}$ "
                            f"< départ {CHALLENGE_START}$ → reset à {CHALLENGE_START}$")
                raise Exception("balance below start")
            if c.get("day_start") != today:
                dob = c.get("current_balance", CHALLENGE_START)
                c.update({"day_start": today, "today_pnl": 0.0,
                          "today_wins": 0, "today_losses": 0, "trades": [],
                          "published": False, "day_open_balance": dob})
                self._save(CHALLENGE_FILE, c)
            return c
        except:
            c = {"start_balance": CHALLENGE_START,
                 "current_balance": CHALLENGE_START,
                 "day_start": today, "today_pnl": 0.0,
                 "today_wins": 0, "today_losses": 0,
                 "best_rr": 0.0, "trades": [], "published": False,
                 "all_time_peak": CHALLENGE_START,
                 "day_open_balance": CHALLENGE_START}
            self._save(CHALLENGE_FILE, c)
            return c

    def save(self):
        self._save("am_v7.json",   self.am)
        self._save(CHALLENGE_FILE, self.challenge)
        # Sauvegarder état volatile
        trades_ser = {}
        for tid, t in self.open_trades.items():
            entry = dict(t)
            trades_ser[str(tid)] = entry
        cds = {k: v.isoformat() for k, v in self.cooldowns.items()
               if isinstance(v, datetime)}
        state_data = {
            "open_trades":  trades_ser,
            "trade_ctr":    self.trade_ctr,
            "cooldowns":    cds,
            "tg_id":        self.tg_id,
            "rejected_sls": self.rejected_sls,
        }
        self._save("state_v7.json", state_data)

    def _restore_state(self):
        try:
            s = self._load("state_v7.json", None)
            if not s: return
            restored = {int(k): v for k, v in s.get("open_trades", {}).items()}
            open_cnt = sum(1 for t in restored.values() if t.get("status")=="open")
            if open_cnt > 0:
                log.warning(f"[STATE] Restauration: {open_cnt} trade(s) ouvert(s) depuis state_v7.json")
            self.open_trades  = restored
            self.trade_ctr    = s.get("trade_ctr", 0)
            self.tg_id        = s.get("tg_id")
            self.rejected_sls = s.get("rejected_sls", {})
            for k, v in s.get("cooldowns", {}).items():
                try:
                    self.cooldowns[k] = datetime.fromisoformat(v)
                except: pass
        except Exception as e:
            log.debug(f"[STATE] Restauration échouée: {e}")

    def new_tid(self):
        self.trade_ctr += 1
        return self.trade_ctr

    def update_am(self, result, pnl, pair, sess, strat, hour):
        am = self.am; old = am["cycle"]
        if result == "WIN":
            am["win_streak"]  = am.get("win_streak",0) + 1
            am["loss_streak"] = 0
            if am["win_streak"] >= AM_MAX:
                am["cycle"] = 0; am["win_streak"] = 0
            else:
                am["cycle"] = min(am["cycle"]+1, AM_MAX)
            am["total_boosted"] = am.get("total_boosted",0) + max(0, pnl - CHALLENGE_START*0.06)
        else:
            am["loss_streak"] = am.get("loss_streak",0) + 1
            am["cycle"] = 0; am["win_streak"] = 0
        am["last"] = result
        am["history"].insert(0, {"old":old,"new":am["cycle"],"result":result,
                                  "pnl":round(pnl,4),"pair":pair,
                                  "sess":sess,"strat":strat,"h":hour,
                                  "ts":datetime.now(timezone.utc).isoformat()})
        am["history"] = am["history"][:60]
        self.memory.record({"strategy":strat,"session":sess,
                            "regime":self.regime.get("regime","?"),
                            "score":0,"rr":0,"side":"?",
                            "amd":"?","struct":"?"}, result, pnl)
        self.save()

    def update_challenge(self, pnl, pair, side, rr, am_cycle):
        c = self.challenge
        c["current_balance"] = round(c["current_balance"]+pnl, 4)
        c["today_pnl"]       = round(c.get("today_pnl",0)+pnl, 4)
        if pnl > 0:
            c["today_wins"]        = c.get("today_wins",0)+1
            c["loss_streak_today"] = 0   # reset série perdante
        else:
            c["loss_streak_today"] = c.get("loss_streak_today",0)+1
            c["today_losses"]      = c.get("today_losses",0)+1
        c["best_rr"]      = max(c.get("best_rr",0), float(rr))
        c["all_time_peak"] = max(c.get("all_time_peak",c["start_balance"]),
                                 c["current_balance"])
        c.setdefault("trades",[]).append({
            "pair":pair,"side":side,"pnl":round(pnl,4),
            "rr":rr,"am_cycle":am_cycle,
            "ts":datetime.now(timezone.utc).strftime("%H:%M")})
        self.save()

STATE = BotState()

# ══════════════════════════════════════════════════════════════════════════
#  TELEGRAM
# ══════════════════════════════════════════════════════════════════════════
def tg(chat_id, text, parse_mode="HTML"):
    """Envoie un message Telegram. Découpe automatiquement si > 4096 chars."""
    if not chat_id:
        log.debug("[TG] chat_id vide, message ignoré"); return False
    max_len = 4000
    chunks  = [text[i:i+max_len] for i in range(0, len(text), max_len)]
    ok = True
    for chunk in chunks:
        try:
            resp = http_post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json_data={"chat_id": str(chat_id), "text": chunk,
                      "parse_mode": parse_mode, "disable_web_page_preview": True},
                timeout=3)   # 3s max — ne jamais bloquer le scan
            if resp is None:
                log.warning("[TG] Telegram injoignable (réseau)")
                ok = False
                continue
            d = resp.json()
            if not d.get("ok"):
                log.warning(f"[TG] {d.get('description','?')}")
                ok = False
        except Exception as e:
            log.warning(f"[TG] {e}"); ok = False
    return ok

def tg_leader() -> str:
    """
    Retourne le chat_id du leader dans l'ordre de priorité :
    1. Variable d'env TG_LEADER_ID (la plus fiable)
    2. STATE.tg_id déjà découvert et sauvegardé
    3. Scan getUpdates (dernier recours)
    """
    # 1. Priorité absolue : variable d'environnement
    if TG_LEADER_ID:
        if not STATE.tg_id:
            STATE.tg_id = TG_LEADER_ID
            STATE.save()
        return TG_LEADER_ID

    # 2. Déjà en mémoire (sauvegardé depuis un scan précédent)
    if STATE.tg_id:
        return STATE.tg_id

    # 3. Scan getUpdates (fallback)
    try:
        resp = http_get(
            f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates",
            params={"limit": 100, "timeout": 1}, timeout=3)
        if resp is None:
            return ""
        for upd in resp.json().get("result", []):
            msg = upd.get("message") or upd.get("callback_query",{}).get("message",{})
            sender = (upd.get("message",{}).get("from",{}) or
                      upd.get("callback_query",{}).get("from",{}))
            if sender.get("username","").lower() == TG_LEADER.lower():
                cid = str(msg["chat"]["id"])
                STATE.tg_id = cid
                STATE.save()
                log.info(f"[TG] Chat ID @{TG_LEADER} trouvé: {cid}")
                return cid
    except Exception as e:
        log.debug(f"[TG] getUpdates: {e}")

    return ""   # vide → tg() ignorera le message sans planter

def dm(t):  tg(tg_leader(), t)
def grp(t): tg(TG_GROUP, t)
def vip(t): tg(TG_VIP, t)

# ══════════════════════════════════════════════════════════════════════════
#  POLLER TELEGRAM — thread de fond qui écoute les messages entrants
# ══════════════════════════════════════════════════════════════════════════
_TG_OFFSET = 0   # offset global pour getUpdates long-polling

def _tg_poller():
    """
    Thread de fond : écoute en permanence les messages entrants du bot.
    - Découvre le chat_id de @leaderOdg dès le 1er message
    - Répond aux commandes : /start /status /positions /stop
    - Ne bloque pas la boucle principale
    """
    global _TG_OFFSET
    log.debug("[TG-POLL] Démarré — en attente d'un message sur le bot")

    # Supprimer le webhook si actif (sinon getUpdates ne fonctionne pas)
    try:
        http_post(f"https://api.telegram.org/bot{TG_TOKEN}/deleteWebhook", timeout=5)
    except: pass

    # Initialiser l'offset pour ignorer les vieux messages
    try:
        resp = http_get(f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates",
                        params={"limit":1,"timeout":1}, timeout=5)
        if resp:
            updates = resp.json().get("result",[])
            if updates:
                _TG_OFFSET = updates[-1]["update_id"] + 1
    except: pass

    _tg_conflict_wait = 10  # backoff en cas de 409
    while STATE.running:
        try:
            resp = http_get(
                f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates",
                params={"offset": _TG_OFFSET, "limit": 10, "timeout": 20},
                timeout=25)
            if resp is None:
                time.sleep(5)
                continue
            # 409 = autre instance déjà active sur ce bot
            if resp.status_code == 409:
                _tg_conflict_wait = min(_tg_conflict_wait * 2, 120)
                if _tg_conflict_wait >= 120:
                    log.warning("[TG-POLL] 409 persistant — poller désactivé. Tue l'autre instance puis redémarre.")
                    break   # stoppe le thread proprement, le bot continue de trader
                log.warning(f"[TG-POLL] 409 Conflit — pause {_tg_conflict_wait}s")
                time.sleep(_tg_conflict_wait)
                continue
            _tg_conflict_wait = 10  # reset si OK
            updates = resp.json().get("result", [])

            for upd in updates:
                _TG_OFFSET = upd["update_id"] + 1
                msg    = upd.get("message", {})
                sender = msg.get("from", {})
                text   = msg.get("text", "").strip()
                cid    = str(msg.get("chat", {}).get("id", ""))
                uname  = sender.get("username","").lower()

                if not cid: continue

                # ── Découverte automatique du chat ID ─────────────────
                if not STATE.tg_id and uname == TG_LEADER.lower():
                    STATE.tg_id = cid
                    STATE.save()
                    log.debug(f"[TG-POLL] ✅ Chat ID @{TG_LEADER} capturé: {cid}")

                # ── Répondre aux commandes (uniquement depuis le leader) ─
                is_leader = (cid == STATE.tg_id or
                             cid == TG_LEADER_ID or
                             uname == TG_LEADER.lower())
                if not is_leader: continue

                # Si c'est le leader et qu'on n'avait pas son ID → save
                if not STATE.tg_id:
                    STATE.tg_id = cid; STATE.save()

                cmd = text.lower().split()[0] if text else ""

                if cmd in ("/start","start"):
                    tg(cid,
                        f"<b>🤖 AlphaBot v7 connecté !</b>\n"
                        f"Chat ID enregistré: <code>{cid}</code>\n"
                        f"Tu recevras tous les rapports ici.\n\n"
                        f"<b>Commandes disponibles:</b>\n"
                        f"/status — État du bot\n"
                        f"/positions — Positions ouvertes\n"
                        f"/stop — Arrêter le bot")

                elif cmd in ("/status","status"):
                    bal   = STATE.challenge.get("current_balance",0)
                    reg   = STATE.regime.get("regime","?")
                    sess  = get_session()
                    open_c= sum(1 for t in STATE.open_trades.values() if t["status"]=="open")
                    wins  = STATE.challenge.get("today_wins",0)
                    loss  = STATE.challenge.get("today_losses",0)
                    pnlj  = STATE.challenge.get("today_pnl",0)
                    mode  = "🟢 LIVE" if LIVE_ORDERS else "🟡 DEMO"
                    tg(cid,
                        f"<b>📊 STATUS AlphaBot v7</b>\n"
                        f"{'─'*24}\n"
                        f"💰 Solde      : <b>{bal:.4f}$</b>\n"
                        f"📈 PnL jour   : {pnlj:+.4f}$\n"
                        f"🏆 W:{wins}  ❌ L:{loss}\n"
                        f"📂 Positions  : {open_c}/{MAX_OPEN}\n"
                        f"🌍 Régime     : {reg}\n"
                        f"🕐 Session    : {sess['label']}\n"
                        f"⚙️ Mode       : {mode}")

                elif cmd in ("/positions","positions","pos"):
                    trades = [t for t in STATE.open_trades.values() if t["status"]=="open"]
                    if not trades:
                        tg(cid, "📂 Aucune position ouverte.")
                    else:
                        lines = [f"<b>📂 POSITIONS OUVERTES ({len(trades)}/{MAX_OPEN})</b>"]
                        for t in trades:
                            price = fetch_price(t["symbol"]) or t["entry"]
                            sld   = abs(t["entry"]-t["sl0"])
                            rrc   = ((price-t["entry"])/sld if t["side"]=="BUY"
                                     else (t["entry"]-price)/sld) if sld>0 else 0
                            pnl   = round(t["risk_usdt"]*rrc - t["fee_total"],4)
                            lev   = t.get("leverage",1)
                            margin= _calc_margin(t.get("notional",0), lev)
                            tags  = ("" + (" [BE]" if t.get("be_active") else "")
                                        + (" [TP1✅]" if t.get("tp1_hit") else "")
                                        + (" [🔒TRAIL]" if t.get("trail_active") else ""))
                            lines += [
                                f"{'─'*22}",
                                f"#{t['id']} {'🟢 LONG' if t['side']=='BUY' else '🔴 SHORT'} "
                                f"<b>{t['symbol']}</b>{tags}",
                                f"📍 {t['entry']:.5f} → <b>{price:.5f}</b>",
                                f"🛑 SL:{t['sl']:.5f}  ✅TP1:{t['tp1']:.5f}  🏆TP2:{t['tp2']:.5f}",
                                f"💵 PnL: <b>{'+' if pnl>=0 else ''}{pnl:.4f}$</b>  "
                                f"RR:{rrc:.2f}  Lev:{lev}x  Marge:{margin:.4f}$",
                            ]
                        tg(cid, "\n".join(lines))

                elif cmd in ("/stop","stop","arrêt","arret"):
                    tg(cid, "⏹ Arrêt du bot demandé...")
                    STATE.running = False

        except requests.exceptions.Timeout:
            pass   # normal pour long-polling
        except Exception as e:
            log.debug(f"[TG-POLL] {e}")
            time.sleep(3)

# ══════════════════════════════════════════════════════════════════════════
#  SYSTÈME DE RAPPORTS DÉTAILLÉS — PRIVÉ UNIQUEMENT (@leaderOdg)
# ══════════════════════════════════════════════════════════════════════════
def _calc_margin(notional: float, leverage: int) -> float:
    """Marge isolée utilisée = notionnel / levier"""
    return round(notional / leverage, 4) if leverage > 0 else notional

def _pnl_if_sl(trade: dict) -> float:
    """Perte nette si le SL est touché maintenant."""
    risk = trade.get("risk_usdt", 0)
    fee  = trade.get("fee_total", 0)
    return round(-risk - fee, 4)

def _pnl_if_tp(trade: dict, tp_level: str) -> float:
    """Gain net si TP1 ou TP2 est touché."""
    entry  = trade["entry"]
    sld0   = abs(entry - trade["sl0"])
    tp_p   = trade.get(tp_level, entry)
    rr     = (abs(tp_p - entry) / sld0) if sld0 > 0 else 0
    gross  = trade["risk_usdt"] * rr
    return round(gross - trade["fee_total"], 4)

def report_open(trade: dict, mgr):
    """
    Rapport complet d'ouverture de position — DM privé @leaderOdg.
    Contient : entrée, SL, TP1, TP2, lot, levier, marge isolée,
    risque en $, gain potentiel TP1/TP2, RR, solde, challenge.
    """
    t       = trade
    sym     = t["symbol"]
    side    = "🟢 LONG" if t["side"] == "BUY" else "🔴 SHORT"
    lev     = t.get("leverage", 1)
    notional= t.get("notional", 0)
    margin  = _calc_margin(notional, lev)
    sl_loss = _pnl_if_sl(t)
    tp1_gain= _pnl_if_tp(t, "tp1")
    tp2_gain= _pnl_if_tp(t, "tp2")
    bal     = STATE.challenge.get("current_balance", 0)
    phase   = mgr.get_phase(bal)
    prog    = mgr.progress_report(STATE.challenge)
    open_c  = sum(1 for x in STATE.open_trades.values() if x["status"]=="open")
    order_s = "🟢 LIVE Binance" if LIVE_ORDERS else "🟡 Simulation"
    rsl     = STATE.rejected_sls.get(str(t["id"]))
    sl_warn = f"\n⚠️ SL rejeté→surveillance manuelle {rsl['sl_price']:.5f}" if rsl else ""
    ts      = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    msg = (
        f"<b>╔══ POSITION OUVERTE #{t['id']} ══╗</b>\n"
        f"{side}  <b>{sym}</b>  |  {ts}\n"
        f"<b>{'─'*30}</b>\n"
        f"<b>📋 DÉTAILS DE L'ORDRE</b>\n"
        f"  📍 Entrée       : <b>{t['entry']:.5f}</b>\n"
        f"  🛑 Stop Loss    : <b>{t['sl']:.5f}</b>  →  Perte max: <b>{sl_loss:.4f}$</b>{sl_warn}\n"
        f"  ✅ TP1          : <b>{t['tp1']:.5f}</b>  →  Gain TP1:  <b>+{tp1_gain:.4f}$</b>\n"
        f"  🏆 TP2          : <b>{t['tp2']:.5f}</b>  →  Gain TP2:  <b>+{tp2_gain:.4f}$</b>\n"
        f"  📐 RR           : <b>1:{t.get('rr','?')}</b>\n"
        f"<b>{'─'*30}</b>\n"
        f"<b>💼 PARAMÈTRES FINANCIERS</b>\n"
        f"  📦 Lot (qty)    : <b>{t.get('qty')}</b>\n"
        f"  💱 Notionnel    : <b>{notional:.2f}$</b>\n"
        f"  ⚙️ Levier       : <b>{lev}x</b>\n"
        f"  🔒 Marge isolée : <b>{margin:.4f}$</b>\n"
        f"  💰 Risque $     : <b>{t.get('risk_usdt',0):.4f}$</b>  "
        f"({t.get('risk_usdt',0)/bal*100:.1f}% du solde)\n"
        f"  💸 Frais totaux : <b>{t.get('fee_total',0):.5f}$</b>\n"
        f"<b>{'─'*30}</b>\n"
        f"<b>💰 COMPTE</b>\n"
        f"  Solde actuel    : <b>{bal:.4f}$</b>\n"
        f"  Phase           : {phase['label']}\n"
        f"  Positions       : {open_c}/{MAX_OPEN}\n"
        f"  AM Cycle        : {t.get('am_cycle',0)}/4\n"
        f"<b>{'─'*30}</b>\n"
        f"<b>🧠 ANALYSE IA</b>\n"
        f"  Score           : <b>{t.get('score',0)}/100</b>\n"
        f"  Stratégie       : {t.get('strategy','?')}\n"
        f"  Régime          : {t.get('regime','?')}\n"
        f"  Session         : {t.get('session','?')}\n"
        f"  Mode            : {order_s}\n"
        f"<b>{'─'*30}</b>\n"
        f"<b>📊 CHALLENGE 5→500$</b>\n"
        f"{prog}\n"
        f"<b>╚══════════════════════════════╝</b>"
    )
    dm(msg)

def report_tp1(trade: dict, price: float, mgr):
    """Rapport TP1 atteint — DM privé complet."""
    t       = trade
    sym     = t["symbol"]
    side    = "LONG" if t["side"]=="BUY" else "SHORT"
    sld0    = abs(t["entry"] - t["sl0"])
    rr_c    = abs(price - t["entry"]) / sld0 if sld0 > 0 else 0
    pnl_tp1 = round(t["risk_usdt"] * rr_c - t["fee_total"] * 0.5, 4)
    tp2_gain= _pnl_if_tp(t, "tp2")
    lev     = t.get("leverage", 1)
    margin  = _calc_margin(t.get("notional",0), lev)
    bal_bef = STATE.challenge.get("current_balance", 0)
    prog    = mgr.progress_report(STATE.challenge)
    dur     = _duration(t)
    ts      = datetime.now(timezone.utc).strftime("%H:%M UTC")

    msg = (
        f"<b>╔══ ✅ TP1 ATTEINT #{t['id']} ══╗</b>\n"
        f"🟢 {side}  <b>{sym}</b>  |  {ts}\n"
        f"<b>{'─'*30}</b>\n"
        f"<b>📋 MOUVEMENT</b>\n"
        f"  📍 Entrée       : {t['entry']:.5f}\n"
        f"  🎯 TP1 touché   : <b>{price:.5f}</b>\n"
        f"  🏆 TP2 cible    : {t['tp2']:.5f}\n"
        f"  📐 RR réel      : <b>{rr_c:.2f}</b>  (cible 1:{t.get('rr','?')})\n"
        f"  ⏱ Durée         : {dur}\n"
        f"<b>{'─'*30}</b>\n"
        f"<b>💵 PNL PARTIEL (50% position)</b>\n"
        f"  Gain TP1        : <b>+{pnl_tp1:.4f}$</b>\n"
        f"  Gain potentiel TP2 : +{tp2_gain:.4f}$\n"
        f"  Frais           : -{t.get('fee_total',0):.5f}$\n"
        f"<b>{'─'*30}</b>\n"
        f"<b>💼 POSITION</b>\n"
        f"  Lot             : {t.get('qty')}\n"
        f"  Levier          : {lev}x\n"
        f"  Marge isolée    : {margin:.4f}$\n"
        f"  🛑 SL monté     : <b>{t['sl']:.5f}</b>  (risque = 0)\n"
        f"<b>{'─'*30}</b>\n"
        f"<b>💰 COMPTE</b>\n"
        f"  Solde           : <b>{bal_bef:.4f}$</b>\n"
        f"  Le trade reste ouvert → TP2: {t['tp2']:.5f}\n"
        f"<b>{'─'*30}</b>\n"
        f"<b>📊 CHALLENGE</b>\n"
        f"{prog}\n"
        f"<b>╚══════════════════════════════╝</b>"
    )
    dm(msg)

def report_trail(trade: dict, new_sl: float, rr_c: float):
    """Rapport activation/mise à jour trailing SL — DM privé."""
    sym  = trade["symbol"]
    side = "LONG" if trade["side"]=="BUY" else "SHORT"
    lev  = trade.get("leverage",1)
    ts   = datetime.now(timezone.utc).strftime("%H:%M UTC")
    bal  = STATE.challenge.get("current_balance", 0)
    tp2_gain = _pnl_if_tp(trade, "tp2")
    msg = (
        f"<b>🔒 TRAILING SL #{trade['id']} — {sym}</b>\n"
        f"{side}  |  {ts}\n"
        f"<b>{'─'*28}</b>\n"
        f"  RR actuel       : <b>{rr_c:.2f}</b>\n"
        f"  Trail SL        : <b>{new_sl:.5f}</b>\n"
        f"  TP2 cible       : {trade['tp2']:.5f}  (+{tp2_gain:.4f}$)\n"
        f"  Lot             : {trade.get('qty')}  Levier: {lev}x\n"
        f"  Marge isolée    : {_calc_margin(trade.get('notional',0), lev):.4f}$\n"
        f"  Solde compte    : {bal:.4f}$\n"
        f"<b>Capital protégé. SL suit le prix.</b>"
    )
    dm(msg)

def report_be(trade: dict, be_price: float, rr_c: float):
    """Rapport Break-Even — DM privé."""
    sym  = trade["symbol"]
    side = "LONG" if trade["side"]=="BUY" else "SHORT"
    lev  = trade.get("leverage",1)
    bal  = STATE.challenge.get("current_balance", 0)
    ts   = datetime.now(timezone.utc).strftime("%H:%M UTC")
    msg = (
        f"<b>🔒 BREAK-EVEN #{trade['id']} — {sym}</b>\n"
        f"{side}  |  {ts}\n"
        f"<b>{'─'*28}</b>\n"
        f"  RR atteint      : <b>{rr_c:.2f}</b>\n"
        f"  SL déplacé →    : <b>{be_price:.5f}</b>\n"
        f"  Entrée          : {trade['entry']:.5f}\n"
        f"  TP1             : {trade['tp1']:.5f}\n"
        f"  TP2             : {trade['tp2']:.5f}\n"
        f"  Lot             : {trade.get('qty')}  Levier: {lev}x\n"
        f"  Marge isolée    : {_calc_margin(trade.get('notional',0), lev):.4f}$\n"
        f"  Solde compte    : {bal:.4f}$\n"
        f"<b>Risque = 0. Trade gratuit.</b>"
    )
    dm(msg)

def report_close(trade: dict, exit_price: float, reason: str, mgr):
    """
    Rapport de clôture complet — DM privé @leaderOdg.
    Envoyé sur : SL touché, TP2 touché, urgence, clôture manuelle.
    """
    t       = trade
    sym     = t["symbol"]
    side_l  = "LONG" if t["side"]=="BUY" else "SHORT"
    entry   = t["entry"]
    sld0    = abs(entry - t["sl0"])
    rr_c    = ((exit_price-entry)/sld0 if t["side"]=="BUY"
               else (entry-exit_price)/sld0) if sld0 > 0 else 0
    result  = t.get("result","?")
    net     = t.get("pnl", 0)
    lev     = t.get("leverage",1)
    margin  = _calc_margin(t.get("notional",0), lev)
    bal_new = STATE.challenge.get("current_balance", 0)
    bal_bef = round(bal_new - net, 4)
    wins    = STATE.challenge.get("today_wins",0)
    losses  = STATE.challenge.get("today_losses",0)
    wr      = round(wins/(wins+losses)*100) if (wins+losses)>0 else 0
    pnlj    = STATE.challenge.get("today_pnl",0)
    prog    = mgr.progress_report(STATE.challenge)
    dur     = _duration(t)
    trail_s = " [🔒TRAIL]" if t.get("trail_active") else ""
    best    = STATE.memory.get_best_context()
    best_s  = " | ".join(x["key"].split("|")[0]+f" WR{x['wr']*100:.0f}%" for x in best[:2])

    if result == "WIN":
        emoji = "✅"; hdr = "TRADE GAGNANT"
    elif result == "BE":
        emoji = "🔒"; hdr = "BREAK-EVEN"
    else:
        emoji = "❌"; hdr = "TRADE PERDANT"

    # Reconstruction SL initial pour afficher la perte max qui était prévue
    sl_loss_initial = _pnl_if_sl(t)

    ts = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    msg = (
        f"<b>╔══ {emoji} {hdr} #{t['id']}{trail_s} ══╗</b>\n"
        f"{'🟢' if t['side']=='BUY' else '🔴'} {side_l}  <b>{sym}</b>  |  {ts}\n"
        f"Raison: <b>{reason}</b>\n"
        f"<b>{'─'*30}</b>\n"
        f"<b>📋 RÉSUMÉ DU TRADE</b>\n"
        f"  📍 Entrée         : {entry:.5f}\n"
        f"  🚪 Sortie         : <b>{exit_price:.5f}</b>\n"
        f"  🛑 SL initial     : {t['sl0']:.5f}\n"
        f"  ✅ TP1            : {t['tp1']:.5f}\n"
        f"  🏆 TP2            : {t['tp2']:.5f}\n"
        f"  📐 RR réel        : <b>{rr_c:.2f}</b>  (cible 1:{t.get('rr','?')})\n"
        f"  ⏱ Durée           : {dur}\n"
        f"  TP1 touché        : {'✅ Oui' if t.get('tp1_hit') else '❌ Non'}\n"
        f"  Trail actif       : {'✅ Oui' if t.get('trail_active') else '❌ Non'}\n"
        f"<b>{'─'*30}</b>\n"
        f"<b>💵 PNL & FINANCES</b>\n"
        f"  PnL net           : <b>{'+' if net>=0 else ''}{net:.4f}$</b>\n"
        f"  Frais payés       : -{t.get('fee_total',0):.5f}$\n"
        f"  Risque initial    : {t.get('risk_usdt',0):.4f}$\n"
        f"  Perte max prévue  : {sl_loss_initial:.4f}$\n"
        f"<b>{'─'*30}</b>\n"
        f"<b>💼 PARAMÈTRES</b>\n"
        f"  Lot (qty)         : <b>{t.get('qty')}</b>\n"
        f"  Notionnel         : {t.get('notional',0):.2f}$\n"
        f"  Levier            : <b>{lev}x</b>\n"
        f"  Marge isolée      : <b>{margin:.4f}$</b>\n"
        f"<b>{'─'*30}</b>\n"
        f"<b>💰 COMPTE</b>\n"
        f"  Solde avant       : {bal_bef:.4f}$\n"
        f"  Solde après       : <b>{bal_new:.4f}$</b>  ({'+' if net>=0 else ''}{net:.4f}$)\n"
        f"  Session           : {t.get('session','?')}\n"
        f"  Régime            : {t.get('regime','?')}\n"
        f"<b>{'─'*30}</b>\n"
        f"<b>📈 STATS JOURNÉE</b>\n"
        f"  W:{wins}  L:{losses}  WR:{wr}%  PnL/j: {pnlj:+.4f}$\n"
        f"  🧠 Contextes: {best_s or '—'}\n"
        f"<b>{'─'*30}</b>\n"
        f"<b>📊 CHALLENGE 5→500$</b>\n"
        f"{prog}\n"
        f"<b>╚══════════════════════════════╝</b>"
    )
    dm(msg)

def _duration(t: dict) -> str:
    """Durée depuis l'ouverture du trade."""
    try:
        od  = datetime.fromisoformat(t.get("open_ts",""))
        sec = int((datetime.now(timezone.utc)-od).total_seconds())
        h, m = divmod(sec // 60, 60)
        return f"{h}h{m:02d}min" if h > 0 else f"{sec//60}min"
    except: return "?"

# ══════════════════════════════════════════════════════════════════════════
#  BINANCE DATA
# ══════════════════════════════════════════════════════════════════════════
def b_get(ep, params=None, timeout=8):
    resp = http_get(f"{BINANCE_BASE}/{ep}", params=params or {}, timeout=timeout)
    if resp is None:
        return None
    try:
        return resp.json()
    except Exception as e:
        log.debug(f"[BN] {ep} JSON parse error: {e}"); return None

# ══════════════════════════════════════════════════════════════════════════
#  ORDRES RÉELS BINANCE FUTURES (signés HMAC-SHA256)
# ══════════════════════════════════════════════════════════════════════════
import hmac, urllib.parse

def _bn_sign(params: dict) -> str:
    qs = urllib.parse.urlencode(params)
    return hmac.new(BN_SECRET.encode(), qs.encode(), hashlib.sha256).hexdigest()

def b_post(ep, params: dict):
    """POST signé vers Binance Futures."""
    if not LIVE_ORDERS:
        log.debug(f"[SIM] POST {ep} {params}"); return {"orderId": -1, "_sim": True}
    try:
        params["timestamp"] = int(time.time() * 1000)
        params["signature"] = _bn_sign(params)
        resp = http_post(
            f"{BINANCE_BASE}/{ep}",
            data=params,
            headers={"X-MBX-APIKEY": BN_API_KEY},
            timeout=10,
        )
        if resp is None:
            log.warning(f"[BN] POST {ep}: pas de réponse (réseau)")
            return None
        d = resp.json()
        if "code" in d and d["code"] != 200:
            log.warning(f"[BN] {ep} erreur {d['code']}: {d.get('msg','?')}")
        return d
    except Exception as e:
        log.warning(f"[BN] POST {ep}: {e}"); return None

def b_delete(ep, params: dict):
    """DELETE signé (annulation d'ordre)."""
    if not LIVE_ORDERS:
        log.debug(f"[SIM] DELETE {ep}"); return {"status": "CANCELED"}
    try:
        params["timestamp"] = int(time.time() * 1000)
        params["signature"] = _bn_sign(params)
        resp = HTTP.delete(
            f"{BINANCE_BASE}/{ep}",
            headers={"X-MBX-APIKEY": BN_API_KEY},
            params=params, timeout=10
        )
        return resp.json()
    except Exception as e:
        log.warning(f"[BN] DELETE {ep}: {e}"); return None

def b_get_signed(ep, params: dict):
    """GET signé (interrogation d'ordre, position, solde)."""
    if not LIVE_ORDERS:
        return None
    try:
        params["timestamp"] = int(time.time() * 1000)
        params["signature"] = _bn_sign(params)
        resp = HTTP.get(
            f"{BINANCE_BASE}/{ep}",
            headers={"X-MBX-APIKEY": BN_API_KEY},
            params=params, timeout=10
        )
        return resp.json()
    except Exception as e:
        log.warning(f"[BN] GET_signed {ep}: {e}"); return None

def set_leverage_isolated(symbol: str, leverage: int):
    """Configure le levier + marge isolée avant d'ouvrir un trade."""
    b_post("marginType",  {"symbol": symbol, "marginType": "ISOLATED"})
    b_post("leverage",    {"symbol": symbol, "leverage":   leverage})

def place_market_order(symbol: str, side: str, qty, reduce_only=False) -> dict:
    """Ordre market Binance Futures. side='BUY'|'SELL'."""
    if LIVE_ORDERS and not reduce_only:
        bal = STATE.challenge.get("current_balance", 0)
        if bal < LIVE_MIN_BALANCE:
            log.warning(f"[LIVE] Ordre bloqué — solde {bal:.2f}$ < minimum {LIVE_MIN_BALANCE}$ "
                        f"(Binance Futures min notional ~100$)")
            return {"orderId": -1, "_blocked": True}
    params = {
        "symbol":     symbol,
        "side":       side,
        "type":       "MARKET",
        "quantity":   qty,
    }
    if reduce_only:
        params["reduceOnly"] = "true"
    return b_post("order", params) or {}

def place_sl_order(symbol: str, close_side: str, qty, stop_price: float,
                   trade_id=None) -> dict:
    """
    STOP_MARKET (stop-loss). close_side = 'SELL' pour LONG, 'BUY' pour SHORT.
    Si l'ordre est rejeté (trop proche, filtre, etc.), enregistre le niveau
    dans STATE.rejected_sls pour surveillance manuelle.
    """
    tick = sym_info(symbol).get("tick", 0.01)
    sp   = _round_price(stop_price, tick)
    params = {
        "symbol":           symbol,
        "side":             close_side,
        "type":             "STOP_MARKET",
        "stopPrice":        sp,
        "quantity":         qty,
        "reduceOnly":       "true",
        "timeInForce":      "GTC",
        "workingType":      "MARK_PRICE",
    }
    res = b_post("order", params) or {}
    # Détecter un rejet Binance
    err_code = res.get("code", 0)
    if err_code and err_code != 200 and trade_id is not None:
        reason = res.get("msg", "?")
        log.warning(f"[SL-REJECT] #{trade_id} {symbol} SL={sp:.5f} rejeté ({err_code}: {reason}) → surveillance manuelle")
        # Mémoriser le niveau pour fermeture manuelle
        side_trade = "BUY" if close_side == "SELL" else "SELL"
        with STATE._lock:
            STATE.rejected_sls[str(trade_id)] = {
                "symbol":     symbol,
                "sl_price":   sp,
                "side":       side_trade,   # côté du TRADE (pas de l'ordre de clôture)
                "close_side": close_side,
                "qty":        qty,
                "reason":     reason,
                "ts":         datetime.now(timezone.utc).isoformat(),
            }
        STATE.save()
        dm(f"<b>⚠️ SL REJETÉ #{trade_id} — {symbol}</b>\n"
           f"Niveau SL={sp:.5f} rejeté par Binance ({err_code}: {reason})\n"
           f"→ Surveillance manuelle activée. Fermeture forcée si prix = {sp:.5f}\n"
           f"<b>@leaderOdg</b>")
    return res

def place_tp_order(symbol: str, close_side: str, qty, tp_price: float) -> dict:
    """TAKE_PROFIT_MARKET."""
    tick = sym_info(symbol).get("tick", 0.01)
    sp   = _round_price(tp_price, tick)
    params = {
        "symbol":           symbol,
        "side":             close_side,
        "type":             "TAKE_PROFIT_MARKET",
        "stopPrice":        sp,
        "quantity":         qty,
        "reduceOnly":       "true",
        "timeInForce":      "GTC",
        "workingType":      "MARK_PRICE",
    }
    return b_post("order", params) or {}

def cancel_order(symbol: str, order_id: int):
    """Annule un ordre Binance."""
    return b_delete("order", {"symbol": symbol, "orderId": order_id})

def get_order_status(symbol: str, order_id: int) -> str:
    """Retourne le statut d'un ordre: NEW|FILLED|CANCELED|EXPIRED|REJECTED."""
    if not LIVE_ORDERS or order_id == -1:
        return "NEW"  # simulation : toujours actif
    d = b_get_signed("order", {"symbol": symbol, "orderId": order_id})
    if not d: return "UNKNOWN"
    return d.get("status", "UNKNOWN")

def _round_price(price: float, tick: float) -> float:
    if tick <= 0: return round(price, 6)
    p = max(0, round(-math.log10(tick)))
    return round(round(price / tick) * tick, p)

def emergency_close(trade: dict, reason: str):
    """
    Fermeture d'urgence au marché si les ordres SL/TP ont été rejetés
    ou annulés par Binance. Annule tous les ordres liés puis market-close.
    """
    sym   = trade["symbol"]
    qty   = trade.get("qty", 0)
    side  = trade["side"]
    close = "SELL" if side == "BUY" else "BUY"

    log.warning(f"[URGENCE] Fermeture manuelle #{trade['id']} {sym} — {reason}")

    # 1. Annuler tous les ordres liés
    for key in ("sl_order_id", "tp1_order_id", "tp2_order_id"):
        oid = trade.get(key)
        if oid and oid != -1:
            try: cancel_order(sym, oid)
            except: pass

    # 2. Fermeture market
    res = place_market_order(sym, close, qty, reduce_only=True)
    fill = float(res.get("avgPrice") or res.get("price") or trade["entry"])
    dm(
        f"<b>🆘 FERMETURE D'URGENCE #{trade['id']} — {sym}</b>\n"
        f"Raison: {reason}\n"
        f"Prix de sortie ≈ {fill:.5f}\n"
        f"Ordres annulés + position fermée au marché.\n"
        f"<b>@leaderOdg</b>"
    )
    return fill

def fetch_top_pairs(n=20):
    d = b_get("ticker/24hr")
    if not d or not isinstance(d, list):
        # Fallback élargi si API indisponible
        return ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT",
                "ADAUSDT","DOGEUSDT","AVAXUSDT","LINKUSDT","DOTUSDT",
                "MATICUSDT","LTCUSDT","NEARUSDT","ATOMUSDT","UNIUSDT",
                "AAVEUSDT","FTMUSDT","SANDUSDT","MANAUSDT","GALAUSDT",
                "APEUSDT","OPUSDT","ARBUSDT","INJUSDT","SUIUSDT",
                "SEIUSDT","TIAUSDT","JUPUSDT","WIFUSDT","BONKUSDT"]
    usdt = [t for t in d if t["symbol"].endswith("USDT") and "_" not in t["symbol"]]
    usdt.sort(key=lambda t: float(t.get("quoteVolume",0)), reverse=True)
    return [t["symbol"] for t in usdt[:n]]

def fetch_price(sym):
    """Prix temps réel avec 3 tentatives et fallback cache."""
    for attempt in range(3):
        d = b_get("ticker/price", {"symbol":sym})
        if d and "price" in d:
            return float(d["price"])
        if attempt < 2:
            time.sleep(0.5 * (attempt + 1))
    # Fallback : dernier prix connu depuis les bougies
    c = list(STATE.candles.get(sym, {}).get("5m", deque()))
    return c[-1]["close"] if c else None

def fetch_klines(sym, tf="5m", limit=60):
    d = b_get("klines", {"symbol":sym,"interval":tf,"limit":limit}, timeout=6)
    if not d or not isinstance(d, list): return None
    try:
        return [{"ts":int(k[0]),"open":float(k[1]),"high":float(k[2]),
                 "low":float(k[3]),"close":float(k[4]),"vol":float(k[5])} for k in d]
    except: return None

def fetch_funding(sym):
    d = b_get("premiumIndex", {"symbol":sym})
    return float(d["lastFundingRate"])*100 if d and "lastFundingRate" in d else None

def fetch_fear_greed() -> dict:
    """
    Fear & Greed Index (VIX Crypto) — alternative.me
    0-25: Extreme Fear | 26-45: Fear | 46-55: Neutral
    56-75: Greed | 76-100: Extreme Greed
    Cache 1h pour ne pas spammer l'API.
    """
    global FG_CACHE
    if time.time() - FG_CACHE["ts"] < FG_TTL:
        return FG_CACHE
    try:
        r = http_get("https://api.alternative.me/fng/?limit=1", timeout=8)
        if r and r.status_code == 200:
            d = r.json()["data"][0]
            val = int(d["value"])
            FG_CACHE = {"value": val, "label": d["value_classification"], "ts": time.time()}
            log.debug(f"[FG] Fear&Greed={val} ({d['value_classification']})")
            return FG_CACHE
    except Exception as e:
        log.debug(f"[FG] Indisponible: {e}")
    return FG_CACHE  # retourne le cache même expiré

def fg_risk_mult() -> float:
    """Multiplieur de risque basé sur Fear & Greed."""
    val = fetch_fear_greed()["value"]
    if val <= 25:  return 1.20   # Extreme Fear  → opportunité
    if val <= 45:  return 1.10   # Fear          → bon pour counter-trend
    if val <= 55:  return 1.00   # Neutral
    if val <= 75:  return 0.85   # Greed         → prudence
    return 0.70                  # Extreme Greed → très prudent

def fetch_imbalance(sym):
    d = b_get("depth", {"symbol":sym,"limit":20})
    if not d: return None
    try:
        bv = sum(float(x[1]) for x in d["bids"][:10])
        av = sum(float(x[1]) for x in d["asks"][:10])
        t = bv+av
        return (bv-av)/t if t > 0 else 0.0
    except: return None

def refresh_data():
    """Refresh données avec résilience totale — skip paires en erreur."""
    pairs = fetch_top_pairs(TOP_N + 10)
    STATE.top_pairs = pairs
    ok = 0; skip = 0
    for sym in pairs[:TOP_N]:
        try:
            loaded = 0
            for tf, lim in [("5m",60),("15m",40),("1h",48),("4h",50)]:
                c = fetch_klines(sym, tf, lim)
                if c:
                    STATE.candles[sym][tf] = deque(c, maxlen=lim)
                    if tf == "5m": STATE.prices[sym] = c[-1]["close"]
                    loaded += 1
                else:
                    time.sleep(0.3)  # petite pause si erreur
            if loaded >= 2: ok += 1
            else: skip += 1
        except Exception as e:
            log.debug(f"[DATA] Skip {sym}: {e}")
            skip += 1
        time.sleep(0.05)
    # Refresh régime marché
    try:
        btc4h = list(STATE.candles["BTCUSDT"].get("4h", deque()))
        btc1h = list(STATE.candles["BTCUSDT"].get("1h", deque()))
        if btc4h: STATE.regime = detect_market_regime(btc4h, btc1h)
    except Exception as e:
        log.debug(f"[DATA] Regime refresh erreur: {e}")
    # Refresh Fear & Greed en arrière-plan
    try: fetch_fear_greed()
    except: pass
    fg = FG_CACHE
    log.debug(f"[DATA] Refresh {ok}OK/{skip}skip | Regime:{STATE.regime.get('regime','?')} | F&G:{fg['value']} {fg['label']}")

# ══════════════════════════════════════════════════════════════════════════
#  SCORING ICT COMPLET + DÉCISION IA
# ══════════════════════════════════════════════════════════════════════════
STRAT_META = {
    "ICT_OB":    {"label":"ICT Order Block",          "wr":0.83,"icon":"🔷","min":72},
    "FVG_BOS":   {"label":"Fair Value Gap + BOS",     "wr":0.81,"icon":"⚡","min":74},
    "LIQ_SWEEP": {"label":"Liquidity Sweep Reversal", "wr":0.85,"icon":"🌊","min":72},
    "OB_HTF":    {"label":"OB HTF + LTF",             "wr":0.82,"icon":"👑","min":75},
    "CHoCH":     {"label":"Change of Character",      "wr":0.84,"icon":"🔄","min":74},
    "AMD_REV":   {"label":"AMD Post-Manip",           "wr":0.86,"icon":"🏦","min":76},
}

def ict_score(symbol, side, c5, c15, c1h, c4h, base, strat, regime, sess) -> dict:
    score = base; details = []; warnings = []

    # 1. Session
    score += sess["bonus"]
    if sess["in_kz"]:  details.append(f"Kill Zone {sess['label']} +15")
    if sess["avoid"]:  warnings.append(f"Session faible: {sess['label']}")

    # 2. Régime de marché
    strats_ok = regime.get("strats", [])
    if strats_ok and strat not in strats_ok:
        score -= 15; warnings.append(f"Strategie hors regime {regime['regime']} -15")
    elif strat in strats_ok:
        score += 8; details.append(f"Strategie optimale pour {regime['regime']} +8")

    # 3. AMD
    amd = detect_amd(c5)
    if amd["phase"]=="MANIP":
        if (amd["dir"]=="UP" and side=="SELL") or (amd["dir"]=="DOWN" and side=="BUY"):
            score += 18; details.append(f"Post-Manip reversal +18")
    elif amd["phase"]=="DIST":
        if (amd["dir"]=="BULL" and side=="BUY") or (amd["dir"]=="BEAR" and side=="SELL"):
            score += 10; details.append(f"Distribution alignee +10")

    # 4. Structure
    struct = detect_structure(c15 if len(c15)>=15 else c5)
    if (struct["bias"]=="BULL" and side=="BUY") or (struct["bias"]=="BEAR" and side=="SELL"):
        score += struct["bonus"]; details.append(f"{struct['label']} +{struct['bonus']}")
    elif struct["bias"] not in ("N","UNKNOWN"):
        score -= 12; warnings.append(f"Structure oppose -12")

    # 5. Liquidité sweep
    liq = detect_liq(c5); sweep = detect_sweep(c5, liq)
    if sweep["swept"]:
        if (sweep["dir"]=="LONG" and side=="BUY") or (sweep["dir"]=="SHORT" and side=="SELL"):
            score += sweep["bonus"]; details.append(sweep["label"])

    # 6. OB
    obs = detect_ob(c5, struct["bias"])
    for ob in obs:
        if ob["side"] == side:
            score += ob["bonus"]; details.append(f"{ob['label']} +{ob['bonus']}"); break

    # 7. FVG
    fvgs = detect_fvg(c5)
    for fvg in fvgs:
        if fvg["side"] == side:
            b2 = 15 if fvg["size"] > calc_atr(c5)*0.4 else 8
            score += b2; details.append(f"{fvg['label']} +{b2}"); break

    # 8. RSI
    rsi = calc_rsi(c5)
    if rsi < 28 and side=="BUY":    score += 12; details.append(f"RSI survente {rsi} +12")
    elif rsi > 72 and side=="SELL": score += 12; details.append(f"RSI surachat {rsi} +12")
    elif (rsi < 45 and side=="BUY") or (rsi > 55 and side=="SELL"):
        score += 4; details.append(f"RSI favorable {rsi} +4")
    elif (rsi > 65 and side=="BUY") or (rsi < 35 and side=="SELL"):
        score -= 8; warnings.append(f"RSI contre {rsi} -8")

    # 9. MTF
    mtf = get_mtf(symbol)
    score += mtf["score"]
    if mtf["aligned"]: details.append(f"MTF aligne {mtf['overall']} +{mtf['score']}")

    # 10. Funding
    fund = fetch_funding(symbol)
    if fund is not None:
        if fund > 0.05 and side=="SELL":   score += 8; details.append(f"Funding {fund:.4f}% +8")
        elif fund < -0.005 and side=="BUY": score += 6; details.append(f"Funding neg +6")
        elif fund > 0.12 and side=="BUY":  score -= 8; warnings.append("Funding extreme -8")

    # 10b. Fear & Greed (VIX Crypto)
    fg = fetch_fear_greed()
    fgv = fg["value"]
    if fgv <= 25:
        if side=="BUY":  score += 10; details.append(f"Extreme Fear {fgv} → reversal +10")
        else:            score += 5;  details.append(f"Extreme Fear {fgv} → SHORT confirmé +5")
    elif fgv <= 45:
        if side=="BUY":  score += 5; details.append(f"Fear {fgv} → opportunité +5")
    elif fgv >= 76:
        if side=="BUY":  score -= 10; warnings.append(f"Extreme Greed {fgv} → LONG risqué -10")
        else:            score += 8;  details.append(f"Extreme Greed {fgv} → SHORT opportunité +8")
    elif fgv >= 56:
        if side=="BUY":  score -= 5; warnings.append(f"Greed {fgv} -5")

    # 11. Carnet d'ordres
    imb = fetch_imbalance(symbol)
    if imb is not None:
        if imb > 0.20 and side=="BUY":    score += 7; details.append(f"Carnet acheteur +7")
        elif imb < -0.20 and side=="SELL": score += 7; details.append(f"Carnet vendeur +7")

    # 12. Mémoire épisodique — WR historique de ce contexte précis
    mem_wr = STATE.memory.query_wr(strat, sess["name"], regime.get("regime","?"))
    if mem_wr > 0.85: score += 8; details.append(f"Memoire: WR {mem_wr*100:.0f}% +8")
    elif mem_wr < 0.45: score -= 12; warnings.append(f"Memoire: contexte perdant {mem_wr*100:.0f}% -12")

    return {"score": min(max(score,0),100), "details": details[:8],
            "warnings": warnings, "sess": sess, "amd": amd,
            "struct": struct, "sweep": sweep, "mtf": mtf,
            "rsi": rsi, "fund": fund, "imb": imb, "mem_wr": round(mem_wr,3)}

# ══════════════════════════════════════════════════════════════════════════
#  STRATÉGIES ICT
# ══════════════════════════════════════════════════════════════════════════
def _ict_ob(c5, bias):
    if len(c5)<12: return None
    n, atr, price = len(c5), calc_atr(c5), c5[-1]["close"]
    for i in range(n-3, max(n-15,2), -1):
        c0,c1,c2 = c5[i-2],c5[i-1],c5[i]
        b=abs(c1["close"]-c1["open"]); r=c1["high"]-c1["low"]
        if r==0: continue
        st = b/r > 0.5
        bi = c2["close"]>c2["open"] and (c2["close"]-c2["open"])>b*1.1
        sei = c2["close"]<c2["open"] and (c2["open"]-c2["close"])>b*1.1
        if c1["close"]<c1["open"] and st and bi and bias!="BEAR" and c1["low"]<=price<=c1["high"]*1.004:
            sl=c1["low"]*0.998; sld=price-sl
            if sld<=0 or sld>atr*3: continue
            bos=price>max(x["high"] for x in c5[max(0,i-10):i])
            return {"strat":"ICT_OB","side":"BUY","entry":price,
                    "sl":sl,"tp1":price+sld*2.5,"tp2":price+sld*5.5,
                    "score":62+(15 if bos else 0)+(8 if bias=="BULL" else 0)}
        if c1["close"]>c1["open"] and st and sei and bias!="BULL" and c1["low"]*0.996<=price<=c1["high"]:
            sl=c1["high"]*1.002; sld=sl-price
            if sld<=0 or sld>atr*3: continue
            bos=price<min(x["low"] for x in c5[max(0,i-10):i])
            return {"strat":"ICT_OB","side":"SELL","entry":price,
                    "sl":sl,"tp1":price-sld*2.5,"tp2":price-sld*5.5,
                    "score":62+(15 if bos else 0)+(8 if bias=="BEAR" else 0)}
    return None

def _fvg_bos(c5, bias):
    if len(c5)<10: return None
    n,atr,price=len(c5),calc_atr(c5),c5[-1]["close"]
    for i in range(n-1,4,-1):
        a,b,d=c5[i-2],c5[i-1],c5[i]
        if d["low"]>a["high"] and b["close"]>b["open"] and a["high"]<=price<=d["low"]+(d["low"]-a["high"])*0.3:
            sl=min(x["low"] for x in c5[max(0,i-5):i])*0.999; sld=price-sl
            if sld<=0 or sld>atr*3: continue
            bos=b["close"]>max(x["high"] for x in c5[max(0,i-10):i])
            return {"strat":"FVG_BOS","side":"BUY","entry":price,
                    "sl":sl,"tp1":price+sld*2.5,"tp2":price+sld*5,
                    "score":65+(18 if bos else 0)+(8 if bias=="BULL" else 0)}
        if d["high"]<a["low"] and b["close"]<b["open"] and d["high"]-(a["low"]-d["high"])*0.3<=price<=a["low"]:
            sl=max(x["high"] for x in c5[max(0,i-5):i])*1.001; sld=sl-price
            if sld<=0 or sld>atr*3: continue
            bos=b["close"]<min(x["low"] for x in c5[max(0,i-10):i])
            return {"strat":"FVG_BOS","side":"SELL","entry":price,
                    "sl":sl,"tp1":price-sld*2.5,"tp2":price-sld*5,
                    "score":65+(18 if bos else 0)+(8 if bias=="BEAR" else 0)}
    return None

def _liq_sweep(c5, bias):
    if len(c5)<15: return None
    n,atr,price=len(c5),calc_atr(c5),c5[-1]["close"]
    rec=c5[n-15:n-3]
    sh=max(x["high"] for x in rec)
    if any(x["high"]>sh for x in c5[n-5:n-1]) and price<sh and bias!="BULL":
        sl=max(x["high"] for x in c5[n-5:n])*1.002; sld=sl-price
        if 0<sld<=atr*3:
            mss=price<min(x["low"] for x in c5[n-5:n-1])
            return {"strat":"LIQ_SWEEP","side":"SELL","entry":price,
                    "sl":sl,"tp1":price-sld*3,"tp2":price-sld*6,
                    "score":68+(22 if mss else 0)+(8 if bias=="BEAR" else 0)}
    sl2=min(x["low"] for x in rec)
    if any(x["low"]<sl2 for x in c5[n-5:n-1]) and price>sl2 and bias!="BEAR":
        sl=min(x["low"] for x in c5[n-5:n])*0.998; sld=price-sl
        if 0<sld<=atr*3:
            mss=price>max(x["high"] for x in c5[n-5:n-1])
            return {"strat":"LIQ_SWEEP","side":"BUY","entry":price,
                    "sl":sl,"tp1":price+sld*3,"tp2":price+sld*6,
                    "score":68+(22 if mss else 0)+(8 if bias=="BULL" else 0)}
    return None

def _ob_htf(symbol, bias):
    h1=list(STATE.candles[symbol].get("1h",deque()))
    m5=list(STATE.candles[symbol].get("5m",deque()))
    if len(h1)<5 or len(m5)<5: return None
    price,atr=m5[-1]["close"],calc_atr(m5)
    h=h1[-2]; hb=abs(h["close"]-h["open"]); hr=h["high"]-h["low"]
    hs=hb/hr>0.5 if hr>0 else False
    if h["close"]>h["open"] and hs and h["open"]*0.998<=price<=h["close"]*1.003 and bias!="BEAR":
        sl=min(x["low"] for x in h1[-3:]+m5[-5:])*0.999; sld=price-sl
        if sld<=0 or sld>atr*5: return None
        return {"strat":"OB_HTF","side":"BUY","entry":price,
                "sl":sl,"tp1":price+sld*3,"tp2":price+sld*6,
                "score":70+(16 if m5[-1]["close"]>m5[-2]["close"] else 0)+(10 if bias=="BULL" else 0)}
    if h["close"]<h["open"] and hs and h["close"]*0.997<=price<=h["open"]*1.002 and bias!="BULL":
        sl=max(x["high"] for x in h1[-3:]+m5[-5:])*1.001; sld=sl-price
        if sld<=0 or sld>atr*5: return None
        return {"strat":"OB_HTF","side":"SELL","entry":price,
                "sl":sl,"tp1":price-sld*3,"tp2":price-sld*6,
                "score":70+(16 if m5[-1]["close"]<m5[-2]["close"] else 0)+(10 if bias=="BEAR" else 0)}
    return None

def _choch(c15, bias):
    if len(c15)<20: return None
    struct=detect_structure(c15)
    if "CHoCH" not in struct["type"]: return None
    price,atr=c15[-1]["close"],calc_atr(c15)
    if struct["type"]=="CHoCH_BULL" and bias!="BEAR":
        sl=min(x["low"] for x in c15[-8:])*0.998; sld=price-sl
        if sld<=0 or sld>atr*4: return None
        return {"strat":"CHoCH","side":"BUY","entry":price,
                "sl":sl,"tp1":price+sld*2.5,"tp2":price+sld*5,
                "score":72+(10 if bias=="BULL" else 0)}
    if struct["type"]=="CHoCH_BEAR" and bias!="BULL":
        sl=max(x["high"] for x in c15[-8:])*1.002; sld=sl-price
        if sld<=0 or sld>atr*4: return None
        return {"strat":"CHoCH","side":"SELL","entry":price,
                "sl":sl,"tp1":price-sld*2.5,"tp2":price-sld*5,
                "score":72+(10 if bias=="BEAR" else 0)}
    return None

def _amd_rev(c5, bias):
    if len(c5)<20: return None
    amd=detect_amd(c5)
    if amd["phase"]!="MANIP" or amd["conf"]<0.75: return None
    price,atr=c5[-1]["close"],calc_atr(c5)
    if amd["dir"]=="UP" and bias!="BULL":
        sl=max(x["high"] for x in c5[-5:])*1.002; sld=sl-price
        if sld<=0 or sld>atr*3: return None
        return {"strat":"AMD_REV","side":"SELL","entry":price,
                "sl":sl,"tp1":price-sld*3,"tp2":price-sld*6,
                "score":70+(12 if bias=="BEAR" else 0)}
    if amd["dir"]=="DOWN" and bias!="BEAR":
        sl=min(x["low"] for x in c5[-5:])*0.998; sld=price-sl
        if sld<=0 or sld>atr*3: return None
        return {"strat":"AMD_REV","side":"BUY","entry":price,
                "sl":sl,"tp1":price+sld*3,"tp2":price+sld*6,
                "score":70+(12 if bias=="BULL" else 0)}
    return None

# ══════════════════════════════════════════════════════════════════════════
#  AGENT — SCAN & DÉCISION
# ══════════════════════════════════════════════════════════════════════════
def btc_bias() -> str:
    scores = {"BULL":0,"BEAR":0}
    for tf, w in [("5m",1),("1h",2),("4h",3)]:
        c = list(STATE.candles["BTCUSDT"].get(tf,deque()))
        if len(c)<5: continue
        cl = [x["close"] for x in c[-10:]]
        d  = (cl[-1]-cl[0])/cl[0]*100 if cl[0]>0 else 0
        if d>0.3: scores["BULL"]+=w
        elif d<-0.3: scores["BEAR"]+=w
    if scores["BULL"]>scores["BEAR"]+1: return "BULL"
    if scores["BEAR"]>scores["BULL"]+1: return "BEAR"
    return "RANGE"

def btc_corr_and_momentum(symbol: str) -> dict:
    """
    Intelligence BTC améliorée :
    - Corrélation Pearson BTC↔symbol sur 1h (20 bougies)
    - Momentum BTC 5m, 1h, 4h (force et direction)
    - Cohérence de direction pour le trade envisagé
    Retourne un dict avec corr, momentum, score_adj, block
    """
    btc_1h = list(STATE.candles["BTCUSDT"].get("1h", deque()))
    sym_1h = list(STATE.candles[symbol].get("1h",   deque()))
    btc_5m = list(STATE.candles["BTCUSDT"].get("5m", deque()))
    btc_4h = list(STATE.candles["BTCUSDT"].get("4h", deque()))

    # ── 1. Corrélation Pearson ────────────────────────────────────────
    corr = 0.0
    n_c  = min(len(btc_1h), len(sym_1h), 20)
    if n_c >= 8:
        b_ret = [(btc_1h[-n_c+i+1]["close"]-btc_1h[-n_c+i]["close"])/btc_1h[-n_c+i]["close"]
                 for i in range(n_c-1) if btc_1h[-n_c+i]["close"]>0]
        s_ret = [(sym_1h[-n_c+i+1]["close"]-sym_1h[-n_c+i]["close"])/sym_1h[-n_c+i]["close"]
                 for i in range(n_c-1) if sym_1h[-n_c+i]["close"]>0]
        n = min(len(b_ret), len(s_ret))
        if n >= 6:
            bm = sum(b_ret[:n])/n; sm = sum(s_ret[:n])/n
            num = sum((b_ret[i]-bm)*(s_ret[i]-sm) for i in range(n))
            db  = (sum((x-bm)**2 for x in b_ret[:n])**0.5)
            ds  = (sum((x-sm)**2 for x in s_ret[:n])**0.5)
            corr = num/(db*ds) if db>0 and ds>0 else 0.0

    # ── 2. Momentum BTC multi-TF ──────────────────────────────────────
    mom = {"5m":0.0, "1h":0.0, "4h":0.0}
    if len(btc_5m) >= 6:
        cl = [x["close"] for x in btc_5m[-6:]]
        mom["5m"] = (cl[-1]-cl[0])/cl[0]*100 if cl[0]>0 else 0
    if len(btc_1h) >= 6:
        cl = [x["close"] for x in btc_1h[-6:]]
        mom["1h"] = (cl[-1]-cl[0])/cl[0]*100 if cl[0]>0 else 0
    if len(btc_4h) >= 6:
        cl = [x["close"] for x in btc_4h[-6:]]
        mom["4h"] = (cl[-1]-cl[0])/cl[0]*100 if cl[0]>0 else 0

    # Direction BTC pondérée (4h pèse 3x, 1h 2x, 5m 1x)
    weighted = mom["4h"]*3 + mom["1h"]*2 + mom["5m"]*1
    btc_dir = "BULL" if weighted > 0.5 else ("BEAR" if weighted < -0.5 else "RANGE")
    btc_strength = abs(weighted)  # force brute

    return {
        "corr":       round(corr, 3),
        "mom":        mom,
        "btc_dir":    btc_dir,
        "btc_strength": round(btc_strength, 2),
        "high_corr":  abs(corr) >= BTC_CORR_THRESHOLD,
        "very_high_corr": abs(corr) >= BTC_CORR_BLOCK,
    }

def btc_filter(symbol: str, side: str, score: int) -> dict:
    """
    Filtre corrélation BTC pour un trade donné.
    Retourne {"ok": bool, "score_adj": int, "reason": str}
    """
    bc = btc_corr_and_momentum(symbol)
    trade_dir = "BULL" if side == "BUY" else "BEAR"
    against   = (bc["btc_dir"] != "RANGE") and (trade_dir != bc["btc_dir"])
    reason    = ""
    score_adj = 0

    if bc["very_high_corr"] and against and bc["btc_strength"] > 1.5:
        # Corrélation très forte + BTC contre + momentum fort → BLOQUE
        return {
            "ok": False, "score_adj": -99,
            "reason": f"BTC corr={bc['corr']:.2f} très fort CONTRE ({bc['btc_dir']}) — trade bloqué"
        }

    if bc["high_corr"] and against:
        score_adj = -18
        reason = f"BTC corr={bc['corr']:.2f} contre ({bc['btc_dir']}) -18"
    elif bc["high_corr"] and not against and bc["btc_dir"] != "RANGE":
        score_adj = +10
        reason = f"BTC corr={bc['corr']:.2f} aligné ({bc['btc_dir']}) +10"
    elif not bc["high_corr"] and against:
        score_adj = -6
        reason = f"BTC faible corr mais contre ({bc['btc_dir']}) -6"

    return {"ok": True, "score_adj": score_adj, "reason": reason, "btc": bc}

def check_exposure(balance: float, phase_name: str, new_notional: float) -> bool:
    """
    Vérifie que l'ajout d'un nouveau trade ne dépasse pas
    le plafond de notionnel total autorisé pour la phase du challenge.
    """
    mult         = MAX_NOTIONAL_MULT.get(phase_name, 5)
    max_notional = balance * mult
    open_notional = sum(
        t.get("notional", 0)
        for t in STATE.open_trades.values()
        if t["status"] == "open"
    )
    return (open_notional + new_notional) <= max_notional

def scan_symbol(symbol, bias, balance, mgr: ChallengeManager) -> list:
    # Prix en temps réel (pas depuis les bougies)
    rt_price = fetch_price(symbol)
    c5  = list(STATE.candles[symbol].get("5m",  deque()))
    # Skip si données insuffisantes (pas encore chargées)
    if len(c5) < 15:
        return []
    c15 = list(STATE.candles[symbol].get("15m", deque()))
    c1h = list(STATE.candles[symbol].get("1h",  deque()))
    c4h = list(STATE.candles[symbol].get("4h",  deque()))
    if len(c5) < 12: return []
    # Injecter le prix temps réel dans les bougies 5m si disponible
    if rt_price and c5:
        c5[-1] = {**c5[-1], "close": rt_price}
        STATE.prices[symbol] = rt_price
    regime = STATE.regime
    sess   = get_session()
    phase  = mgr.get_phase(balance)
    results = []
    for fn in [lambda: _ict_ob(c5, bias),
               lambda: _fvg_bos(c5, bias),
               lambda: _liq_sweep(c5, bias),
               lambda: _ob_htf(symbol, bias),
               lambda: _choch(c15 if len(c15)>=20 else c5, bias),
               lambda: _amd_rev(c5, bias)]:
        try:
            s = fn()
            if not s: continue
            meta = STRAT_META.get(s["strat"], STRAT_META["ICT_OB"])
            sld = abs(s["entry"]-s["sl"])
            tp1d = abs(s["tp1"]-s["entry"])
            if sld<=0 or tp1d/sld<2.3: continue  # RR min 2.3 : seulement bons rapports
            # TP doit être à au moins 1.5× ATR de distance (niveau significatif)
            try:
                atr_sym = calc_atr(list(STATE.candles[symbol].get("5m", deque())))
                if atr_sym > 0 and tp1d < atr_sym * 1.5: continue  # TP trop proche
            except: pass
            if s["score"] < meta["min"]: continue
            cd = STATE.cooldowns.get(symbol)
            if cd and datetime.now(timezone.utc) < cd: continue
            with STATE._lock:
                if any(t["symbol"]==symbol and t["status"]=="open"
                       for t in STATE.open_trades.values()): continue
            safety = mgr.check_safety(STATE.challenge)
            if not safety["ok"]: continue

            # ── Score ICT complet ────────────────────────────────────
            ict = ict_score(symbol, s["side"], c5, c15, c1h, c4h,
                            s["score"], s["strat"], regime, sess)
            final = ict["score"]
            min_sc = regime.get("min_score", 72)
            if final < min_sc: continue
            if sess["avoid"] and final < 70: continue  # seuil bas en session faible

            # ── Filtre direction/régime : alignement obligatoire ──────
            reg_name = regime.get("regime","")
            trade_side = s["side"]
            if reg_name == "TRENDING_BULL" and trade_side == "SELL":
                log.debug(f"[DIR] {symbol} SHORT bloqué — régime TRENDING_BULL (LONG only)")
                continue
            if reg_name == "TRENDING_BEAR" and trade_side == "BUY":
                log.debug(f"[DIR] {symbol} LONG bloqué — régime TRENDING_BEAR (SHORT only)")
                continue

            # ── Détection de pièges de marché ────────────────────────
            trap = detect_market_trap(c5)
            if trap["score_penalty"] > 0:
                final = max(0, final - trap["score_penalty"])
                log.debug(f"[TRAP] {symbol} pénalité -{trap['score_penalty']} "
                          f"({' | '.join(trap['reasons'])})")
            if final < min_sc: continue
            if trap["trap"]:
                log.debug(f"[TRAP] {symbol} trade bloqué: {' | '.join(trap['reasons'])}")
                continue

            # ── Filtre BTC corrélation ───────────────────────────────
            btc_f = btc_filter(symbol, s["side"], final)
            if not btc_f["ok"]:
                log.debug(f"[BTC-FILTER] {symbol} bloqué: {btc_f['reason']}")
                continue
            final = min(100, max(0, final + btc_f["score_adj"]))
            if final < min_sc: continue

            # ── Calculs financiers ───────────────────────────────────
            risk = mgr.calc_risk(balance, final, STATE.am["cycle"], regime, sess)
            lev  = mgr.get_leverage(symbol, balance, final, regime)
            lot  = calc_lot(symbol, risk, sld, s["entry"], lev)

            # ── Garde exposition totale + marge (challenge) ──────────
            if not check_exposure(balance, phase["name"], lot["notional"]):
                log.debug(f"[EXPO] {symbol} rejeté: exposition totale dépassée "
                          f"(phase {phase['name']} × {MAX_NOTIONAL_MULT.get(phase['name'],5)})")
                continue
            # ── Notionnel minimum Binance Futures : 100$ ─────────────
            # Bloqué en LIVE uniquement — simulation libre dès 5$
            if LIVE_ORDERS and lot["notional"] < 100.0:
                log.debug(f"[MIN-NOT] {symbol} rejeté: notionnel {lot['notional']:.2f}$ < 100$ (Binance min)")
                continue

            # Marge isolée : doit être < 90% du solde (garder 10% pour fees)
            margin = lot.get("margin_needed", lot["notional"] / lev)
            open_margin = sum(
                t.get("notional",0) / t.get("leverage",1)
                for t in STATE.open_trades.values() if t["status"]=="open"
            )
            if open_margin + margin > balance * 0.90:
                log.debug(f"[MARGE] {symbol} rejeté: marge insuffisante "
                          f"({open_margin + margin:.2f}$ > {balance*0.90:.2f}$ = 90% solde)")
                continue

            results.append({
                **s, "symbol":symbol, "score":final, "rr":round(tp1d/sld,1),
                "risk_usdt":risk, "leverage":lev,
                "qty":lot["qty"], "notional":lot["notional"],
                "fee_open":lot["fee_open"],"fee_close":lot["fee_close"],
                "fee_total":lot["fee_total"],"real_risk":lot["real_risk"],
                "am_cycle":STATE.am["cycle"], "meta":meta, "ict":ict,
                "btc_filter": btc_f,
                "btc_bias":bias, "regime":regime["regime"],
            })
        except Exception as e:
            log.debug(f"[SCAN] {symbol}: {e}")
    return results

def agent_scan(balance, mgr) -> list:
    bc = btc_corr_and_momentum("BTCUSDT")  # momentum global BTC
    bias = bc["btc_dir"]
    all_s = []
    for sym in STATE.top_pairs[:TOP_N]:
        all_s.extend(scan_symbol(sym, bias, balance, mgr))
    # Tri final : score ICT + alignement BTC + RR
    for s in all_s:
        bf = btc_filter(s["symbol"], s["side"], s["score"])
        btc_bonus = bf.get("delta", 0)
        # Score composite = score ICT + bonus BTC (max +15 si aligné, -20 si contre)
        s["final_score"] = s["score"] + btc_bonus
    all_s.sort(key=lambda x: (x["final_score"], x["rr"]), reverse=True)
    return all_s

# ══════════════════════════════════════════════════════════════════════════
#  GESTION TRADES & RAPPORTS TELEGRAM
# ══════════════════════════════════════════════════════════════════════════
def open_trade(setup, mgr):
    tid  = STATE.new_tid()
    sym  = setup["symbol"]
    meta = setup["meta"]
    ict  = setup["ict"]
    sess = ict["sess"]
    phase = mgr.get_phase(STATE.challenge.get("current_balance", CHALLENGE_START))
    side  = setup["side"]
    close_side = "SELL" if side == "BUY" else "BUY"
    qty   = setup["qty"]
    lev   = setup["leverage"]

    # ── 1. Placer les ordres Binance ──────────────────────────────────
    sl_oid = tp1_oid = tp2_oid = entry_oid = -1
    order_ok = True
    order_errors = []

    if LIVE_ORDERS:
        set_leverage_isolated(sym, lev)
        time.sleep(0.1)

    # Ordre d'entrée market
    entry_res = place_market_order(sym, side, qty)
    if not entry_res or entry_res.get("code"):
        order_ok = False
        order_errors.append(f"ENTRY rejeté: {entry_res.get('msg','?') if entry_res else 'timeout'}")
    else:
        entry_oid = entry_res.get("orderId", -1)
        fill = entry_res.get("avgPrice") or entry_res.get("price")
        if fill:
            setup["entry"] = float(fill)
        if not LIVE_ORDERS:
            # Simulation réaliste : slippage + spread à l'entrée (market order imparfait)
            slip_pct = SIM_SLIPPAGE + SIM_SPREAD
            if side == "BUY":
                setup["entry"] = round(setup["entry"] * (1 + slip_pct), 8)
            else:
                setup["entry"] = round(setup["entry"] * (1 - slip_pct), 8)

    sl_oid  = -1; tp1_oid = -1; tp2_oid = -1
    if order_ok or not LIVE_ORDERS:
        # SL
        sl_res = place_sl_order(sym, close_side, qty, setup["sl"], trade_id=tid)
        sl_oid = (sl_res or {}).get("orderId", -1)
        if LIVE_ORDERS and (not sl_res or sl_res.get("code")):
            order_errors.append(f"SL rejeté: {(sl_res or {}).get('msg','?')}")
            order_ok = False
        time.sleep(0.05)

        # TP1 (50% de la position)
        qty_tp1 = round_step(qty * 0.5, sym_info(sym)["step"])
        tp1_res = place_tp_order(sym, close_side, qty_tp1, setup["tp1"])
        tp1_oid = (tp1_res or {}).get("orderId", -1)
        if LIVE_ORDERS and (not tp1_res or tp1_res.get("code")):
            order_errors.append(f"TP1 rejeté: {(tp1_res or {}).get('msg','?')}")
        time.sleep(0.05)

        # TP2 (50% restant)
        qty_tp2 = round_step(qty - qty_tp1, sym_info(sym)["step"])
        tp2_res = place_tp_order(sym, close_side, qty_tp2, setup["tp2"])
        tp2_oid = (tp2_res or {}).get("orderId", -1)
        if LIVE_ORDERS and (not tp2_res or tp2_res.get("code")):
            order_errors.append(f"TP2 rejeté: {(tp2_res or {}).get('msg','?')}")

    if order_errors:
        log.warning(f"[ORDRE] #{tid} {sym} erreurs: {' | '.join(order_errors)}")

    # ── 2. Créer le trade en mémoire ──────────────────────────────────
    trade = {
        "id":tid,"symbol":sym,"side":side,
        "entry":setup["entry"],"sl":setup["sl"],"sl0":setup["sl"],
        "tp1":setup["tp1"],"tp2":setup["tp2"],
        "risk_usdt":setup["risk_usdt"],"rr":setup["rr"],
        "leverage":lev,"qty":qty,
        "qty_tp1":qty_tp1 if order_ok or not LIVE_ORDERS else qty,
        "qty_tp2":qty_tp2 if order_ok or not LIVE_ORDERS else 0,
        "notional":setup["notional"],
        "fee_open":setup["fee_open"],"fee_close":setup["fee_close"],
        "fee_total":setup["fee_total"],"real_risk":setup["real_risk"],
        "strategy":setup["strat"],"score":setup["score"],
        "am_cycle":setup["am_cycle"],"status":"open",
        "be_active":False,"tp1_hit":False,
        "session":sess["name"],"regime":setup["regime"],
        "open_ts":datetime.now(timezone.utc).isoformat(),
        # IDs des ordres Binance pour surveillance
        "entry_order_id": entry_oid,
        "sl_order_id":    sl_oid,
        "tp1_order_id":   tp1_oid,
        "tp2_order_id":   tp2_oid,
        "order_ok":       order_ok or not LIVE_ORDERS,
        "order_errors":   order_errors,
        # Suivi watchdog
        "sl_confirmed":   False,
        "last_order_check": datetime.now(timezone.utc).isoformat(),
        # Trailing SL
        "trail_active":   False,          # devient True à RR 1:1
        "trail_sl":       setup["sl"],    # niveau de trailing courant
        "trail_high":     setup["entry"], # meilleur prix atteint (pour LONG)
        "context":{
            "strategy":setup["strat"],"session":sess["name"],
            "regime":setup["regime"],"score":setup["score"],
            "rr":setup["rr"],"side":setup["side"],
            "amd":ict["amd"]["phase"],"struct":ict["struct"]["type"],
        }
    }

    with STATE._lock:
        STATE.open_trades[tid] = trade
        STATE.cooldowns[sym] = datetime.now(timezone.utc)+timedelta(minutes=COOLDOWN_MIN)

    # ── 3. Rapport privé complet → DM @leaderOdg ─────────────────────
    report_open(trade, mgr)

    _id = lambda x: 'SIM' if x == -1 else str(x)
    log.info(f"[OUVERT] #{tid} {sym} {'LONG' if side=='BUY' else 'SHORT'} "
             f"Score:{setup['score']} RR:{setup['rr']} "
             f"Qty:{qty} Risk:{setup['risk_usdt']:.2f}$ Lev:{lev}x "
             f"SL:{_id(sl_oid)} TP1:{_id(tp1_oid)} TP2:{_id(tp2_oid)}")
    STATE.save()
    return tid

# ══════════════════════════════════════════════════════════════════════════
#  WATCHDOG ORDRES + CHECK TRADES
# ══════════════════════════════════════════════════════════════════════════
def _update_sl_on_exchange(trade: dict, new_sl: float):
    """
    Annule l'ancien SL et pose un nouveau STOP_MARKET au niveau be/trailé.
    Si rejeté → stocke dans rejected_sls pour fermeture manuelle.
    """
    sym        = trade["symbol"]
    tid        = trade["id"]
    close_side = "SELL" if trade["side"]=="BUY" else "BUY"
    old_id     = trade.get("sl_order_id", -1)
    if LIVE_ORDERS and old_id and old_id != -1:
        cancel_order(sym, old_id)
        time.sleep(0.05)
    res    = place_sl_order(sym, close_side, trade["qty"], new_sl, trade_id=tid)
    new_id = (res or {}).get("orderId", -1)
    err    = (res or {}).get("code", 0)
    with STATE._lock:
        trade["sl"]          = new_sl
        trade["trail_sl"]    = new_sl
        if not err or err == 200:
            trade["sl_order_id"] = new_id
    log.debug(f"[SL-UPDATE] #{tid} {sym} SL→{new_sl:.5f} [ID:{new_id}] "
             f"{'✅' if not err or err==200 else '⚠️ rejeté→manuel'}")

def order_watchdog(mgr):
    """
    Thread de surveillance des ordres Binance.
    - Vérifie SL/TP1/TP2 actifs → détecte fills et urgences
    - Surveille les SL rejetés → ferme manuellement si prix atteint le niveau
    - Tourne toutes les ORDER_WATCH_SEC secondes
    """
    log.debug("[WATCHDOG] Démarré")
    while STATE.running:
        try:
            with STATE._lock:
                trades = [t for t in STATE.open_trades.values() if t["status"]=="open"]

            # ── Surveillance ordres actifs ───────────────────────────────
            for t in trades:
                sym = t["symbol"]

                # Vérifier SL
                sl_id = t.get("sl_order_id", -1)
                if LIVE_ORDERS and sl_id != -1:
                    sl_status = get_order_status(sym, sl_id)
                    if sl_status == "FILLED":
                        price = fetch_price(sym) or t["sl"]
                        log.info(f"[WATCHDOG] SL rempli #{t['id']} {sym}")
                        _close_trade_from_watchdog(t, mgr, price, "SL_FILLED")
                        continue
                    elif sl_status in ("REJECTED","EXPIRED","CANCELED"):
                        log.warning(f"[WATCHDOG] SL {sl_status} #{t['id']} — urgence")
                        price = emergency_close(t, f"SL {sl_status}")
                        _close_trade_from_watchdog(t, mgr, price, "SL_EMERGENCY")
                        continue

                # Vérifier TP1
                tp1_id = t.get("tp1_order_id", -1)
                if LIVE_ORDERS and tp1_id != -1 and not t.get("tp1_hit"):
                    s = get_order_status(sym, tp1_id)
                    if s == "FILLED":
                        price = fetch_price(sym) or t["tp1"]
                        log.info(f"[WATCHDOG] TP1 rempli #{t['id']}")
                        with STATE._lock: t["tp1_hit"] = True
                        _update_sl_on_exchange(t, t["tp1"])
                        report_tp1(t, price, mgr)

                # Vérifier TP2
                tp2_id = t.get("tp2_order_id", -1)
                if LIVE_ORDERS and tp2_id != -1:
                    s = get_order_status(sym, tp2_id)
                    if s == "FILLED":
                        price = fetch_price(sym) or t["tp2"]
                        log.info(f"[WATCHDOG] TP2 rempli #{t['id']}")
                        _close_trade_from_watchdog(t, mgr, price, "TP2_FILLED")
                        continue

                with STATE._lock:
                    t["last_order_check"] = datetime.now(timezone.utc).isoformat()

            # ── Surveillance SL rejetés (mode manuel) ───────────────────
            with STATE._lock:
                rejected = dict(STATE.rejected_sls)
            for tid_str, rsl in list(rejected.items()):
                tid_int = int(tid_str)
                # Vérifier que le trade est encore ouvert
                trade = STATE.open_trades.get(tid_int)
                if not trade or trade["status"] != "open":
                    with STATE._lock:
                        STATE.rejected_sls.pop(tid_str, None)
                    continue
                price = fetch_price(rsl["symbol"])
                if price is None: continue
                sl_hit = (price <= rsl["sl_price"] if rsl["side"] == "BUY"
                          else price >= rsl["sl_price"])
                if sl_hit:
                    log.warning(f"[WATCHDOG] SL manuel déclenché #{tid_int} "
                                f"{rsl['symbol']} prix={price:.5f} SL={rsl['sl_price']:.5f}")
                    exit_p = emergency_close(trade, f"SL manuel (niveau rejeté {rsl['sl_price']:.5f})")
                    _close_trade_from_watchdog(trade, mgr, exit_p or price, "SL_MANUAL")
                    with STATE._lock:
                        STATE.rejected_sls.pop(tid_str, None)

        except Exception as e:
            log.warning(f"[WATCHDOG] Erreur: {e}")
        time.sleep(ORDER_WATCH_SEC)

def _close_trade_from_watchdog(trade: dict, mgr, exit_price: float, reason: str):
    """Clôture propre d'un trade depuis le watchdog (SL/TP rempli ou urgence)."""
    if trade.get("status") != "open": return
    sid   = trade["side"]
    entry = trade["entry"]
    sld0  = abs(entry - trade["sl0"])
    rr_c  = ((exit_price-entry)/sld0 if sid=="BUY" else (entry-exit_price)/sld0) if sld0>0 else 0
    result = ("WIN"  if "TP" in reason or (trade.get("tp1_hit") and rr_c > 0)
              else ("BE" if trade.get("be_active") else "LOSS"))
    gross = trade["risk_usdt"] * (rr_c if result in ("WIN","BE") else -1)
    net   = round(gross - trade["fee_total"], 4)
    with STATE._lock:
        trade.update({"status":"closed","exit":exit_price,"pnl":net,
                      "result":result,"close_ts":datetime.now(timezone.utc).isoformat()})
    am_old = STATE.am["cycle"]
    STATE.update_am(result, net, trade["symbol"], trade.get("session","?"),
                    trade.get("strategy","?"), datetime.now(timezone.utc).hour)
    STATE.update_challenge(net, trade["symbol"], sid, trade["rr"], am_old)
    report_close(trade, exit_price, reason, mgr)
    STATE.save()

def _compute_trail_sl(trade: dict, price: float, c5: list) -> float:
    """Calcule le nouveau SL trailé basé sur ATR."""
    side  = trade["side"]
    entry = trade["entry"]
    atr   = calc_atr(c5) if len(c5) >= 5 else abs(entry - trade["sl0"]) * 1.5
    mult  = TRAIL_ATR_TIGHT if trade.get("tp1_hit") else TRAIL_ATR_MULT
    if side == "BUY":
        new_sl = price - atr * mult
        new_sl = max(new_sl, entry * 1.0001)          # jamais sous l'entrée
        new_sl = max(new_sl, trade.get("trail_sl", trade["sl0"]))  # ne descend pas
    else:
        new_sl = price + atr * mult
        new_sl = min(new_sl, entry * 0.9999)
        new_sl = min(new_sl, trade.get("trail_sl", trade["sl0"]))
    return new_sl

def check_trades(mgr):
    """
    - Prix temps réel sur chaque position
    - Trailing SL actif dès RR 1:1
    - SL rejetés : surveillance manuelle en simulation
    - TP1/TP2/SL simulation propre
    """
    with STATE._lock: trades = list(STATE.open_trades.values())
    for t in trades:
        if t["status"] != "open": continue
        sym   = t["symbol"]
        price = fetch_price(sym)
        if price is None: continue
        STATE.prices[sym] = price

        side  = t["side"]
        entry = t["entry"]
        sl    = t["sl"]
        tp1   = t["tp1"]
        tp2   = t["tp2"]
        sld0  = abs(entry - t["sl0"])
        rr_c  = ((price-entry)/sld0 if side=="BUY" else (entry-price)/sld0) if sld0>0 else 0

        # ── Tracking meilleur prix ───────────────────────────────────
        if side == "BUY":
            if price > t.get("trail_high", entry):
                with STATE._lock: t["trail_high"] = price
        else:
            if price < t.get("trail_high", entry):
                with STATE._lock: t["trail_high"] = price

        # ── Trailing SL (actif à RR ≥ 1:1) ─────────────────────────
        if rr_c >= TRAIL_ACTIVATE_RR:
            c5 = list(STATE.candles[sym].get("5m", deque()))
            new_trail = _compute_trail_sl(t, price, c5)
            trail_moved = (
                (side == "BUY"  and new_trail > t.get("trail_sl", sl) + entry * TRAIL_MIN_STEP_PCT) or
                (side == "SELL" and new_trail < t.get("trail_sl", sl) - entry * TRAIL_MIN_STEP_PCT)
            )
            if trail_moved or not t.get("trail_active"):
                first = not t.get("trail_active")
                if first:
                    with STATE._lock: t["trail_active"] = True
                if LIVE_ORDERS:
                    _update_sl_on_exchange(t, new_trail)
                else:
                    with STATE._lock:
                        t["sl"]        = new_trail
                        t["trail_sl"]  = new_trail
                        t["be_active"] = True
                report_trail(t, new_trail, rr_c)
                sl = new_trail

        # ── BE anticipé : à RR 0.65 → SL à entrée + frais ──────────
        # Philosophie : mieux vaut 0$ que -0.50$
        if rr_c >= BE_ACTIVATE_RR and not t.get("be_active"):
            fee_pct = (FEE_TAKER * 2 + SIM_SLIPPAGE + SIM_SPREAD)
            # BE = entrée + frais (on ressort avec ~0$, pas de perte)
            be = entry * (1 + fee_pct) if side == "BUY" else entry * (1 - fee_pct)
            if LIVE_ORDERS:
                _update_sl_on_exchange(t, be)
            else:
                with STATE._lock: t["sl"] = be; t["trail_sl"] = be; t["be_active"] = True
            t["be_active"] = True
            report_be(t, be, rr_c)
            log.debug(f"[BE] #{t['id']} BE anticipé à RR{rr_c:.2f} — SL={be:.6f} (frais couverts)")

        # ── TP1 : fermeture 50% + SL à TP1 (profit garanti sur reste) ──
        hit_tp1 = (price >= tp1 if side == "BUY" else price <= tp1)
        if hit_tp1 and not t.get("tp1_hit"):
            with STATE._lock:
                t["tp1_hit"] = True
                t["sl"]      = tp1   # SL déplacé à TP1 = profit garanti
                t["trail_sl"]= tp1
                # Enregistrer gain partiel (50% de la position)
                pnl_partial = round(t["risk_usdt"] * (abs(tp1-entry)/abs(entry-t["sl0"])) * 0.5
                                    - t["fee_total"] * 0.5, 4)
                t["pnl_tp1_partial"] = pnl_partial
            report_tp1(t, price, mgr)
            sl = tp1
            log.debug(f"[TP1] #{t['id']} 50% fermé +{pnl_partial:.4f}$ — reste court vers TP2")

        # ── Surveillance SL rejetés (démo + live) ────────────────────
        tid_str = str(t["id"])
        rsl = STATE.rejected_sls.get(tid_str)
        if rsl:
            rsl_hit = (price <= rsl["sl_price"] if side == "BUY"
                       else price >= rsl["sl_price"])
            if rsl_hit:
                log.warning(f"[SL-MANUEL] #{t['id']} {sym} niveau rejeté {rsl['sl_price']:.5f} atteint")
                with STATE._lock: STATE.rejected_sls.pop(tid_str, None)
                _force_close_sim(t, mgr, rsl["sl_price"], "SL_MANUEL")
                continue

        # ── SL / TP2 fermeture simulation ────────────────────────────
        if not LIVE_ORDERS:
            hit_sl  = (price <= sl  if side == "BUY" else price >= sl)
            hit_tp2 = (price >= tp2 if side == "BUY" else price <= tp2)
            if hit_tp2:
                _force_close_sim(t, mgr, tp2, "TP2")   # fermeture au prix TP2 exact
            elif hit_sl:
                _force_close_sim(t, mgr, sl, "SL")     # fermeture au prix SL exact (pas au prix courant)

def _force_close_sim(t: dict, mgr, price: float, reason: str):
    """Fermeture propre d'un trade en simulation avec tous les coûts réels."""
    if t["status"] != "open": return
    side  = t["side"]
    entry = t["entry"]
    sld0  = abs(entry - t["sl0"])
    rr_c  = ((price-entry)/sld0 if side=="BUY" else (entry-price)/sld0) if sld0>0 else 0
    is_win  = reason.startswith("TP") or (t.get("tp1_hit") and rr_c > 0)
    risk    = t["risk_usdt"]

    # ── Coûts réels simulés ───────────────────────────────────────────
    notional    = t.get("notional", 0)
    lev         = t.get("leverage", 1)
    slip_exit   = notional * SIM_SLIPPAGE
    spread_exit = notional * SIM_SPREAD
    open_ts = t.get("open_ts")
    if open_ts:
        try:
            dt = (datetime.now(timezone.utc) -
                  datetime.fromisoformat(open_ts.replace("Z","+00:00"))).total_seconds()
            funding_cost = notional / lev * SIM_FUNDING_8H * (dt / (8*3600))
        except:
            funding_cost = 0
    else:
        funding_cost = 0

    extra_costs = round(slip_exit + spread_exit + funding_cost, 6)
    total_costs = round(t["fee_total"] + extra_costs, 6)

    if is_win:
        # WIN : gain basé sur RR réel
        gross = risk * rr_c
        net   = round(gross - total_costs, 4)
    else:
        # LOSS : perte = exactement risk_usdt + frais extra (frais déjà inclus dans real_risk)
        # Le SL a été calculé pour perdre exactement risk_usdt sur le mouvement de prix
        # On ne déduit que les coûts supplémentaires (slippage/spread/funding)
        net = round(-risk - extra_costs, 4)

    log.debug(f"[SIM-COSTS] #{t['id']} {'WIN' if is_win else 'LOSS'} "
              f"risk:{risk:.4f}$ frais:{t['fee_total']:.4f}$ "
              f"slip+spread:{extra_costs:.4f}$ → net:{net:.4f}$")
    result  = ("WIN" if reason.startswith("TP") or (t.get("tp1_hit") and rr_c > 0)
               else "BE" if t.get("be_active") else "LOSS")
    with STATE._lock:
        t.update({"status":"closed","exit":price,"pnl":net,
                  "result":result,"close_ts":datetime.now(timezone.utc).isoformat()})
    am_old = STATE.am["cycle"]
    STATE.update_am(result, net, t["symbol"], t.get("session","?"),
                    t.get("strategy","?"), datetime.now(timezone.utc).hour)
    STATE.update_challenge(net, t["symbol"], side, t["rr"], am_old)
    report_close(t, price, reason, mgr)
    STATE.save()

# ══════════════════════════════════════════════════════════════════════════
#  RAPPORTS PÉRIODIQUES COMPLETS
# ══════════════════════════════════════════════════════════════════════════
def rapport_positions(mgr):
    trades = [t for t in STATE.open_trades.values() if t["status"]=="open"]
    bal = STATE.challenge.get("current_balance",0)
    if not trades: dm("📂 Aucune position ouverte."); return
    lines = [f"<b>━━━ POSITIONS OUVERTES ({len(trades)}/{MAX_OPEN}) ━━━</b>"]
    tot = 0.0
    for t in trades:
        price = fetch_price(t["symbol"]) or STATE.prices.get(t["symbol"],t["entry"])
        sld   = abs(t["entry"]-t["sl0"])
        rr_c  = ((price-t["entry"])/sld if t["side"]=="BUY" else (t["entry"]-price)/sld) if sld>0 else 0
        pnl   = round(t["risk_usdt"]*rr_c - t["fee_total"], 4)
        tot  += pnl
        tags  = ("" + (" [BE]" if t["be_active"] else "") + (" [TP1✅]" if t["tp1_hit"] else ""))
        lines += [
            f"<b>{'─'*24}</b>",
            f"#{t['id']} {'🟢 LONG' if t['side']=='BUY' else '🔴 SHORT'} <b>{t['symbol']}</b>{tags}",
            f"📍 {t['entry']:.5f} → <b>{price:.5f}</b>",
            f"🛑 {t['sl']:.5f}  ✅{t['tp1']:.5f}  🏆{t['tp2']:.5f}",
            f"💵 PnL: <b>{'+' if pnl>=0 else ''}{pnl:.4f}$</b>  RR:{rr_c:.2f}  Qty:{t.get('qty')}",
            f"📊 {t.get('strategy')}  Score:{t.get('score')}  Reg:{t.get('regime','?')}",
        ]
    lines += [
        f"<b>{'─'*24}</b>",
        f"PnL live total: <b>{'+' if tot>=0 else ''}{tot:.4f}$</b>",
        f"Solde: <b>{bal:.4f}$</b>",
        f"<b>{mgr.progress_report(STATE.challenge)}</b>",
        f"<b>@leaderOdg</b>",
    ]
    dm("\n".join(lines))

def rapport_horaire(mgr):
    c    = STATE.challenge
    bal  = c["current_balance"]
    start= c["start_balance"]
    wins = c.get("today_wins",0); loss = c.get("today_losses",0)
    tot  = wins+loss; wr = round(wins/tot*100) if tot>0 else 0
    pnl  = c.get("today_pnl",0)
    am   = STATE.am
    sess = get_session()
    reg  = STATE.regime
    open_t = [t for t in STATE.open_trades.values() if t["status"]=="open"]
    safety = mgr.check_safety(c)
    phase  = mgr.get_phase(bal)
    best   = STATE.memory.get_best_context()
    worst  = STATE.memory.get_losing_context()
    lines  = [
        f"<b>━━━ RAPPORT {datetime.now(timezone.utc).strftime('%H:%M UTC')} ━━━</b>",
        f"<b>{'─'*28}</b>",
        f"<b>Challenge:</b>",
        f"{mgr.progress_report(c)}",
        f"<b>{'─'*28}</b>",
        f"✅ W:{wins}  ❌ L:{loss}  WR:{wr}%",
        f"📈 PnL jour: <b>{'+' if pnl>=0 else ''}{pnl:.4f}$</b>",
        f"🔄 AM Cycle: {am['cycle']}/4  Streak W:{am.get('win_streak',0)} L:{am.get('loss_streak',0)}",
        f"📂 Positions: {len(open_t)}/{MAX_OPEN}",
        f"<b>{'─'*28}</b>",
        f"🌍 Régime   : <b>{reg.get('regime','?')}</b> — {reg.get('label','?')}",
        f"   ATR:{reg.get('atr_pct','?')}%  Mom:{reg.get('mom_20','?')}%  Vol:{reg.get('vol_ratio','?')}x",
        f"🕐 Session  : {sess['label']}{'  🔥' if sess['in_kz'] else ''}",
        f"🛡 Sécurité : {'✅ OK' if safety['ok'] else '🚨 '+safety.get('reason','?')}",
        f"   DD jour: {safety.get('dd_day',0):.1f}%",
        f"<b>{'─'*28}</b>",
        f"📋 Phase: {phase['name']} — {phase['label']}",
        f"   Risque max: {phase['risk_pct']*100:.0f}%  Lev max: {phase['lev_max']}x",
    ]
    if open_t:
        lines.append(f"<b>{'─'*28}</b>")
        lines.append("📂 Positions ouvertes:")
        for t in open_t:
            pr = STATE.prices.get(t["symbol"], t["entry"])
            sld = abs(t["entry"]-t["sl0"])
            rrc = ((pr-t["entry"])/sld if t["side"]=="BUY" else (t["entry"]-pr)/sld) if sld>0 else 0
            pl  = round(t["risk_usdt"]*rrc - t["fee_total"],4)
            lines.append(f"  #{t['id']} {t['symbol']} {'L' if t['side']=='BUY' else 'S'} "
                         f"PnL:{'+' if pl>=0 else ''}{pl:.4f}$ RR:{rrc:.2f}")
    if best:
        lines.append(f"<b>{'─'*28}</b>")
        lines.append("🧠 Top contextes (mémoire):")
        for b in best[:2]:
            lines.append(f"  {b['key']} → WR:{b['wr']*100:.0f}% ({b['total']}t)")
    last = c.get("trades",[])[-5:]
    if last:
        lines.append(f"<b>{'─'*28}</b>")
        lines.append("📋 Derniers trades:")
        for t in last:
            e = "✅" if t["pnl"]>=0 else "❌"
            lines.append(f"  {e} {t['pair']} {t['side']} "
                         f"{'+' if t['pnl']>=0 else ''}{t['pnl']:.4f}$ RR:{t['rr']}")
    lines.append("<b>@leaderOdg</b>")
    dm("\n".join(lines))

def rapport_journalier(mgr):
    if STATE.challenge.get("published"): return
    c    = STATE.challenge
    bal  = c["current_balance"]
    start= c["start_balance"]
    gain = bal-start; pct = gain/start*100 if start>0 else 0
    wins = c.get("today_wins",0); loss = c.get("today_losses",0)
    tot  = wins+loss; wr = round(wins/tot*100) if tot>0 else 0
    am   = STATE.am
    best = STATE.memory.get_best_context()
    worst = STATE.memory.get_losing_context()
    prog = mgr.progress_report(c)
    lines = [
        f"<b>━━━ RAPPORT JOURNALIER ━━━</b>",
        f"Agent Alpha v7  |  {datetime.now(timezone.utc).strftime('%d/%m/%Y')}",
        f"<b>{'─'*28}</b>",
        f"<b>Challenge:</b>",
        f"{prog}",
        f"<b>{'─'*28}</b>",
        f"📈 PnL jour : <b>{'+' if gain>=0 else ''}{gain:.4f}$</b> ({pct:+.1f}%)",
        f"🏔 Pic total: {c.get('all_time_peak',bal):.4f}$",
        f"✅ W:{wins}  ❌ L:{loss}  WR:{wr}%",
        f"🔄 AM Cycle: {am['cycle']}/4  Booste: {am.get('total_boosted',0):.4f}$",
        f"<b>{'─'*28}</b>",
    ]
    for t in c.get("trades",[])[-8:]:
        e = "✅" if t["pnl"]>=0 else "❌"
        lines.append(f"  {e} {t['pair']} {t['side']} "
                     f"{'+' if t['pnl']>=0 else ''}{t['pnl']:.4f}$ RR:{t['rr']} AM:{t['am_cycle']}")
    if best:
        lines += [f"<b>{'─'*28}</b>","🧠 Meilleurs contextes appris:"]
        for b in best:
            lines.append(f"  {b['key']} WR:{b['wr']*100:.0f}% ({b['total']}t)")
    if worst:
        lines += [f"<b>{'─'*28}</b>","⚠️ Contextes à éviter:"]
        for w in worst:
            lines.append(f"  {w['key']} WR:{w['wr']*100:.0f}% ({w['total']}t)")
    lines += [f"<b>{'─'*28}</b>", f"<b>@leaderOdg</b>  |  t.me/bluealpha_signals"]
    msg = "\n".join(lines)
    dm(msg); grp(msg)
    STATE.challenge["published"] = True
    STATE.save()

# ══════════════════════════════════════════════════════════════════════════
#  BOUCLE PRINCIPALE
# ══════════════════════════════════════════════════════════════════════════
def _print_pos(mgr):
    trades = [t for t in STATE.open_trades.values() if t["status"]=="open"]
    if not trades: return
    print(f"\n  [POSITIONS {len(trades)}/{MAX_OPEN}]")
    for t in trades:
        price = fetch_price(t["symbol"]) or STATE.prices.get(t["symbol"], t["entry"])
        if price: STATE.prices[t["symbol"]] = price
        sld  = abs(t["entry"] - t["sl0"])
        rrc  = ((price-t["entry"])/sld if t["side"]=="BUY" else (t["entry"]-price)/sld) if sld>0 else 0
        pnl  = round(t["risk_usdt"]*rrc - t["fee_total"], 4)
        tags = ("" + (" [BE]" if t.get("be_active") else "")
                   + (" [TP1✅]" if t.get("tp1_hit") else "")
                   + (" [🔒TRAIL]" if t.get("trail_active") else ""))
        rsl  = STATE.rejected_sls.get(str(t["id"]))
        sl_display = t["sl"]
        rsl_str = f"  ⚠️ SL rejeté→surveil {rsl['sl_price']:.5f}" if rsl else ""
        print(f"  #{t['id']} {t['symbol']} {'LONG' if t['side']=='BUY' else 'SHORT'}{tags}")
        print(f"     {t['entry']:.5f}→{price:.5f}  PnL:{'+' if pnl>=0 else ''}{pnl:.4f}$  "
              f"RR:{rrc:.2f}  Qty:{t.get('qty')}  Reg:{t.get('regime','?')}")
        print(f"     SL:{sl_display:.5f}  TP1:{t['tp1']:.5f}  TP2:{t['tp2']:.5f}{rsl_str}")

def _ping_server():
    """Serveur HTTP minimal pour satisfaire Render healthcheck sur /ping."""
    class PingHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            bal = STATE.challenge.get("current_balance", 0)
            trades = sum(1 for t in STATE.open_trades.values() if t["status"]=="open")
            self.wfile.write(f"OK bal={bal:.2f} trades={trades}".encode())
        def log_message(self, *a): pass  # silence les logs HTTP
    port = int(os.environ.get("PORT", 10000))
    srv = HTTPServer(("0.0.0.0", port), PingHandler)
    srv.serve_forever()

def run():
    mgr = ChallengeManager(STATE)
    STATE.challenge_mgr = mgr

    print("\n" + "="*66)
    print("  ALPHABOT PRO v7 — AGENT IA SUPRA-INTELLIGENT")
    print("  Cerveau adaptatif : Régime | Mémoire | Sessions | ICT/SMC")
    print("  Challenge 5$→500$ | Lots Binance exacts | Frais réels")
    mode_str = "🟢 LIVE ORDERS (Binance réel)" if LIVE_ORDERS else "🟡 SIMULATION (aucun ordre réel)"
    print(f"  Mode           : {mode_str}")
    print("="*66)
    log.debug("[v7] Init exchange info...")
    print("  ⏳ Chargement exchange info + données marché...")
    # Exchange info en arrière-plan — timeout 5s max sinon on démarre quand même
    def _bg_exch():
        try: refresh_exchange_info()
        except: pass
    t_exch = threading.Thread(target=_bg_exch, daemon=True)
    t_exch.start()
    t_exch.join(timeout=5)  # attend max 5s

    # Démarrage immédiat — les données se chargent en fond
    # Le bot commence à scanner dès que les premières paires sont disponibles
    def _bg_refresh():
        try: refresh_data()
        except Exception as e: log.warning(f"[DATA] refresh initial erreur: {e}")

    bg = threading.Thread(target=_bg_refresh, daemon=True)
    bg.start()
    # Attendre max 8s pour avoir au moins quelques paires
    for _ in range(16):
        if len(STATE.top_pairs) > 0 and len(STATE.candles) > 2:
            break
        time.sleep(0.5)
    print(f"  ✅ {len(STATE.top_pairs)} paires chargées — démarrage scan")

    c    = STATE.challenge
    bal  = c["current_balance"]
    sess = get_session()
    reg  = STATE.regime
    phase= mgr.get_phase(bal)
    safety = mgr.check_safety(c)

    print(f"\n  Solde          : {bal:.4f}$")
    print(f"  Objectif       : {c['start_balance']*100:.0f}$")
    print(f"  Phase          : {phase['name']} — {phase['label']}")
    print(f"  Régime marché  : {reg['regime']} — {reg['label']}")
    print(f"  Session        : {sess['label']}")
    print(f"  AM Cycle       : {STATE.am['cycle']}/4")
    print(f"  Sécurité       : {'✅ OK' if safety['ok'] else '🚨 '+safety.get('reason','?')}")
    print(f"  Mode ordres    : {mode_str}")

    # DM de démarrage en arrière-plan — ne bloque JAMAIS le scan
    def _dm_start():
        try:
            dm(
                f"<b>Agent Alpha v7 SUPRA-INTELLIGENT — {('LIVE' if LIVE_ORDERS else 'DEMO')}</b>\n"
                f"Mode: {mode_str}\n"
                f"Régime: {reg['regime']} | Session: {sess['label']}\n"
                f"Phase: {phase['label']}\n"
                f"{mgr.progress_report(c)}\n"
                f"Sécurité: {'✅ OK' if safety['ok'] else '🚨 '+safety.get('reason','?')}"
            )
        except: pass
    threading.Thread(target=_dm_start, daemon=True).start()

    # ── Ping server pour Render healthcheck ──────────────────────────
    ping_thread = threading.Thread(target=_ping_server, daemon=True)
    ping_thread.start()
    log.debug(f"[PING] Serveur HTTP démarré port {os.environ.get('PORT',10000)}")

    # ── Démarrer le poller Telegram ───────────────────────────────────
    tg_thread = threading.Thread(target=_tg_poller, daemon=True)
    tg_thread.start()

    # ── Vérifier si on a déjà le chat ID ─────────────────────────────
    if TG_LEADER_ID or STATE.tg_id:
        log.debug(f"[TG] Chat ID connu: {TG_LEADER_ID or STATE.tg_id} → DM activés")
    else:
        print("\n" + "🔔"*33)
        print("  ACTION REQUISE — CONNEXION TELEGRAM")
        print("  ─────────────────────────────────────────────────")
        print(f"  1. Ouvre Telegram et cherche ce bot par son token")
        print(f"  2. Envoie /start au bot")
        print(f"  3. Le bot capturera ton Chat ID automatiquement")
        print(f"  OU : export TG_LEADER_ID='ton_id'  (depuis @userinfobot)")
        print("🔔"*33 + "\n")
        log.warning("[TG] Chat ID inconnu — envoie /start au bot sur Telegram")

    # ── Démarrer le watchdog en thread de fond ────────────────────────
    wd_thread = threading.Thread(target=order_watchdog, args=(mgr,), daemon=True)
    wd_thread.start()
    log.debug(f"[v7] Watchdog ordres démarré (intervalle: {ORDER_WATCH_SEC}s)")

    scan_n = 0; data_ref = 0; last_h = datetime.now(timezone.utc).hour

    while STATE.running:
        now  = datetime.now(timezone.utc)
        hour = now.hour

        if data_ref % 10 == 0:
            threading.Thread(target=refresh_data, daemon=True).start()
        data_ref += 1

        check_trades(mgr)

        if hour == 21 and not STATE.challenge.get("published"):
            rapport_journalier(mgr)
        if hour != last_h:
            rapport_horaire(mgr); last_h = hour

        scan_n += 1
        bal    = STATE.challenge.get("current_balance", CHALLENGE_START)
        open_c = sum(1 for t in STATE.open_trades.values() if t["status"]=="open")
        sess   = get_session()
        bc     = btc_corr_and_momentum("BTCUSDT")
        bias   = bc["btc_dir"]
        reg    = STATE.regime
        pnlj   = STATE.challenge.get("today_pnl",0)
        wins   = STATE.challenge.get("today_wins",0)
        loss   = STATE.challenge.get("today_losses",0)
        safety = mgr.check_safety(STATE.challenge)
        phase  = mgr.get_phase(bal)

        secu_tag = "✅" if safety["ok"] else f"🚨 {safety.get('reason','?')}"
        kz_tag   = "🔥KZ" if sess["in_kz"] else sess["name"]
        mode_tag = "LIVE🟢" if LIVE_ORDERS else "SIM🟡"
        print(f"[#{scan_n}] {now.strftime('%H:%M')} | {bal:.2f}$ W{wins}/L{loss} {pnlj:+.2f}$ "
              f"| {reg['regime']} {kz_tag} | {secu_tag} {mode_tag}")

        if not safety["ok"]:
            print(f"\n  🚨 TRADING SUSPENDU — {safety.get('reason','?')}")
            time.sleep(SCAN_INTERVAL); continue
        if open_c >= MAX_OPEN:
            print(f"\n  Max positions ({MAX_OPEN}) — attente..."); time.sleep(SCAN_INTERVAL); continue
        if sess["avoid"]:
            print(f"\n  Session évitée: {sess['label']}")

        setups = agent_scan(bal, mgr)

        n_pairs = len([s for s in STATE.top_pairs[:TOP_N]
                       if len(list(STATE.candles[s].get("5m",deque()))) >= 15])
        if not setups:
            print(f"  → Aucun setup ({reg['regime']} | seuil {reg.get('min_score',72)}/100 | {n_pairs}/{TOP_N} paires prêtes)")
        else:
            best = setups[0]
            d    = "LONG" if best["side"]=="BUY" else "SHORT"
            print(f"  🎯 SETUP: {best['symbol']} {d} Score:{best['score']}/100 "
                  f"RR:1:{best['rr']} Lev:{best['leverage']}x")
            open_trade(best, mgr)
            mode_tag = "LIVE🟢" if LIVE_ORDERS else "SIM🟡"
            print(f"  ✅ Trade #{STATE.trade_ctr} ouvert [{mode_tag}]")
            if scan_n % 10 == 0 or best["score"] >= 87:
                rapport_positions(mgr)

        print(f"  ⏱ +{SCAN_INTERVAL}s...")
        time.sleep(SCAN_INTERVAL)

# ══════════════════════════════════════════════════════════════════════════
#  POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    MODE = "demo"
    if len(sys.argv) > 1:
        a = sys.argv[1].lstrip("-").lower()
        if a in ("demo","reset"): MODE = a
    if MODE == "reset":
        for f in ("am_v7.json", CHALLENGE_FILE, "memory_v7.json", "state_v7.json", "alphabot_v7.log"):
            try: os.remove(f); print(f"Supprimé: {f}")
            except: pass
        print("Reset OK."); sys.exit(0)
    else:
        try:
            run()
        except KeyboardInterrupt:
            log.info("[v7] Arrêt")
            mgr = ChallengeManager(STATE)
            rapport_journalier(mgr)
