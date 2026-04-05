"""
BIST Analyzer v3 — TradingView + İş Yatırım + yfinance
=======================================================
Mimari:
  TradingView Screener → Tüm teknik göstergeler (toplu, saniyeler içinde)
  İş Yatırım          → KAP bilanço verisi (önbellekli)
  yfinance            → Haberler (önbellekli)

Hız: BIST30 ~5sn · BIST100 ~20sn · Tüm BIST ~2-3dk
"""
import asyncio
import json
import logging
import queue
import re
import threading
import time
import webbrowser
from datetime import datetime
from typing import Optional

from flask import Flask, Response, jsonify, render_template_string, stream_with_context, request

import analyzer    as anlz
import data_fetcher as df_mod
import hisse_listesi as hl
import news_scorer   as ns

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("bist_v3")

app = Flask(__name__)

_state = {
    "calisıyor": False,
    "sonuclar":  [],
    "ilerleme":  {"islem": 0, "toplam": 0, "aktif": "", "baslangic": None},
    "ist":       {"guclu_al":0,"al":0,"izle":0,"zayif":0,"kacin":0,"hata":0},
    "log":       [],
    "durdur":    False,
}
_sse_q: queue.Queue = queue.Queue(maxsize=2000)


def _log(msg: str, sev: str = "INFO") -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    e  = {"ts": ts, "mesaj": msg, "seviye": sev}
    _state["log"].append(e)
    if len(_state["log"]) > 300:
        _state["log"] = _state["log"][-300:]
    try: _sse_q.put_nowait({"tur":"log", **e})
    except queue.Full: pass


def _sse(data: dict) -> None:
    try: _sse_q.put_nowait(data)
    except queue.Full: pass


def _ist_up(sig: str) -> None:
    k = {"GÜÇLÜ AL":"guclu_al","AL":"al","İZLE":"izle","ZAYIF":"zayif","KAÇIN":"kacin"}.get(sig,"kacin")
    _state["ist"][k] = _state["ist"].get(k,0) + 1


# ── Ana Analiz Döngüsü ────────────────────────────────────

async def _analiz_async(hisseler: list) -> None:
    toplam = len(hisseler)
    _state["ilerleme"].update({"toplam": toplam, "baslangic": time.time()})

    # ── 1. ADIM: TradingView'den toplu teknik veri çek ──
    _log(f"📡 TradingView Screener — {toplam} hisse toplu çekiliyor...")
    _sse({"tur":"asama","mesaj":f"TradingView'den {toplam} hisse indiriliyor..."})

    loop = asyncio.get_event_loop()

    try:
        tv_cache = await loop.run_in_executor(
            None, df_mod.fetch_tv_batch, hisseler
        )
        bulunan = len(tv_cache)
        _log(f"✓ TradingView: {bulunan}/{toplam} hisse alındı")
        _sse({"tur":"asama","mesaj":f"✓ TradingView: {bulunan} hisse alındı — bilanço ve haberler çekiliyor..."})
    except Exception as e:
        _log(f"✗ TradingView toplu çekim başarısız: {e}", "ERROR")
        _log("⚠ Analiz durduruluyor — İnternet bağlantısını kontrol edin", "ERROR")
        _state["calisıyor"] = False
        _sse({"tur":"tamamlandi","sure":0,"ist":dict(_state["ist"]),"hata":"TradingView bağlantısı yok"})
        return

    # ── 2. ADIM: Endeks değişimi ──
    try:
        endeks_degisim = await loop.run_in_executor(None, df_mod.fetch_endeks_degisim)
        _log(f"📊 BIST100 günlük değişim: {endeks_degisim:+.2f}%")
    except Exception:
        endeks_degisim = 0.0

    # ── 3. ADIM: Hisse hisse bilanço + haber + analiz ──
    sem = asyncio.Semaphore(5)  # Bilanço için 5 paralel istek

    for i, ticker in enumerate(hisseler):
        if _state["durdur"]:
            _log("⛔ Analiz durduruldu.", "WARN")
            break

        _state["ilerleme"].update({"islem": i+1, "aktif": ticker})
        _sse({"tur":"ilerleme","islem":i+1,"toplam":toplam,
              "aktif":ticker,"ist":dict(_state["ist"])})

        try:
            veri = await df_mod.fetch_single_async(ticker, tv_cache, sem)

            tv_data = veri.get("tv_data", {})
            fin     = veri.get("fin", {})
            news    = veri.get("news", [])

            if not tv_data:
                msg = f"— {ticker}: TradingView'de bulunamadı"
                _log(msg, "WARN")
                _state["ist"]["hata"] += 1
                _sse({"tur":"hata","ticker":ticker,"mesaj":msg,
                      "hata_sayisi":_state["ist"]["hata"]})
                continue

            haber_r = ns.analyze_news_sentiment(news)
            sonuc   = anlz.analyze_stock(
                ticker, tv_data, fin, haber_r, endeks_degisim, hl
            )

            if sonuc:
                _state["sonuclar"].append(sonuc)
                _ist_up(sonuc["sinyal"])
                _sse({"tur":"sonuc","veri":sonuc})
                fin_k = fin.get("kaynak","?")
                _log(f"✓ {ticker} → {sonuc['toplam_skor']:.1f} [{sonuc['sinyal']}] RSI:{tv_data.get('RSI',0):.0f} [{fin_k}]")
            else:
                msg = f"— {ticker}: Yetersiz veri"
                _log(msg, "WARN")
                _state["ist"]["hata"] += 1
                _sse({"tur":"hata","ticker":ticker,"mesaj":msg,
                      "hata_sayisi":_state["ist"]["hata"]})

        except Exception as e:
            msg = f"✗ {ticker}: {str(e)[:60]}"
            _log(msg, "ERROR")
            _state["ist"]["hata"] += 1
            _sse({"tur":"hata","ticker":ticker,"mesaj":msg,
                  "hata_sayisi":_state["ist"]["hata"]})

        # Bilanço çekimi için küçük bekleme (rate limit)
        await asyncio.sleep(0.1)

    # ── ✅ SKORA GÖRE SIRALA (En yüksek skor en üstte) ──
    _state["sonuclar"].sort(key=lambda x: x.get("toplam_skor", 0), reverse=True)
    
    sure = time.time() - (_state["ilerleme"]["baslangic"] or time.time())
    _log(f"✅ Tamamlandı! {len(_state['sonuclar'])} hisse · {sure:.0f}s")
    _state["calisıyor"] = False
    _state["ilerleme"]["aktif"] = ""
    _sse({"tur":"tamamlandi","sure":sure,"ist":dict(_state["ist"])})


def _thread(hisseler: list) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_analiz_async(hisseler))
    finally:
        loop.close()


