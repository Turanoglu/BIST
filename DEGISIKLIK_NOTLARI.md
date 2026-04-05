# BIST Analyzer v3 - Sıralama Güncellemesi

## 📊 Yapılan Değişiklikler

### ✅ Ana Güncelleme: Skor Bazlı Sıralama

Artık hisseler **en yüksek skordan başlayarak** sıralanıyor (alfabetik sıralama kaldırıldı).

**Değişen Dosya:** `app.py`

#### 1️⃣ Backend Sıralama (Satır 157-161)
```python
# ── ✅ SKORA GÖRE SIRALA (En yüksek skor en üstte) ──
_state["sonuclar"].sort(key=lambda x: x.get("toplam_skor", 0), reverse=True)
```
Analiz tamamlandığında tüm sonuçlar **toplam_skor**'a göre büyükten küçüğe sıralanıyor.

#### 2️⃣ SSE Stream Sıralama (Satır 249-254)
```python
# Mevcut sonuçları skora göre sıralı gönder
sorted_results = sorted(_state["sonuclar"], key=lambda x: x.get("toplam_skor", 0), reverse=True)
for s in sorted_results:
    yield "data: " + json.dumps({"tur":"sonuc","veri":s}) + "\n\n"
```
SSE bağlantısı açıldığında mevcut sonuçlar da sıralı şekilde iletiliyor.

---

## 🚀 Kullanım

### Kurulum (Değişiklik Yok)
```bash
# Linux/Mac/Windows Git Bash:
./baslat.sh

# Windows CMD/PowerShell:
python app.py
```

### Davranış
- **Analiz sırasında:** Hisseler işlendikçe tabloya ekleniyor
- **Analiz bitince:** Tüm hisseler **SKORA göre** otomatik sıralanıyor
- **Yeni bağlantıda:** SSE stream başladığında sonuçlar **zaten sıralı** geliyor

**Sıralama düzeni:**
- 🟢 **GÜÇLÜ AL** (≥72) → En üstte
- 🟢 **AL** (≥60)
- 🟡 **İZLE** (≥50)
- 🟠 **ZAYIF** (≥40)
- 🔴 **KAÇIN** (<40) → En altta

---

## 📦 Dosya Listesi

- ✅ `app.py` → **GÜNCELLENDİ** (sıralama eklendi)
- `analyzer.py` → Değişiklik yok
- `data_fetcher.py` → Değişiklik yok
- `hisse_listesi.py` → Değişiklik yok
- `news_scorer.py` → Değişiklik yok
- `requirements.txt` → Değişiklik yok
- `baslat.sh` → Değişiklik yok

---

## 🔄 GitHub'a Yükleme (Render Deploy için)

```bash
# Güncellenmiş dosyaları GitHub'a push et:
git add app.py
git commit -m "Skor bazlı sıralama eklendi - en yüksek skor üstte"
git push origin main

# Render otomatik deploy edecek (5-10 dk)
```

---

## ✨ Test

Analiz çalıştır → **En yüksek skorlu hisseler listenin en üstünde görünecek!**

**Örnek:**
```
AKBNK → 82.8 → GÜÇLÜ AL ← En üstte
AKGSY → 81.2 → GÜÇLÜ AL
ALCTL → 76.3 → GÜÇLÜ AL
...
ADEL  → 34.1 → KAÇIN     ← En altta
```

---

## 📧 Destek

Sorun olursa:
1. Tarayıcıda **F12** → Console sekmesini aç
2. Hata mesajını kontrol et
3. `baslat.sh` çıktısını incele

**Mutlu analizler!** 🚀📊
