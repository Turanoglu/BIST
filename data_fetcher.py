"""
Veri Çekme Modülü v3
====================
Birincil : TradingView Screener  — tüm teknik göstergeler, TEK istekte, saniyeler içinde
İkincil  : İş Yatırım            — KAP bilanço verisi (önbellekli)
Haber    : yfinance              — son 7 gün haberleri (önbellekli)

TradingView avantajları:
  - RSI, MACD, Bollinger, EMA, StochRSI, Williams%R zaten hesaplanmış geliyor
  - BIST100 tamamı TEK istekte ~2 saniyede
  - Canlı fiyat (15dk gecikmeli ücretsiz planda)
  - Sütun formatı: Query().set_markets('turkey').select(...).get_scanner_data()
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Önbellek ─────────────────────────────────────────────
_cache: dict = {}
TV_TTL       = 60          # TradingView teknik: 1 dk (canlı veri)
FINANSAL_TTL = 6 * 3600    # Bilanço: 6 saat
HABER_TTL    = 30 * 60     # Haberler: 30 dk
ENDEKS_TTL   = 120         # Endeks: 2 dk


def _cget(key):
    if key in _cache:
        d, ts, ttl = _cache[key]
        if time.time() - ts < ttl:
            return d
        del _cache[key]
    return None


def _cset(key, data, ttl):
    _cache[key] = (data, time.time(), ttl)


def _bugun():
    return datetime.today().strftime("%d-%m-%Y")


def _n_gun_once(n):
    return (datetime.today() - timedelta(days=n)).strftime("%d-%m-%Y")


# TradingView'den çekilecek alanlar
TV_COLUMNS = [
    # Fiyat
    "close", "open", "high", "low", "volume", "change", "change_abs",
    # Teknik göstergeler — hazır hesaplanmış
    "RSI",          # RSI(14)
    "RSI[1]",       # Önceki RSI (trend için)
    "MACD.macd",    # MACD line
    "MACD.signal",  # Signal line
    "MACD.hist",    # Histogram (macd-signal) — bazı versiyonlarda yok, hesaplayacağız
    "Stoch.K",      # Stochastic K
    "Stoch.D",      # Stochastic D
    "Stoch.RSI.K",  # StochRSI K
    "W.R",          # Williams %R
    "BB.upper",     # Bollinger üst
    "BB.lower",     # Bollinger alt
    "BB.middle",    # Bollinger orta (SMA20)
    "EMA5",
    "EMA10",
    "EMA20",
    "EMA50",
    "EMA200",
    "SMA20",
    "volume",
    "relative_volume_10d_calc",  # Göreceli hacim
    # Temel veriler (TradingView'den gelebiliyorsa)
    "price_earnings_ttm",        # F/K
    "price_book_ratio",          # PD/DD
    "earnings_per_share_basic_ttm",
    "gross_profit_margin_ttm",   # Brüt marj
    "net_profit_margin_ttm",     # Net marj (varsa)
    "return_on_equity",          # ROE
    "debt_to_equity",            # Borç/Özkaynak
    "current_ratio",             # Cari oran
    # Meta
    "market_cap_basic",
    "sector",
    "description",
    "Recommend.All",             # TradingView genel öneri
]


# ════════════════════════════════════════════════════════
# A) TradingView SCREENER — toplu çekim
# ════════════════════════════════════════════════════════

def fetch_tv_batch(tickers: list[str]) -> dict[str, dict]:
    """
    TradingView Screener ile toplu hisse verisi çek.
    Tüm BIST30 veya BIST100 tek istekte ~2 saniyede gelir.

    Args:
        tickers: ['THYAO', 'GARAN', ...] — BIST kodu, .IS veya BIST: olmadan

    Returns:
        {ticker: {close, RSI, MACD.macd, ...}} dict
    """
    cache_key = f"tv_batch:{','.join(sorted(tickers[:10]))}_len{len(tickers)}"
    cached = _cget(cache_key)
    if cached is not None:
        return cached

    result = {}
    try:
        from tradingview_screener import Query

        # BIST:THYAO formatına çevir
        tv_symbols = [f"BIST:{t}" for t in tickers]

        # İstenen sütunları dene, olmayan sütunları yok say
        cols_to_try = TV_COLUMNS.copy()

        count, df = (
            Query()
            .set_markets("turkey")
            .select(*cols_to_try)
            .set_tickers(*tv_symbols)
            .limit(len(tickers) + 10)
            .get_scanner_data()
        )

        logger.info(f"TradingView Screener: {count} hisse, {len(df)} satır alındı")

        for _, row in df.iterrows():
            tv_ticker = str(row.get("ticker", ""))
            ticker = tv_ticker.replace("BIST:", "").strip()
            if ticker:
                result[ticker] = row.to_dict()

    except Exception as e:
        logger.warning(f"TradingView Screener toplu çekim hatası: {e}")
        # Fallback: boş dict — analyzer None döndürür, hata loglanır

    _cset(cache_key, result, TV_TTL)
    return result


def fetch_tv_single(ticker: str) -> Optional[dict]:
    """
    Tek hisse için TradingView verisi.
    Genellikle toplu çekim tercih edilmeli.
    """
    batch = fetch_tv_batch([ticker])
    return batch.get(ticker)


def tv_to_ohlcv(tv_data: dict) -> Optional[pd.DataFrame]:
    """
    TradingView'den gelen anlık veriyi kullanarak
    tarihi OHLCV DataFrame'i İş Yatırım'dan çek.
    Teknik göstergeler TV'den geliyor — bu fonksiyon
    Bollinger bant hesabı için kullanılan tarihi veri içindir.
    """
    # TradingView zaten hesaplanmış RSI/MACD/BB verir,
    # tarihi OHLCV çekmeye gerek yok. Sadece F/K ve
    # bilanço için isyatirimhisse kullanıyoruz.
    return None


# ════════════════════════════════════════════════════════
# B) İş Yatırım — Bilanço verisi (önbellekli, 6 saat)
# ════════════════════════════════════════════════════════

def fetch_financials_isyat(ticker: str) -> dict:
    """İş Yatırım'dan KAP kaynaklı bilanço verisi."""
    ckey = f"fin:{ticker}"
    cached = _cget(ckey)
    if cached is not None:
        return cached

    result = {}
    try:
        from isyatirimhisse import fetch_financials
        df = None
        for grp in ["2", "1", "3"]:
            try:
                df = fetch_financials(
                    symbols=ticker,
                    start_year=datetime.today().year - 2,
                    end_year=datetime.today().year,
                    exchange="TRY",
                    financial_group=grp,
                )
                if df is not None and not df.empty:
                    break
            except Exception:
                continue

        if df is None or df.empty:
            _cset(ckey, result, FINANSAL_TTL)
            return result

        meta = ["FINANCIAL_ITEM_CODE","FINANCIAL_ITEM_NAME_TR",
                "FINANCIAL_ITEM_NAME_EN","SYMBOL"]
        deger_cols = [c for c in df.columns if c not in meta]
        if not deger_cols:
            _cset(ckey, result, FINANSAL_TTL)
            return result

        son  = deger_cols[-1]
        yoy  = deger_cols[-5] if len(deger_cols) >= 5 else None

        def g(kod):
            row = df[df["FINANCIAL_ITEM_CODE"].str.upper().str.contains(
                kod.upper()[:20], na=False, regex=False)]
            if row.empty:
                row = df[df["FINANCIAL_ITEM_NAME_TR"].str.upper().str.contains(
                    kod.upper()[:15], na=False, regex=False)]
            if row.empty:
                return None
            try:
                v = float(str(row.iloc[0][son]).replace(",",".").replace(" ",""))
                return None if np.isnan(v) else v
            except Exception:
                return None

        def gy(kod):
            if not yoy:
                return None
            row = df[df["FINANCIAL_ITEM_CODE"].str.upper().str.contains(
                kod.upper()[:20], na=False, regex=False)]
            if row.empty:
                return None
            try:
                v = float(str(row.iloc[0][yoy]).replace(",",".").replace(" ",""))
                return None if np.isnan(v) else v
            except Exception:
                return None

        ni   = g("NET_DONEM") or g("NET KAR")
        rev  = g("SATIS_HASILATI") or g("HASILAT") or g("SATIS")
        opi  = g("ESAS_FAALIYET") or g("FAALIYET KARI")
        eq   = g("TOPLAM_OZKAYNAKLAR") or g("OZKAYNAK")
        sd   = g("KISA_VADELI_BORCLAR")
        ld   = g("UZUN_VADELI_BORCLAR")
        ca   = g("DONEN_VARLIKLAR")
        cl   = g("KISA_VADELI_YUK")
        cash = g("NAKIT_VE_NAKITE") or g("NAKIT")
        ni_y = gy("NET_DONEM") or gy("NET KAR")
        rv_y = gy("SATIS_HASILATI") or gy("HASILAT")

        td  = (sd or 0) + (ld or 0) if (sd is not None or ld is not None) else None
        cr  = (ca / cl) if (ca and cl and cl > 0) else None
        dte = (td / eq * 100) if (td is not None and eq and eq > 0) else None
        npm = (ni / rev * 100) if (ni is not None and rev and rev > 0) else None
        opm = (opi / rev * 100) if (opi is not None and rev and rev > 0) else None
        roe = (ni / eq * 100) if (ni is not None and eq and eq > 0) else None
        nig = (ni - ni_y) / abs(ni_y) if (ni and ni_y and ni_y != 0) else None
        rvg = (rev - rv_y) / abs(rv_y) if (rev and rv_y and rv_y != 0) else None

        result = {
            "net_income": ni, "revenue": rev, "op_income": opi,
            "total_equity": eq, "total_debt": td, "cash": cash,
            "current_ratio": cr, "debt_to_equity": dte,
            "net_profit_margin": npm, "op_margin": opm, "roe": roe,
            "net_income_growth": nig, "revenue_growth": rvg,
            "son_donem": son, "kaynak": "isyatirim",
        }
    except Exception as e:
        logger.warning(f"İş Yatırım bilanço [{ticker}]: {e}")

    _cset(ckey, result, FINANSAL_TTL)
    return result