# ── Flask Routes ──────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/analiz/baslat", methods=["POST"])
def baslat():
    if _state["calisıyor"]:
        return jsonify({"hata": "Analiz zaten çalışıyor"}), 409

    data     = request.get_json() or {}
    endeks   = data.get("endeks", "BIST30")
    ozel_raw = data.get("ozel_liste", [])

    if ozel_raw:
        parcalar = []
        for item in (ozel_raw if isinstance(ozel_raw, list) else [ozel_raw]):
            for p in re.split(r"[,\s]+", str(item)):
                p = p.upper().replace(".IS","").replace("BIST:","").strip()
                if p and re.match(r"^[A-Z0-9]{2,8}$", p):
                    parcalar.append(p)
        hisseler = list(dict.fromkeys(parcalar))
    else:
        hisseler = hl.get_hisse_listesi(endeks)

    hisseler = hisseler[:450]
    if not hisseler:
        return jsonify({"hata": "Geçerli hisse kodu bulunamadı"}), 400

    _state.update({
        "calisıyor": True, "durdur": False, "sonuclar": [],
        "ist": {"guclu_al":0,"al":0,"izle":0,"zayif":0,"kacin":0,"hata":0},
        "log": [],
    })
    while not _sse_q.empty():
        try: _sse_q.get_nowait()
        except queue.Empty: break

    _log(f"🚀 Analiz: {endeks} · {len(hisseler)} hisse")
    _log("📡 Kaynak: TradingView (teknik) + İş Yatırım (bilanço) + yfinance (haber)")

    # Bağlantı testi arka planda
    def _test():
        t = df_mod.baglanti_test()
        _log(t["mesaj"])
        if not t["tv"]:
            _log("❌ TradingView'e erişilemiyor! İnternet bağlantısını ve güvenlik duvarını kontrol edin.", "ERROR")
    threading.Thread(target=_test, daemon=True).start()

    threading.Thread(target=_thread, args=(hisseler,), daemon=True).start()
    return jsonify({"durum": "başlatıldı", "hisse_sayisi": len(hisseler)})


@app.route("/api/analiz/durdur", methods=["POST"])
def durdur():
    _state["durdur"] = True
    _state["calisıyor"] = False
    _log("⛔ Durduruldu.", "WARN")
    return jsonify({"durum": "durduruldu"})


@app.route("/api/sonuclar")
def sonuclar():
    return jsonify({
        "sonuclar":  _state["sonuclar"],
        "ist":       _state["ist"],
        "ilerleme":  {k: _state["ilerleme"][k] for k in ("islem","toplam","aktif")},
        "calisıyor": _state["calisıyor"],
    })


@app.route("/analiz")
def stream():
    def gen():
        yield "data: " + json.dumps({"tur":"baglandi"}) + "\n\n"
        # Mevcut sonuçları skora göre sıralı gönder
        sorted_results = sorted(_state["sonuclar"], key=lambda x: x.get("toplam_skor", 0), reverse=True)
        for s in sorted_results:
            yield "data: " + json.dumps({"tur":"sonuc","veri":s}) + "\n\n"
        while True:
            try:
                msg = _sse_q.get(timeout=30)
                yield "data: " + json.dumps(msg) + "\n\n"
                if msg.get("tur") == "tamamlandi":
                    break
            except queue.Empty:
                yield "data: " + json.dumps({"tur":"ping"}) + "\n\n"
    return Response(stream_with_context(gen()), mimetype="text/event-stream",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})


@app.route("/export/csv")
def export_csv():
    import io, csv as cm
    out = io.StringIO()
    w   = cm.writer(out)
    w.writerow(["Hisse","Ad","Endeks","Sektör","Skor","Sinyal","TV Öneri",
                "Fiyat","Değişim%","T","H","K","F","B","D","R","N","M",
                "RSI","Hacim_TL","BB%","Vol_Rel","F/K","PD/DD","Büyüme%",
                "Net_Marj%","OP_Marj%","ROE%","Cari","Borç/Özk",
                "Giriş","Hedef","Stop","Risk%","Pot%","Fin_Kaynak"])
    for s in sorted(_state["sonuclar"], key=lambda x: x["toplam_skor"], reverse=True):
        f = s["f"]
        w.writerow([
            s["ticker"], s["ad"], s["endeks"], s["sektor"],
            s["toplam_skor"], s["sinyal"], s.get("tv_oneri",""),
            s["fiyat"], s["gunluk_degisim"],
            s["t"]["skor"], s["h"]["skor"], s["k"]["skor"], f["skor"],
            s["b"]["skor"], s["d"]["skor"], s["r"]["skor"],
            s["n"]["skor"], s["m"]["skor"],
            s["t"]["rsi"], s["h"].get("gunluk_hacim_tl",""),
            s["b"]["bb_pos"], s["h"].get("vol_relative",""),
            f.get("fk",""), f.get("pddd",""), f.get("buyume",""),
            f.get("net_marj",""), f.get("op_marj",""), f.get("roe",""),
            f.get("cur_ratio",""), f.get("borc_ozkaynak",""),
            s["ghs"]["giris"], s["ghs"]["hedef"], s["ghs"]["stop"],
            s["ghs"]["risk_pct"], s["ghs"]["potansiyel_pct"],
            f.get("fin_kaynak",""),
        ])
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=bist_v3_{ts}.csv"})


# ════════════════════════════════════════════════════════
# HTML / CSS / JS
# ════════════════════════════════════════════════════════
HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BIST Analyzer v3 — TradingView + İş Yatırım</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;700&family=Syne:wght@400;600;700;800&display=swap');
:root{
  --bg:#060c14;--bg2:#0b1521;--bg3:#101e2e;--bg4:#162438;
  --border:#1b3050;--border2:#244060;
  --text:#bdd4ec;--text2:#6a95b8;--text3:#3d6080;
  --acc:#00d4ff;--acc2:#0099cc;
  --ga:#00e676;--al:#4caf50;--iz:#ffc107;--zy:#ff9800;--ka:#f44336;
  --mono:'JetBrains Mono',monospace;--sans:'Syne',sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:14px;min-height:100vh}
body::before{content:'';position:fixed;inset:0;
  background:radial-gradient(ellipse at 15% 50%,rgba(0,153,204,.05) 0%,transparent 55%),
             radial-gradient(ellipse at 85% 10%,rgba(0,212,255,.03) 0%,transparent 45%),
             repeating-linear-gradient(0deg,transparent,transparent 39px,rgba(27,48,80,.2) 40px),
             repeating-linear-gradient(90deg,transparent,transparent 79px,rgba(27,48,80,.1) 80px);
  pointer-events:none;z-index:0}
.wrap{position:relative;z-index:1;max-width:1700px;margin:0 auto;padding:0 14px}
header{background:linear-gradient(180deg,rgba(0,153,204,.08) 0%,transparent 100%);
  border-bottom:1px solid var(--border);padding:12px 0;
  position:sticky;top:0;z-index:100;backdrop-filter:blur(14px)}
