import feedparser
from kafka import KafkaProducer
from pymongo import MongoClient
import json
import time

# Kafka ayarları
KAFKA_TOPIC = "haber-akisi"
KAFKA_BOOTSTRAP_SERVERS = "localhost:9292"

# RSS kaynakları
RSS_FEEDS = [
    "https://www.cnnturk.com/feed/rss/news",
    "https://www.bbc.com/news/10628494",
    "https://www.aa.com.tr/tr/rss/default?cat=guncel"
]

# Kafka producer
producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8")
)

# MongoDB bağlantısı (sadece kontrol için)
client = MongoClient("mongodb://localhost:27017/")
db = client["haberDB"]
raw_collection = db["ham_haberler"]  # Yeni koleksiyon adı (Kafka’ya gidenler burada tutulacak)

def rss_verisini_al_ve_gonder():
    for url in RSS_FEEDS:
        kaynak = url.split("/")[2]
        feed = feedparser.parse(url)

        for entry in feed.entries:
            baslik = entry.get("title", "")
            yayim_zamani = entry.get("published", "")
            unique_key = baslik + yayim_zamani  # Benzersiz anahtar oluştur

            # Bu haber daha önce işlendi mi?
            if raw_collection.find_one({"unique_key": unique_key}):
                continue  # Atlansın

            haber = {
                "baslik": baslik,
                "icerik": entry.get("summary", ""),
                "yayim_zamani": yayim_zamani,
                "kaynak": kaynak,
                "link": entry.get("link", ""),
                "unique_key": unique_key
            }

            # Kafka'ya gönder
            producer.send(KAFKA_TOPIC, haber)
            print(f"[+] Kafka’ya gönderildi → {haber['baslik']}")

            # MongoDB'ye kaydet (kontrol için)
            raw_collection.insert_one(haber)

if __name__ == "__main__":
    print("🔄 Haberler çekiliyor ve Kafka’ya gönderiliyor...")

    while True:
        try:
            rss_verisini_al_ve_gonder()
            print("⏳ 60 saniye bekleniyor...\n")
            time.sleep(60)
        except Exception as e:
            print(f"[!] Hata: {e}")
            time.sleep(10)
