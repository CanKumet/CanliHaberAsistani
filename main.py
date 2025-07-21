#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import sys
import time
import os
from threading import Thread
import signal


class HaberSistemi:
    def __init__(self):
        self.processes = []
        self.running = True

    def log(self, mesaj):
        """Zaman damgalı log mesajı"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {mesaj}")

    def script_calistir(self, script_adi, arka_planda=False):
        """Python script'ini çalıştır"""
        try:
            self.log(f"🚀 {script_adi} başlatılıyor...")

            if arka_planda:
                # Arka planda çalıştır
                process = subprocess.Popen(
                    [sys.executable, script_adi],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                self.processes.append(process)
                self.log(f"✅ {script_adi} arka planda başlatıldı (PID: {process.pid})")
                return process
            else:
                # Senkron çalıştır (bitene kadar bekle)
                result = subprocess.run([sys.executable, script_adi],
                                        capture_output=True,
                                        text=True,
                                        timeout=300)  # 5 dakika timeout

                if result.returncode == 0:
                    self.log(f"✅ {script_adi} başarıyla tamamlandı")
                else:
                    self.log(f"❌ {script_adi} hata ile sonlandı:")
                    self.log(f"   STDOUT: {result.stdout}")
                    self.log(f"   STDERR: {result.stderr}")

                return result

        except subprocess.TimeoutExpired:
            self.log(f"⏰ {script_adi} timeout'a uğradı")
        except FileNotFoundError:
            self.log(f"❌ {script_adi} dosyası bulunamadı!")
        except Exception as e:
            self.log(f"❌ {script_adi} çalıştırılırken hata: {e}")

    def kontrol_et(self, dosya_adi):
        """Dosya var mı kontrol et"""
        if not os.path.exists(dosya_adi):
            self.log(f"⚠️  {dosya_adi} dosyası bulunamadı!")
            return False
        return True

    def bekle(self, saniye):
        """Belirtilen süre bekle"""
        self.log(f"⏳ {saniye} saniye bekleniyor...")
        time.sleep(saniye)

    def sistem_baslat(self):
        """Tüm sistemi sırasıyla başlat"""
        self.log("🎯 Haber Analiz Sistemi Başlatılıyor")
        self.log("=" * 60)

        # Dosya kontrolü
        dosyalar = ["producer.py", "spark_streaming.py", "ozetleyici.py",
                    "index_haberler.py", "app.py"]

        for dosya in dosyalar:
            if not self.kontrol_et(dosya):
                self.log("❌ Sistem başlatılamıyor, eksik dosyalar var!")
                return False

        try:
            # 1. Producer başlat (arka planda)
            self.log("1️⃣ RSS Producer başlatılıyor...")
            self.script_calistir("producer.py", arka_planda=True)
            self.bekle(15)

            # 2. Spark Streaming başlat (arka planda)
            self.log("2️⃣ Spark Streaming başlatılıyor...")
            self.script_calistir("spark_streaming.py", arka_planda=True)
            self.bekle(15)

            # 3. Özetleyici başlat (arka planda)
            self.log("3️⃣ Haber Özetleyici başlatılıyor...")
            self.script_calistir("ozetleyici.py", arka_planda=True)
            self.bekle(15)

            # 4. Indexer çalıştır (tek seferlik)
            self.log("4️⃣ Haber İndexleyici çalıştırılıyor...")
            self.script_calistir("index_haberler.py", arka_planda=False)
            self.bekle(15)

            # 5. Flask App başlat (arka planda)
            self.log("5️⃣ Flask Web Uygulaması başlatılıyor...")
            self.script_calistir("app.py", arka_planda=True)

            self.log("🎉 Tüm servisler başarıyla başlatıldı!")
            self.log("🌐 Web uygulaması: http://localhost:5000")
            self.log("=" * 60)
            self.log("💡 Sistem durdurmak için Ctrl+C tuşlayın")

            # Ana döngü - sistemin çalışmasını bekle
            self.ana_dongu()

        except KeyboardInterrupt:
            self.log("🛑 Kullanıcı tarafından durduruldu")
            self.sistemi_durdur()
        except Exception as e:
            self.log(f"❌ Sistem hatası: {e}")
            self.sistemi_durdur()

    def ana_dongu(self):
        """Ana döngü - servisleri izle"""
        while self.running:
            try:
                # Her 30 saniyede bir servislerin durumunu kontrol et
                time.sleep(30)

                # Sonlandırılan servisleri kontrol et
                for i, process in enumerate(self.processes):
                    if process.poll() is not None:  # Process sonlandırılmış
                        self.log(f"⚠️  Servis {i + 1} beklenmedik şekilde sonlandı (return code: {process.returncode})")

            except KeyboardInterrupt:
                break

    def sistemi_durdur(self):
        """Tüm servisleri güvenli şekilde durdur"""
        self.log("🛑 Sistem durduruluyor...")
        self.running = False

        for i, process in enumerate(self.processes):
            try:
                if process.poll() is None:  # Hala çalışıyor
                    self.log(f"🔄 Servis {i + 1} sonlandırılıyor...")
                    process.terminate()

                    # 5 saniye bekle, hala çalışıyorsa zorla öldür
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.log(f"⚡ Servis {i + 1} zorla sonlandırılıyor...")
                        process.kill()
                        process.wait()

            except Exception as e:
                self.log(f"❌ Servis {i + 1} durdurulurken hata: {e}")

        self.log("✅ Tüm servisler durduruldu")
        self.log("👋 Görüşmek üzere!")


def signal_handler(signum, frame):
    """Sinyal yakalandığında sistemi durdur"""
    print("\n🛑 Sistem durduruluyor...")
    sys.exit(0)


if __name__ == "__main__":
    # Sinyal yakalayıcıları ayarla
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("""
╔══════════════════════════════════════╗
║          HABER ANALİZ SİSTEMİ        ║
║              v1.0.0                  ║
╚══════════════════════════════════════╝
    """)

    # Sistemi başlat
    sistem = HaberSistemi()
    sistem.sistem_baslat()