.h-inner{display:flex;align-items:center;gap:20px;flex-wrap:wrap}
.logo{display:flex;align-items:center;gap:11px}
.logo-box{width:34px;height:34px;background:linear-gradient(135deg,var(--acc2),var(--acc));
  border-radius:8px;display:flex;align-items:center;justify-content:center;
  font:700 17px/1 var(--mono);color:#000;box-shadow:0 0 18px rgba(0,212,255,.3)}
.logo-title{font-size:18px;font-weight:800;letter-spacing:-.5px;
  background:linear-gradient(90deg,var(--acc),#e0f4ff);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.logo-sub{font-size:9.5px;color:var(--text3);font-family:var(--mono);margin-top:1px}
.h-acts{margin-left:auto;display:flex;gap:7px}
.btn{padding:7px 18px;border:none;border-radius:7px;font-family:var(--sans);font-size:12px;
  font-weight:700;cursor:pointer;transition:all .18s;display:inline-flex;align-items:center;gap:5px;white-space:nowrap}
.btn-p{background:linear-gradient(135deg,var(--acc2),var(--acc));color:#000;box-shadow:0 0 18px rgba(0,212,255,.18)}
.btn-p:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 4px 22px rgba(0,212,255,.38)}
.btn-d{background:rgba(244,67,54,.13);color:var(--ka);border:1px solid rgba(244,67,54,.28)}
.btn-d:hover:not(:disabled){background:rgba(244,67,54,.22)}
.btn-sm{padding:5px 11px;font-size:11px;border-radius:6px}
.btn-g{background:transparent;border:1px solid var(--border2);color:var(--text2)}
.btn-g:hover{border-color:var(--acc2);color:var(--acc)}
.btn:disabled{opacity:.35;cursor:not-allowed}
.yasal{background:rgba(244,67,54,.07);border:1px solid rgba(244,67,54,.18);
  border-radius:8px;padding:7px 14px;font-size:11px;color:var(--text3);
  text-align:center;margin:12px 0 8px}
.ctrl{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:14px 18px;margin-bottom:10px}
.ctrl-row{display:flex;align-items:flex-end;gap:10px;flex-wrap:wrap}
.ctrl-g{display:flex;flex-direction:column;gap:3px}
.ctrl-l{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.6px;font-family:var(--mono)}
select,.txt{background:var(--bg3);border:1px solid var(--border2);color:var(--text);
  border-radius:6px;padding:6px 9px;font-family:var(--mono);font-size:12px;cursor:pointer;outline:none;transition:border-color .2s}
select:focus,.txt:focus{border-color:var(--acc)}
input[type=range]{background:var(--bg3);border:1px solid var(--border2);border-radius:6px;padding:3px 6px;cursor:pointer;accent-color:var(--acc2)}
.prog{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:13px 18px;margin-bottom:10px;display:none}
.prog.on{display:block}
.prog-hdr{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
.prog-bar-w{background:var(--bg4);border-radius:3px;height:3px;overflow:hidden;margin-bottom:9px}
.prog-bar-f{height:100%;background:linear-gradient(90deg,var(--acc2),var(--acc));border-radius:3px;transition:width .4s;box-shadow:0 0 7px rgba(0,212,255,.4)}
.prog-st{display:flex;gap:14px;flex-wrap:wrap;align-items:center}
.stb{display:flex;align-items:center;gap:5px;font-size:11px;font-family:var(--mono)}
.dot{width:7px;height:7px;border-radius:50%}
.pulse{width:7px;height:7px;border-radius:50%;background:var(--acc);animation:pls 1.2s infinite}
@keyframes pls{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(.8)}}
.abadge{display:inline-flex;align-items:center;gap:5px;
  background:rgba(0,153,204,.1);border:1px solid rgba(0,153,204,.28);
  border-radius:5px;padding:2px 9px;font-family:var(--mono);font-size:12px;color:var(--acc)}
.log-p{background:var(--bg3);border-radius:7px;padding:6px 10px;margin-top:9px;
  max-height:75px;overflow:hidden;font-family:var(--mono);font-size:11px;color:var(--text3)}
.log-e{line-height:1.6}.log-e.warn{color:var(--iz)}.log-e.error{color:var(--ka)}
/* Aşama banner */
.asama-banner{background:rgba(0,153,204,.08);border:1px solid rgba(0,153,204,.2);
  border-radius:7px;padding:7px 12px;font-size:11px;color:var(--acc);
  font-family:var(--mono);margin-bottom:9px;display:none}
.asama-banner.on{display:block}
.card-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:7px;margin-bottom:10px}
.card{background:var(--bg2);border:1px solid var(--border);border-radius:10px;
  padding:11px;text-align:center;cursor:pointer;transition:all .18s}
.card:hover{border-color:var(--border2);transform:translateY(-1px)}
.card.on{border-color:var(--acc2);background:rgba(0,153,204,.07)}
.card-n{font-size:26px;font-weight:800;font-family:var(--mono);line-height:1;margin-bottom:3px}
.card-l{font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--text2)}
.tbl-sec{background:var(--bg2);border:1px solid var(--border);border-radius:12px;overflow:hidden}
.tbl-hdr{padding:10px 15px;border-bottom:1px solid var(--border);
  display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}
.tbl-title{font-size:11px;font-weight:700;color:var(--text2);font-family:var(--mono);text-transform:uppercase;letter-spacing:.5px}
.tbl-w{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:11.5px}
thead th{background:var(--bg3);padding:7px 9px;text-align:left;color:var(--text3);
  font-size:9.5px;text-transform:uppercase;letter-spacing:.4px;cursor:pointer;
  user-select:none;white-space:nowrap;border-bottom:1px solid var(--border);transition:color .18s;font-weight:600}
thead th:hover{color:var(--acc)}
thead th.sa::after{content:" ↑";color:var(--acc)}
thead th.sd::after{content:" ↓";color:var(--acc)}
tbody tr{border-bottom:1px solid rgba(27,48,80,.4);transition:background .1s;cursor:pointer}
tbody tr:hover{background:rgba(0,153,204,.04)}
tbody tr.sel{background:rgba(0,212,255,.07)}
td{padding:6px 9px;white-space:nowrap}
.tk{font-weight:700;color:var(--acc)}
.adc{color:var(--text2);font-size:10.5px;max-width:130px;overflow:hidden;text-overflow:ellipsis}
.eb{display:inline-block;padding:1px 5px;border-radius:3px;font-size:8.5px;font-weight:700}
.sc{font-size:13px;font-weight:800}
.chip{display:inline-block;padding:2px 7px;border-radius:4px;font-size:9.5px;font-weight:700;letter-spacing:.2px}
.pp{color:var(--ga)}.pm{color:var(--ka)}
.hi{color:var(--ga)}.mi{color:var(--iz)}.lo{color:var(--ka)}
.c-ga{color:var(--ga)!important}.c-al{color:var(--al)!important}
.c-iz{color:var(--iz)!important}.c-zy{color:var(--zy)!important}.c-ka{color:var(--ka)!important}
.bg-ga{background:rgba(0,230,118,.1);color:var(--ga)}
.bg-al{background:rgba(76,175,80,.1);color:var(--al)}
.bg-iz{background:rgba(255,193,7,.1);color:var(--iz)}
.bg-zy{background:rgba(255,152,0,.1);color:var(--zy)}
.bg-ka{background:rgba(244,67,54,.1);color:var(--ka)}
.tbl-ft{padding:8px 15px;border-top:1px solid var(--border);
  display:flex;justify-content:space-between;align-items:center;
  font-size:10px;color:var(--text3);font-family:var(--mono)}
.empty{text-align:center;padding:55px 20px;color:var(--text3)}
.empty-ic{font-size:44px;margin-bottom:14px;opacity:.35}
.empty-t{font-size:14px}.empty-a{font-size:11px;margin-top:7px}
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.52);z-index:150;display:none;backdrop-filter:blur(2px)}
.overlay.on{display:block}
.detay{position:fixed;right:-510px;top:0;bottom:0;width:490px;
  background:var(--bg2);border-left:1px solid var(--border);z-index:200;
  transition:right .3s cubic-bezier(.4,0,.2,1);overflow-y:auto;padding:22px}
.detay.on{right:0}
.det-kapat{position:absolute;top:14px;right:14px;background:var(--bg3);
  border:1px solid var(--border2);color:var(--text2);width:28px;height:28px;
  border-radius:6px;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:15px}
.det-ticker{font-size:22px;font-weight:800;color:var(--acc);font-family:var(--mono);margin-bottom:3px}
.det-ad{font-size:12px;color:var(--text2);margin-bottom:14px}
.det-sb{display:flex;align-items:center;gap:14px;margin-bottom:18px;
  padding:14px;background:var(--bg3);border-radius:10px;border:1px solid var(--border)}
