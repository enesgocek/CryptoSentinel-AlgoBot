# Bakım araçları

Eski PostgreSQL migration, bakiye sıfırlama ve işlem silme araçları etkin
proje ağacından kaldırıldı. Orijinalleri `archive/github-8bf1390-original.zip`
ve `archive/drive-original-20261018.zip` içinde korunuyor. Yeni yerel hesap bu araçları kullanmaz.

Durum: `python main.py --status`

Yeni bağımsız deney: `python main.py --db data/deney-2.sqlite3`

Mevcut kayıtlar otomatik sıfırlanmaz veya silinmez. Eski PostgreSQL verilerini
yeni hesapla birleştirmek ayrı bir veri aktarımı işi olarak ele alınmalıdır.
