import os
import requests
from bs4 import BeautifulSoup
import mysql.connector
from dotenv import load_dotenv

# Load environment variables
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

def auto_cleanup():
    """Fitur Auto Clean-Up Storage: Hapus artikel yang usianya lebih dari 180 hari (6 bulan)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM artikel_kesehatan WHERE created_at < NOW() - INTERVAL 180 DAY")
        deleted_count = cursor.rowcount
        conn.commit()
        print(f"[CLEANUP] Berhasil membersihkan {deleted_count} artikel lama.")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[CLEANUP ERROR] Gagal membersihkan storage: {e}")

def scrape_kesehatan():
    print("[SCRAPER] Memulai proses scraping berita kesehatan...")
    init_db()
    
    # Contoh endpoint berita RSS/Scraping sederhana
    # Kamu bisa menambahkan daftar URL portal kesehatan lainnya di sini
    sources = [
        {
            "name": "Detik Health",
            "url": "https://health.detik.com/"
        }
    ]
    
    conn = get_db_connection()
    cursor = conn.cursor()
    inserted_count = 0

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    for src in sources:
        try:
            res = requests.get(src["url"], headers=headers, timeout=10)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                articles = soup.find_all('article')
                
                for art in articles[:10]:  # Ambil 10 artikel terbaru per portal
                    title_elem = art.find('h3') or art.find('h2')
                    link_elem = art.find('a')
                    img_elem = art.find('img')
                    
                    if title_elem and link_elem:
                        judul = title_elem.get_text(strip=True)
                        url_artikel = link_elem.get('href', '')
                        url_gambar = img_elem.get('src', '') if img_elem else ''
                        ringkasan = f"Artikel kesehatan terbaru dari {src['name']}."

                        if url_artikel.startswith('http'):
                            try:
                                sql = """
                                INSERT INTO artikel_kesehatan (judul, ringkasan, sumber_portal, url_artikel, url_gambar)
                                VALUES (%s, %s, %s, %s, %s)
                                ON DUPLICATE KEY UPDATE judul=VALUES(judul)
                                """
                                cursor.execute(sql, (judul, ringkasan, src['name'], url_artikel, url_gambar))
                                inserted_count += cursor.rowcount
                            except Exception as db_err:
                                print(f"Error insert artikel: {db_err}")
        except Exception as e:
            print(f"Gagal scraping dari {src['name']}: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    print(f"[SCRAPER] Selesai! Berhasil memproses {inserted_count} artikel.")
    
    # Jalankan pembersihan otomatis
    auto_cleanup()

if __name__ == "__main__":
    scrape_kesehatan()
