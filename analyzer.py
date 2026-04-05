"""
BIST Skor Motoru v3
===================
TradingView Screener'dan gelen hazır teknik göstergeler kullanılır.
RSI, MACD, StochRSI, Williams%R, EMA, BB — hepsi TV'den hazır geliyor.
Artık manuel hesaplama YOK — sadece normalize et ve ağırlıklandır.

F parametresi: TradingView temel verisi + İş Yatırım bilanço birleşimi.
"""
import logging
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)


def sf(val, default=np.nan) -> float:
    """Safe float dönüşümü."""
    try:
        if val is None:
            return default
        f = float(val)
        return default if (np.isnan(f) or np.isinf(f)) else f
    except Exception:
        return default


def norm(val: float, lo: float, hi: float, rev: bool = False) -> float:
    """0-10 normalizasyon."""
    if hi == lo:
        return 5.0
    r = max(0.0, min(1.0, (val - lo) / (hi - lo)))
    return (1.0 - r if rev else r) * 10.0


# ════════════════════════════════════════════════════════
# T: TEKNİK MOMENTUM  (%22)
# TradingView'den hazır: RSI, MACD.macd, MACD.signal,
# Stoch.RSI.K, W.R
# ════════════════════════════════════════════════════════

def score_T(tv: dict) -> dict:
    rsi      = sf(tv.get("RSI"), 50.0)
    rsi_prev = sf(tv.get("RSI[1]"), rsi)
    macd     = sf(tv.get("MACD.macd"), 0.0)
    signal   = sf(tv.get("MACD.signal"), 0.0)
    hist     = macd - signal          # histogram hesapla
    # Önceki histogram: tahmin (macd trend için rsi trend kullanılır)
    stoch_rsi = sf(tv.get("Stoch.RSI.K"), 50.0)
    wr         = sf(tv.get("W.R"), -50.0)

    # RSI puanı
    if rsi < 25:    rp = 10.0
    elif rsi < 40:  rp = 9.0
    elif rsi < 55:  rp = norm(rsi, 40, 55) * 0.4 + 6.0
    elif rsi < 65:  rp = 7.0
    elif rsi < 75:  rp = norm(rsi, 65, 75, rev=True) * 0.5 + 4.0
    else:           rp = 2.0

    # MACD histogram + trend
    hist_rising = rsi > rsi_prev   # RSI trend proxy olarak kullan
    if hist > 0 and hist_rising:   mp = 9.0
    elif hist > 0:                 mp = 7.0
    elif hist < 0 and hist_rising: mp = 5.0
    elif hist < 0:                 mp = 2.0
    else:                          mp = 6.0

    # StochRSI
    if stoch_rsi < 20:    sp = 9.0
    elif stoch_rsi < 50:  sp = norm(stoch_rsi, 20, 50) * 3.0 + 5.0
    elif stoch_rsi < 80:  sp = norm(stoch_rsi, 50, 80, rev=True) * 2.0 + 5.0
    else:                 sp = 2.0

    # Williams %R
    if -100 <= wr <= -80: wp = 9.0
    elif wr <= -50:       wp = 6.0
    elif wr <= -20:       wp = 5.0
    else:                 wp = 2.0

    skor = rp*0.35 + mp*0.35 + sp*0.15 + wp*0.15
    return {
        "skor": round(skor, 2),
        "rsi": round(rsi, 1), "rsi_puan": round(rp, 2),
        "macd_macd": round(macd, 4), "macd_signal": round(signal, 4),
        "macd_hist": round(hist, 4), "macd_puan": round(mp, 2),
        "stochrsi": round(stoch_rsi, 1), "stoch_puan": round(sp, 2),
        "williams_r": round(wr, 1), "wr_puan": round(wp, 2),
    }


# ════════════════════════════════════════════════════════
# H: HACİM ANALİZİ  (%18)
# TradingView: volume, relative_volume_10d_calc, change
# ════════════════════════════════════════════════════════