.det-sn{font-size:40px;font-weight:800;font-family:var(--mono);line-height:1}
.det-sec{margin-bottom:18px}
.det-st{font-size:9px;text-transform:uppercase;letter-spacing:1px;color:var(--text3);
  font-family:var(--mono);margin-bottom:9px;padding-bottom:5px;border-bottom:1px solid var(--border)}
.br-row{display:flex;align-items:center;gap:7px;margin-bottom:7px}
.br-lbl{width:26px;font-size:9.5px;color:var(--text3);font-family:var(--mono)}
.br-info{flex:1}.br-name{font-size:9px;color:var(--text3);margin-bottom:2px}
.br-wrap{height:5px;background:var(--bg4);border-radius:3px;overflow:hidden}
.br-fill{height:100%;border-radius:3px;transition:width .5s}
.br-val{width:28px;text-align:right;font-size:10.5px;font-family:var(--mono)}
.ghs-g{display:grid;grid-template-columns:1fr 1fr 1fr;gap:7px}
.ghs-b{background:var(--bg3);border:1px solid var(--border);border-radius:7px;padding:9px;text-align:center}
.ghs-l{font-size:8.5px;text-transform:uppercase;color:var(--text3);margin-bottom:3px}
.ghs-v{font-size:14px;font-weight:700;font-family:var(--mono)}
.uy-l{display:flex;flex-direction:column;gap:4px}
.uy-i{background:rgba(255,193,7,.07);border:1px solid rgba(255,193,7,.18);border-radius:5px;padding:5px 9px;font-size:10.5px;color:var(--iz)}
.hbr-i{background:var(--bg3);border-radius:5px;padding:7px 9px;margin-bottom:5px;border-left:3px solid var(--border2)}
.hbr-i.poz{border-left-color:var(--al)}.hbr-i.neg{border-left-color:var(--ka)}
.hbr-t{font-size:10.5px;color:var(--text);line-height:1.4;margin-bottom:3px}
.hbr-m{font-size:9.5px;color:var(--text3);display:flex;gap:9px;font-family:var(--mono)}
.ft{width:100%}.ft tr:nth-child(even) td{background:rgba(27,48,80,.2)}
.ft td{padding:3px 5px;font-size:10.5px;font-family:var(--mono)}
.ft td:first-child{color:var(--text3)}.ft td:last-child{text-align:right;color:var(--text)}
.kb{display:inline-block;padding:2px 6px;border-radius:4px;font-size:9px;font-weight:700}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:3px}
/* TV öneri */
.tv-rec{display:inline-block;padding:1px 6px;border-radius:3px;font-size:9px;font-weight:700}
.tv-sb{background:rgba(0,230,118,.15);color:var(--ga)}
.tv-b{background:rgba(76,175,80,.12);color:var(--al)}
.tv-n{background:rgba(122,155,184,.12);color:var(--text2)}
.tv-s{background:rgba(255,152,0,.12);color:var(--zy)}
.tv-ss{background:rgba(244,67,54,.12);color:var(--ka)}
</style>
</head>
<body>
<header>
  <div class="wrap">
    <div class="h-inner">
      <div class="logo">
        <div class="logo-box">B</div>
        <div>
          <div class="logo-title">BIST Analyzer v3</div>
          <div class="logo-sub">TRADİNGVİEW + İŞ YATIRIM + YF · CANLI TEKNİK · KAP BİLANÇO</div>
        </div>
      </div>
      <div class="h-acts">
        <button class="btn btn-sm btn-g" onclick="exportCSV()">⬇ CSV</button>
        <button class="btn btn-sm btn-g" onclick="favGoster()">⭐ Favoriler</button>
      </div>
    </div>
  </div>
</header>

