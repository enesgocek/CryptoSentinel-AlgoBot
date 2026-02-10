import pandas as pd
from typing import Optional, List, Dict
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from datetime import datetime

from app.core import config 

class DatabaseManager:
    def __init__(self):
        """Veritabanı bağlantı motorunu hazırlar."""
        print("🔌 Cloud Veritabanına bağlanılıyor...")
        
        # Cloud bağlantısı
        try:
            self.engine = create_engine(config.DB_CONNECTION_STRING)
            print("✅ Bağlantı Başarılı!")
            
            # Başlangıçta tabloları kontrol et
            self.initialize_db()
            
        except Exception as e:
            print(f"❌ Bağlantı Hatası: {e}")

    def initialize_db(self):
        """Gerekli tabloları eksiksiz oluşturur."""
        print("🛠️ Veritabanı tabloları kontrol ediliyor...")

        # 1. MARKET VERİSİ TABLOSU
        create_market_table = text("""
            CREATE TABLE IF NOT EXISTS market_data (
                timestamp TIMESTAMP,
                symbol TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                sentinel_score REAL,
                vol_z_score REAL,
                ema_50 REAL,
                ema_200 REAL,
                rsi REAL,
                atr REAL,
                bbw REAL,
                adx REAL,
                macd_line REAL,   -- Yeni: MACD
                macd_signal REAL, -- Yeni: Sinyal
                macd_hist REAL,   -- Yeni: Histogram
                obv REAL,         -- Yeni: On-Balance Volume
                is_support REAL,
                pivot_p REAL,     -- Yeni: Pivot Point
                pivot_r1 REAL,    -- Yeni: Res 1
                pivot_r2 REAL,    -- Yeni: Res 2
                pivot_r3 REAL,    -- Yeni: Res 3
                pivot_s1 REAL,    -- Yeni: Sup 1
                pivot_s2 REAL,    -- Yeni: Sup 2
                pivot_s3 REAL     -- Yeni: Sup 3
            );
        """)

        # 2. İŞLEM GEÇMİŞİ TABLOSU
        create_trade_table = text("""
            CREATE TABLE IF NOT EXISTS trade_history (
                id SERIAL PRIMARY KEY,
                symbol TEXT,
                position TEXT,
                entry_price REAL,
                entry_time TIMESTAMP,
                exit_price REAL,
                exit_time TIMESTAMP,
                pnl REAL,
                status TEXT,
                leverage INT,
                liquidation_price REAL,
                tp_price REAL,    -- Yeni: Hedef Fiyat
                sl_price REAL,    -- Yeni: Stop Fiyatı
                position_size REAL, -- Yeni: İşlem Büyüklüğü (USDT)
                is_tp1_filled BOOLEAN DEFAULT FALSE, -- YENİ: TP1 (Kar Al 1) Gerçekleşti mi?
                is_pivot_tp_filled BOOLEAN DEFAULT FALSE, -- YENİ: Pivot TP (Çeyrek Kar) Gerçekleşti mi?
                is_main_tp_filled BOOLEAN DEFAULT FALSE,  -- YENİ: Ana Hedef (50% ROE) Gerçekleşti mi?
                is_moonbag_filled BOOLEAN DEFAULT FALSE,  -- YENİ: Moonbag Hedef (200% ROE) Gerçekleşti mi?
                timeframe TEXT,   -- YENİ: Zaman Dilimi ('1h', '15m' vb.)
                notes TEXT
            );
        """)

        # 3. CÜZDAN TABLOSU (SANAL BAKİYE) - GÜNCELLENDİ (reset_count eklendi)
        create_wallet_table = text("""
            CREATE TABLE IF NOT EXISTS wallet (
                id SERIAL PRIMARY KEY,
                balance REAL,
                updated_at TIMESTAMP,
                reset_count INTEGER DEFAULT 0 -- PHOENIX MODU: Kaç kere battık?
            );
        """)
        
        # 4. DUPLICATE TRADE ÖNLEME
        # Aynı coin için birden fazla 'OPEN' işlemi olamaz.
        create_unique_index = text("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_open_trades 
            ON trade_history (symbol) 
            WHERE status = 'OPEN';
        """)

        try:
            with self.engine.connect() as conn:
                conn.execute(create_market_table)
                conn.execute(create_trade_table)
                conn.execute(create_wallet_table)
                conn.execute(create_unique_index)
                
                # --- MIGRATION: Eğer tablo varsa ama sütun yoksa ekle ---
                try:
                    conn.execute(text("ALTER TABLE wallet ADD COLUMN IF NOT EXISTS reset_count INTEGER DEFAULT 0;"))
                except Exception:
                    pass # Sütun zaten varsa devam et

                conn.commit()
            print("✅ Tablolar ve Kısıtlamalar Hazır (Otomatik Kurulum Tamam).")
            
            # --- MIGRATION: Pivot Kolonlarını Ekle (Eğer yoksa) ---
            self._migrate_pivots()
            self._migrate_pivot_tp_flag()
            self._migrate_timeframe()
            self._migrate_telemetry_flags() # YENİ

        except Exception as e:
            print(f"❌ Tablo Oluşturma Hatası: {e}")

    def _migrate_pivots(self):
        """Mevcut market_data tablosuna pivot kolonlarını ekler."""
        pivot_cols = ['pivot_p', 'pivot_r1', 'pivot_r2', 'pivot_r3', 'pivot_s1', 'pivot_s2', 'pivot_s3']
        with self.engine.connect() as conn:
            for col in pivot_cols:
                try:
                    conn.execute(text(f"ALTER TABLE market_data ADD COLUMN IF NOT EXISTS {col} REAL;"))
                except Exception:
                    pass
            conn.commit()

    def _migrate_pivot_tp_flag(self):
        """trade_history tablosuna is_pivot_tp_filled kolonunu ekler."""
        with self.engine.connect() as conn:
            try:
                conn.execute(text("ALTER TABLE trade_history ADD COLUMN IF NOT EXISTS is_pivot_tp_filled BOOLEAN DEFAULT FALSE;"))
                conn.commit()
            except Exception:
                pass

    def _migrate_timeframe(self):
        """trade_history tablosuna timeframe kolonunu ekler."""
        with self.engine.connect() as conn:
            try:
                conn.execute(text("ALTER TABLE trade_history ADD COLUMN IF NOT EXISTS timeframe TEXT;"))
                conn.commit()
            except Exception:
                pass

    def _migrate_telemetry_flags(self):
        """trade_history tablosuna telemetry kolonlarını (Main TP vs Moonbag) ekler."""
        with self.engine.connect() as conn:
            # 1. Timeframe (Garanti olsun diye tekrar kontrol)
            try:
                conn.execute(text("ALTER TABLE trade_history ADD COLUMN IF NOT EXISTS timeframe TEXT;"))
                conn.commit()
            except Exception:
                pass

            # 2. is_main_tp_filled
            try:
                conn.execute(text("ALTER TABLE trade_history ADD COLUMN IF NOT EXISTS is_main_tp_filled BOOLEAN DEFAULT FALSE;"))
                conn.commit()
            except Exception:
                pass

            # 3. is_moonbag_filled
            try:
                conn.execute(text("ALTER TABLE trade_history ADD COLUMN IF NOT EXISTS is_moonbag_filled BOOLEAN DEFAULT FALSE;"))
                conn.commit()
            except Exception:
                pass

    def save_to_db(self, df, table_name):
        """DataFrame'i veritabanına yazar."""
        try:
            df.to_sql(table_name, self.engine, if_exists='append', index=False)
            # print(f"💾 {len(df)} satır veri '{table_name}' tablosuna eklendi.")
        except Exception as e:
            print(f"❌ Veri Kayıt Hatası: {e}")

    # --- CÜZDAN YÖNETİMİ ---

    def get_balance(self) -> float:
        """Cüzdan bakiyesini getirir, yoksa oluşturur."""
        query = text("SELECT balance FROM wallet ORDER BY id DESC LIMIT 1")
        try:
            with self.engine.connect() as conn:
                result = conn.execute(query).fetchone()
                
                if result:
                    return float(result[0])
                else:
                    # İlk kez çalışıyor, başlangıç bakiyesini ekle
                    return self.update_balance(0, is_initial=True)
        except Exception as e:
            print(f"❌ Bakiye Hatası: {e}")
            return 0.0

    def update_balance(self, amount_change: float, is_initial: bool = False) -> float:
        """Bakiyeyi günceller (Kar/Zarar ekler)."""
        try:
            current_balance = config.INITIAL_CAPITAL if is_initial else self.get_balance()
            new_balance = current_balance + amount_change
            
            # reset_count değerini korumak için son değeri alıyoruz
            last_reset_count = 0
            try:
                with self.engine.connect() as conn:
                    res = conn.execute(text("SELECT reset_count FROM wallet ORDER BY id DESC LIMIT 1")).fetchone()
                    if res and res[0] is not None:
                        last_reset_count = res[0]
            except: pass

            query = text("""
                INSERT INTO wallet (balance, updated_at, reset_count)
                VALUES (:balance, :time, :reset_count)
            """)
            
            with self.engine.connect() as conn:
                conn.execute(query, {
                    'balance': new_balance, 
                    'time': datetime.now(),
                    'reset_count': last_reset_count
                })
                conn.commit()
            
            if not is_initial:
                # Loglama (Sadece değişim varsa)
                if amount_change > 0: print(f"💰 Cüzdan Güncellendi: +{amount_change:.2f}$ (Yeni: {new_balance:.2f}$)")
                elif amount_change < 0: print(f"💸 Cüzdan Güncellendi: {amount_change:.2f}$ (Yeni: {new_balance:.2f}$)")
                
            return new_balance
        except Exception as e:
            print(f"❌ Bakiye Güncelleme Hatası: {e}")
            return 0.0

    # --- PHOENIX MODU: YENİDEN DOĞUŞ ---
    def check_and_reset_balance(self):
        """
        Bakiye 10$'ın altına düştüyse (Batış), kasayı sıfırlar ve sayacı artırır.
        Return: (is_reset, new_balance, reset_count)
        """
        try:
            with self.engine.connect() as conn:
                # Son bakiye ve sayaç bilgisini al
                cursor = conn.execute(text("SELECT balance, reset_count FROM wallet ORDER BY id DESC LIMIT 1"))
                row = cursor.fetchone()
                
                if row:
                    current_balance = float(row[0])
                    # reset_count null gelirse 0 kabul et
                    current_reset_count = int(row[1]) if row[1] is not None else 0
                    
                    # Eşik Değer: 10$ (İşlem açamayacak kadar az para)
                    if current_balance < 10.0:
                        new_reset_count = current_reset_count + 1
                        
                        # Yeni bakiyeyi (1000$) ve artan sayacı ekle
                        insert_query = text("""
                            INSERT INTO wallet (balance, updated_at, reset_count) 
                            VALUES (:balance, :time, :reset_count)
                        """)
                        
                        conn.execute(insert_query, {
                            'balance': config.INITIAL_CAPITAL,
                            'time': datetime.now(),
                            'reset_count': new_reset_count
                        })
                        conn.commit()
                        
                        print(f"💀 KASA SIFIRLANDI! ({new_reset_count}. Kez Yeniden Doğuş)")
                        return True, config.INITIAL_CAPITAL, new_reset_count
                        
            return False, 0, 0
        except Exception as e:
            print(f"❌ Phoenix Modu Hatası: {e}")
            return False, 0, 0

    # --- TRADER FONKSİYONLARI ---

    def get_open_trades(self):
        """Şu an AÇIK (OPEN) olan işlemleri getirir."""
        query = text("SELECT * FROM trade_history WHERE status = 'OPEN'")
        try:
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn)
            return df
        except Exception as e:
            return pd.DataFrame() 

    def get_monitored_trades(self):
        """Websocket için izlenecek işlemleri (OPEN + MOONBAG) getirir."""
        query = text("SELECT * FROM trade_history WHERE status IN ('OPEN', 'MOONBAG')")
        try:
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn)
            return df
        except Exception as e:
            return pd.DataFrame()

    def open_trade(self, symbol: str, position: str, price: float, liq_price: float, tp_price: float, sl_price: float, position_size: float, timeframe: str = '1h') -> bool:
        """Yeni işlem açar. Başarılıysa True döner."""
        query = text("""
            INSERT INTO trade_history (symbol, position, entry_price, entry_time, status, leverage, liquidation_price, tp_price, sl_price, position_size, timeframe)
            VALUES (:symbol, :position, :price, :time, 'OPEN', :leverage, :liq_price, :tp_price, :sl_price, :position_size, :timeframe)
        """)
        
        params = {
            'symbol': symbol,
            'position': position,
            'price': float(price),
            'time': datetime.now(),
            'leverage': int(config.LEVERAGE),
            'liq_price': float(liq_price),
            'tp_price': float(tp_price),
            'sl_price': float(sl_price),
            'position_size': float(position_size),
            'timeframe': str(timeframe)
        }

        try:
            with self.engine.connect() as conn:
                conn.execute(query, params)
                conn.commit() 
            print(f"🚀 {symbol} için {position} işlemi açıldı! Büyüklük: {params['position_size']}$ | Giriş: {params['price']}$")
            return True
        except IntegrityError:
            print(f"⚠️ {symbol} için zaten AÇIK bir işlem var! (DB Reddedildi)")
            return False
        except Exception as e:
            print(f"❌ İşlem açma hatası: {e}")
            return False

    def close_trade(self, trade_id, exit_price, pnl, status, notes="", is_main_tp=False, is_moonbag=False):
        """Açık bir işlemi kapatır ve günceller."""
        # DÜZELTME: entry_time yerine exit_time güncelleniyor
        
        # Dinamik SQL oluştur (Flagleri sadece True ise güncellemek daha güvenli ama burada direkt set edebiliriz)
        # Basitlik için her zaman set edelim, varsayılanlar zaten False DB'de. 
        # Ama var olan değeri bozmamak lazım.
        # Bu yüzden SQL'i dinamik yapalım veya COALESCE kullanalım? 
        # En temizi: Parametre olarak geçilen True değerlerini set etmek.
        
        update_parts = [
            "exit_price = :exit_price",
            "exit_time = :exit_time",
            "pnl = :pnl",
            "status = :status",
            "notes = :notes"
        ]
        
        params = {
            'exit_price': float(exit_price),
            'exit_time': datetime.now(),
            'pnl': float(pnl),
            'status': status,
            'notes': notes,
            'trade_id': int(trade_id)
        }
        
        if is_main_tp:
            update_parts.append("is_main_tp_filled = TRUE")
            
        if is_moonbag:
            update_parts.append("is_moonbag_filled = TRUE")
            
        query = text(f"""
            UPDATE trade_history
            SET {', '.join(update_parts)}
            WHERE id = :trade_id
        """)

        try:
            with self.engine.connect() as conn:
                conn.execute(query, params)
                conn.commit()
            print(f"🏁 İşlem Sonlandı (ID: {trade_id}) -> Durum: {status} | PNL: %{params['pnl']}")
        except Exception as e:
            print(f"❌ İşlem kapatma hatası: {e}")

    def update_trade_after_tp1(self, trade_id, new_size, new_sl_price):
        """
        TP1 (Kısmi Kar Al) sonrası işlemi günceller:
        1. Pozisyon büyüklüğünü yarıya indirir.
        2. Stop Loss'u giriş seviyesine çeker.
        3. is_tp1_filled bayrağını True yapar.
        """
        query = text("""
            UPDATE trade_history
            SET position_size = :new_size,
                sl_price = :new_sl_price,
                is_tp1_filled = TRUE,
                notes = 'TP1 ALINDI - Risk Free Modu'
            WHERE id = :trade_id
        """)
        
        try:
            with self.engine.connect() as conn:
                conn.execute(query, {
                    'new_size': float(new_size),
                    'new_sl_price': float(new_sl_price),
                    'trade_id': int(trade_id)
                })
                conn.commit()
            print(f"✨ TP1 GÜNCELLEMESİ BAŞARILI (Trade ID: {trade_id})")
        except Exception as e:
            print(f"❌ TP1 Güncelleme Hatası: {e}")

    def update_trade_after_pivot(self, trade_id, new_size, new_sl_price):
        """
        Pivot TP (Çeyrek Kar Al) sonrası işlemi günceller:
        1. Pozisyon büyüklüğü güncellenir.
        2. Stop Loss giriş seviyesine çekilir.
        3. is_pivot_tp_filled True yapılır.
        """
        query = text("""
            UPDATE trade_history
            SET position_size = :new_size,
                sl_price = :new_sl_price,
                is_pivot_tp_filled = TRUE,
                notes = 'PIVOT TP - Kademeli Kar Alım'
            WHERE id = :trade_id
        """)
        
        try:
            with self.engine.connect() as conn:
                conn.execute(query, {
                    'new_size': float(new_size),
                    'new_sl_price': float(new_sl_price),
                    'trade_id': int(trade_id)
                })
                conn.commit()
            print(f"✨ PIVOT TP GÜNCELLEMESİ BAŞARILI (Trade ID: {trade_id})")
        except Exception as e:
            print(f"❌ Pivot TP Güncelleme Hatası: {e}")

    def set_trade_to_moonbag(self, trade_id, new_size, new_tp, new_sl):
        """
        İşlemi Moonbag moduna geçirir:
        1. Status -> 'MOONBAG'
        2. Size -> Küçültülmüş miktar (Runner)
        3. TP -> 200% ROE Hedefi
        4. SL -> Giriş Seviyesi
        """
        query = text("""
            UPDATE trade_history
            SET status = 'MOONBAG',
                position_size = :new_size,
                tp_price = :new_tp,
                sl_price = :new_sl,
                is_main_tp_filled = TRUE,  -- MOONBAG'e geçiş = MAIN TP VURULDU
                notes = 'MOONBAG ACTIVATED - 200% Hedefi'
            WHERE id = :trade_id
        """)
        
        try:
            with self.engine.connect() as conn:
                conn.execute(query, {
                    'new_size': float(new_size),
                    'new_tp': float(new_tp),
                    'new_sl': float(new_sl),
                    'trade_id': int(trade_id)
                })
                conn.commit()
            print(f"🌕 MOONBAG AKTİF (Trade ID: {trade_id}) -> Hedef: {new_tp}, Stop: {new_sl}")
        except Exception as e:
            print(f"❌ Moonbag Update Hatası: {e}")

    # --- PERFORMANS ANALİZİ (CIRCUIT BREAKER) ---

    def get_recent_pnl(self, hours=24) -> float:
        """
        Son N saat içinde kapatılan işlemlerden elde edilen 
        TOPLAM GERÇEKLEŞMİŞ KAR/ZARAR (PnL) tutarını ($) döner.
        """
        query = text(f"""
            SELECT SUM(pnl * position_size / 100.0) 
            FROM trade_history 
            WHERE status IN ('CLOSED', 'LIQUIDATED')
            AND exit_time >= NOW() - INTERVAL '{hours} hours'
        """)
        # Not: PNL veritabanında % olarak tutuluyor (Örn: 50.0). 
        # Tutar hesabı: (PNL / 100) * Position_Size
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(query).fetchone()
                return float(result[0]) if result and result[0] is not None else 0.0
        except Exception as e:
            print(f"❌ PnL Hesaplama Hatası: {e}")
            return 0.0

    def get_last_trade_exit_time(self) -> Optional[datetime]:
        """
        En son kapatılan işlemin çıkış zamanını döner.
        Wait/Cooldown hesabı için kullanılır.
        """
        query = text("""
            SELECT exit_time FROM trade_history 
            WHERE status IN ('CLOSED', 'LIQUIDATED') 
            ORDER BY exit_time DESC LIMIT 1
        """)
        try:
            with self.engine.connect() as conn:
                result = conn.execute(query).fetchone()
                return result[0] if result else None
        except Exception as e:
            print(f"❌ Son İşlem Zamanı Hatası: {e}")
            return None

    # --- MARKET VERİSİ ---
    
    def get_latest_pivots(self, symbol: str) -> Optional[Dict[str, float]]:
        """
        Coin için en son kaydedilen pivot seviyelerini getirir.
        """
        query = text("""
            SELECT pivot_p, pivot_r1, pivot_r2, pivot_r3, pivot_s1, pivot_s2, pivot_s3
            FROM market_data 
            WHERE symbol = :symbol 
            ORDER BY timestamp DESC LIMIT 1
        """)
        try:
            with self.engine.connect() as conn:
                row = conn.execute(query, {'symbol': symbol}).fetchone()
                if row:
                    return {
                        'P': row[0], 'R1': row[1], 'R2': row[2], 'R3': row[3],
                        'S1': row[4], 'S2': row[5], 'S3': row[6]
                    }
                return None
        except Exception as e:
            # print(f"⚠️ Pivot Sorgu Hatası ({symbol}): {e}")
            return None

    # --- BAKIM VE TEMİZLİK ---
    
    def maintenance_clean_data(self, days=3):
        """Eski verileri temizler (Açık işlem verileri hariç)."""
        print(f"🧹 Veritabanı Bakımı Başlıyor... ({days} günden eski veriler taranıyor)")
        
        # PostgreSQL uyumlu NOW() - INTERVAL kullanımı
        query = text(f"""
            DELETE FROM market_data
            WHERE timestamp < NOW() - INTERVAL '{days} days'
            AND NOT EXISTS (
                SELECT 1 FROM trade_history 
                WHERE market_data.timestamp BETWEEN trade_history.entry_time AND COALESCE(trade_history.exit_time, NOW())
            );
        """)

        try:
            with self.engine.connect() as conn:
                result = conn.execute(query)
                conn.commit()
                print(f"✨ Temizlik Tamamlandı! Silinen Satır Sayısı: {result.rowcount}")
        except Exception as e:
            # Tablo henüz yoksa hata vermesin, sessizce geçsin
            print(f"⚠️ Bakım Bilgisi: Tablolar henüz boş veya oluşmadı ({e}).")