def score_H(tv: dict) -> dict:
    vol      = sf(tv.get("volume"), 0.0)
    rel_vol  = sf(tv.get("relative_volume_10d_calc"), 1.0)
    change   = sf(tv.get("change"), 0.0)    # günlük değişim %
    close    = sf(tv.get("close"), 1.0)

    # relative_volume: 1.0 = ortalama, 2.0 = 2x ortalama
    skor = norm(rel_vol, 0.7, 3.0) * 0.7

    # Hacim + yükseliş bonusu
    if rel_vol > 1.5 and change > 0:
        skor = min(10.0, skor + 1.0)

    hacim_tl = vol * close if (vol and close) else 0.0

    return {
        "skor": round(skor, 2),
        "vol_relative": round(rel_vol, 2),
        "gunluk_degisim": round(change, 2),
        "gunluk_hacim_tl": round(hacim_tl, 0),
    }


# ════════════════════════════════════════════════════════
# K: KISA VADE TREND  (%18)
# TradingView: EMA5, EMA10, EMA20, close, change
# ════════════════════════════════════════════════════════

def score_K(tv: dict) -> dict:
    son  = sf(tv.get("close"), 0.0)
    e5   = sf(tv.get("EMA5"))
    e10  = sf(tv.get("EMA10"))
    e20  = sf(tv.get("EMA20"))
    chg  = sf(tv.get("change"), 0.0)

    if all(not np.isnan(v) for v in [e5, e10, e20]) and son > 0:
        if son > e5 > e10 > e20:  hiz = 9.0
        elif son > e5 > e10:      hiz = 7.0
        elif e5 < e10:            hiz = 3.0
        else:                     hiz = 5.0
    else:
        hiz = 5.0

    # 3 günlük momentum yok — change % ile yaklaşıyoruz
    skor = hiz * 0.7 + norm(chg, -5, 8) * 0.3

    return {
        "skor": round(skor, 2),
        "ema5":  round(e5, 2) if not np.isnan(e5) else None,
        "ema10": round(e10, 2) if not np.isnan(e10) else None,
        "ema21": round(e20, 2) if not np.isnan(e20) else None,  # EMA20 ≈ EMA21
        "hizalama_puan": round(hiz, 2),
        "momentum_3g": round(chg, 2),
    }


# ════════════════════════════════════════════════════════
# F: FİNANSAL SAĞLIK  (%12)
# TradingView temel + İş Yatırım bilanço birleşimi
# ════════════════════════════════════════════════════════