<div class="wrap" style="padding-top:12px;padding-bottom:50px">
  <div class="yasal">
    ⚠️ Bilgi amaçlıdır, yatırım tavsiyesi değildir. Karar ve sorumluluk yatırımcıya aittir. Stop-loss kullanın.
  </div>

  <!-- KONTROL -->
  <div class="ctrl">
    <div class="ctrl-row">
      <div class="ctrl-g">
        <div class="ctrl-l">Endeks</div>
        <select id="selE">
          <option value="BIST30">BIST 30</option>
          <option value="BIST100">BIST 100</option>
          <option value="BIST100Disi">BIST 100 Dışı</option>
          <option value="TumBIST">Tüm BIST</option>
          <option value="Ozel">Özel Liste</option>
        </select>
      </div>
      <div class="ctrl-g">
        <div class="ctrl-l">Sinyal</div>
        <select id="selS" onchange="tabloGuncelle()">
          <option value="">Tümü</option>
          <option value="GÜÇLÜ AL">🟢 Güçlü Al</option>
          <option value="AL">🟩 Al</option>
          <option value="İZLE">🟡 İzle</option>
          <option value="ZAYIF">🟠 Zayıf</option>
          <option value="KAÇIN">🔴 Kaçın</option>
        </select>
      </div>
      <div class="ctrl-g">
        <div class="ctrl-l">Sektör</div>
        <select id="selSek" onchange="tabloGuncelle()">
          <option value="">Tüm Sektörler</option>
          <option>Bankacılık</option><option>Enerji</option>
          <option>Teknoloji</option><option>Perakende</option>
          <option>Havacılık</option><option>Otomotiv</option>
          <option>Gıda</option><option>Holding</option>
          <option>GYO</option><option>Demir-Çelik</option>
          <option>Madencilik</option><option>Telekomünikasyon</option>
          <option>Diğer</option>
        </select>
      </div>
      <div class="ctrl-g">
        <div class="ctrl-l">Top N</div>
        <select id="selN" onchange="tabloGuncelle()">
          <option value="10">10</option><option value="20">20</option>
          <option value="50">50</option><option value="9999" selected>Tümü</option>
        </select>
      </div>
      <div class="ctrl-g">
        <div class="ctrl-l">Ara</div>
        <input type="text" id="inpAra" class="txt" style="width:130px"
               placeholder="THYAO..." oninput="tabloGuncelle()">
      </div>
      <div class="ctrl-g">
        <div class="ctrl-l" id="lblH">Min Hacim: 0M ₺</div>
        <input type="range" id="slH" min="0" max="100" step="5" value="0"
               oninput="hacimG(this.value)">
      </div>
      <div style="display:flex;gap:7px;margin-left:auto;align-items:flex-end">
        <button class="btn btn-p" id="btnB" onclick="analizBaslat()">▶ ANALİZ ET</button>
        <button class="btn btn-d" id="btnD" onclick="analizDurdur()" disabled>■ DURDUR</button>
      </div>
    </div>
    <div id="ozelDiv" style="display:none;margin-top:10px">
      <div class="ctrl-l" style="margin-bottom:3px">Hisse Kodları (virgül veya boşlukla)</div>
      <input type="text" id="inpOzel" class="txt" style="width:340px"
             placeholder="THYAO, GARAN, EREGL, AKBNK ...">
    </div>
  </div>

  <!-- PROGRESS -->
  <div class="prog" id="prog">
    <div class="prog-hdr">
      <div style="display:flex;align-items:center;gap:10px">
        <span id="progTxt" style="font-size:12px;color:var(--text2)">Hazırlanıyor...</span>
        <div class="abadge" id="abadge" style="display:none">
          <div class="pulse"></div><span id="aktifT">—</span>
        </div>
      </div>
      <div style="display:flex;align-items:center;gap:12px">
        <span id="hataN" style="font-size:10px;color:var(--ka);font-family:var(--mono)"></span>
        <span id="progP" style="font-size:11px;color:var(--text3);font-family:var(--mono)">0%</span>
      </div>
    </div>
    <div class="asama-banner" id="asamaBanner"></div>
    <div class="prog-bar-w"><div class="prog-bar-f" id="progF" style="width:0%"></div></div>
    <div class="prog-st">
      <div class="stb"><div class="dot" style="background:var(--ga)"></div>Güçlü Al: <b id="sGA">0</b></div>
      <div class="stb"><div class="dot" style="background:var(--al)"></div>Al: <b id="sAl">0</b></div>
      <div class="stb"><div class="dot" style="background:var(--iz)"></div>İzle: <b id="sIz">0</b></div>
      <div class="stb"><div class="dot" style="background:var(--zy)"></div>Zayıf: <b id="sZy">0</b></div>
      <div class="stb"><div class="dot" style="background:var(--ka)"></div>Kaçın: <b id="sKa">0</b></div>
    </div>
    <div class="log-p" id="logP"></div>
  </div>

  <!-- KARTLAR -->
  <div class="card-grid">
    <div class="card" onclick="filtrele('')"><div class="card-n" style="color:var(--text2)" id="cTot">0</div><div class="card-l">Toplam</div></div>
    <div class="card" onclick="filtrele('GÜÇLÜ AL')"><div class="card-n c-ga" id="cGA">0</div><div class="card-l" style="color:var(--ga)">🟢 Güçlü Al</div></div>
    <div class="card" onclick="filtrele('AL')"><div class="card-n c-al" id="cAl">0</div><div class="card-l" style="color:var(--al)">🟩 Al</div></div>
    <div class="card" onclick="filtrele('İZLE')"><div class="card-n c-iz" id="cIz">0</div><div class="card-l" style="color:var(--iz)">🟡 İzle</div></div>
    <div class="card" onclick="filtrele('ZAYIF')"><div class="card-n c-zy" id="cZy">0</div><div class="card-l" style="color:var(--zy)">🟠 Zayıf</div></div>
    <div class="card" onclick="filtrele('KAÇIN')"><div class="card-n c-ka" id="cKa">0</div><div class="card-l" style="color:var(--ka)">🔴 Kaçın</div></div>
  </div>

  <!-- TABLO -->
  <div class="tbl-sec">
    <div class="tbl-hdr">
      <div class="tbl-title">ANALİZ SONUÇLARI</div>
      <span style="font-size:10px;color:var(--text3);font-family:var(--mono)" id="goster">0 hisse</span>
    </div>
    <div class="tbl-w">
      <table id="tbl">
        <thead><tr>
          <th onclick="sirala('ticker')">Hisse</th>
          <th onclick="sirala('ad')">Ad</th>
          <th onclick="sirala('endeks')">Endeks</th>
          <th onclick="sirala('toplam_skor')">Skor</th>
          <th onclick="sirala('sinyal')">Sinyal</th>
          <th onclick="sirala('tv_oneri')" title="TradingView Öneri">TV</th>
          <th onclick="sirala('t')" title="Teknik">T</th>
          <th onclick="sirala('h')" title="Hacim">H</th>
          <th onclick="sirala('k')" title="Trend">K</th>
          <th onclick="sirala('f')" title="Finansal">F</th>
          <th onclick="sirala('b')" title="Bollinger">B</th>
          <th onclick="sirala('d')" title="Destek">D</th>
          <th onclick="sirala('r')" title="Risk">R</th>
          <th onclick="sirala('n')" title="Haber">N</th>
          <th onclick="sirala('m')" title="Piyasa">M</th>
          <th onclick="sirala('fiyat')">Fiyat</th>
          <th onclick="sirala('rsi')">RSI</th>
          <th onclick="sirala('hacim')">Hacim</th>
          <th onclick="sirala('bb')">BB%</th>
          <th onclick="sirala('degisim')">Değişim</th>
          <th onclick="sirala('fk')">F/K</th>
          <th onclick="sirala('pddd')">PD/DD</th>
          <th onclick="sirala('marj')">Marj%</th>
          <th onclick="sirala('buyume')">Büy%</th>
          <th>Saat</th>
        </tr></thead>
        <tbody id="tbody">
          <tr><td colspan="25">
            <div class="empty">
              <div class="empty-ic">📊</div>
              <div class="empty-t">Analiz bekleniyor</div>
              <div class="empty-a">Endeks seçip ANALİZ ET butonuna basın — TradingView canlı veri ile saniyeler içinde başlar</div>
            </div>
          </td></tr>
        </tbody>
      </table>
    </div>
    <div class="tbl-ft">
      <span id="tblAlt">—</span><span id="sonG">—</span>
    </div>
  </div>
</div>

<div class="overlay" id="overlay" onclick="detayKapat()"></div>
<div class="detay" id="detay">
  <button class="det-kapat" onclick="detayKapat()">✕</button>
  <div id="detayIc"></div>
</div>

<script>
let tumS=[], filtS=[], sortK='toplam_skor', sortY='desc', minH=0;
let es=null, favs=JSON.parse(localStorage.getItem('bist_v3_fav')||'[]'), saatler={};
const RC={'GÜÇLÜ AL':'ga','AL':'al','İZLE':'iz','ZAYIF':'zy','KAÇIN':'ka'};
const EC={'BIST30':'#00d4ff','BIST100':'#4caf50','BIST+':'#6a95b8'};

document.getElementById('selE').addEventListener('change',e=>{
  document.getElementById('ozelDiv').style.display=e.target.value==='Ozel'?'block':'none';
});

async function analizBaslat(){
  const endeks=document.getElementById('selE').value;
  let ozel=[];
  if(endeks==='Ozel'){
    const raw=document.getElementById('inpOzel').value;
    ozel=raw.split(/[,\s]+/).map(s=>s.trim().toUpperCase().replace('.IS','').replace('BIST:','')).filter(s=>s.length>=2);
    if(!ozel.length){alert('Geçerli hisse kodu girin');return;}
  }
  document.getElementById('btnB').disabled=true;
  document.getElementById('btnD').disabled=false;
  document.getElementById('prog').classList.add('on');
  document.getElementById('abadge').style.display='flex';
  tumS=[];filtS=[];saatler={};
  tabloTemizle();kartG();
  if(es){es.close();}
  try{
    const res=await fetch('/api/analiz/baslat',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({endeks,ozel_liste:ozel})
    });
    if(!res.ok){const e=await res.json();alert('Hata: '+(e.hata||'?'));analizBitti();return;}
    const d=await res.json();
    document.getElementById('progTxt').textContent=`${endeks} — ${d.hisse_sayisi} hisse`;
    es=new EventSource('/analiz');
    es.onmessage=sseOlay;
    es.onerror=()=>{};
  }catch(e){alert('Bağlantı hatası: '+e.message);analizBitti();}
}

async function analizDurdur(){
  await fetch('/api/analiz/durdur',{method:'POST'});
  if(es)es.close();analizBitti();
}

function analizBitti(){
  document.getElementById('btnB').disabled=false;
  document.getElementById('btnD').disabled=true;
  document.getElementById('abadge').style.display='none';
  document.getElementById('aktifT').textContent='—';
  document.getElementById('sonG').textContent='Son: '+new Date().toLocaleTimeString('tr-TR');
}

