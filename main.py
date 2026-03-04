6 # ╔══════════════════════════════════════════════════════════════╗
# ║   ALPHABOT — STYLE UCHE Trade&Gagne                         ║
# ║   Signaux M1 ICT + Témoignages + Services + Urgence VIP     ║
# ║   pip install requests yfinance pyTelegramBotAPI schedule    ║
# ╚══════════════════════════════════════════════════════════════╝

import requests, time, io, schedule, threading, random
from datetime import datetime, timezone
import yfinance as yf

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_OK = True
except ImportError:
    PIL_OK = False

# ══════════════════════════════════════════════════════════════
#  CONFIG — CHANGE UNIQUEMENT ICI
# ══════════════════════════════════════════════════════════════

TELEGRAM_TOKEN   = "6950706659:AAGXw-27ebhWLm2HfG7lzC7EckpwCPS_JFg"
GROUP_PUBLIC     = "-1003757467015"
GROUP_VIP        = "-1003771736496"
ADMIN_USERNAME   = "@leaderOdg"
ADMIN_BOT        = "@leaderOdg"
XM_LINK          = "https://www.xmglobal.com/referral?token=bI3vuZ9O9H9s-XivlQS3RA"
BINANCE_LINK     = "https://www.binance.com/fr/activity/referral-entry/CPA?ref=CPA_00M8ZVBF2G"

CANAL_NAME       = "Forex Alpha Vip"
VIP_MENSUEL      = 10
VIP_TRIMESTRIEL  = 25
VIP_ANNUEL       = 80

SCAN_EVERY       = 120    # secondes entre chaque scan
COOLDOWN_MIN     = 60     # minutes cooldown par paire (1 heure)
MIN_RR           = 3.0
MIN_SCORE        = 85

PAIRS = {
    "EURUSD=X": {"label": "EUR/USD",  "vol_pct": 0.0020, "flag": "EU"},
    "GBPUSD=X": {"label": "GBP/USD",  "vol_pct": 0.0025, "flag": "GB"},
    "USDJPY=X": {"label": "USD/JPY",  "vol_pct": 0.0030, "flag": "JP"},
    "GBPJPY=X": {"label": "GBP/JPY",  "vol_pct": 0.0035, "flag": "GJ"},
    "XAUUSD=X": {"label": "XAU/USD",  "vol_pct": 0.0040, "flag": "AU"},
    "AUDUSD=X": {"label": "AUD/USD",  "vol_pct": 0.0022, "flag": "AD"},
    "CADJPY=X": {"label": "CAD/JPY",  "vol_pct": 0.0032, "flag": "CJ"},
}

# ══════════════════════════════════════════════════════════════
#  ETAT — COMPTEURS HORAIRES
# ══════════════════════════════════════════════════════════════

cooldowns  = {}
daily_wins = []
BASE_URL   = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Compteurs par heure (reset automatique chaque nouvelle heure)
_current_hour       = -1
_signals_this_hour  = 0   # max 1 signal par heure
_messages_this_hour = 0   # max 3 messages par heure (signal+motiv+actu)
MAX_SIGNALS_HOUR    = 1
MAX_MESSAGES_HOUR   = 3

def _check_hour_reset():
    """Remet les compteurs a zero a chaque nouvelle heure."""
    global _current_hour, _signals_this_hour, _messages_this_hour
    h = datetime.now(timezone.utc).hour
    if h != _current_hour:
        _current_hour       = h
        _signals_this_hour  = 0
        _messages_this_hour = 0
        print(f"[HOUR] Nouvelle heure {h}h UTC — compteurs remis a zero")

def can_send_signal():
    _check_hour_reset()
    if _signals_this_hour  >= MAX_SIGNALS_HOUR:  return False, "max signal heure atteint"
    if _messages_this_hour >= MAX_MESSAGES_HOUR: return False, "max messages heure atteint"
    return True, "ok"

def can_send_message():
    _check_hour_reset()
    if _messages_this_hour >= MAX_MESSAGES_HOUR: return False
    return True

