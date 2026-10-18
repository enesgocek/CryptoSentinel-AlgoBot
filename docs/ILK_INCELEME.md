# CryptoSentinel ilk inceleme

İnceleme tarihi: 15 Ekim 2026.

Kaynak: https://github.com/enesgocek/CryptoSentinel-AlgoBot

İndirilen dal: `main`. Commit: `8bf1390f5d35273cce7f074a6b48b9476552fb21`.
Son commit tarihi: 11 Şubat 2026, 23:49:24 (+03:00).

## Mevcut yapı

Python uygulaması BTC/USDT, ETH/USDT ve BNB/USDT spot piyasa verilerini
CCXT ve Binance WebSocket üzerinden alıyor. Göstergelerden kurallı bir skor
üretiyor; PostgreSQL üzerinde sanal LONG/SHORT pozisyonları ve cüzdanı
tutuyor. Telegram bildirimleri ve günlük raporlama mevcut.

Varsayımlar: 1 saatlik mumlar, 1.000 USDT başlangıç sermayesi, 25x kaldıraç.
İncelenen kodda gerçek borsaya emir gönderen bir çağrı veya eğitilmiş makine
öğrenmesi modeli bulunmadı. README'deki yapay zekâ tanımı mevcut kurallı
puanlamayı olduğundan farklı anlatıyor.

## Öncelikli teknik bulgular

1. **Temiz kurulumda şema eksik.** `app/core/database.py` içindeki tablo
   oluşturma ve otomatik migration akışı `current_size` ve `exit_size`
   kolonlarını eklemiyor; işlem açma/güncelleme kodu bu kolonları kullanıyor.
   Bunlar ayrı `scripts/migrations/migrate_non_destructive.py` dosyasında var,
   fakat ana başlangıç akışına bağlanmamış. Eski veritabanında bulunmaları,
   temiz kurulumun çalışacağı anlamına gelmiyor.
2. **Çoklu WebSocket bağlantısı düzeltilmeli.** `stream_manager.py:22`,
   `/ws/` altında birden fazla akış adını birleştiriyor. Binance belgeleri
   birleşik akışlar için `/stream?streams=...` biçimini belirtiyor; bu yola
   geçildiğinde mesajların birleşik akış zarfı da ayrıştırılmalı.
   Kaynak: https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams
3. **Serbest bakiye ve marjin ayrımı eksik.** `open_trade()` yalnızca işlem
   kaydı ekliyor; sermayeyi ayırmıyor. Yeni işlemler son cüzdan bakiyesine
   göre açılabiliyor. Ayrılan marjin, serbest bakiye, gerçekleşmemiş PnL ve
   toplam özsermaye birlikte ve tutarlı izlenmeli.
4. **Kademeli çıkış muhasebesi eksik.** Cüzdana kısmi çıkışlarda PnL
   ekleniyor; `get_recent_pnl()` ise son çıkış yüzdesini başlangıç büyüklüğüne
   uyguluyor. Önceki kısmi çıkışlar bu formülle yeniden oluşturulamıyor.
   `MOONBAG_CLOSED` da bu sorgunun durum filtresinde yok. Bu nedenle zarar
   kesici ve raporlar gerçek gerçekleşmiş PnL ile uyuşmayabilir. Her dolumun
   miktarı, fiyatı, maliyeti ve gerçekleşmiş PnL tutarı ayrı kaydedilmeli.
5. **İşlem ve cüzdan güncellemeleri atomik değil.** Stream yöneticisi cüzdanı
   güncelledikten sonra ayrı çağrıyla işlemi değiştiriyor. İkinci adım
   başarısız olursa tekrar gelen fiyat aynı kazanç/zararı yeniden yazabilir.
6. **Kaydedilen skor hatalı.** `bot.py:97` skor fonksiyonuna satır veriyor;
   `calculate_sentinel_score()` geçmiş mumları içeren DataFrame bekliyor.
   Mevcut kolon sayısı 50'den az olduğu için satır çağrıları nötr 50 skoruna
   dönüyor. İşlem kararındaki tam DataFrame çağrısı ayrı; sorun kayıt altına
   alınan skorları etkiliyor.
