from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import time

# .env dosyasını yükle
load_dotenv()

# OpenRouter ayarları
os.environ["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"
os.environ["OPENAI_API_KEY"] = os.getenv("OPENROUTER_API_KEY")

# MongoDB bağlantısı
client = MongoClient("mongodb://localhost:27018/")
db = client["haberDB"]
collection = db["analizli_haberler"]

# LLM modeli
model = ChatOpenAI(
    model="google/gemma-3-27b-it:free",
    temperature=0.4,
    max_tokens=300
)

def ozetlenmemis_haberleri_getir():
    return list(collection.find({"ozet": {"$exists": False}}).limit(5))

def haberi_ozetle(haber):
    icerik = haber.get("icerik", "")
    prompt = f"""Aşağıdaki haber metnini 2-3 cümleyle, önemli bilgileri kapsayacak şekilde özetle. Gereksiz detayları atla:
---
{icerik}
"""
    yanit = model([HumanMessage(content=prompt)])
    return yanit.content.strip()

def ozetleri_ekle():
    haberler = ozetlenmemis_haberleri_getir()
    if not haberler:
        print("⏳ Özetlenecek haber kalmadı.")
        return

    for haber in haberler:
        try:
            ozet = haberi_ozetle(haber)
            collection.update_one(
                {"_id": haber["_id"]},
                {"$set": {"ozet": ozet}}
            )
            print(f"[✓] Özetlendi: {haber.get('baslik', '')}")
            time.sleep(2)
        except Exception as e:
            print(f"[!] Hata oluştu: {e}")

if __name__ == "__main__":
    while True:
        ozetleri_ekle()
        print("🔄 60 saniye sonra tekrar kontrol ediliyor...\n")
        time.sleep(60)