def score_F(tv: dict, fin: dict) -> dict:
    eksik = 0

    def gv(key, src):
        v = sf(src.get(key))
        if np.isnan(v):
            return None
        return v

    def gv2(tv_key, fin_key, src_tv, src_fin):
        """TV'den dene, yoksa İş Yatırım'dan al."""
        nonlocal eksik
        v = gv(tv_key, src_tv)
        if v is None:
            v = gv(fin_key, src_fin)
        if v is None:
            eksik += 1
        return v

    # F/K — TV'den, yoksa İş Yatırım'dan
    fk = gv2("price_earnings_ttm", "trailing_pe", tv, fin)
    # PD/DD
    pddd = gv2("price_book_ratio", "price_to_book", tv, fin)
    # Borç/Özkaynak — İş Yatırım öncelikli (daha güvenilir TRY)
    dte = gv("debt_to_equity", fin) or gv("debt_to_equity", tv)
    if dte is None: eksik += 1
    # Net marj — İş Yatırım öncelikli
    npm = gv("net_profit_margin", fin) or (
        gv("net_profit_margin_ttm", tv) or
        gv("gross_profit_margin_ttm", tv)
    )
    if npm is None: eksik += 1
    # Op marj
    opm = gv("op_margin", fin)
    # ROE — İş Yatırım öncelikli
    roe = gv("roe", fin) or gv("return_on_equity", tv)
    # Büyüme
    byr = gv("net_income_growth", fin) or gv("revenue_growth", fin)
    if byr is None: eksik += 1
    # Cari oran
    cr = gv("current_ratio", fin) or gv("current_ratio", tv)

    # ── Puanlama ──────────────────────────────────────
    if fk is None:      fk_p = 5.0
    elif fk < 0:        fk_p = 0.5
    elif fk < 8:        fk_p = 10.0
    elif fk < 15:       fk_p = 8.0
    elif fk < 25:       fk_p = 6.0
    elif fk < 50:       fk_p = 4.0
    else:               fk_p = 2.0

    if pddd is None:    pd_p = 5.0
    elif pddd < 0:      pd_p = 1.0
    elif pddd < 1:      pd_p = 10.0
    elif pddd < 2:      pd_p = 7.0
    elif pddd < 4:      pd_p = 4.0
    else:               pd_p = 2.0

    if dte is None:     bo_p = 5.0
    elif dte < 30:      bo_p = 9.0
    elif dte < 100:     bo_p = 7.0
    elif dte < 200:     bo_p = 4.0
    else:               bo_p = 2.0

    if byr is None:     by_p = 5.0
    elif byr > 0.50:    by_p = 10.0
    elif byr > 0.20:    by_p = 8.0
    elif byr > 0:       by_p = 6.0
    elif byr > -0.20:   by_p = 3.0
    else:               by_p = 1.0

    if npm is not None:  mj_p = norm(npm, -5, 30)
    elif opm is not None: mj_p = norm(opm, -5, 35)
    else:                mj_p = 5.0

    skor = (fk_p*0.25 + pd_p*0.20 + bo_p*0.20 + by_p*0.20 + mj_p*0.15)
    skor = max(0.0, skor - min(1.5, eksik * 0.3))

    return {
        "skor": round(skor, 2),
        "fk": round(fk, 2) if fk is not None else None,
        "fk_puan": round(fk_p, 2),
        "pddd": round(pddd, 2) if pddd is not None else None,
        "pddd_puan": round(pd_p, 2),
        "borc_ozkaynak": round(dte, 1) if dte is not None else None,
        "borc_puan": round(bo_p, 2),
        "buyume": round(byr * 100, 1) if byr is not None else None,
        "buyume_puan": round(by_p, 2),
        "net_marj": round(npm, 1) if npm is not None else None,
        "op_marj": round(opm, 1) if opm is not None else None,
        "roe": round(roe, 1) if roe is not None else None,
        "cur_ratio": round(cr, 2) if cr is not None else None,
        "marj_puan": round(mj_p, 2),
        "eksik_veri": eksik,
        "fin_kaynak": fin.get("kaynak","tv"),
        "son_donem": fin.get("son_donem","?"),
    }


# ════════════════════════════════════════════════════════
# B: BOLLINGER BANT  (%8)
# TradingView: BB.upper, BB.lower, BB.middle
# ════════════════════════════════════════════════════════

def score_B(tv: dict) -> dict:
    son = sf(tv.get("close"), 0.0)
    up  = sf(tv.get("BB.upper"))
    lo  = sf(tv.get("BB.lower"))
    mid = sf(tv.get("BB.middle"))

    if np.isnan(up) or np.isnan(lo) or up == lo:
        return {"skor": 5.0, "bb_pos": 0.5, "squeeze": False,
                "bb_upper": None, "bb_middle": None, "bb_lower": None}

    bb_pos = (son - lo) / (up - lo)
    bb_pos = max(0.0, min(1.0, bb_pos))

    # Sıkışma: bant genişliği düşükse (threshold %3 mid'in)
    bant_genislik = (up - lo) / mid if (mid and mid > 0) else 0.1
    squeeze = bant_genislik < 0.03

    if squeeze:
        skor = 8.5 if son > mid else 6.0
    elif bb_pos < 0.15:
        skor = 7.5
    elif bb_pos > 0.85:
        skor = 3.0
    else:
        skor = norm(bb_pos, 0.15, 0.85) * 4.0 + 3.0

    return {
        "skor": round(skor, 2), "bb_pos": round(bb_pos, 3),
        "squeeze": squeeze,
        "bb_upper":  round(up, 2) if not np.isnan(up) else None,
        "bb_middle": round(mid, 2) if not np.isnan(mid) else None,
        "bb_lower":  round(lo, 2) if not np.isnan(lo) else None,
        "bant_genislik_pct": round(bant_genislik * 100, 2),
    }