function sseOlay(ev){
  const msg=JSON.parse(ev.data);
  switch(msg.tur){
    case 'asama':
      const b=document.getElementById('asamaBanner');
      b.textContent=msg.mesaj;b.classList.add('on');
      break;
    case 'hata':
      logEkle(msg.mesaj||('⚠ '+msg.ticker),'error');
      const he=document.getElementById('hataN');
      if(he)he.textContent=(msg.hata_sayisi||0)+' hata';
      break;
    case 'sonuc':
      const s=msg.veri;
      saatler[s.ticker]=new Date().toLocaleTimeString('tr-TR',{hour:'2-digit',minute:'2-digit'});
      tumS.push(s);tabloGuncelle();kartG();
      break;
    case 'ilerleme':
      const pct=msg.toplam>0?Math.round(msg.islem/msg.toplam*100):0;
      document.getElementById('progF').style.width=pct+'%';
      document.getElementById('progP').textContent=pct+'%';
      document.getElementById('progTxt').textContent=`${msg.islem} / ${msg.toplam}`;
      document.getElementById('aktifT').textContent=msg.aktif;
      if(msg.ist){
        document.getElementById('sGA').textContent=msg.ist.guclu_al||0;
        document.getElementById('sAl').textContent=msg.ist.al||0;
        document.getElementById('sIz').textContent=msg.ist.izle||0;
        document.getElementById('sZy').textContent=msg.ist.zayif||0;
        document.getElementById('sKa').textContent=msg.ist.kacin||0;
      }
      break;
    case 'log':
      logEkle(msg.mesaj,msg.seviye==='WARN'?'warn':msg.seviye==='ERROR'?'error':'');
      break;
    case 'tamamlandi':
      logEkle('✅ Tamamlandı! '+tumS.length+' hisse · '+Math.round(msg.sure)+'s');
      document.getElementById('asamaBanner').classList.remove('on');
      if(es)es.close();analizBitti();
      break;
  }
}

function logEkle(msg,cls=''){
  const p=document.getElementById('logP');
  const d=document.createElement('div');
  d.className='log-e '+cls;
  d.textContent='['+new Date().toLocaleTimeString('tr-TR')+'] '+msg;
  p.insertBefore(d,p.firstChild);
  while(p.children.length>6)p.removeChild(p.lastChild);
}

function tabloGuncelle(){
  const sin=document.getElementById('selS').value;
  const sek=document.getElementById('selSek').value;
  const ara=document.getElementById('inpAra').value.toUpperCase().trim();
  const topN=parseInt(document.getElementById('selN').value);
  filtS=tumS.filter(s=>{
    if(sin&&s.sinyal!==sin)return false;
    if(sek&&s.sektor!==sek)return false;
    if(ara&&!s.ticker.includes(ara)&&!s.ad.toUpperCase().includes(ara))return false;
    if(minH>0&&(s.h.gunluk_hacim_tl||0)<minH*1e6)return false;
    return true;
  });
  filtS.sort((a,b)=>{
    let va=getSV(a,sortK),vb=getSV(b,sortK);
    if(typeof va==='string')return sortY==='asc'?va.localeCompare(vb):vb.localeCompare(va);
    return sortY==='asc'?va-vb:vb-va;
  });
  const goster=filtS.slice(0,topN);
  renderT(goster);
  document.getElementById('goster').textContent=goster.length+' / '+filtS.length+' hisse';
  document.getElementById('tblAlt').textContent='Toplam: '+tumS.length+' hisse';
}

function getSV(s,k){
  const m={
    ticker:s.ticker,ad:s.ad,endeks:s.endeks,sinyal:s.sinyal,
    toplam_skor:s.toplam_skor,tv_oneri:s.tv_oneri||0,
    t:s.t.skor,h:s.h.skor,k:s.k.skor,f:s.f.skor,
    b:s.b.skor,d:s.d.skor,r:s.r.skor,n:s.n.skor,m:s.m.skor,
    fiyat:s.fiyat,rsi:s.t.rsi,hacim:s.h.gunluk_hacim_tl||0,
    bb:s.b.bb_pos,degisim:s.gunluk_degisim,
    fk:s.f.fk??999,pddd:s.f.pddd??999,
    marj:s.f.net_marj??-99,buyume:s.f.buyume??-999,
  };
  return m[k]??s.toplam_skor;
}

function tvRecHtml(v){
  if(v===null||v===undefined||v==='')return '—';
  const n=parseFloat(v);
  if(n>=0.5) return '<span class="tv-rec tv-sb">G.AL</span>';
  if(n>=0.1) return '<span class="tv-rec tv-b">AL</span>';
  if(n>=-0.1)return '<span class="tv-rec tv-n">NÖT</span>';
  if(n>=-0.5)return '<span class="tv-rec tv-s">SAT</span>';
  return '<span class="tv-rec tv-ss">G.SAT</span>';
}

function renderT(liste){
  const tbody=document.getElementById('tbody');
  if(!liste.length){
    tbody.innerHTML=`<tr><td colspan="25"><div class="empty"><div class="empty-ic">🔍</div><div class="empty-t">Sonuç bulunamadı</div></div></td></tr>`;
    return;
  }
  tbody.innerHTML=liste.map(s=>{
    const rc=RC[s.sinyal]||'ka';
    const ec=EC[s.endeks]||'#6a95b8';
    const dpc=s.gunluk_degisim>=0?'pp':'pm';
    const dps=(s.gunluk_degisim>=0?'+':'')+s.gunluk_degisim.toFixed(2)+'%';
    const sc=s.toplam_skor>=72?'c-ga':s.toplam_skor>=60?'c-al':s.toplam_skor>=50?'c-iz':s.toplam_skor>=40?'c-zy':'c-ka';
    const fav=favs.includes(s.ticker)?'⭐':'☆';
    return `<tr onclick="detayAc('${s.ticker}')" data-ticker="${s.ticker}">
      <td class="tk"><span onclick="event.stopPropagation();favT('${s.ticker}')" style="cursor:pointer;opacity:.5;margin-right:3px">${fav}</span>${s.ticker}</td>
      <td class="adc" title="${s.ad}">${s.ad}</td>
      <td><span class="eb" style="color:${ec};background:${ec}18">${s.endeks}</span></td>
      <td class="sc ${sc}">${s.toplam_skor.toFixed(1)}</td>
      <td><span class="chip bg-${rc}">${s.sinyal}</span></td>
      <td>${tvRecHtml(s.tv_oneri)}</td>
      ${pc(s.t.skor)}${pc(s.h.skor)}${pc(s.k.skor)}${pc(s.f.skor)}
      ${pc(s.b.skor)}${pc(s.d.skor)}${pc(s.r.skor)}${pc(s.n.skor)}${pc(s.m.skor)}
      <td>${s.fiyat.toFixed(2)}<br><span class="${dpc}" style="font-size:9.5px">${dps}</span></td>
      <td class="${s.t.rsi<30?'c-ga':s.t.rsi>70?'c-ka':''}">${s.t.rsi.toFixed(0)}</td>
      <td>${fmtH(s.h.gunluk_hacim_tl)}</td>
      <td>${(s.b.bb_pos*100).toFixed(0)}%</td>
      <td class="${s.gunluk_degisim>=0?'pp':'pm'}">${s.gunluk_degisim>=0?'+':''}${s.gunluk_degisim.toFixed(2)}%</td>
      <td>${s.f.fk!=null?s.f.fk.toFixed(1):'—'}</td>
      <td>${s.f.pddd!=null?s.f.pddd.toFixed(2):'—'}</td>
      <td class="${(s.f.net_marj||0)>=0?'pp':'pm'}">${s.f.net_marj!=null?s.f.net_marj.toFixed(1)+'%':'—'}</td>
      <td class="${(s.f.buyume||0)>=0?'pp':'pm'}">${s.f.buyume!=null?(s.f.buyume>=0?'+':'')+s.f.buyume.toFixed(1)+'%':'—'}</td>
      <td style="color:var(--text3);font-size:9.5px">${saatler[s.ticker]||'—'}</td>
    </tr>`;
  }).join('');
}

