# Crypto Sentinel 🛡️

**Crypto Sentinel**, modern yazılım mimarisiyle geliştirilmiş, hibrit (REST + WebSocket) yapıda çalışan, gelişmiş bir **yapay zeka destekli kripto ticaret botudur.**

Bu proje; anlık piyasa verilerini analiz eder, kendi geliştirdiği "Sentinel Score" algoritması ile fırsatları belirler ve Binance üzerinde (proje kapsamında simülasyon olarak) otomatik al-sat işlemleri yapar. Tüm bu süreçte sizi **anlık Telegram bildirimleri** ile haberdar ederken, işlemlerinizi ve performans verilerinizi **güvenli bir veritabanında** saklar. Aynı zamanda "Circuit Breaker" (Akıllı Şalter) ve "Moonbag" gibi risk yönetimi stratejileriyle sermayenizi korur.

---

## 🚀 Öne Çıkan Özellikler

### 🧠 Sentinel Score (Yapay Zeka Puanlaması)
Bot, sadece tek bir indikatöre bakmaz. RSI, MACD, Bollinger Bantları, OBV (Hacim), EMA ve Pivot noktalarını harmanlayarak **0-100** arası bir puan üretir.
*   **> 60 Puan:** 🐂 **LONG** (Yükseliş) Sinyali
*   **< 40 Puan:** 🐻 **SHORT** (Düşüş) Sinyali

### ⚡ Hibrit Mimari
*   **Analiz:** Belirli aralıklarla (Polling) piyasayı tarar ve strateji kurar.
*   **Takip:** İşlem açıldığı an **WebSocket** devreye girer ve fiyatı milisaniyelik gecikmeyle takip eder.

### 🛡️ Risk Yönetimi (Profesyonel Seviye)
*   **Circuit Breaker (Akıllı Şalter):** Günlük belirlenen zarar limitine ulaşılırsa bot kendini kilitler ve "intikam ticareti"ni (revenge trading) engeller.
*   **Phoenix Modu:** Eğer sanal bakiye tükenirse (örn: <10$), sistem otomatik olarak kasayı sıfırlar ve simülasyona devam etmenizi sağlar.
*   **Moonbag Stratejisi:** Yüksek riskli işlemlerde ana para erkenden çekilir, içeride sadece "kar" bırakılır (Free Ride) ve fiyatın "aya gitmesi" (Moon) beklenir.

### 📚 Kripto Sözlüğü ve Bot Mantığı (Nedir, Nasıl Çalışır?)

Bu botu kullanırken karşılaşacağınız terimlerin en basit haliyle açıklamaları:

*   **RSI (Hız Göstergesi):** "Fiyat çok mu şişti yoksa çok mu düştü?" sorusunun cevabıdır.
    *   *Örnek:* RSI 70 üzerine çıkarsa fiyat "pahalı" kabul edilir ve satış sinyali aranır.
*   **MACD (Trend Dedektifi):** Fiyatın yönü yukarı mı aşağı mı? Trendin gücünü ve dönüş sinyallerini yakalar.
*   **Bollinger Bantları (Volatilite):** Fiyatın ne kadar sakin veya hırçın olduğunu ölçer.
    *   *Sıkışma (Squeeze):* Fırtına öncesi sessizliktir. Büyük bir hareketin (patlamanın) habercisidir.
*   **Pivot Noktaları (Görünmez Duvarlar):** Fiyatın çarpıp dönebileceği matematiksel destek ve direnç seviyeleridir. Bot bu seviyelerde kar almayı sever.
*   **ROE (Ana Para Getirisi):** Toplam işlem büyüklüğüne değil, sadece **cebinizden koyduğunuz paraya** (Marjin) göre kar oranınızdır.
*   **Moonbag (Bedava Bilet):** İşlem hedefe ulaştığında ana paranızı ve biraz karı cebinize koyup, kalan küçük bir miktarı "Ay'a giderse zengin olurum" diyerek içeride bırakma stratejisidir.
*   **Circuit Breaker (Sigorta):** Evdeki sigorta gibidir. Eğer o gün çok zarar ederseniz, bot "Bugün şansımız yok" diyerek kendine 8 saatlik bir mola verir. Sizi hırsa kapılıp hata yapmaktan korur.

---


## 🛠️ Kurulum

### Gereksinimler
*   Python 3.9 veya üzeri
*   PostgreSQL (Tercihen Cloud veya Yerel)

### Adım Adım Kurulum

1.  **Projeyi Klonlayın:**
    ```bash
    git clone https://github.com/kullaniciadi/CryptoSentinel.git
    cd CryptoSentinel
    ```

2.  **Sanal Ortam Oluşturun (Önerilen):**
    ```bash
    python -m venv venv
    # Windows:
    .\venv\Scripts\activate
    # Mac/Linux:
    source venv/bin/activate
    ```

3.  **Kütüphaneleri Yükleyin:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Ayarları Yapılandırın:**
    *   `.env.example` dosyasının adını `.env` olarak değiştirin.
    *   İçerisine kendi API anahtarlarınızı ve veritabanı bağlantı linkini ekleyin.

    ```ini
    TELEGRAM_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
    TELEGRAM_CHAT_ID=123456789
    DB_CONNECTION_STRING=postgresql://kullanici:sifre@host:port/veritabani
    ```

---

## 🏃‍♂️ Kullanım

Botu başlatmak için ana dosyayı çalıştırın:

```bash
python main.py
```

Bot başladığında:
1.  Veritabanına bağlanır ve tabloları kontrol eder.
2.  Telegram üzerinden size "Sistem Aktif" mesajı gönderir.
3.  Belirlenen coinleri, belirlenen zaman diliminde (Örn: 1 Saatlik) analiz etmeye başlar.

---

## 📂 Proje Yapısı

*   `app/core/`: Ayarlar ve Veritabanı yönetimi (Config, Database).
*   `app/analysis/`: Piyasa analizi ve gösterge hesaplamaları (Analyzer).
*   `app/trading/`: Botun ana mantığı ve WebSocket yöneticisi (Bot, StreamManager).
*   `app/services/`: Dış servisler (Binance, Telegram).
*   `scripts/`: Yardımcı araçlar ve veritabanı bakım scriptleri.

---

## ⚠️ Yasal Uyarı

Bu yazılım **yatırım tavsiyesi değildir.** Sadece eğitim ve simülasyon amaçlı geliştirilmiştir. Kripto para piyasaları yüksek risk içerir. Botun yapacağı işlemlerden doğacak kar veya zarardan geliştirici sorumlu tutulamaz.

---

**İyi Kodlamalar & Bol Kazançlar!** 💸
