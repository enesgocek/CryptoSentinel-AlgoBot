# GitHub ve Drive sürümlerinin karşılaştırması

Tarih: 15 Ekim 2026.

GitHub referansı: `main`, `8bf1390f5d35273cce7f074a6b48b9476552fb21`.
Drive kaynağı: `CryptoSentinel-3-Suanki/CryptoSentinel`.

## Karar

Drive kopyası, geliştirme kapsamı bakımından daha iyi adaydır. Ancak mevcut
haliyle çalışır ve kârlı bir sürüm olarak kabul edilmemelidir. Asenkron yapıya
geçiş tamamlanmamış, canlı emir kodları simülasyon akışına karışmış ve tarihsel
test ile çalışan bot farklı işlem kuralları kullanmaktadır.

Öneri: Drive sürümünün geliştirmelerini yeni temele al; GitHub'daki yararlı
dosyaları değerlendirerek taşı. Çalışma doğrulanana kadar iki kaynak kopyasını
koru. Tam klasörün diğerinin üzerine kopyalanması veya eski dosyaların topluca
silinmesi doğru bir birleştirme yöntemi değildir.

Drive'ın daha fazla geliştirme içermesi, bütün dosyalarının GitHub'dan daha
yeni veya daha doğru olduğunu kanıtlamaz. İçeride sürümü doğrulayacak Git
geçmişi bulunmadı; karar dosya içeriklerine dayanmaktadır.

## Karşılaştırma

| Alan | GitHub | Drive | Değerlendirme |
| --- | --- | --- | --- |
| Çalışma modeli | Senkron ana döngü, WebSocket thread'i | asyncio, kuyruk, yeniden bağlanma ve watchdog | Drive daha kapsamlı; başlatma hatası var |
| Sinyal mumu | Son gelen mum | Skor için önceki kapanmış mum | Drive'da iyileşme var |
| Skorun kaydı | DataFrame bekleyen fonksiyona satır gönderiliyor | Fonksiyon satır kabul ediyor | Eski arayüz hatası giderilmiş; BTC kaydında makro katkı hâlâ eksik |
| Para hesapları | float | Decimal, veritabanı sınırında float | Drive'da kısmi iyileşme; muhasebe sorunu sürüyor |
| Tarihsel test | Yok | Backtrader motoru, komisyon/kayma ayarı, eski raporlar | Faydalı başlangıç; çalışan stratejiyle eşleşmiyor |
| Risk ayarları | 25x kaldıraç | Rejime göre 25–50x kaldıraç | Daha çok ayar var; daha iyi performans kanıtı değil |
| Günlük rapor | reporting.py ve zamanlayıcı mevcut | Bu modül ve çağrısı yok | GitHub'daki işlev ayrıca değerlendirilmeli |
| Kurulum | Gereksinimler ve README mevcut | Ek bağımlılıklar listeye işlenmemiş, README yok | Drive eksiksiz teslim paketi değil |

GitHub'daki 22 dosyanın 7'si aynı içerikle bulunuyor, 9'u değişmiş, 6'sı
aynı yolda bulunmuyor. Drive kopyasında toplam 35 Python dosyası var;
bunların 18'i `tools/` altında yardımcı veya doğrulama scripti.

## Kullanımdan önce giderilecek sorunlar

1. **Başlatma:** `main.py:13`, `bot.run()` çağırıyor; Drive'da `run()`
   asenkron. Çağrı await edilmiyor ve ana döngü çalışmıyor. `bot.py:388`
   içindeki `start()` sarmalayıcısı veya eşdeğer bir asyncio giriş noktası
   kullanılmalı. Bu hata dış servisleri taklit eden çevrimdışı çalıştırmayla
   doğrulandı: bot örneği oluşturuldu, `run` gövdesi çalışmadı ve await
   edilmeyen coroutine uyarısı oluştu.
2. **Simülasyon ve gerçek emir ayrımı:** `USE_LIMIT_ORDERS=True` varsayılanı,
   `bot.py` üzerinden `BinanceClient.create_order()` çağırıyor; bu da gerçek
   CCXT emir uç noktasına gidiyor. İncelenen istemci borsa API anahtarı
   yapılandırmıyor, dolayısıyla mevcut durumda kimlik doğrulama hatası
   beklenir. Bu bir sanal limit emir motoru değil. Emir durum kontrolü,
   kısmi dolum, iptal sonucu ve borsadaki miktar ile sanal kaldıraçlı miktarın
   uyumu da tamamlanmalı. Hiçbir emir çağrısı çalıştırılmadı.
3. **WebSocket:** Eski hatalı çoklu `/ws/.../...` adresi korunmuş;
   birleşik akış adresi ve mesaj zarfı birlikte düzeltilmeli.
   [Binance akış belgeleri](https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams).