# ════════════════════════════════════════════════════════
# D: DESTEK/DİRENÇ  (%5)
# TradingView: EMA20, high, low (52 hafta için EMA200)
# ════════════════════════════════════════════════════════

def score_D(tv: dict) -> dict:
    son  = sf(tv.get("close"), 0.0)
    e20  = sf(tv.get("EMA20"))
    e200 = sf(tv.get("EMA200"))
    high = sf(tv.get("high"), son)    # günlük yüksek
    low  = sf(tv.get("low"), son)     # günlük düşük

    if not np.isnan(e20) and e20 > 0:
        pct20 = (son / e20 - 1) * 100
    else:
        pct20 = 0.0

    if 0 <= pct20 <= 3:    skor = 9.0
    elif pct20 <= 8:       skor = 7.0
    elif pct20 > 8:        skor = norm(pct20, 8, 25, rev=True) * 0.4 + 4.0
    elif pct20 >= -3:      skor = 5.5
    else:                  skor = norm(pct20, -15, -3) * 0.3 + 1.0

    # EMA200 ile uzun vade trendi bonus
    if not np.isnan(e200) and e200 > 0 and son > e200:
        skor = min(10.0, skor + 0.5)

    return {
        "skor": round(skor, 2),
        "ema21_uzaklik_pct": round(pct20, 2),  # EMA20 ≈ EMA21
        "ema200": round(e200, 2) if not np.isnan(e200) else None,
        "high52": None,  # TV'den 52H yüksek gelmez, günlük high kullanıldı
        "low52":  None,
        "zirveye_mesafe_pct": None,
    }


# ════════════════════════════════════════════════════════
# R: RİSK/ÖDÜL  (%5)
# TradingView: high, low, close
# ════════════════════════════════════════════════════════

def score_R(tv: dict) -> dict:
    son  = sf(tv.get("close"), 0.0)
    high = sf(tv.get("high"), son)
    low  = sf(tv.get("low"), son)

    if son <= 0:
        return {"skor": 5.0, "risk_odul": 1.0, "h10": None, "l10": None}

    upside   = high - son
    downside = son - low
    ro = upside / max(downside, son * 0.001)

    return {
        "skor": round(norm(ro, 0.2, 2.5), 2),
        "risk_odul": round(ro, 2),
        "h10": round(high, 2),
        "l10": round(low, 2),
    }


# ════════════════════════════════════════════════════════
# M: PİYASA BAĞLAMI  (%5)
# ════════════════════════════════════════════════════════

def score_M(endeks_degisim: float) -> dict:
    if endeks_degisim > 1:    delta = 1.0
    elif endeks_degisim > 0:  delta = 0.0
    elif endeks_degisim > -1: delta = -1.0
    else:                     delta = -2.0

    return {
        "skor": round(max(0.0, min(10.0, 5.0 + delta)), 2),
        "endeks_degisim": round(endeks_degisim, 2),
        "delta": round(delta, 2),
    }


# ════════════════════════════════════════════════════════
# ANA SKOR + SINYAL
# ════════════════════════════════════════════════════════

def hesapla_skor(t, h, k, f, b, d, r, n, m) -> float:
    ag = {"T":0.22,"H":0.18,"K":0.18,"F":0.12,"B":0.08,
          "D":0.05,"R":0.05,"N":0.07,"M":0.05}
    p  = {"T":t["skor"],"H":h["skor"],"K":k["skor"],"F":f["skor"],
          "B":b["skor"],"D":d["skor"],"R":r["skor"],"N":n["skor"],"M":m["skor"]}
    return round(sum(p[k_]*ag[k_] for k_ in ag) * 10, 2)


