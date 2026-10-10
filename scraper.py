import os
import feedparser
from datetime import datetime
import time
import re
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 26070)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )

def init_db():
    """Memastikan tabel database sudah dibuat berdasarkan schema.sql"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS artikel_kesehatan (
        id INT AUTO_INCREMENT PRIMARY KEY,
        judul VARCHAR(255) NOT NULL,
        ringkasan TEXT,
        sumber_portal VARCHAR(100) NOT NULL,
        url_artikel VARCHAR(500) NOT NULL UNIQUE,
        url_gambar VARCHAR(500),
        tanggal_terbit DATETIME DEFAULT CURRENT_TIMESTAMP,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FULLTEXT KEY ft_pencarian (judul, ringkasan)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)
    conn.commit()
    cursor.close()
    conn.close()

def parse_date(entry):
    """Mendeteksi tanggal terbit dari RSS feed secara akurat"""
    if hasattr(entry, 'published_parsed') and entry.published_parsed:
        return datetime.fromtimestamp(time.mktime(entry.published_parsed))
    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
        return datetime.fromtimestamp(time.mktime(entry.updated_parsed))
    return datetime.now()

def is_health_article(judul):
    """Filter berbasis judul untuk memastikan kontennya seputar kesehatan/medis"""
    text = judul.lower()

    # Kata Kunci Negatif (Buang jika membahas non-kesehatan)
    exclude_keywords = [
        'resep', 'kuliner', 'restoran', 'makanan', 'gaun', 'fashion', 
        'outfit', 'skincare', 'makeup', 'wisata', 'destinasi', 'hotel', 
        'tiket', 'konser', 'film', 'zodiak', 'ramalan', 'pariwisata'
    ]
    if any(ex in text for ex in exclude_keywords):
        return False

    # Kata Kunci Positif (Unsur kesehatan/medis)
    health_keywords = [
        'kesehatan', 'sehat', 'dokter', 'rs', 'rumah sakit', 'obat', 'penyakit', 
        'virus', 'bakteri', 'vaksin', 'gizi', 'nutrisi', 'diet', 'kanker', 
        'diabetes', 'jantung', 'stroke', 'hipertensi', 'darah tinggi', 'mental', 
        'depresi', 'stres', 'klinik', 'medis', 'pasien', 'infeksi', 'demam', 
        'dbd', 'flu', 'covid', 'tumor', 'kulit', 'gigi', 'mpox', 'bpjs', 
        'imunisasi', 'tidur', 'gejala', 'stunting', 'cedera', 'olahraga'
    ]
    
    return any(keyword in text for keyword in health_keywords)

def auto_cleanup():
    """Hapus artikel yang usianya lebih dari 180 hari"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM artikel_kesehatan WHERE created_at < NOW() - INTERVAL 180 DAY")
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[CLEANUP ERROR]: {e}")

def scrape_kesehatan():
    print("[SCRAPER] Memulai proses penarikan RSS berita kesehatan...")
    init_db()
    
    # MULTI-SLOT RSS SOURCES: Tambahkan link RSS portal lain di bawah sini jika sudah menemukannya!
    sources = [
        {
            "name": "CNN Indonesia",
            "url": "https://www.cnnindonesia.com/gaya-hidup/rss"
        },
        # {"name": "Portal Lain", "url": "https://link-rss-lain.com/rss"}
    ]
    
    conn = get_db_connection()
    cursor = conn.cursor()
    inserted_count = 0

    for src in sources:
        try:
            parsed_feed = feedparser.parse(src["url"])
            
            for entry in parsed_feed.entries:
                judul = entry.get('title', '').strip()
                url_artikel = entry.get('link', '').strip()
                
                raw_summary = entry.get('summary', '').strip() or entry.get('description', '').strip()
                ringkasan = re.sub('<[^<]+?>', '', raw_summary)
                if len(ringkasan) > 200:
                    ringkasan = ringkasan[:200] + "..."

                # Ambil gambar jika ada
                url_gambar = ""
                if hasattr(entry, 'media_content') and entry.media_content:
                    url_gambar = entry.media_content[0].get('url', '')
                elif hasattr(entry, 'enclosures') and entry.enclosures:
                    url_gambar = entry.enclosures[0].get('href', '')

                tanggal_terbit = parse_date(entry)

                if judul and url_artikel and is_health_article(judul):
                    try:
                        sql = """
                        INSERT IGNORE INTO artikel_kesehatan 
                        (judul, ringkasan, sumber_portal, url_artikel, url_gambar, tanggal_terbit)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """
                        cursor.execute(sql, (judul, ringkasan, src['name'], url_artikel, url_gambar, tanggal_terbit))
                        inserted_count += cursor.rowcount
                    except Exception as db_err:
                        print(f"Error insert artikel: {db_err}")
        except Exception as e:
            print(f"Gagal memproses RSS dari {src['name']}: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    print(f"[SCRAPER] Selesai! Berhasil memproses {inserted_count} artikel baru.")
    auto_cleanup()

if __name__ == "__main__":
    scrape_kesehatan()