# ════════════════════════════════════════════════════════
# C) Haberler — yfinance (önbellekli)
# ════════════════════════════════════════════════════════

def fetch_news(ticker: str) -> list:
    ckey = f"news:{ticker}"
    cached = _cget(ckey)
    if cached is not None:
        return cached
    try:
        import yfinance as yf
        news = yf.Ticker(f"{ticker}.IS").news or []
        _cset(ckey, news, HABER_TTL)
        return news
    except Exception:
        return []


# ════════════════════════════════════════════════════════
# D) Endeks verisi — piyasa bağlamı için
# ════════════════════════════════════════════════════════

def fetch_endeks_degisim() -> float:
    """BIST100 günlük değişim yüzdesini döndür."""
    ckey = "endeks_degisim"
    cached = _cget(ckey)
    if cached is not None:
        return cached

    degisim = 0.0
    try:
        from tradingview_screener import Query
        _, df = (Query()
                 .set_markets("turkey")
                 .select("close", "change")
                 .set_tickers("BIST:XU100")
                 .get_scanner_data())
        if not df.empty:
            degisim = float(df.iloc[0].get("change", 0) or 0)
    except Exception:
        try:
            import yfinance as yf
            raw = yf.Ticker("XU100.IS").history(period="2d")
            if raw is not None and len(raw) >= 2:
                degisim = float((raw["Close"].iloc[-1] / raw["Close"].iloc[-2] - 1) * 100)
        except Exception:
            pass

    _cset(ckey, degisim, ENDEKS_TTL)
    return degisim