def sinyal(skor, f, h) -> str:
    liste = ["GÜÇLÜ AL","AL","İZLE","ZAYIF","KAÇIN"]
    if skor >= 72:   idx = 0
    elif skor >= 60: idx = 1
    elif skor >= 50: idx = 2
    elif skor >= 40: idx = 3
    else:            idx = 4
    if (f.get("fk") or 0) < 0:                        idx = min(idx+1, 4)
    if h.get("gunluk_hacim_tl", 1e9) < 5_000_000:     idx = min(idx+1, 4)
    return liste[idx]


def uyarilar(b, f, h, d, n) -> list:
    u = []
    if b.get("squeeze"):                               u.append("⚡ BB Sıkışma")
    if (f.get("fk") or 0) < 0:                        u.append("⚠️ Zarar Eden")
    if h.get("gunluk_hacim_tl", 1e9) < 5_000_000:     u.append("💧 Düşük Likidite")
    if abs(n.get("ham_skor", 0)) >= 4:
        yon = "Pozitif" if n["ham_skor"] > 0 else "Negatif"
        u.append(f"📰 Güçlü {yon} Haber")
    if f.get("fin_kaynak") == "tv":                    u.append("⚠️ Bilanço: TV verisi")
    return u


def giris_hedef_stop(tv: dict, k: dict) -> dict:
    son  = sf(tv.get("close"), 0.0)
    e20  = k.get("ema21") or son
    low  = sf(tv.get("low"), son * 0.95)

    giris = round(son * 1.001, 2)
    stop  = round(max(son * 0.93, float(low) * 0.99, float(e20) * 0.97), 2)
    risk  = giris - stop
    hedef = round(giris + risk * 2.0, 2)
    rp    = round((giris - stop) / giris * 100, 2) if giris > 0 else 0
    pp    = round((hedef - giris) / giris * 100, 2) if giris > 0 else 0

    return {
        "giris": giris, "stop": stop, "hedef": hedef,
        "risk_pct": rp, "potansiyel_pct": pp,
        "rr_oran": round(pp / rp, 2) if rp > 0 else 0,
    }


def analyze_stock(ticker: str, tv_data: dict, fin: dict,
                  haber: dict, endeks_degisim: float,
                  hl_module) -> Optional[dict]:
    """Tek hisse tam analizi."""
    if not tv_data or not tv_data.get("close"):
        return None

    son_fiyat = sf(tv_data.get("close"), 0.0)
    if son_fiyat <= 0:
        return None

    try:
        t = score_T(tv_data)
        h = score_H(tv_data)
        k = score_K(tv_data)
        f = score_F(tv_data, fin)
        b = score_B(tv_data)
        d = score_D(tv_data)
        r = score_R(tv_data)
        n = {"skor": haber.get("skor", 5.0), **haber}
        m = score_M(endeks_degisim)

        toplam = hesapla_skor(t, h, k, f, b, d, r, n, m)
        sig    = sinyal(toplam, f, h)
        degisim = sf(tv_data.get("change"), 0.0)

        # TradingView'in kendi önerisi (bonus bilgi)
        tv_oneri = sf(tv_data.get("Recommend.All"), 0.0)
        # -1=STRONG SELL, 0=NEUTRAL, +1=STRONG BUY

        ad = str(tv_data.get("description") or ticker)[:35]

        return {
            "ticker": ticker,
            "ad":     ad,
            "endeks": hl_module.get_endeks(ticker),
            "sektor": hl_module.get_sektor(ticker),
            "toplam_skor":    toplam,
            "sinyal":         sig,
            "fiyat":          round(son_fiyat, 2),
            "gunluk_degisim": round(degisim, 2),
            "tv_oneri":       round(tv_oneri, 2),
            "t": t, "h": h, "k": k, "f": f,
            "b": b, "d": d, "r": r, "n": n, "m": m,
            "uyarilar":    uyarilar(b, f, h, d, n),
            "ghs":         giris_hedef_stop(tv_data, k),
            "veri_kalite": round(max(0, 1 - f.get("eksik_veri",0) / 10), 2),
        }
    except Exception as e:
        logger.error(f"{ticker} analiz hatası: {e}", exc_info=True)
        return None