function pc(v){const c=v>=7?'hi':v>=5?'mi':'lo';return `<td class="${c}">${v.toFixed(1)}</td>`;}
function fmtH(tl){if(!tl)return '—';if(tl>=1e9)return (tl/1e9).toFixed(1)+'B';if(tl>=1e6)return (tl/1e6).toFixed(1)+'M';if(tl>=1e3)return (tl/1e3).toFixed(0)+'K';return tl.toFixed(0);}
function tabloTemizle(){document.getElementById('tbody').innerHTML=`<tr><td colspan="25"><div class="empty"><div class="empty-ic">⏳</div><div class="empty-t">TradingView'den veri indiriliyor...</div></div></td></tr>`;}
function sirala(k){sortY=(sortK===k)?(sortY==='asc'?'desc':'asc'):'desc';sortK=k;document.querySelectorAll('thead th').forEach(th=>th.classList.remove('sa','sd'));event.target.classList.add(sortY==='asc'?'sa':'sd');tabloGuncelle();}
function filtrele(s){document.getElementById('selS').value=s;tabloGuncelle();}
function hacimG(v){minH=parseInt(v);document.getElementById('lblH').textContent='Min Hacim: '+v+'M ₺';tabloGuncelle();}
function kartG(){
  const ist={guclu_al:0,al:0,izle:0,zayif:0,kacin:0};
  tumS.forEach(s=>{const k={'GÜÇLÜ AL':'guclu_al','AL':'al','İZLE':'izle','ZAYIF':'zayif','KAÇIN':'kacin'}[s.sinyal]||'kacin';ist[k]++;});
  document.getElementById('cTot').textContent=tumS.length;
  document.getElementById('cGA').textContent=ist.guclu_al;
  document.getElementById('cAl').textContent=ist.al;
  document.getElementById('cIz').textContent=ist.izle;
  document.getElementById('cZy').textContent=ist.zayif;
  document.getElementById('cKa').textContent=ist.kacin;
}