def register_signal():
    global _signals_this_hour, _messages_this_hour
    _signals_this_hour  += 1
    _messages_this_hour += 1

def register_message():
    global _messages_this_hour
    _messages_this_hour += 1

# ══════════════════════════════════════════════════════════════
#  TELEGRAM
# ══════════════════════════════════════════════════════════════

def tg_text(chat_id, text):
    try:
        requests.post(f"{BASE_URL}/sendMessage",
            json={"chat_id": chat_id, "text": text,
                  "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10)
    except Exception as e:
        print(f"[TG] {e}")

def tg_photo(chat_id, buf, caption):
    try:
        buf.seek(0)
        requests.post(f"{BASE_URL}/sendPhoto",
            data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
            files={"photo": ("img.png", buf, "image/png")},
            timeout=20)
    except Exception as e:
        print(f"[TG photo] {e}")

# ══════════════════════════════════════════════════════════════
#  IMAGES PIL
# ══════════════════════════════════════════════════════════════

PB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
PR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def f(path, size):
    try:    return ImageFont.truetype(path, size)
    except: return ImageFont.load_default()

def make_signal_img(label, side, entry, sl, tp1, tp2, rr, score, session, heure):
    if not PIL_OK: return None
    try:
        W, H   = 900, 500
        accent = "#00c896" if side == "LONG" else "#ff4757"
        img    = Image.new("RGB", (W, H), "#07070f")
        draw   = ImageDraw.Draw(img)
        for i in range(H):
            v = 7 + i // 55
            draw.line([(0,i),(W,i)], fill=(v,v,v+14))
        draw.rectangle([0,0,6,H], fill=accent)
        draw.rectangle([0,0,W,4], fill=accent)
        draw.text((20,12), f"{CANAL_NAME.upper()}  -  {session.upper()} SESSION",
                  font=f(PR,12), fill="#223344")
        draw.text((20,52), label, font=f(PB,52), fill="white")
        dir_txt = "EN HAUT" if side == "LONG" else "EN BAS"
        draw.text((22,116), dir_txt, font=f(PB,22), fill=accent)
        draw.text((W-20,116), f"Heure : {heure}", font=f(PB,18), fill="#445566", anchor="rm")
        draw.rectangle([20,152,W-20,154], fill="#1a2a3a")

        def fp(v):
            if v >= 100: return f"{v:.3f}"
            if v >= 1:   return f"{v:.5f}"
            return f"{v:.6f}"

        cols = [("ENTREE",fp(entry),"#ffffff"),("STOP",fp(sl),"#ff4757"),
                ("TP 1",fp(tp1),"#00c896"),("TP 2",fp(tp2),"#00aaff")]
        cw = (W-40)//4
        for i,(lbl,val,col) in enumerate(cols):
            x=20+i*cw; mid=x+cw//2
            draw.text((mid,165), lbl, font=f(PR,11), fill="#445566", anchor="mm")
            draw.text((mid,188), val, font=f(PB,18), fill=col,       anchor="mm")
            if i<3: draw.line([(x+cw,155),(x+cw,205)], fill="#1a2a3a", width=1)
        draw.rectangle([20,208,W-20,210], fill="#1a2a3a")
        draw.text((20,222),  f"R:R  1:{rr}", font=f(PB,22), fill=accent)
        draw.text((W-20,222),f"Score ICT : {score}%", font=f(PB,18), fill="#445566", anchor="rm")
        analyse = ("Breaker Block confirme apres sweep de liquidite.\n"
                   f"Retour sur zone valide - setup {'haussier' if side=='LONG' else 'baissier'}.")
        draw.text((20,252), analyse, font=f(PR,13), fill="#334455")
        draw.rectangle([0,H-38,W,H-36], fill="#111122")
        draw.rectangle([0,H-35,W,H],    fill="#080810")
        draw.text((W//2,H-17),
            f"Not financial advice  -  Risk 1% max  -  {CANAL_NAME}  -  {ADMIN_USERNAME}",
            font=f(PR,11), fill="#1a2030", anchor="mm")
        hd=img.resize((W*2,H*2),Image.LANCZOS)
        buf=io.BytesIO(); hd.save(buf,"PNG",optimize=True); buf.seek(0)
        return buf
    except Exception as e:
        print(f"[IMG signal] {e}"); return None


def make_results_img(wins):
    if not PIL_OK or not wins: return None
    try:
        rows=wins[:7]; W=860; H=110+len(rows)*54+60
        img=Image.new("RGB",(W,H),"#07070f"); draw=ImageDraw.Draw(img)
        for i in range(H):
            v=7+i*15//H; draw.line([(0,i),(W,i)],fill=(v,v,v+18))
        draw.rectangle([0,0,W,72], fill="#0d1117")
        draw.text((W//2,20),"RESULTATS DU JOUR",font=f(PB,26),fill="#ffd700",anchor="mm")
        draw.text((W//2,50),f"{CANAL_NAME}  -  {ADMIN_USERNAME}",font=f(PR,13),fill="#445566",anchor="mm")
        medals=["1","2","3"]+["ok"]*10
        for i,w in enumerate(rows):
            y=80+i*54
            draw.rectangle([0,y,W,y+52],fill="#0f1520" if i%2==0 else "#0a0e18")
            d="EN HAUT" if w.get("direction")=="LONG" else "EN BAS"
            col="#00c896" if w.get("direction")=="LONG" else "#ff4757"
            draw.text((18, y+16),f"#{i+1}",     font=f(PB,16),fill="#ffd700")
            draw.text((65, y+16),w.get("pair",""),font=f(PB,16),fill="white")
            draw.text((280,y+16),d,             font=f(PR,14),fill=col)
            draw.text((W-20,y+16),f"+{w.get('gain',0):.2f} $",font=f(PB,16),fill="#00c896",anchor="rm")
        draw.rectangle([0,H-40,W,H],fill="#050508")
        draw.text((W//2,H-20),"Discipline + Strategie + Gestion du risque = Gains reguliers",
                  font=f(PR,13),fill="#1a2030",anchor="mm")
        hd=img.resize((W*2,H*2),Image.LANCZOS)
        buf=io.BytesIO(); hd.save(buf,"PNG",optimize=True); buf.seek(0)
        return buf
    except Exception as e:
        print(f"[IMG results] {e}"); return None


def make_motivation_img(titre, corps):
    if not PIL_OK: return None
    try:
        W,H=860,420; img=Image.new("RGB",(W,H),"#08060e"); draw=ImageDraw.Draw(img)
        for i in range(H):
            r=int(15+i*30//H); g=int(10+i*10//H)
            draw.line([(0,i),(W,i)],fill=(r,g,20))
        draw.rectangle([0,0,6,H],fill="#ffd700")
        draw.rectangle([0,0,W,4],fill="#ffd700")
        draw.text((W//2,35),titre,font=f(PB,24),fill="#ffd700",anchor="mm")
        draw.rectangle([60,58,W-60,60],fill="#2a1a00")
        words=corps.split(); lines=[]; line=""
        for w in words:
            test=(line+" "+w).strip()
            bb=draw.textbbox((0,0),test,font=f(PR,15))
            if bb[2]>W-80: lines.append(line); line=w
            else: line=test
        if line: lines.append(line)
        y=78
        for l in lines:
            draw.text((W//2,y),l,font=f(PR,15),fill="white",anchor="mm"); y+=32
        draw.text((W//2,H-28),f"{CANAL_NAME}  -  {ADMIN_USERNAME}",
                  font=f(PR,11),fill="#2a1a00",anchor="mm")
        hd=img.resize((W*2,H*2),Image.LANCZOS)
        buf=io.BytesIO(); hd.save(buf,"PNG",optimize=True); buf.seek(0)
        return buf
    except Exception as e:
        print(f"[IMG motiv] {e}"); return None

# ══════════════════════════════════════════════════════════════
#  DONNEES M1 + DETECTION ICT BREAKER BLOCK
# ══════════════════════════════════════════════════════════════

def get_candles(symbol, n=120):
    try:
        df=yf.Ticker(symbol).history(period="1d",interval="1m")
        if df.empty or len(df)<30: return []
        df=df.tail(n)
        return [{"open":float(r["Open"]),"high":float(r["High"]),
                 "low":float(r["Low"]),"close":float(r["Close"])}
                for _,r in df.iterrows()]
    except Exception as e:
        print(f"[DATA] {symbol}: {e}"); return []

def detect_breaker(candles, vol_pct):
    if len(candles)<25: return None
    highs=[c["high"] for c in candles]
    lows =[c["low"]  for c in candles]
    closes=[c["close"] for c in candles]
    atr=sum(highs[k]-lows[k] for k in range(-14,0))/14
    if atr<=0: return None
    price=closes[-1]
    # SHORT
    for i in range(5,len(candles)-6):
        if highs[i]!=max(highs[i-2:i+3]): continue
        swing=highs[i]
        swept=next((j for j in range(i+1,min(i+15,len(candles)-3))
                    if highs[j]>swing*1.0001),None)
        if swept is None or closes[-1]>=swing: continue
        bb_h,bb_l=swing,lows[i]
        if not(bb_l*0.9996<=price<=bb_h*1.0004): continue
        score=60
        if(bb_h-bb_l)<atr*1.5:        score+=15
        if closes[-1]<closes[-2]:      score+=10
        if highs[-1]<highs[-2]:        score+=10
        if highs[swept]-swing>atr*0.3: score+=5
        if score<MIN_SCORE: continue
        entry=price; sl=bb_h*(1+vol_pct*0.5); risk=sl-entry
        if risk<=0 or risk>atr*4: continue
        tp1=entry-risk*3.0; tp2=entry-risk*5.5
        rr=round((entry-tp1)/risk,1)
        if rr<MIN_RR: continue
        return {"side":"SHORT","entry":entry,"sl":sl,"tp1":tp1,"tp2":tp2,
                "rr":rr,"score":score,"bb_high":bb_h,"bb_low":bb_l}
    # LONG
    for i in range(5,len(candles)-6):
        if lows[i]!=min(lows[i-2:i+3]): continue
        swing=lows[i]
        swept=next((j for j in range(i+1,min(i+15,len(candles)-3))
                    if lows[j]<swing*0.9999),None)
        if swept is None or closes[-1]<=swing: continue
        bb_l,bb_h=swing,highs[i]
        if not(bb_l*0.9996<=price<=bb_h*1.0004): continue
        score=60
        if(bb_h-bb_l)<atr*1.5:         score+=15
        if closes[-1]>closes[-2]:       score+=10
        if lows[-1]>lows[-2]:           score+=10
        if swing-lows[swept]>atr*0.3:   score+=5
        if score<MIN_SCORE: continue
        entry=price; sl=bb_l*(1-vol_pct*0.5); risk=entry-sl
        if risk<=0 or risk>atr*4: continue
        tp1=entry+risk*3.0; tp2=entry+risk*5.5
        rr=round((tp1-entry)/risk,1)
        if rr<MIN_RR: continue
        return {"side":"LONG","entry":entry,"sl":sl,"tp1":tp1,"tp2":tp2,
                "rr":rr,"score":score,"bb_high":bb_h,"bb_low":bb_l}
    return None

# ══════════════════════════════════════════════════════════════
#  SESSION
# ══════════════════════════════════════════════════════════════

def get_session():
    h=datetime.now(timezone.utc).hour
    if 7<=h<16 and 12<=h<21: return "london+ny"
    if 7<=h<16:  return "london"
    if 12<=h<21: return "new_york"
    return None

# ══════════════════════════════════════════════════════════════
#  ENVOI SIGNAL — FORMAT UCHE EXACT
# ══════════════════════════════════════════════════════════════

def send_signal(label, side, entry, sl, tp1, tp2, rr, score, session):
    def fp(v):
        if v>=100: return f"{v:.3f}"
        if v>=1:   return f"{v:.5f}"
        return f"{v:.6f}"
    heure=datetime.now(timezone.utc).strftime("%H:%M")
    dir_em="(En haut)" if side=="LONG" else "(En bas)"

    analyses_long=[
        "Le prix a forme une base solide et commence a montrer des signes clairs de hausse. La cassure au-dessus du Breaker Block confirme une forte pression acheteuse — le moment ideal pour entrer En haut.",
        "Structure haussiere confirmee sur M1. Le sweep de liquidite a ete absorbe — retour sur zone propre, momentum positif. Setup ICT valide.",
        "BOS haussier valide apres sweep des lows. Zone Breaker propre. Les acheteurs reprennent le controle — entree En haut.",
    ]
    analyses_short=[
        "Le prix a forme un sommet clair et montre des signes de rejet. La cassure en-dessous du Breaker Block confirme une pression vendeuse forte — le moment ideal pour entrer En bas.",
        "Structure baissiere confirmee sur M1. Le sweep des highs absorbe — retour sur zone, momentum negatif. Setup ICT valide.",
        "BOS baissier valide apres sweep des highs. Zone Breaker propre. Les vendeurs reprennent le controle — entree En bas.",
    ]
    analyse=random.choice(analyses_long if side=="LONG" else analyses_short)

    # ── PUBLIC — format EXACT style UCHE ──────────────────────
    pub=(
        f"(UTC +1)\n"
        f"Paire de devises : <b>{label}</b>\n"
        f"Expiration : Session {session.upper()} [M1]\n\n"
        f"<b>Heure d'entree : {heure}</b>\n\n"
        f"<i>Direction : <b>{dir_em}</b></i>\n\n"
        f"<i>{analyse}</i>\n\n"
        f"Pour les niveaux complets (SL, TP1, TP2) -> {ADMIN_BOT}"
    )

    # ── VIP — avec tous les niveaux ───────────────────────────
    vip=(
        f"[VIP] <b>{label}  {dir_em}</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"Entree : <b>{fp(entry)}</b>\n"
        f"Stop    : {fp(sl)}\n"
        f"TP1    : <b>{fp(tp1)}</b>\n"
        f"TP2    : <b>{fp(tp2)}</b>\n"
        f"R:R    : <b>1:{rr}</b>  |  Score : {score}%\n"
        f"Session : {session.upper()}  |  {heure} UTC\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"<i>{analyse}</i>\n\n"
        f"Move SL to BE apres TP1. Risk 1% max.\n"
        f"On est ensemble.\n\n"
        f"XM -> {XM_LINK}"
    )

    img=make_signal_img(label,side,entry,sl,tp1,tp2,rr,score,session,heure)
    if img:
        tg_photo(GROUP_PUBLIC,img,pub); img.seek(0); tg_photo(GROUP_VIP,img,vip)
    else:
        tg_text(GROUP_PUBLIC,pub); tg_text(GROUP_VIP,vip)

    gain_est=abs(tp1-entry)*10000*2.5
    daily_wins.append({"pair":label,"direction":side,"gain":round(gain_est,2)})
    register_signal()  # compteur horaire
    print(f"[SENT] {label} {side} {heure} | RR 1:{rr} | Score {score}%")

# ══════════════════════════════════════════════════════════════
#  POSTS MARKETING — STYLE UCHE EXACT (3 formats)
# ══════════════════════════════════════════════════════════════

# --- Témoignages clients ---
TEMOIGNAGES=[
    {"prenom":"Ibrahim",  "gain":"6 000",  "capital":"3 500"},
    {"prenom":"Kofi",     "gain":"4 500",  "capital":"2 000"},
    {"prenom":"Moussa",   "gain":"8 200",  "capital":"5 000"},
    {"prenom":"Aminata",  "gain":"3 800",  "capital":"1 500"},
    {"prenom":"Seydou",   "gain":"5 500",  "capital":"2 800"},
    {"prenom":"Fatou",    "gain":"7 000",  "capital":"4 000"},
    {"prenom":"Bamba",    "gain":"11 000", "capital":"6 000"},
    {"prenom":"Diallo",   "gain":"2 900",  "capital":"1 200"},
]

def post_temoignage():
    """FORMAT 1 — UCHE : 'PLUS DE 5 000$ DE PROFIT'"""
    t=random.choice(TEMOIGNAGES)
    msg=(
        f"<b>PLUS DE {t['gain']}$ DE PROFIT</b>\n\n"
        f"Quand la discipline rencontre la strategie, les resultats suivent\n\n"
        f"<i>{t['prenom']} a simplement respecte les regles :\n"
        f"gestion du risque   patience\n"
        f"et execution propre</i>\n\n"
        f"<b><u>Resultat ? Plus de {t['gain']}$ sur le balance</u></b>\n\n"
        f"Ce n'est pas la chance.\n"
        f"C'est la constance et une methode claire.\n\n"
        f"<i>Acces au Premium Channel</i>\n"
        f"<b>{ADMIN_BOT}</b>"
    )
    if not can_send_message():
        print("[TEMOIGNAGE] Skip — max messages heure atteint"); return
    tg_text(GROUP_PUBLIC,msg)
    register_message()
    print(f"[TEMOIGNAGE] {t['prenom']} +{t['gain']}$")


def post_comment_gagner():
    """FORMAT 2 — UCHE : 'COMMENT COMMENCER A GAGNER AVEC NOUS'"""
    msg=(
        f"<b>COMMENT COMMENCER A GAGNER AVEC NOUS</b>\n\n"
        f"Si tu debutes, voici les options principales pour avancer rapidement\n\n"
        f"<b>SESSIONS VIP</b>\n"
        f"<i>2 sessions par jour — signaux ICT M1 en temps reel\n"
        f"Entry precis - SL - TP1 + TP2 - R:R minimum 1:{MIN_RR}</i>\n\n"
        f"<b>BOT SIGNAL AUTOMATIQUE</b>\n"
        f"<i>Scan 24h/24 sur toutes les paires forex et or\n"
        f"Tu recois le signal direct sur Telegram des qu'un setup est detecte</i>\n\n"
        f"<b>FORMATION TRADING ICT</b>\n"
        f"<i>Strategies avancees et connaissances concretes du marche\n"
        f"Pour comprendre et agir avec confiance</i>\n\n"
        f"<b>COACHING INDIVIDUEL</b>\n"
        f"<i>Accompagnement personnalise en 1-on-1\n"
        f"On analyse tes trades ensemble</i>\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"Acces VIP :\n"
        f"Mensuel : <b>{VIP_MENSUEL} USDT</b>\n"
        f"Trimestriel : <b>{VIP_TRIMESTRIEL} USDT</b>\n"
        f"Annuel : <b>{VIP_ANNUEL} USDT</b>\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"Pret a generer ton premier profit aujourd'hui ?\n"
        f"<b>{ADMIN_BOT}</b>\n\n"
        f"XM -> {XM_LINK}"
    )
    if not can_send_message():
        print("[PROMO] Skip — max messages heure atteint"); return
    tg_text(GROUP_PUBLIC,msg)
    register_message()
    print("[PROMO] Comment gagner envoye")


def post_acces_vip_limite():
    """FORMAT 3 — UCHE : 'ACCES VIP — PLACES LIMITEES'"""
    intro=random.choice([
        "Cette semaine, j'ouvre seulement quelques places pour rejoindre le canal VIP.",
        "Cette session, quelques places sont disponibles pour rejoindre le canal VIP.",
        "Pour les prochains jours seulement, j'ouvre l'acces au canal VIP.",
    ])
    msg=(
        f"<b>ACCES VIP — PLACES LIMITEES</b>\n\n"
        f"{intro}\n\n"
        f"<i>Tu y trouves :</i>\n\n"
        f"<i>Des signaux ICT M1 precis\n"
        f"Une strategie claire\n"
        f"Une gestion du risque structuree\n"
        f"Un accompagnement serieux</i>\n\n"
        f"Ce n'est pas pour tester.\n"
        f"C'est pour ceux qui veulent progresser et obtenir de vrais resultats.\n\n"
        f"<i><b>L'acces se ferme des que les places sont prises.</b></i>\n\n"
        f"Demande ton acces ici :\n"
        f"<b>{ADMIN_BOT}</b>"
    )
    if not can_send_message():
        print("[PROMO] Skip — max messages heure atteint"); return
    tg_text(GROUP_PUBLIC,msg)
    register_message()
    print("[PROMO] Acces VIP limite envoye")


def post_motivation_soir():
    """Post motivation du soir — style UCHE."""
    posts=[
        {"titre":"DISCIPLINE DU SOIR",
         "corps":"Quand la journee ralentit, les vrais ambitieux analysent encore. C'est dans le calme que se preparent les meilleures decisions. Le succes ne vient pas du hasard. Il se construit avec constance, strategie et focus. Tu veux avancer pour de vrai ?"},
        {"titre":"LE MARCHE FERME, LA FORMATION CONTINUE",
         "corps":"Pendant que d'autres se reposent, toi tu analyses. Relis tes trades du jour. Qu'est-ce qui a bien marche ? Les grands traders ne deviennent pas grands par hasard. Ils travaillent quand les autres dorment."},
        {"titre":"RECAP DU SOIR",
         "corps":"Une autre journee de trading terminee. Si tu as respecte ton plan, tu as deja gagne — peu importe le resultat. La discipline d'aujourd'hui construit le compte de demain. Reste focus. On avance ensemble."},
    ]
    p=random.choice(posts)
    msg=f"<b>{p['titre']}</b>\n\n<i>{p['corps']}</i>\n\n<b>{ADMIN_BOT}</b>"
    img=make_motivation_img(p["titre"],p["corps"])
    if not can_send_message():
        print("[MOTIV] Skip — max messages heure atteint"); return
    if img: tg_photo(GROUP_PUBLIC,img,msg)
    else:   tg_text(GROUP_PUBLIC,msg)
    register_message()
    print("[MOTIV] Post soir envoye")


def post_resultats_jour():
    """Post resultats — style UCHE 'PROFITS DU SOIR'."""
    if not daily_wins: return
    wins=daily_wins[:7]; nb=len(wins); total=sum(w["gain"] for w in wins)
    lines=""
    for w in wins:
        d="(En haut)" if w["direction"]=="LONG" else "(En bas)"
        lines+=f"<i>{w['pair']} {d}  +{w['gain']:.2f} $</i>\n"
    msg=(
        f"<b>PROFITS DU SOIR — {CANAL_NAME}</b>\n\n"
        f"Encore une session solide et disciplinee — "
        f"profit total : <b>+{total:.2f} $</b> en quelques heures.\n\n"
        f"{lines}\n"
        f"<b>{nb} trades gagnants sur {nb}</b> — execution precise et controle total.\n\n"
        f"Tu veux generer des gains reguliers comme ca ?\n"
        f"<b>{ADMIN_BOT}</b>"
    )
    img=make_results_img(wins)
    if img: tg_photo(GROUP_PUBLIC,img,msg)
    else:   tg_text(GROUP_PUBLIC,msg)
    daily_wins.clear()
    print(f"[RESULTS] {nb} trades — total +{total:.2f}$")

# ══════════════════════════════════════════════════════════════
#  SCANNER
# ══════════════════════════════════════════════════════════════

def scan_once():
    sess=get_session(); now=time.time()
    ts=datetime.now(timezone.utc).strftime('%H:%M UTC')
    if not sess:
        print(f"[{ts}] Hors session — skip"); return

    # Verif limite horaire AVANT de scanner
    ok, reason = can_send_signal()
    if not ok:
        h_next = (datetime.now(timezone.utc).hour + 1) % 24
        print(f"[{ts}] Signal limite cette heure ({reason}) — prochain slot : {h_next}h UTC")
        return

    print(f"[{ts}] {sess.upper()} — scan M1 Breaker Block... (Score min: {MIN_SCORE}%)")
    seen={}
    best = None  # garde le meilleur setup de ce cycle
    for symbol,meta in PAIRS.items():
        label=meta["label"]
        if label in seen: continue
        seen[label]=True
        vol_pct=meta["vol_pct"]
        if now-cooldowns.get(symbol,0)<COOLDOWN_MIN*60:
            mins=int((COOLDOWN_MIN*60-(now-cooldowns.get(symbol,0)))/60)
            print(f"  {label}: cooldown ({mins}min)"); continue
        candles=get_candles(symbol)
        if len(candles)<30:
            print(f"  {label}: donnees insuffisantes"); continue
        result=detect_breaker(candles,vol_pct)
        if not result:
            print(f"  {label}: pas de setup"); continue
        print(f"  {label}: SETUP {result['side']} | RR 1:{result['rr']} | Score {result['score']}%")
        # Garde le meilleur score de ce cycle
        if best is None or result["score"] > best["score"]:
            best = {**result, "label": label, "session": sess}
            cooldowns[symbol] = time.time()

    # Envoie uniquement le MEILLEUR setup du cycle
    if best:
        print(f"  >>> MEILLEUR SETUP: {best['label']} {best['side']} Score {best['score']}%")
        send_signal(label=best["label"],side=best["side"],entry=best["entry"],
                    sl=best["sl"],tp1=best["tp1"],tp2=best["tp2"],
                    rr=best["rr"],score=best["score"],session=best["session"])

# ══════════════════════════════════════════════════════════════
#  SCHEDULER
# ══════════════════════════════════════════════════════════════

def setup_schedule():
    # Motivation soir (20h et 22h UTC)
    schedule.every().day.at("20:00").do(post_motivation_soir)
    schedule.every().day.at("22:00").do(post_motivation_soir)
    # Resultats du jour
    schedule.every().day.at("21:30").do(post_resultats_jour)
    # Temoignages (lun/mer/ven)
    schedule.every().monday.at("09:00").do(post_temoignage)
    schedule.every().wednesday.at("14:00").do(post_temoignage)
    schedule.every().friday.at("11:00").do(post_temoignage)
    # Comment gagner (mar/sam)
    schedule.every().tuesday.at("08:00").do(post_comment_gagner)
    schedule.every().saturday.at("09:00").do(post_comment_gagner)
    # Acces VIP limite (lun/jeu/dim)
    schedule.every().monday.at("18:00").do(post_acces_vip_limite)
    schedule.every().thursday.at("12:00").do(post_acces_vip_limite)
    schedule.every().sunday.at("10:00").do(post_acces_vip_limite)
    print("[SCHEDULE] Tous les posts automatiques configures OK")

def run_schedule():
    while True:
        schedule.run_pending(); time.sleep(30)

# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("="*54)
    print("  ALPHABOT — STYLE UCHE Trade&Gagne")
    print(f"  Canal : {CANAL_NAME}  |  Admin : {ADMIN_USERNAME}")
    print(f"  Paires : {len(PAIRS)} forex  |  Scan toutes les {SCAN_EVERY}s")
    print(f"  RR min : 1:{MIN_RR}  |  Score min : {MIN_SCORE}%")
    print(f"  Max : {MAX_SIGNALS_HOUR} signal/heure  |  {MAX_MESSAGES_HOUR} messages/heure")
    print(f"  Sessions : London 07h-16h + NY 12h-21h UTC")
    print("="*54)
    setup_schedule()
    threading.Thread(target=run_schedule, daemon=True).start()
    scan_once()
    while True:
        time.sleep(SCAN_EVERY)
        try: scan_once()
        except Exception as e: print(f"[ERR] {e}")
