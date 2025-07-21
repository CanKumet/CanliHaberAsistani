from flask import Flask, render_template, jsonify, request
from pymongo import MongoClient
from datetime import datetime, timedelta
from collections import Counter
import re
import traceback

# LLM Chat için gerekli kütüphaneler
try:
    from sentence_transformers import SentenceTransformer
    from chromadb import PersistentClient
    from langchain_openai import ChatOpenAI
    from langchain.schema import HumanMessage
    from dotenv import load_dotenv
    import os

    ADVANCED_CHAT_AVAILABLE = True
except ImportError:
    ADVANCED_CHAT_AVAILABLE = False
    print("⚠️ Gelişmiş chat kütüphaneleri bulunamadı. Basit chat modu aktif olacak.")

# .env dosyasını yükle
if ADVANCED_CHAT_AVAILABLE:
    load_dotenv()

app = Flask(__name__)

# MongoDB bağlantısı
client = MongoClient("mongodb://localhost:27018/")
db = client["haberDB"]
collection = db["analizli_haberler"]

# LLM Chat için global değişkenler
embedding_model = None
chroma_client = None
chroma_collection = None
llm = None


def init_llm_components():
    """LLM bileşenlerini başlat"""
    global embedding_model, chroma_client, chroma_collection, llm

    if not ADVANCED_CHAT_AVAILABLE:
        return False

    try:
        # OpenRouter ayarları
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            print("❌ OPENROUTER_API_KEY bulunamadı!")
            return False

        os.environ["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"
        os.environ["OPENAI_API_KEY"] = api_key

        # Embedding modeli
        print("🔄 Embedding modeli yükleniyor...")
        embedding_model = SentenceTransformer("intfloat/multilingual-e5-base")

        # ChromaDB bağlantısı
        print("🔄 ChromaDB bağlantısı kuruluyor...")
        chroma_client = PersistentClient(path="./chroma_haber")
        chroma_collection = chroma_client.get_or_create_collection("haber_vektor")

        # Koleksiyonda veri var mı kontrol et
        veri_sayisi = chroma_collection.count()
        print(f"📊 ChromaDB'de {veri_sayisi} vektör bulundu.")

        if veri_sayisi == 0:
            print("⚠️ ChromaDB boş! index_haberler.py çalıştırılmalı.")
            # Otomatik olarak verileri indexle
            auto_index_data()

        # LLM modeli (Google Gemma)
        print("🔄 LLM modeli yükleniyor...")
        llm = ChatOpenAI(
            model="google/gemma-3-27b-it:free",
            temperature=0.4,
            max_tokens=400
        )

        print("✅ LLM bileşenleri başarıyla yüklendi.")
        return True
    except Exception as e:
        print(f"❌ LLM bileşenleri yüklenemedi: {e}")
        traceback.print_exc()
        return False


def auto_index_data():
    """Otomatik olarak MongoDB'deki verileri ChromaDB'ye indexle"""
    try:
        print("🔄 Otomatik veri indexleme başlıyor...")

        # MongoDB'dan özet olan haberleri getir
        veriler = list(collection.find(
            {"ozet": {"$exists": True}},
            {"baslik": 1, "ozet": 1, "kaynak": 1, "link": 1}
        ).limit(100))  # İlk 100 haberi indexle

        if not veriler:
            print("❌ MongoDB'de indexlenecek veri bulunamadı!")
            return False

        for veri in veriler:
            haber_id = str(veri["_id"])

            # Daha önce eklenmiş mi kontrol et
            try:
                mevcut = chroma_collection.get(ids=[haber_id])
                if mevcut.get("ids"):
                    continue  # Zaten var, geç
            except:
                pass  # Hata varsa devam et

            # Metni oluştur ve vektörle
            metin = f"{veri.get('baslik', '')} - {veri.get('ozet', '')}"

            try:
                embedding = embedding_model.encode(metin).tolist()

                # ChromaDB'ye ekle
                chroma_collection.add(
                    documents=[metin],
                    ids=[haber_id],
                    embeddings=[embedding],
                    metadatas=[{
                        "kaynak": veri.get("kaynak", ""),
                        "link": veri.get("link", ""),
                        "baslik": veri.get("baslik", "")
                    }]
                )
                print(f"[+] Indexlendi: {veri.get('baslik', '')[:50]}...")
            except Exception as e:
                print(f"[!] Indexleme hatası: {e}")
                continue

        veri_sayisi = chroma_collection.count()
        print(f"✅ Otomatik indexleme tamamlandı. Toplam {veri_sayisi} vektör.")
        return True

    except Exception as e:
        print(f"❌ Otomatik indexleme hatası: {e}")
        return False


@app.route('/')
def ana_sayfa():
    return render_template('index.html')


@app.route('/api/ozetler')
def ozetler_api():
    """Son 50 haberi tarih sırasına göre getir"""
    try:
        haberler = list(collection.find(
            {"ozet": {"$exists": True}},
            {"baslik": 1, "ozet": 1, "kaynak": 1, "duygu": 1, "islenme_zamani": 1}
        ).sort("islenme_zamani", -1).limit(50))

        # MongoDB ObjectId'yi string'e çevir
        for haber in haberler:
            haber['_id'] = str(haber['_id'])
            # Tarih formatını düzenle
            if 'islenme_zamani' in haber:
                try:
                    if isinstance(haber['islenme_zamani'], str):
                        tarih = datetime.fromisoformat(haber['islenme_zamani'].replace('Z', '+00:00'))
                    else:
                        tarih = haber['islenme_zamani']
                    haber['tarih'] = tarih.strftime("%d.%m.%Y %H:%M")
                except:
                    haber['tarih'] = "Bilinmiyor"
            else:
                haber['tarih'] = "Bilinmiyor"

        return jsonify(haberler)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/duygular')
def duygular_api():
    """Son 7 günün duygu dağılımını getir"""
    try:
        # MongoDB aggregate ile duygu dağılımını al
        pipeline = [
            {
                "$match": {
                    "duygu": {"$exists": True}
                }
            },
            {
                "$group": {
                    "_id": "$duygu",
                    "sayi": {"$sum": 1}
                }
            }
        ]

        sonuc = list(collection.aggregate(pipeline))

        # Chart.js için format
        duygu_verileri = {
            "labels": [],
            "values": [],
            "colors": []
        }

        renk_haritasi = {
            "pozitif": "#28a745",
            "negatif": "#dc3545",
            "notr": "#ffc107",
            "bilinmiyor": "#6c757d"
        }

        for item in sonuc:
            duygu_verileri["labels"].append(item["_id"].title())
            duygu_verileri["values"].append(item["sayi"])
            duygu_verileri["colors"].append(renk_haritasi.get(item["_id"], "#6c757d"))

        return jsonify(duygu_verileri)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/populer_konular')
def populer_konular_api():
    """En çok geçen kelimeleri bul"""
    try:
        haberler = collection.find(
            {"baslik": {"$exists": True}},
            {"baslik": 1, "ozet": 1}
        ).limit(100)

        # Tüm başlık ve özetleri birleştir
        metin = ""
        for haber in haberler:
            metin += " " + haber.get("baslik", "") + " " + haber.get("ozet", "")

        # Kelime temizliği ve sayma
        kelimeler = re.findall(r'\b[a-zA-ZçğıöşüÇĞIİÖŞÜ]{3,}\b', metin.lower())

        # Yaygın kelimeleri filtrele
        stop_words = {
            'için', 'olan', 'olan', 'dedi', 'etti', 'bir', 'ile', 'daha', 'var', 'yok',
            'bu', 'şu', 'da', 'de', 've', 'ki', 'mi', 'mu', 'mı', 'mü', 'gibi', 'kadar',
            'sonra', 'önce', 'üzere', 'beri', 'dolayı', 'göre', 'karşı', 'rağmen',
            'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with'
        }

        kelimeler = [k for k in kelimeler if k not in stop_words and len(k) > 3]

        # En popüler 10 kelime
        populer = Counter(kelimeler).most_common(10)

        return jsonify({
            "kelimeler": [item[0] for item in populer],
            "sayilar": [item[1] for item in populer]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/stats')
def istatistikler_api():
    """Genel istatistikler"""
    try:
        toplam_haber = collection.count_documents({})
        ozetlenmis = collection.count_documents({"ozet": {"$exists": True}})

        # Kaynak dağılımı
        pipeline = [
            {
                "$group": {
                    "_id": "$kaynak",
                    "sayi": {"$sum": 1}
                }
            },
            {"$sort": {"sayi": -1}}
        ]

        kaynaklar = list(collection.aggregate(pipeline))

        return jsonify({
            "toplam_haber": toplam_haber,
            "ozetlenmis": ozetlenmis,
            "kaynaklar": kaynaklar[:5]  # İlk 5 kaynak
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/chat', methods=['POST'])
def chat_api():
    """LLM Chat API"""
    try:
        data = request.get_json()
        soru = data.get('message', '').strip()

        if not soru:
            return jsonify({"error": "Soru boş olamaz"}), 400

        # Gelişmiş chat sistemi kullanılabilir mi?
        if ADVANCED_CHAT_AVAILABLE and all([embedding_model, chroma_collection, llm]):
            try:
                # RAG sistemi ile cevap üret
                cevap = rag_chat_cevabi(soru)
                return jsonify({"response": cevap})
            except Exception as e:
                print(f"RAG hatası: {e}")
                traceback.print_exc()
                # RAG başarısız olursa basit sisteme geri dön
                return jsonify({"response": basit_chat_cevabi(soru)})
        else:
            # Basit cevap sistemi kullan
            return jsonify({"response": basit_chat_cevabi(soru)})

    except Exception as e:
        print(f"Chat API hatası: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Chat hatası: {str(e)}"}), 500


def rag_chat_cevabi(soru):
    """RAG sistemi ile LLM'den cevap al"""
    try:
        print(f"🤖 RAG sorusu: {soru}")

        # Soru vektörleştirme
        soru_vektoru = embedding_model.encode(soru).tolist()
        print("✅ Soru vektörleştirildi")

        # ChromaDB'den alakalı belgeleri getir
        sonuclar = chroma_collection.query(
            query_embeddings=[soru_vektoru],
            n_results=5,  # Daha fazla sonuç getir
            include=["documents", "metadatas"]
        )

        print(f"📊 {len(sonuclar['documents'][0]) if sonuclar['documents'] else 0} belge bulundu")

        # Belgeleri birleştir
        belgeler = sonuclar["documents"][0] if sonuclar["documents"] else []
        metadatalar = sonuclar["metadatas"][0] if sonuclar["metadatas"] else []

        if not belgeler:
            print("⚠️ Hiç belge bulunamadı, basit sisteme geçiliyor")
            return basit_chat_cevabi(soru)

        # En alakalı belgeleri seç ve birleştir
        icerik = "\n\n".join(belgeler[:3])  # İlk 3 belgeyi al

        print(f"📝 Kullanılan içerik uzunluğu: {len(icerik)} karakter")

        # Prompt oluştur
        prompt = f"""Sen bir haber analiz asistanısın. Aşağıdaki haber içeriklerini kullanarak soruyu yanıtla:

HABERLERDEKİ BİLGİLER:
{icerik}

KULLANICI SORUSU: {soru}

YANITLAMA KURALLARI:
- Sadece verilen haber içeriklerinden yararlan
- Cevabını detaylandır ve açıklayıcı ol
- Türkçe yanıtla
- Eğer bilgi yetersizse bunu belirt

CEVAP:"""

        # LLM'den cevap al
        print("🤖 LLM'e gönderiliyor...")
        yanit = llm([HumanMessage(content=prompt)])

        sonuc = yanit.content.strip()
        print(f"✅ LLM yanıtı alındı: {len(sonuc)} karakter")

        return sonuc

    except Exception as e:
        print(f"❌ RAG sistem hatası: {e}")
        traceback.print_exc()
        return basit_chat_cevabi(soru)


def basit_chat_cevabi(soru):
    """Basit chat cevap sistemi (LLM olmadığında fallback)"""
    try:
        soru_lower = soru.lower()
        print(f"💬 Basit chat sorusu: {soru}")

        # MongoDB'den gerçek verileri al
        son_haberler = list(collection.find(
            {"ozet": {"$exists": True}},
            {"baslik": 1, "ozet": 1, "duygu": 1, "kaynak": 1, "islenme_zamani": 1}
        ).sort("islenme_zamani", -1).limit(15))

        print(f"📊 {len(son_haberler)} haber bulundu")

        if any(word in soru_lower for word in ['kaç', 'sayı', 'adet', 'toplam']):
            toplam = collection.count_documents({})
            ozetli = len(son_haberler)
            return f"📊 **Sistem İstatistikleri:**\n\n• Toplam haber: **{toplam}**\n• Özetlenmiş haber: **{ozetli}**\n• Analiz edilen haber sayısı günlük olarak artmaktadır."

        elif any(word in soru_lower for word in ['duygu', 'analiz', 'sentiment', 'his']):
            duygular = {}
            for haber in son_haberler:
                duygu = haber.get('duygu', 'bilinmiyor')
                duygular[duygu] = duygular.get(duygu, 0) + 1

            if duygular:
                duygu_metni = "\n".join([f"• {duygu.title()}: {sayi} haber" for duygu, sayi in duygular.items()])
                en_fazla = max(duygular.items(), key=lambda x: x[1])
                return f"📈 **Son Haberlerin Duygu Analizi:**\n\n{duygu_metni}\n\n🔍 **Genel Trend:** {en_fazla[0].title()} duygu ağırlıkta ({en_fazla[1]} haber)."
            return "⚠️ Henüz duygu analizi verisi bulunmuyor."

        elif any(word in soru_lower for word in ['gündem', 'neler', 'haber', 'son', 'başlık']):
            if son_haberler:
                haber_listesi = []
                for i, haber in enumerate(son_haberler[:8]):
                    baslik = haber.get('baslik', '')
                    kaynak = haber.get('kaynak', 'Bilinmiyor')
                    duygu = haber.get('duygu', 'bilinmiyor')

                    # Duygu emoji'leri
                    duygu_emoji = {'pozitif': '😊', 'negatif': '😔', 'notr': '😐', 'bilinmiyor': '❓'}
                    emoji = duygu_emoji.get(duygu, '❓')

                    haber_listesi.append(
                        f"{i + 1}. {emoji} **{baslik[:80]}{'...' if len(baslik) > 80 else ''}** ({kaynak})")

                return f"📰 **Güncel Haberler:**\n\n" + "\n\n".join(haber_listesi)
            return "⚠️ Henüz haber verisi bulunmuyor."

        elif any(word in soru_lower for word in ['kaynak', 'site', 'nereden', 'nerden']):
            kaynaklar = {}
            for haber in son_haberler:
                kaynak = haber.get('kaynak', 'Bilinmiyor')
                kaynaklar[kaynak] = kaynaklar.get(kaynak, 0) + 1

            if kaynaklar:
                kaynak_listesi = "\n".join([f"• {kaynak}: {sayi} haber" for kaynak, sayi in
                                            sorted(kaynaklar.items(), key=lambda x: x[1], reverse=True)])
                return f"📺 **Aktif Haber Kaynakları:**\n\n{kaynak_listesi}"
            return "⚠️ Kaynak bilgisi bulunamadı."

        elif any(word in soru_lower for word in ['ozet', 'özet', 'özetler']):
            if son_haberler:
                ozetler = []
                for i, haber in enumerate(son_haberler[:5]):
                    baslik = haber.get('baslik', '')
                    ozet = haber.get('ozet', 'Özet mevcut değil')
                    ozetler.append(f"**{i + 1}. {baslik}**\n   {ozet}")

                return f"📋 **Son Haber Özetleri:**\n\n" + "\n\n".join(ozetler)
            return "⚠️ Henüz özetlenmiş haber bulunmuyor."

        elif any(word in soru_lower for word in ['yardım', 'nasıl', 'ne yapabilir', 'komut']):
            return """🤖 **Size Nasıl Yardımcı Olabilirim:**

📊 **İstatistikler için:**
• "Kaç haber var?"
• "Toplam haber sayısı nedir?"

📰 **Haberler için:**
• "Son haberler neler?"
• "Güncel haberler"
• "Son başlıklar"

🎭 **Duygu analizi için:**
• "Duygu analizi nasıl?"
• "Haberlerin genel havası nasıl?"

📺 **Kaynaklar için:**
• "Hangi kaynaklardan haber geliyor?"
• "Aktif kaynaklar neler?"

💬 Daha spesifik sorularınız varsa çekinmeyin!"""

        else:
            # Genel arama yap
            arama_kelimeler = soru_lower.split()
            bulunan_haberler = []

            for haber in son_haberler:
                baslik = haber.get('baslik', '').lower()
                ozet = haber.get('ozet', '').lower()

                if any(kelime in baslik or kelime in ozet for kelime in arama_kelimeler):
                    bulunan_haberler.append(haber)

            if bulunan_haberler:
                sonuc_listesi = []
                for i, haber in enumerate(bulunan_haberler[:5]):
                    baslik = haber.get('baslik', '')
                    ozet = haber.get('ozet', 'Özet mevcut değil')
                    sonuc_listesi.append(f"**{i + 1}. {baslik}**\n   {ozet}")

                return f"🔍 **'{soru}' ile ilgili {len(bulunan_haberler)} haber bulundu:**\n\n" + "\n\n".join(
                    sonuc_listesi)
            else:
                return f"""🤔 **'{soru}' konusunda henüz bir haber bulamadım.**

💡 **Öneriler:**
• Daha genel terimler kullanın
• "Son haberler neler?" diye sorun
• Spesifik konular: ekonomi, spor, teknoloji vb.

📊 Sistemde toplam {collection.count_documents({})} haber mevcut."""

    except Exception as e:
        print(f"❌ Basit chat hatası: {e}")
        return "😅 Üzgünüm, bir teknik sorun yaşandı. Lütfen tekrar deneyin veya farklı bir soru sorun."


if __name__ == '__main__':
    print("🚀 Flask uygulaması başlatılıyor...")
    print(f"📚 Gelişmiş chat: {'✅ Mevcut' if ADVANCED_CHAT_AVAILABLE else '❌ Mevcut değil'}")

    # LLM bileşenlerini başlatmaya çalış
    if ADVANCED_CHAT_AVAILABLE:
        llm_ready = init_llm_components()
        if llm_ready:
            print("✅ Gelişmiş RAG chat sistemi aktif.")
        else:
            print("⚠️ RAG sistemi başlatılamadı, basit chat aktif.")
    else:
        print("⚠️ Basit chat sistemi aktif.")

    app.run(debug=True, host='0.0.0.0', port=5000)