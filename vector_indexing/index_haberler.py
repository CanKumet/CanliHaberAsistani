from sentence_transformers import SentenceTransformer
import chromadb
from pymongo import MongoClient
from bson.objectid import ObjectId
from dotenv import load_dotenv
import os

# Ortam değişkenlerini yükle
load_dotenv()

# MongoDB bağlantısı
client = MongoClient("mongodb://localhost:27018/")
db = client["haberDB"]
collection = db["analizli_haberler"]

# Embedding modeli
model = SentenceTransformer("intfloat/multilingual-e5-base")

# ChromaDB client ayarı
chroma_client = chromadb.PersistentClient(path="./chroma_haber")

# Koleksiyon (vektör verisi için)
chroma_collection = chroma_client.get_or_create_collection("haber_vektor")

# Mongo’dan veri çek (sadece özet olanlar ve daha önce eklenmeyenler)
veriler = list(collection.find({"ozet": {"$exists": True}}))

print(f"📄 {len(veriler)} haber bulundu, vektörleniyor...")

for veri in veriler:
    haber_id = str(veri["_id"])

    # Aynı veri daha önce eklenmiş mi kontrol et
    mevcut = chroma_collection.get(ids=[haber_id], include=[])  # varsa boş dönmez
    if mevcut.get("ids"):
        continue  # geç

    metin = f"{veri.get('baslik', '')} - {veri.get('ozet', '')}"
    embedding = model.encode(metin).tolist()

    # Vektörü kaydet
    chroma_collection.add(
        documents=[metin],
        ids=[haber_id],
        embeddings=[embedding],
        metadatas=[{"kaynak": veri.get("kaynak", ""), "link": veri.get("link", "")}]
    )
    print(f"[✓] Eklendi → {veri.get('baslik', '')}")

# Kalıcı hale getir
print("✅ Tüm veriler ChromaDB'e kaydedildi.")
