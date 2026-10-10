import os
import feedparser
from datetime import datetime, timedelta
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
        database=os.getenv("DB_NAME"),
        connect_timeout=5
    )

def init_db():
    """Memastikan tabel database sudah dibuat berdasarkan schema"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS artikel_kesehatan (
        id INT AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        summary TEXT,
        source VARCHAR(100) NOT NULL,
        url VARCHAR(500) NOT NULL UNIQUE,
        image_url VARCHAR(500),
        published_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FULLTEXT KEY ft_pencarian (title, summary)
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

def is_health_article(title):
    """Filter cerdas berbasis judul untuk mengisolasi isu kesehatan dari berita umum/lifestyle"""
    text = title.lower()

    # Kata Kunci Negatif (Segera buang jika membahas non-kesehatan)
    exclude_keywords = [
        'resep', 'kuliner', 'restoran', 'makanan', 'gaun', 'fashion', 
        'outfit', 'skincare', 'makeup', 'wisata', 'destinasi', 'hotel', 
        'tiket', 'konser', 'film', 'zodiak', 'ramalan', 'pariwisata'
    ]
    if any(ex in text for ex in exclude_keywords):
        return False

    # Kata Kunci Positif (Wajib ada unsur kesehatan/medis)
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
    """Auto Clean-up Storage: Hapus artikel yang usianya lebih dari 365 hari (1 tahun)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        one_year_ago = datetime.now() - timedelta(days=365)
        cursor.execute("DELETE FROM artikel_kesehatan WHERE published_at < %s OR created_at < %s", (one_year_ago, one_year_ago))
        deleted_count = cursor.rowcount
        conn.commit()
        print(f"[CLEANUP] Berhasil membersihkan {deleted_count} artikel lama.")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[CLEANUP ERROR] Gagal membersihkan storage: {e}")

def scrape_kesehatan():
    print("[SCRAPER] Memulai proses penarikan RSS berita kesehatan...")
    init_db()
    
    # MULTI-SLOT RSS SOURCES: Tambahkan link RSS portal lain di bawah baris ini jika sudah menemukannya!
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
            print(f"[SCRAPER] Membaca feed: {src['name']}...")
            parsed_feed = feedparser.parse(src["url"])
            
            for entry in parsed_feed.entries:
                title = entry.get('title', '').strip()
                url = entry.get('link', '').strip()
                
                # Tangani summary jika kosong dari RSS
                raw_summary = entry.get('summary', '').strip() or entry.get('description', '').strip()
                summary = re.sub('<[^<]+?>', '', raw_summary)
                if len(summary) > 250:
                    summary = summary[:250] + "..."
                
                # Jika ringkasan benar-benar kosong dari sumbernya, biarkan string kosong (agar frontend bisa skip)
                if not summary:
                    summary = ""

                # Ambil gambar thumbnail jika tersedia
                image_url = ""
                if hasattr(entry, 'media_content') and entry.media_content:
                    image_url = entry.media_content[0].get('url', '')
                elif hasattr(entry, 'enclosures') and entry.enclosures:
                    image_url = entry.enclosures[0].get('href', '')

                published_at = parse_date(entry)

                # Filter khusus judul kesehatan
                if title and url and is_health_article(title):
                    try:
                        sql = """
                        INSERT IGNORE INTO artikel_kesehatan 
                        (title, summary, source, url, image_url, published_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """
                        cursor.execute(sql, (title, summary, src['name'], url, image_url, published_at))
                        inserted_count += cursor.rowcount
                    except Exception as db_err:
                        print(f"Error insert artikel: {db_err}")
        except Exception as e:
            print(f"Gagal memproses RSS dari {src['name']}: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    print(f"[SCRAPER] Selesai! Berhasil memproses {inserted_count} artikel baru.")
    
    # Jalankan pembersihan otomatis database
    auto_cleanup()

if __name__ == "__main__":
    scrape_kesehatan()