function detayAc(ticker){
  const s=tumS.find(x=>x.ticker===ticker);if(!s)return;
  document.getElementById('overlay').classList.add('on');
  document.getElementById('detay').classList.add('on');
  document.querySelectorAll('tbody tr').forEach(r=>r.classList.remove('sel'));
  const row=document.querySelector(`tr[data-ticker="${ticker}"]`);
  if(row)row.classList.add('sel');
  const rc=RC[s.sinyal]||'ka';
  const sc=s.toplam_skor>=72?'var(--ga)':s.toplam_skor>=60?'var(--al)':s.toplam_skor>=50?'var(--iz)':s.toplam_skor>=40?'var(--zy)':'var(--ka)';
  const params=[
    {l:'T',v:s.t.skor,n:'Teknik Momentum (%22)'},
    {l:'H',v:s.h.skor,n:'Hacim Analizi (%18)'},
    {l:'K',v:s.k.skor,n:'Kısa Vade Trend (%18)'},
    {l:'F',v:s.f.skor,n:'Finansal Sağlık (%12)'},
    {l:'B',v:s.b.skor,n:'Bollinger Bant (%8)'},
    {l:'D',v:s.d.skor,n:'Destek/Direnç (%5)'},
    {l:'R',v:s.r.skor,n:'Risk/Ödül (%5)'},
    {l:'N',v:s.n.skor,n:'Haber/Katalist (%7)'},
    {l:'M',v:s.m.skor,n:'Piyasa Bağlamı (%5)'},
  ];
  const barH=params.map(p=>{const c=p.v>=7?'#4caf50':p.v>=5?'#ffc107':'#f44336';return `<div class="br-row"><div class="br-lbl">${p.l}</div><div class="br-info"><div class="br-name">${p.n}</div><div class="br-wrap"><div class="br-fill" style="width:${p.v*10}%;background:${c}"></div></div></div><div class="br-val" style="color:${c}">${p.v.toFixed(1)}</div></div>`;}).join('');
  const uyH=s.uyarilar.length?`<div class="uy-l">${s.uyarilar.map(u=>`<div class="uy-i">${u}</div>`).join('')}</div>`:`<div style="color:var(--text3);font-size:11px">Önemli uyarı yok</div>`;
  const hbrH=(s.n.haberler||[]).length?s.n.haberler.map(h=>{const hc=h.sentiment.includes('pozitif')?'poz':h.sentiment.includes('negatif')?'neg':'';return `<div class="hbr-i ${hc}"><div class="hbr-t">${h.baslik}</div><div class="hbr-m"><span>${h.tarih}</span><span style="color:${hc==='poz'?'var(--al)':hc==='neg'?'var(--ka)':'var(--text3)'}">${h.sentiment}</span><span>${h.skor>0?'+':''}${h.skor}</span></div></div>`;}).join(''):`<div style="color:var(--text3);font-size:11px">Haber bulunamadı</div>`;
  const ghs=s.ghs;const f=s.f;
  const finK=f.fin_kaynak==='isyatirim'?`<span class="kb" style="background:rgba(0,230,118,.1);color:var(--ga)">İŞY ✓</span>`:`<span class="kb" style="background:rgba(255,193,7,.1);color:var(--iz)">TV</span>`;
  document.getElementById('detayIc').innerHTML=`
    <div class="det-ticker">${s.ticker}</div>
    <div class="det-ad">${s.ad} · ${s.endeks} · ${s.sektor} · ${f.son_donem||'?'} ${finK}</div>
    <div class="det-sb">
      <div class="det-sn" style="color:${sc}">${s.toplam_skor.toFixed(1)}</div>
      <div>
        <span class="chip bg-${rc}" style="font-size:12px;padding:4px 12px">${s.sinyal}</span>
        <div style="margin-top:4px;font-size:11px;color:var(--text3)">TV Öneri: ${tvRecHtml(s.tv_oneri)}</div>
        <div style="margin-top:6px;font-size:12px;color:var(--text3)">
          Fiyat: <b style="color:var(--text)">${s.fiyat.toFixed(2)} ₺</b>
          <span class="${s.gunluk_degisim>=0?'pp':'pm'}" style="margin-left:7px">${s.gunluk_degisim>=0?'+':''}${s.gunluk_degisim.toFixed(2)}%</span>
        </div>
      </div>
    </div>
    <div class="det-sec"><div class="det-st">Parametre Skorları</div>${barH}</div>
    <div class="det-sec">
      <div class="det-st">Teknik Göstergeler (TradingView Canlı)</div>
      <table class="ft">
        <tr><td>RSI(14)</td><td style="color:${s.t.rsi<30?'var(--ga)':s.t.rsi>70?'var(--ka)':'var(--text)'}">${s.t.rsi.toFixed(1)}</td></tr>
        <tr><td>MACD Line</td><td class="${s.t.macd_macd>=0?'pp':'pm'}">${s.t.macd_macd.toFixed(4)}</td></tr>
        <tr><td>MACD Signal</td><td>${s.t.macd_signal.toFixed(4)}</td></tr>
        <tr><td>MACD Histogram</td><td class="${s.t.macd_hist>=0?'pp':'pm'}">${s.t.macd_hist.toFixed(4)}</td></tr>
        <tr><td>StochRSI K</td><td>${s.t.stochrsi.toFixed(1)}</td></tr>
        <tr><td>Williams %R</td><td>${s.t.williams_r.toFixed(1)}</td></tr>
        <tr><td>EMA5 / EMA10 / EMA20</td><td>${[s.k.ema5,s.k.ema10,s.k.ema21].map(v=>v!=null?v.toFixed(2):'—').join(' / ')}</td></tr>
        <tr><td>BB Alt / Orta / Üst</td><td>${[s.b.bb_lower,s.b.bb_middle,s.b.bb_upper].map(v=>v!=null?v.toFixed(2):'—').join(' / ')}</td></tr>
        <tr><td>BB Pozisyon</td><td>${(s.b.bb_pos*100).toFixed(1)}%${s.b.squeeze?' ⚡ Sıkışma':''}</td></tr>
        <tr><td>Hacim (₺)</td><td>${fmtH(s.h.gunluk_hacim_tl)}</td></tr>
        <tr><td>Göreceli Hacim (10g)</td><td class="${s.h.vol_relative>1.5?'pp':''}">${s.h.vol_relative.toFixed(2)}x</td></tr>
        <tr><td>Günlük Değişim</td><td class="${s.gunluk_degisim>=0?'pp':'pm'}">${s.gunluk_degisim>=0?'+':''}${s.gunluk_degisim.toFixed(2)}%</td></tr>
        <tr><td>EMA20'ye Uzaklık</td><td>${s.d.ema21_uzaklik_pct>=0?'+':''}${s.d.ema21_uzaklik_pct.toFixed(2)}%</td></tr>
      </table>
    </div>
    <div class="det-sec">
      <div class="det-st">Finansal Özet ${finK} ${f.son_donem?'· '+f.son_donem:''}</div>
      <table class="ft">
        <tr><td>F/K (P/E)</td><td>${f.fk!=null?f.fk.toFixed(2):'—'}</td></tr>
        <tr><td>PD/DD (P/B)</td><td>${f.pddd!=null?f.pddd.toFixed(2):'—'}</td></tr>
        <tr><td>Borç/Özkaynak</td><td>${f.borc_ozkaynak!=null?f.borc_ozkaynak.toFixed(1)+'%':'—'}</td></tr>
        <tr><td>Net Kâr Marjı</td><td class="${(f.net_marj||0)>=0?'pp':'pm'}">${f.net_marj!=null?f.net_marj.toFixed(1)+'%':'—'}</td></tr>
        <tr><td>FAVÖK Marjı</td><td>${f.op_marj!=null?f.op_marj.toFixed(1)+'%':'—'}</td></tr>
        <tr><td>ROE</td><td>${f.roe!=null?f.roe.toFixed(1)+'%':'—'}</td></tr>
        <tr><td>Cari Oran</td><td>${f.cur_ratio!=null?f.cur_ratio.toFixed(2):'—'}</td></tr>
        <tr><td>Net Kâr Büyümesi (YoY)</td><td class="${(f.buyume||0)>=0?'pp':'pm'}">${f.buyume!=null?(f.buyume>=0?'+':'')+f.buyume.toFixed(1)+'%':'—'}</td></tr>
        <tr><td>Veri Kalitesi</td><td style="color:${f.eksik_veri>3?'var(--ka)':'var(--text3)'}">%${Math.round(s.veri_kalite*100)}</td></tr>
      </table>
    </div>
    <div class="det-sec">
      <div class="det-st">📈 Giriş / Hedef / Stop</div>
      <div class="ghs-g">
        <div class="ghs-b"><div class="ghs-l">Giriş</div><div class="ghs-v c-iz">${ghs.giris.toFixed(2)}</div></div>
        <div class="ghs-b"><div class="ghs-l">Hedef (+${ghs.potansiyel_pct.toFixed(1)}%)</div><div class="ghs-v c-ga">${ghs.hedef.toFixed(2)}</div></div>
        <div class="ghs-b"><div class="ghs-l">Stop (-${ghs.risk_pct.toFixed(1)}%)</div><div class="ghs-v c-ka">${ghs.stop.toFixed(2)}</div></div>
      </div>
      <div style="margin-top:9px;font-size:10.5px;color:var(--text3);text-align:center">
        R/R: <b style="color:var(--text)">${ghs.rr_oran.toFixed(2)}</b>
        &nbsp;·&nbsp; Risk: <b class="c-ka">${ghs.risk_pct.toFixed(1)}%</b>
        &nbsp;·&nbsp; Potansiyel: <b class="c-ga">${ghs.potansiyel_pct.toFixed(1)}%</b>
      </div>
    </div>
    <div class="det-sec"><div class="det-st">⚠️ Uyarılar</div>${uyH}</div>
    <div class="det-sec">
      <div class="det-st">📰 Son Haberler (7 gün · yfinance)</div>
      <div style="margin-bottom:7px;font-size:10.5px;color:var(--text3)">
        ${s.n.pozitif||0} pozitif · ${s.n.negatif||0} negatif · Etki: ${(s.n.ham_skor||0)>=0?'+':''}${s.n.ham_skor||0}
      </div>${hbrH}
    </div>
    <div style="margin-top:18px;padding-top:14px;border-top:1px solid var(--border)">
      <button class="btn btn-g btn-sm" style="width:100%" id="btnFav"
        onclick="favT('${s.ticker}');document.getElementById('btnFav').textContent=favs.includes('${s.ticker}')?'⭐ Favorilerden Çıkar':'☆ Favorilere Ekle'">
        ${favs.includes(s.ticker)?'⭐ Favorilerden Çıkar':'☆ Favorilere Ekle'}
      </button>
    </div>`;
}

function detayKapat(){
  document.getElementById('overlay').classList.remove('on');
  document.getElementById('detay').classList.remove('on');
  document.querySelectorAll('tbody tr').forEach(r=>r.classList.remove('sel'));
}

function favT(t){
  const i=favs.indexOf(t);
  if(i>=0)favs.splice(i,1);else favs.push(t);
  localStorage.setItem('bist_v3_fav',JSON.stringify(favs));
  tabloGuncelle();
}

function favGoster(){alert('Favorileriniz:\n'+(favs.join(', ')||'Henüz yok'));}
function exportCSV(){if(!tumS.length){alert('Önce analiz çalıştırın');return;}window.location.href='/export/csv';}
document.addEventListener('keydown',e=>{if(e.key==='Escape')detayKapat();});
</script>
</body>
</html>"""


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5001))
    logger.info("=" * 55)
    logger.info("BIST Analyzer v3 başlatılıyor...")
    logger.info(f"Adres  : http://localhost:{port}")
    logger.info("Teknik : TradingView Screener (canlı)")
    logger.info("Bilanço: İş Yatırım (KAP)")
    logger.info("Haber  : yfinance")
    logger.info("=" * 55)

    def _browser():
        import time as _t; _t.sleep(1.8)
        webbrowser.open(f"http://localhost:{port}")

    threading.Thread(target=_browser, daemon=True).start()
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