# ════════════════════════════════════════════════════════
# E) Bağlantı testi
# ════════════════════════════════════════════════════════

def baglanti_test() -> dict:
    """Analiz başlamadan kaynak kontrolü."""
    sonuc = {"tv": False, "isyatirim": False, "mesaj": ""}
    msgs = []

    try:
        from tradingview_screener import Query
        _, df = (Query()
                 .set_markets("turkey")
                 .select("close", "RSI")
                 .set_tickers("BIST:THYAO")
                 .limit(1)
                 .get_scanner_data())
        if not df.empty:
            rsi_val = df.iloc[0].get("RSI", "?")
            sonuc["tv"] = True
            msgs.append(f"✓ TradingView OK — THYAO RSI: {rsi_val:.1f}" if rsi_val != "?" else "✓ TradingView OK")
        else:
            msgs.append("⚠ TradingView veri döndürmedi")
    except Exception as e:
        msgs.append(f"✗ TradingView: {str(e)[:60]}")

    try:
        from isyatirimhisse import fetch_stock_data
        df2 = fetch_stock_data("THYAO", start_date=_n_gun_once(5), end_date=_bugun())
        if df2 is not None and not df2.empty:
            sonuc["isyatirim"] = True
            msgs.append("✓ İş Yatırım OK (bilanço kaynağı)")
        else:
            msgs.append("⚠ İş Yatırım veri yok")
    except Exception as e:
        msgs.append(f"⚠ İş Yatırım: {str(e)[:50]} (bilanço sınırlı olabilir)")

    sonuc["mesaj"] = " | ".join(msgs)
    return sonuc


# ════════════════════════════════════════════════════════
# F) Async wrapper — app.py için
# ════════════════════════════════════════════════════════

async def fetch_single_async(ticker: str,
                              tv_cache: dict,
                              sem: asyncio.Semaphore) -> dict:
    """
    Tek hisse verisi — TV cache'den al, bilanço ve haberi çek.
    TV verisi zaten toplu geldi (tv_cache dict), burada sadece
    bilanço ve haber için İş Yatırım + yfinance'e gidiyoruz.
    """
    async with sem:
        loop = asyncio.get_event_loop()
        tv_data = tv_cache.get(ticker, {})

        # Bilanço — İş Yatırım (önbellekli, paralel)
        fin = await loop.run_in_executor(None, fetch_financials_isyat, ticker)
        await asyncio.sleep(0.05)

        # Haberler — yfinance (önbellekli)
        news = await loop.run_in_executor(None, fetch_news, ticker)

        return {
            "ticker":  ticker,
            "tv_data": tv_data,
            "fin":     fin,
            "news":    news,
            "hata":    None if tv_data else "TradingView'den veri gelmedi",
        }
