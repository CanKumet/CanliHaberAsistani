from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json, current_timestamp
from pyspark.sql.types import StructType, StringType
from pymongo import MongoClient
import os
import json
from textblob import TextBlob

# PySpark için ortam değişkeni
os.environ["PYSPARK_PYTHON"] = "python"
os.environ["PYSPARK_DRIVER_PYTHON"] = "python"

# MongoDB bağlantısı
mongo_client = MongoClient("mongodb://localhost:27018/")
db = mongo_client["haberDB"]
collection = db["analizli_haberler"]

# Mongo'ya kayıt fonksiyonu (güncellemeli)
def save_to_mongodb(df, epoch_id):
    def duygu_analiz(metin):
        try:
            skor = TextBlob(metin).sentiment.polarity
            if skor > 0.2:
                return "pozitif"
            elif skor < -0.2:
                return "negatif"
            else:
                return "notr"
        except:
            return "bilinmiyor"

    data = df.toJSON().map(lambda x: json.loads(x)).collect()
    for item in data:
        item["duygu"] = duygu_analiz(item.get("icerik", ""))
        item["islenme_zamani"] = str(item.get("islenme_zamani", ""))
        unique_key = item.get("baslik", "") + item.get("yayim_zamani", "")
        item["unique_key"] = unique_key  # kontrol için key oluştur

        # Eğer varsa güncelle, yoksa ekle
        collection.update_one(
            {"unique_key": unique_key},
            {"$set": item},
            upsert=True
        )

    if data:
        print(f"[✓] {len(data)} haber MongoDB'ye eklendi/güncellendi.")
    else:
        print("[!] Hiç haber alınamadı.")

# Spark session
spark = SparkSession.builder \
    .appName("KafkaHaberConsumer") \
    .config("spark.sql.streaming.forceDeleteTempCheckpointLocation", "true") \
    .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.13:4.0.0") \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN")

# JSON şeması
schema = StructType() \
    .add("baslik", StringType()) \
    .add("icerik", StringType()) \
    .add("yayim_zamani", StringType()) \
    .add("kaynak", StringType()) \
    .add("link", StringType())

# Kafka'dan oku
df_kafka = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "localhost:9292") \
    .option("subscribe", "haber-akisi") \
    .option("startingOffsets", "latest") \
    .load()

# Parse işlemi
df_parsed = df_kafka.selectExpr("CAST(value AS STRING) as json") \
    .select(from_json(col("json"), schema).alias("data")) \
    .select("data.*") \
    .withColumn("islenme_zamani", current_timestamp())

# Mongo'ya yaz
df_parsed.writeStream \
    .foreachBatch(save_to_mongodb) \
    .outputMode("append") \
    .start()

# Konsola da yaz
df_parsed.writeStream \
    .outputMode("append") \
    .format("console") \
    .option("truncate", False) \
    .start() \
    .awaitTermination()
