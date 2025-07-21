from sentence_transformers import SentenceTransformer
from chromadb import PersistentClient
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage
from dotenv import load_dotenv
import os

# .env dosyasını yükle
load_dotenv()

# OpenRouter ayarları
os.environ["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"
os.environ["OPENAI_API_KEY"] = os.getenv("OPENROUTER_API_KEY")

# Embedding modeli
embedding_model = SentenceTransformer("intfloat/multilingual-e5-base")

# ChromaDB bağlantısı
chroma_client = PersistentClient(path="./chroma_haber")
collection = chroma_client.get_or_create_collection("haber_vektor")

# LLM modeli (Google Gemma)
llm = ChatOpenAI(
    model="google/gemma-3-27b-it:free",
    temperature=0.4,
    max_tokens=300
)

# Kullanıcıdan soru al
soru = input("❓ Sorunuzu yazın: ")

# Soru vektörleştirme
soru_vektoru = embedding_model.encode(soru).tolist()

# En alakalı 3 haberi getir
sonuclar = collection.query(
    query_embeddings=[soru_vektoru],
    n_results=3
)

# Belgeleri birleştir
belgeler = sonuclar["documents"][0]
icerik = "\n\n".join(belgeler)

# Prompt oluştur
prompt = f"""Aşağıdaki haber içeriklerine göre soruya cevap ver fakat cevapları biraz daha ayrıntılı verebilirsin. Daha fazla detaylandır cevapları:

Haber Özeti İçeriği:
{icerik}

Soru:
{soru}

Cevap:"""

# LLM'den cevap al
yanit = llm([HumanMessage(content=prompt)])

# Cevabı yazdır
print("\n🧠 LLM Yanıtı:\n", yanit.content.strip())
