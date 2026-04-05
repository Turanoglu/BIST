"""Haber Sentiment — yfinance haberlerini analiz eder."""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

POZITIF = [
    "sözleşme","anlaşma","kâr","kar","büyüme","ihracat","teşvik",
    "temettü","kapasite","yatırım","sipariş","rekor","artış","güçlü",
    "nato","ihale","kazanç","başarı","prim","yükseliş","pozitif",
    "patent","ruhsat","onay","yeni ürün","genişleme","ortaklık",
    "birleşme","sipariş aldı","ciro büyüdü","ihracat arttı",
]

NEGATIF = [
    "zarar","dava","soruşturma","haciz","iflas","düşüş","kayıp",
    "erteleme","iptal","devalüasyon","ceza","yaptırım","temerrüt",
    "borcunu","sermaye azaltımı","net zarar","konkordato","uyarı",
    "manipülasyon","usulsüzlük","para cezası","zarara geçti",
    "olumsuz","satış düştü","üretim durdu",
]


def analyze_news_sentiment(news_list: list) -> dict:
    if not news_list:
        return {"skor": 5.0, "pozitif": 0, "negatif": 0,
                "toplam": 0, "ham_skor": 0, "haberler": []}

    simdi = datetime.now(timezone.utc).timestamp()
    yedi_gun = 7 * 24 * 3600
    toplam_skor = poz = neg = 0
    analiz = []

    for h in news_list[:20]:
        try:
            pub = h.get("providerPublishTime", 0)
            if simdi - pub > yedi_gun:
                continue
            metin = ((h.get("title","") or "") + " " + (h.get("summary","") or "")).lower()
            poz_k = [k for k in POZITIF if k in metin]
            neg_k = [k for k in NEGATIF if k in metin]
            hs = 0
            sentiment = "nötr"
            if poz_k and not neg_k:    hs = 2;  sentiment = "pozitif";       poz += 1
            elif neg_k and not poz_k:  hs = -2; sentiment = "negatif";       neg += 1
            elif poz_k and neg_k:
                if len(poz_k) > len(neg_k): hs = 1;  sentiment = "hafif pozitif"; poz += 1
                elif len(neg_k) > len(poz_k): hs = -1; sentiment = "hafif negatif"; neg += 1
            toplam_skor += hs
            tarih = datetime.fromtimestamp(pub, tz=timezone.utc).strftime("%d.%m %H:%M") if pub else "?"
            analiz.append({"baslik": h.get("title","")[:80], "sentiment": sentiment,
                           "skor": hs, "tarih": tarih, "url": h.get("link","")})
        except Exception:
            continue

    toplam_skor = max(-10, min(10, toplam_skor))
    return {
        "skor": max(0.0, min(10.0, 5.0 + toplam_skor)),
        "pozitif": poz, "negatif": neg, "toplam": len(analiz),
        "ham_skor": toplam_skor, "haberler": analiz[:5],
    }