4. **Bağımlılıklar:** Yeni motor doğrudan `backtrader`, akış yöneticisi
   doğrudan `aiohttp` kullanıyor; gereksinimlerde yok. `numpy` da doğrudan
   kullanılıyor ancak listelenmemiş. `aiohttp` ve `numpy` başka paketlerin
   bağımlılığı olarak gelebilir; bu açık ve tekrarlanabilir kurulumun yerini
   tutmaz. Regresyon araçları ayrıca `yfinance`, `scipy`, `matplotlib` istiyor.
5. **Strateji eşleşmesi:** Analyzer ATR tabanlı stop/hedef veriyor ve backtest
   bunları kullanıyor. Bot sinyal listesini kullanmak yerine skora göre yön
   belirleyip ROE/kaldıraç tabanlı ayrı stop/hedef hesaplıyor. Backtestteki
   pozisyon büyüklüğü ve kaldıraç modeli de botla aynı değil. Backtest,
   mevcut botun başarısını doğrudan ölçmüyor.
6. **Backtest emirleri:** Manuel parent/child emirleri `transmit` dizisi
   kurulmadan gönderiliyor. Bekleyen emir engeli de yok; pozisyon açılmadan
   aynı yönde yeni emirler birikebilir. Bracket emirlerinin yaşam döngüsü
   doğrulanmalı. [Backtrader bracket belgeleri](https://www.backtrader.com/docu/order-creation-execution/bracket/bracket/).
7. **Muhasebe:** İşlem açılışında marjin ayrılmıyor. Kısmi satışlar cüzdana
   ayrı eklenirken günlük PnL yalnızca son ROE ile kalan `position_size`
   üzerinden hesaplanıyor; önceki satışların PnL'si hesaba katılmıyor.
   Cüzdan ve işlem güncellemeleri hâlâ ayrı transaction'larda.
8. **Yarım refaktör:** `calculate_sentinel_score()` aynı sınıfta iki kez
   tanımlı; ikinci tanım ilkini geçersiz kılıyor. `initial_position_size`
   kaydı bulunmasına rağmen kısmi çıkış sonrası risk sınıfı başlangıç
   büyüklüğü yerine sabit oranlarla tahmin ediliyor. Bazı test araçları
   eski senkron metotları çağırıyor; çok sayıda araç bulunması testlerin
   mevcut sürümde geçtiği anlamına gelmiyor.
9. **Tekrarlanabilirlik:** Backtest yükleyicisi veriyi son 1.000 mumla
   sınırlıyor. Kopyada CSV bulunmuyor; eski sonuçlar yeniden üretilemedi.
   BTC makro kanal katsayıları sabit; geriye dönük testte bu katsayıların
   test tarihinden sonraki verilerle hesaplanmadığı doğrulanmalı.

## Eski sonuç dosyası

`app/backtesting/backtest_results.txt` içindeki kayıt BTC için 1.000 USDT
başlangıçtan 996,75 USDT'ye, yaklaşık %-0,33 getiri gösteriyor. Toplam 148
işlem, 43 kazanan ve 104 kaybeden yazılmış; kapalı işlemler toplamı 147.
Tarih aralığı, kullanılan veri, kod sürümü ve açık pozisyon ayrıntısı
raporda yok. Bu kayıt tarafımızca üretilmedi; mevcut stratejinin güncel
performansı veya karşılaştırılabilir bir ölçüm olarak sunulmamalı.

## Korunacak dosyalar ve sonraki adım

GitHub kopyasındaki README, `app/services/reporting.py`, `tests/` ve
`scripts/` dosyaları Drive'daki aynı yollarda yok. Bazı bakım araçlarının
Drive'da `tools/` altında benzerleri var; birebir eşdeğer oldukları
varsayılmamalı. Eski test ve migration dosyaları yeni şemaya uyarlanmadan
çalıştırılmamalı.

Drive'da `.env` mevcut. Özel değerler okunmadı, çıktıya yazılmadı veya
başka yere kopyalanmadı. PostgreSQL verileri klasör kopyasının içinde değil;
eski veritabanına bağlanılmadı.

İlk uygulama işi: sürümleri korunmuş şekilde tek proje düzeninde birleştir;
simülasyon sınırını açıkça kur; giriş noktasını, bağımlılıkları ve veri
akışını düzelt; ardından işlem muhasebesini ve ortak strateji motorunu test
et. Sonrasında maliyetler dahil tarihsel test ve canlı veride sanal işlem
karşılaştırmasına geç.

## Bu incelemede yapılanlar

Kaynaklar içerik üzerinden karşılaştırıldı. Drive'daki 35 Python dosyası
sözdizimi açısından ayrıştırıldı; hata bulunmadı. Giriş noktası sahte botla
çevrimdışı doğrulandı. Entegrasyon testleri, gerçek bot ve backtest
çalıştırılmadı. Dosyalar silinmedi veya taşınmadı; uygulama kodu değiştirilmedi.
