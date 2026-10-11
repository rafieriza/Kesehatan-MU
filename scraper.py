import os
import feedparser
from datetime import datetime, timedelta
import time
import re
import mysql.connector
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup

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

def scrape_alodokter(cursor):
    """Fungsi HTML Scraping universal untuk mengambil artikel dari Alodokter"""
    print("[SCRAPER] Memulai proses HTML scraping Alodokter...")
    url = "https://www.alodokter.com/kesehatan"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    inserted_alodokter = 0
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"[Error] Gagal mengakses Alodokter, Status Code: {response.status_code}")
            return 0

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Ambil semua tag 'a' yang ada di halaman yang mengarah ke link artikel kesehatan/penyakit
        all_links = soup.find_all('a', href=True)
        
        processed_urls = set()

        for a in all_links:
            try:
                link = a.get('href', '').strip()
                
                # Filter agar hanya mengambil link artikel internal alodokter yang valid
                if not link or not (link.startswith('/') or 'alodokter.com' in link):
                    continue
                
                # Biasanya artikel kesehatan alodokter berupa slug teks, hindari halaman kategori umum
                if link in ['/kesehatan', '/penyakit', '/obat', '/community', '/tanya-dokter']:
                    continue

                if not link.startswith('http'):
                    link = "https://www.alodokter.com" + link

                if link in processed_urls:
                    continue
                processed_urls.add(link)

                # Ambil judul dari teks di dalam tag 'a' atau dari elemen anak terdekatnya (h2, h3, span)
                title_elem = a.find(['h2', 'h3', 'span', 'p'])
                title = title_elem.get_text(strip=True) if title_elem else a.get_text(strip=True)

                # Jika teks terlalu pendek atau menyerupai tombol (seperti "Baca Selengkapnya"), abaikan
                if not title or len(title) < 15 or title.lower() in ['baca selengkapnya', 'selanjutnya']:
                    continue

                # Ambil ringkasan jika ada di sekitar elemen
                summary = title # Default summary pakai judul jika tidak ketemu paragraf pendukung
                parent = a.find_parent('div')
                if parent:
                    p_elem = parent.find('p')
                    if p_elem and p_elem.get_text(strip=True) != title:
                        summary = p_elem.get_text(strip=True)

                if len(summary) > 250:
                    summary = summary[:250] + "..."

                # Ambil gambar thumbnail jika ada di dalam card yang sama
                image_url = ""
                if parent:
                    img_elem = parent.find('img')
                    if img_elem:
                        image_url = img_elem.get('src') or img_elem.get('data-src', '')

                published_at = datetime.now()

                # Masukkan ke database jika lolos filter kesehatan
                if title and link and is_health_article(title):
                    sql = """
                    INSERT IGNORE INTO artikel_kesehatan 
                    (title, summary, source, url, image_url, published_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(sql, (title, summary, "Alodokter", link, image_url, published_at))
                    inserted_alodokter += cursor.rowcount
            except Exception as item_err:
                continue

    except Exception as e:
        print(f"[Scraper Exception (Alodokter)]: {e}")

    print(f"[SCRAPER] Berhasil menyerap {inserted_alodokter} artikel dari Alodokter.")
    return inserted_alodokter

def scrape_kompas(cursor):
    """Fungsi HTML Scraping khusus untuk mengambil artikel dari Kompas Health"""
    print("[SCRAPER] Memulai proses HTML scraping Kompas Health...")
    url = "https://health.kompas.com"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    inserted_kompas = 0
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"[Error] Gagal mengakses Kompas Health, Status Code: {response.status_code}")
            return 0

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Cari semua elemen artikel (biasanya Kompas menggunakan class article__item atau tag link di rubrik)
        article_items = soup.select('div.article__item, div.articleItem, .neath-item')
        
        # Fallback jika selector spesifik tidak ketemu, ambil semua tag 'a' yang mengarah ke health.kompas.com
        if not article_items:
            article_items = soup.find_all('a', href=True)

        processed_urls = set()

        for item in article_items:
            try:
                # Jika item berupa tag <a> langsung atau dibungkus dalam div
                if item.name == 'a':
                    link = item.get('href', '').strip()
                    a_elem = item
                else:
                    a_elem = item.find('a', href=True)
                    if not a_elem:
                        continue
                    link = a_elem.get('href', '').strip()

                # Filter link valid milik kompas health
                if not link or 'kompas.com' not in link or '/read/' not in link:
                    continue

                if link in processed_urls:
                    continue
                processed_urls.add(link)

                # Ambil Judul
                title_elem = item.find(['h2', 'h3', 'h4']) if item.name != 'a' else item
                title = title_elem.get_text(strip=True) if title_elem else a_elem.get_text(strip=True)

                if not title or len(title) < 15:
                    continue

                # Ambil Ringkasan
                summary = title
                p_elem = item.find('p')
                if p_elem:
                    summary = p_elem.get_text(strip=True)
                
                if len(summary) > 250:
                    summary = summary[:250] + "..."

                # Ambil Gambar
                img_elem = item.find('img')
                image_url = ""
                if img_elem:
                    image_url = img_elem.get('data-src') or img_elem.get('src', '')

                published_at = datetime.now()

                # Masukkan ke database jika lolos filter kesehatan
                if title and link and is_health_article(title):
                    sql = """
                    INSERT IGNORE INTO artikel_kesehatan 
                    (title, summary, source, url, image_url, published_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(sql, (title, summary, "Kompas Health", link, image_url, published_at))
                    inserted_kompas += cursor.rowcount
            except Exception as item_err:
                continue

    except Exception as e:
        print(f"[Scraper Exception (Kompas)]: {e}")

    print(f"[SCRAPER] Berhasil menyerap {inserted_kompas} artikel dari Kompas Health.")
    return inserted_kompas

def scrape_detik(cursor):
    """Fungsi HTML Scraping khusus untuk mengambil artikel dari Detik Health dengan penanganan gambar lazy-load"""
    print("[SCRAPER] Memulai proses HTML scraping Detik Health...")
    url = "https://health.detik.com"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    inserted_detik = 0
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"[Error] Gagal mengakses Detik Health, Status Code: {response.status_code}")
            return 0

        soup = BeautifulSoup(response.text, 'html.parser')
        article_items = soup.select('article, div.list-content, div.media__text')
        
        if not article_items:
            article_items = soup.find_all('a', href=True)

        processed_urls = set()

        for item in article_items:
            try:
                if item.name == 'a':
                    link = item.get('href', '').strip()
                    a_elem = item
                else:
                    a_elem = item.find('a', href=True)
                    if not a_elem:
                        continue
                    link = a_elem.get('href', '').strip()

                if not link or 'detik.com' not in link:
                    continue

                # FILTER BARU: Buang halaman tag, indeks, foto, atau video
                if '/tag/' in link or '/indeks' in link or '/foto/' in link or '/video/' in link:
                    continue

                if link in processed_urls:
                    continue
                processed_urls.add(link)

                # Ambil Judul
                title_elem = item.find(['h2', 'h3', 'h4']) if item.name != 'a' else item
                title = title_elem.get_text(strip=True) if title_elem else a_elem.get_text(strip=True)

                if not title or len(title) < 15 or title.lower() in ['baca selengkapnya', 'selanjutnya']:
                    continue

                # Ambil Ringkasan
                summary = title
                p_elem = item.find('p')
                if p_elem:
                    summary = p_elem.get_text(strip=True)
                
                if len(summary) > 250:
                    summary = summary[:250] + "..."

                # PENGAMBILAN GAMBAR LEBIH AMAN (Mendeteksi berbagai atribut lazy loading Detik)
                img_elem = item.find('img')
                image_url = ""
                if img_elem:
                    image_url = (
                        img_elem.get('src') or 
                        img_elem.get('data-src') or 
                        img_elem.get('data-lazy-src') or 
                        img_elem.get('data-original') or 
                        ""
                    )
                    # Pastikan jika URL gambar berupa relative path, diubah jadi absolute
                    if image_url and not image_url.startswith('http'):
                        image_url = ""

                published_at = datetime.now()

                # Masukkan ke database jika lolos filter kesehatan
                if title and link and is_health_article(title):
                    sql = """
                    INSERT IGNORE INTO artikel_kesehatan 
                    (title, summary, source, url, image_url, published_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(sql, (title, summary, "Detik Health", link, image_url, published_at))
                    inserted_detik += cursor.rowcount
            except Exception as item_err:
                continue

    except Exception as e:
        print(f"[Scraper Exception (Detik)]: {e}")

    print(f"[SCRAPER] Berhasil menyerap {inserted_detik} artikel dari Detik Health.")
    return inserted_detik
    
def scrape_kesehatan():
    print("[SCRAPER] Memulai proses penarikan berita kesehatan...")
    init_db()
    
    sources = [
        {
            "name": "CNN Indonesia",
            "url": "https://www.cnnindonesia.com/gaya-hidup/rss"
        },
    ]
    
    conn = get_db_connection()
    cursor = conn.cursor()
    inserted_count = 0

    # 1. Jalankan RSS Scraping (Sistem Lama)
    for src in sources:
        try:
            print(f"[SCRAPER] Membaca feed: {src['name']}...")
            parsed_feed = feedparser.parse(src["url"])
            
            for entry in parsed_feed.entries:
                title = entry.get('title', '').strip()
                url = entry.get('link', '').strip()
                
                raw_summary = entry.get('summary', '').strip() or entry.get('description', '').strip()
                summary = re.sub('<[^<]+?>', '', raw_summary)
                if len(summary) > 250:
                    summary = summary[:250] + "..."
                
                if not summary:
                    summary = ""

                image_url = ""
                if hasattr(entry, 'media_content') and entry.media_content:
                    image_url = entry.media_content[0].get('url', '')
                elif hasattr(entry, 'enclosures') and entry.enclosures:
                    image_url = entry.enclosures[0].get('href', '')

                published_at = parse_date(entry)

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
                        print(f"Error insert artikel RSS: {db_err}")
        except Exception as e:
            print(f"Gagal memproses RSS dari {src['name']}: {e}")

    # 2. Jalankan HTML Scraping Alodokter (Sistem Baru)
    try:
        alo_count = scrape_alodokter(cursor)
        inserted_count += alo_count
    except Exception as e:
        print(f"Gagal menjalankan Alodokter scraper: {e}")

    # 3. Jalankan HTML Scraping Kompas Health (Ditambahkan agar tereksekusi)
    try:
        kompas_count = scrape_kompas(cursor)
        inserted_count += kompas_count
    except Exception as e:
        print(f"Gagal menjalankan Kompas scraper: {e}")

    # 4. Jalankan HTML Scraping Detik Health (Ditambahkan agar tereksekusi)
    try:
        detik_count = scrape_detik(cursor)
        inserted_count += detik_count
    except Exception as e:
        print(f"Gagal menjalankan Detik scraper: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    print(f"[SCRAPER] Selesai! Total keseluruhan berhasil memproses {inserted_count} artikel baru.")
    
    # Jalankan pembersihan otomatis database
    auto_cleanup()

if __name__ == "__main__":
    scrape_kesehatan()