7. **Moonbag çıkışında tanımsız değişken var.** `stream_manager.py:285`
   mesajında `position_size` kullanılıyor; bu fonksiyonda tanımlı değil.
   Hata, cüzdan ve işlem güncellendikten sonra mesaj hazırlanırken oluşuyor.
8. **Simülasyon maliyetleri ve piyasa modeli eksik.** Komisyon, alış/satış
   farkı, fiyat kayması ve fonlama modellenmemiş. Spot fiyatları üzerine
   kaldıraçlı LONG/SHORT ve yaklaşık likidasyon uygulanıyor. Gerçekçi bir
   spot veya vadeli işlem modeli açıkça seçilmeli; vadeli modelde sözleşme
   fiyatları, mark price, fonlama ve bakım marjı hesaba katılmalı.
9. **Sinyal ve değerlendirme altyapısı.** Ana mum verisinde kapanmamış son
   mum ayrılmıyor; aynı mumda tekrar giriş engeli yok. Geriye dönük strateji
   testi bulunamadı. `self.weights` tanımlanıyor ancak puanlamada uygulanmıyor.

## GitHub ve Drive karşılaştırması

GitHub'da 22 takip edilen dosya mevcut. `.env`, yerel veri dosyaları,
loglar ve sanal ortam `.gitignore` kapsamında. Bunların repoda olmaması
tek başına eksiklik değil. PostgreSQL içindeki eski işlem geçmişi de
Git klonuyla gelmez. Drive sürümü görülmeden hangi sürümün daha kapsamlı
olduğu veya kaynak dosya kaybı bulunup bulunmadığı kesinleştirilemez.

Drive kopyası ayrı bir klasörde açılmalı. Dosyalar içerik ve Git geçmişiyle
karşılaştırılmalı; yalnızca dosya değiştirme tarihine güvenilmemeli. Özellikle
ek kaynak kodlar, bağımlılık listeleri, veri şeması/yedekleri ve eski performans
kayıtları aranmalı. Gizli anahtarların içeriği rapora veya Git'e eklenmemeli.

## Önerilen çalışma sırası

1. Drive kopyasını ve varsa veritabanı yedeğini karşılaştır; referans sürümü
   belirle. Eski performans verisini koru.
2. İzole yerel ortamda temiz kurulum, şema, veri akışı ve işlem muhasebesini
   düzelt. Kısmi çıkış, tekrar mesaj ve yeniden başlama senaryolarını test et.
3. Spot/vadeli modelini seç; maliyetleri ve portföy düzeyinde risk sınırlarını
   ekle. Başlangıç sermayesi sıfırlamaları ayrı deney olarak kaydedilsin.
4. Kapanmış mumlarla ve gelecekteki bilgiyi kullanmadan tarihsel test kur.
   Parametre geliştirme dönemiyle değerlendirme dönemini ayır; farklı piyasa
   koşullarında net getiri, en büyük sermaye düşüşü, işlem başına net beklenti,
   işlem sayısı ve maliyet hassasiyetini ölç. Basit stratejiler ve uygun bir
   al-tut karşılaştırması kullan.
5. Aynı stratejiyi canlı fiyatlarla sanal işlemde izle; tarihsel sonuçlarla
   farkları ölç. Kârlılık ancak bu ölçümlerden sonra tartışılabilir; garanti
   edilemez.

## Yapılan doğrulama ve sınırlar

18 Python dosyası AST ile ayrıştırıldı; sözdizimi hatası bulunmadı. Bu,
çalışma zamanı doğrulaması değildir. Sistem Python'unda pandas, SQLAlchemy,
CCXT ve bazı diğer bağımlılıklar yok. `.env` ve veritabanı bağlantısı mevcut
değil. Bot ve mevcut entegrasyon testi çalıştırılmadı; harici veritabanına
bağlanılmadı, Telegram mesajı veya borsa emri gönderilmedi. Kaynak kodda
değişiklik yapılmadı; bu dosya inceleme notudur.
