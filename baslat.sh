#!/usr/bin/env bash
cd "$(dirname "$0")"
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║     BIST Analyzer v3 — TradingView + İş Yatırım     ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3 bulunamadı"; exit 1; }
echo "✓ $(python3 --version)"
if [ ! -d "venv" ]; then
    echo "→ Sanal ortam oluşturuluyor..."
    python3 -m venv venv
fi
source venv/bin/activate 2>/dev/null || . venv/Scripts/activate 2>/dev/null || true
echo "→ Paketler yükleniyor..."
pip install -r requirements.txt -q --upgrade
echo ""
echo "✅ http://localhost:5001 açılıyor..."
echo ""
python3 app.py
