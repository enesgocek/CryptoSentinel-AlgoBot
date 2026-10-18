# Çalışan yerel simülasyon sürümü

Tarih: 18 Ekim 2026.

## Sonuç

Drive sürümünün gösterge hesapları ve asenkron yaklaşımı ana projeye alındı.
Başlatma, public fiyat bağlantıları, yerel muhasebe, raporlama ve tarihsel
test ortak bir sanal işlem motorunda birleştirildi. Kurulum `.env`, borsa API
anahtarı, Telegram veya PostgreSQL olmadan çalışıyor.

## Değişiklikler

- `main.py` asenkron ana döngüyü gerçekten başlatıyor; demo, tek tur, canlı
  veri tanılama, durum ve tarihsel test komutlarını sunuyor.
- `BinanceClient` yalnızca public veriye erişiyor. Gerçek emir oluşturma,
  emir iptali veya gerçek pozisyon kapatma kodu aktif uygulamada yok.
- Birleşik WebSocket adresi/zarfı ve zaman damgası kontrolü düzeltildi.
  Her coin ayrı tazelik kontrolüne sahip; REST fiyat takibi yedek olarak çalışıyor.
- Kapanmamış mumlar Binance sunucu saatiyle ayıklanıyor. Eksik, sırasız,
  yinelenmiş veya zaman dilimiyle uyuşmayan mumlar reddediliyor.
- Drive'daki aynı isimli skor fonksiyonlarından sonuncusu temel alındı;
  yinelenen tanım kaldırıldı. RSI/ADX/volume hesaplarında sıfır bölmeleri ve
  yön hesabı düzeltildi. Sıfır hareket/hacim işlem sinyali üretmiyor.
- Eski, tarihe bağlı BTC regresyon katsayıları aktif sinyale bağlanmadı;
  eğitim dönemi/son tarihi bilinmeden tarihsel teste sızıntı yaratabilirler.
- SQLite `paper_*` tabloları eski bulut şemasından bağımsız. Para değerleri
  metin olarak Decimal hassasiyetinde saklanıyor. Marjin, nakit ve dolum
  kaydı tek transaction'da güncelleniyor. Tekrar kapanış tekrar ödeme yapmıyor.
- Kısmi satış, bütün komisyonlar ve son kapanış ayrı dolumlar. Raporlar ve
  son 24 saatlik giriş freni doğrudan bu net tutarları kullanıyor.
- Aynı sinyal mumundan yeniden giriş, yeniden başlatmalar arasında engelleniyor.
  Bakiye otomatik yenilenmiyor. Demo ve canlı hesap birbirinden ayrılıyor.
- Backtrader adaptörünün ayrı işlem kuralları kaldırıldı. Tarihsel tekrar
  canlı modla aynı strateji ve muhasebeyi kullanıyor; karar kapanışta, giriş
  sonraki açılışta. Belirsiz mum içi sırada stop önce kabul ediliyor.
- Telegram isteğe bağlı; token hata günlüklerine yazılmıyor. Çıkış
  bildirimlerinin yavaşlığı stop/muhasebe akışını bekletmiyor.
- Kurulum paketleri ve transitif bağımlılıklar sabitlendi. Windows/Linux
  için GitHub Actions test tanımı eklendi; uzak CI henüz çalıştırılmadı.

## Doğrulama

- Python 3.12.10 üzerinde 30 otomatik test geçti. Testler gerçek ağa,
  veritabanı servisine veya Telegram'a erişmiyor.
- Sermaye ayırma, maliyetler, LONG/SHORT, kısmi satıştan sonra stop, yetersiz
  bakiye, atomik geri alma, eşzamanlı tekrar kapanış, kalıcı sinyal engeli,
  yeniden açılış ve mod ayrımı doğrulandı.
- Hazır olmayan/eski/bozuk veri, gelecek fiyatların geçmiş göstergeleri
  değiştirmemesi, sonraki açılıştan giriş ve asenkron giriş noktası doğrulandı.
- Gerçek Binance REST bağlantısından BTC/ETH/BNB mum ve fiyatları alındı;
  WebSocket üzerinden üç coin için güncel olaylar geldi.
- Normal `--once` komutu yerel canlı hesapta tamamlandı. Kontrol anında
  üç skor da nötrdü; pozisyon açılmadı. Canlı hesap 1.000 USDT ile duruyor.
- Sürekli çalışma yolu ayrıca geçici hesapta 20 saniye çalıştırılıp
  iptal edildi: üç coin izlendi, HTTP oturumu kapandı ve bekleyen görev
  kalmadı. Kalıcı bir bot süreci arka planda bırakılmadı.
- Sentetik 650 mumluk demo ve aynı verinin CSV üzerinden CLI tekrarı 21
  işlemi tamamladı; her dolum hesapla uzlaştı. Bu sonuç bir piyasa performansı
  iddiası değildir. Üretilen raporlar `data/` altında Git dışında tutulur.
- `pip check`, Python ayrıştırma/derleme ve `git diff --check` başarılı.

## Korunan kaynaklar

GitHub kaynaklarının 22 dosyalık arşivi:
`archive/github-8bf1390-original.zip` (ZIP bütünlüğü kontrol edildi).

Drive kopyası: `archive/drive-original-20261018.zip`. Kaynak klasörün 101
dosyası içerikleriyle birebir doğrulanarak arşivlendi; gereksiz iç içe Drive
klasörü kaldırıldı. İki arşiv ve içlerindeki özel `.env` yalnızca yerelde,
Git dışında tutuluyor. Aktif ağaçtaki eski destructive bakım
scriptleri kaldırıldı; orijinalleri arşivde. Eski bulut veritabanına
bağlanılmadı; buradaki hesap/geçmiş otomatik aktarılmadı.

## Geçerli sınırlar

Bu sürüm spot fiyatıyla kaldıraçlı LONG/SHORT işlemleri yaklaşık izole marjin
modelinde simüle eder. Binance vadeli işlemlerinin fonlama, mark price,
bakım marjı, gerçek likidasyon ve emir defteri dolumları modellenmez.
Sanal piyasa dolumları kullanılır. Gerçek borsada kullanıma hazır bir emir
botu değildir; bu çalışma o amaçla yapılmadı.

Uygulama kapalıyken fiyat takibi yapılmaz. Uzun süreli çalışma dayanıklılığı,
gerçek tarihsel veriyle strateji değerlendirmesi, bulut geçmişi aktarımı ve
strateji iyileştirmeleri sonraki çalışma başlıklarıdır. Mevcut kaynaklarda
tarihsel CSV olmadığı için gerçek veride getirinin yeterliliği doğrulanmadı.

Çalıştırma ve ayarlar için ana `README.md` dosyasına bakın.
