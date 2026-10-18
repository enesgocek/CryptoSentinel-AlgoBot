# CryptoSentinel

Binance public fiyatlarıyla BTC, ETH ve BNB takip eden **sanal alım satım**
uygulaması. Python 3.12+ kullanır. Borsa hesabı, API anahtarı veya PostgreSQL
gerektirmez. Emirler yalnızca yerel SQLite hesabında gerçekleşir.

## Kurulum (Windows / PowerShell)

```powershell
cd C:\PROJELERIM\CryptoSentinel-AlgoBot
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Aktivasyon gerekmiyor. İstersen `.env.example` dosyasını `.env` olarak
kopyalayıp ayarları değiştir. `.env` zorunlu değildir. Program yalnızca ana
proje dizinindeki `.env` dosyasını okur; Drive yedeğindeki özel ayarları
kullanmaz. `DB_CONNECTION_STRING` ve eski bulut veritabanı kullanılmaz.

## Çalıştırma

İnternetsiz uçtan uca kontrol (sentetik veri, geçici ve ayrı hesap):

```powershell
.\.venv\Scripts\python.exe main.py --demo
```

Gerçek Binance verisini üç coin için kontrol et; yeni pozisyon açma:

```powershell
.\.venv\Scripts\python.exe main.py --check-live
```

Canlı fiyatlarla sürekli sanal işlem:

```powershell
.\.venv\Scripts\python.exe main.py
```

Tek analiz turu: `python main.py --once`. Durdurma: `Ctrl+C`. Açık sanal
pozisyonlar dosyada kalır, tekrar açılışta izlenir. Uygulama kapalıyken
fiyatlar izlenmez; yeniden başlatıldığında ilk güncel fiyatla değerlendirilir.

Canlı hesabın varsayılan dosyası `data/paper.sqlite3`. Çevrimdışı durum:

```powershell
.\.venv\Scripts\python.exe main.py --status
```

Bu komutta açık pozisyonlar giriş fiyatından değerlenir; güncel piyasa
özsermayesi için canlı çalışmanın fiyatları gerekir. Yeni bağımsız hesap
için `--db data/deney-2.sqlite3` kullan. Mevcut hesap hiçbir zaman otomatik
sıfırlanmaz. Demo ve tarihsel test canlı hesap dosyasını paylaşamaz.

## İşlem ve bakiye modeli

- Başlangıç sermayesi 1.000 USDT; ilk sürümden devralınan kaldıraç 25x.
  İşlem marjini skora göre 75 veya 100 USDT. Bunlar sanal deney ayarlarıdır.
- Girişte marjin ayrılır, komisyon serbest bakiyeden düşer. Çıkışta yalnızca
  kapanan miktarın marjini ve net kâr/zararı serbest bakiyeye döner.
- Her dolumun miktarı, fiyatı, komisyonu ve net PnL'si ayrı kaydedilir.
  Giriş/kısmi çıkış/tam çıkış aynı atomik veritabanı işlemiyle güncellenir.
- Aynı coin için tek açık pozisyon; aynı mumdan yeniden giriş engeli kalıcıdır.
  Veri alınamazsa eski fiyatla yeni pozisyon açılmaz. WebSocket koparsa REST
  fiyat takibi sürer; iki kaynak da kesilirse fiyat koşulları değerlendirilemez.
- Göstergeler yalnızca kapanmış mumlarla hesaplanır. Önceki tamamlanmış
  gün/hafta/ay pivotları kullanılır. Yeterli ısınma verisi yoksa işlem açılmaz.
- ROE hedefinin yarısında %50 kısmi satış ve giriş fiyatına stop taşıma;
  uygun pivotta ek kısmi satış; nihai hedef/stopta kapanış uygulanır.
  Giriş fiyatındaki stop komisyon ve kayma sonrası küçük zarar yaratabilir.
- Son 24 saatin gerçekleşmiş net sonucu -100 USDT veya +250 USDT sınırına
  ulaştığında yeni giriş durur; açık pozisyonlar izlenir. Güçlü skor bu sınırı
  gevşetmez. Bu, fiyat boşluklarında kesin zarar garantisi değildir.
- Komisyon ve kayma her iki yönde maliyet olarak uygulanır. Varsayılan
  komisyon işlem hacminin %0,1'i, kayma %0,05'idir; gerçek hesap tarifesi
  iddiası değildir. Kaldıraçlı hacim nedeniyle maliyet marjine göre büyür.

**Model sınırı:** Kaynak spot fiyatıdır; LONG/SHORT, kaldıraç ve izole marjin
yerelde modellenir. Bu, Binance vadeli işlemlerinin birebir kopyası değildir.
Fonlama, mark price, bakım marjı kademeleri ve emir defteri dolumları
modellenmez. Likidasyon yaklaşık ve kayıp kalan izole marjinle sınırlıdır.
Pozisyonlar sanal piyasa dolumuyla açılır; tamamlanmamış gerçek limit emir
akışı etkin kodda bulunmaz.

## Tarihsel test

CSV kolonları: `timestamp,open,high,low,close,volume`. Tarihler ISO 8601
(tercihen UTC), Unix saniye veya milisaniye olabilir. Satırlar artan, tekil ve
geçerli olmalı. En az 201 mum gerekir; ilk 200 mum ısınmadır. Zaman dilimini
CSV ile aynı `TIMEFRAME` olarak ayarla. Veri sessizce son 1.000 satıra kesilmez.

```powershell
.\.venv\Scripts\python.exe main.py --backtest data/btc-1h.csv --symbol BTC/USDT --report data/backtest.json
```

Canlı botla aynı strateji, maliyet ve kayıt motoru kullanılır. Karar kapanmış
mumdan, giriş sonraki mum açılışındandır. Aynı mumda hem hedef hem stop
görülürse stop önce kabul edilir. Bu muhafazakâr bir OHLC yaklaşımıdır;
mum içi gerçek fiyat sırasını bilmez. Test sonunda kalan pozisyon maliyetlerle
kapatılır. Rapor veri aralığını, ayarları, dolumları ve mum kapanışlarında
ölçülen en büyük özsermaye düşüşünü içerir. Demo sonuçları piyasa getirisi
kanıtı değildir.

## Telegram

Varsayılan olarak kapalıdır. Kullanmak istediğinde ana `.env` dosyasında
`TELEGRAM_ENABLED=true`, `TELEGRAM_TOKEN` ve `TELEGRAM_CHAT_ID` ayarla.
Bildirim hatası yerel muhasebeyi geri almaz. Tanılama/demo/test komutları
mesaj göndermez. Borsa API anahtarı hiçbir modda istenmez.

## Doğrulama

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Testler ağ/bulut/Telegram kullanmadan işlem muhasebesini, atomik geri alma,
eşzamanlı tekrar kapanış, yeniden başlatma, giriş noktası, veri doğrulama,
gelecekteki fiyatlardan etkilenmeme ve WebSocket ayrıştırmasını kontrol eder.

## Eski kaynaklar

GitHub sürümünün doğrulanmış kopyası `archive/github-8bf1390-original.zip`;
Drive kopyası `archive/drive-original-20261018.zip` içinde değişmeden
korunuyor; gereksiz iç içe kaynak klasörü kaldırıldı. İki arşiv de yalnızca
yerelde tutulur ve Git dışında bırakılır. Eski bakım araçları, statik BTC
regresyon katsayıları, agresif deney ayarları ve eski Backtrader adaptörü bu
kopyalarda bulunabilir. Aktif uygulama bunları otomatik çalıştırmaz. Önceki
bulut kayıtlarının aktarımı bu kurulumun parçası değildir.
