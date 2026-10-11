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
        # --- KULINER, MAKANAN, & GAYA HIDUP ---
        'resep', 'kuliner', 'restoran', 'makanan', 'minuman', 'kafe', 'cafe', 'menu', 
        'masak', 'memasak', 'lezat', 'enak', 'camilan', 'snack', 'jajanan', 'mukbang',
        'hidangan', 'bumbu', 'dapur', 'warung', 'kedai', 'Review Makanan', 'liburan', 'kebanjiran', 'hiburan',

        # --- FASHION, KECANTIKAN, & SKINCARE ---
        'gaun', 'fashion', 'outfit', 'skincare', 'makeup', 'kosmetik', 'gaya', 'tren',
        'baju', 'pakaian', 'model', 'peragaan', 'lipstik', 'skincare rutin', 'glowing',
        'gaya rambut', 'potongan rambut', 'parfum', 'aksesoris', 'OOTD', 'timnas',

        # --- WISATA, TRAVEL, & TRANSPORTASI ---
        'wisata', 'destinasi', 'hotel', 'tiket', 'pariwisata', 'bandara', 'pesawat',
        'liburan', 'traveling', 'resort', 'penginapan', 'pantai', 'gunung', 'rute',
        'stasiun', 'mudik', 'koper', 'oleh-oleh', 'backpacker', 'rumah', 'apart', 'apartemen',

        # --- HIBURAN, FILM, MUSIK, & GOSIP (ENTERTAINMENT) ---
        'konser', 'film', 'bioskop', 'sinopsis', 'aktor', 'aktris', 'seleb', 'selebriti',
        'artis', 'gosip', 'rumor', 'pacar', 'menikah', 'cerai', 'lagu', 'album', 'musik',
        'drama', 'drakor', 'series', 'netflix', 'konser musik', 'manggung',

        # --- ASTROLOGI, HOBI, & HIBURAN RINGAN ---
        'zodiak', 'ramalan', 'horoskop', 'shio', 'bintang', 'keberuntungan', 'primbon',
        'ikan', 'kucing', 'anjing', 'hewan peliharaan', 'pet', 'tanaman hias', 'kebun', 'pengunjung', 'wisatawan', 'konsumen'
        'otomotif', 'mobil', 'motor', 'game', 'gaming', 'esports', 'gadget', 'hp', 'pengunjung', 'pilot', 'pramugari', 'pramugara',

        # --- POLITIK & BISNIS NON-MEDIS (Untuk mencegah spam berita reguler) ---
        'saham', 'investasi', 'bisnis', 'ekonomi', 'rupiah', 'dolar', 'politik', 'pemilu', 'daerah', 'pemda', 'teknologi', 'gubernur'
        'pilkada', 'dpr', 'presiden', 'menteri', 'korupsi', 'kriminal', 'rampok', 'begal', 'jalan', 'partai', 'kejahatan', 'pemprov'
    ]
    if any(ex in text for ex in exclude_keywords):
        return False

    # Kata Kunci Positif (Wajib ada unsur kesehatan/medis)
    health_keywords = [
        # --- FAKILITAS, TENAGA, & ADMINISTRASI MEDIS ---
        'kesehatan', 'sehat', 'sakit', 'gejala', 'medis', 'klinik', 'puskesmas', 'rs', 'rumah sakit', 'dokter', 'kedokteran',
        'dokter', 'psikolog', 'psikologi', 'pasien', 'bpjs', 'perawat', 'bidan', 'apotek', 'laboratorium', 'donor darah',
        'faskes', 'igd', 'icu', 'rawat inap', 'rawat jalan', 'rekam medis', 'rujukan', 'diagnosis', 'obat', 'farmasi',
        'prosedur', 'operasi', 'bedah', 'terapi obat', 'rehabilitasi', 'ambulan', 'screening', 'diagnosa', 'onkolog',
    
        # --- GEJALA & KONDISI UMUM ---
        'infeksi', 'demam', 'cedera', 'sariawan', 'stunting', 'luka', 'nyeri', 'pusing', 'sakit kepala',
        'mual', 'muntah', 'diare', 'batuk', 'pilek', 'sesak napas', 'alergi', 'ruam', 'bengkak',
        'kelelahan', 'lemas', 'insomnia', 'kejang', 'pingsan', 'radang', 'inflamasi', 'sel', 'jaringan', 'diagnosis',
    
        # --- PENYAKIT INFEKSI (VIRUS, BAKTERI, PARASIT) ---
        'virus', 'bakteri', 'flu', 'dbd', 'demam berdarah', 'covid', 'mpox', 'cacar', 'tbc', 'tuberculosis',
        'tifus', 'tipes', 'malaria', 'hiv', 'aids', 'hepatitis', 'tetanus', 'pneumonia', 'ispa', 'rabies',
        'leptospirosis', 'anthrax', 'kusta', 'tokso', 'cacingan', 'kudis', 'scabies',
    
        # --- PENYAKIT KRONIS & NON-MENULAR (PTM) ---
        'kanker', 'tumor', 'diabetes', 'kencing manis', 'jantung', 'stroke', 'hipertensi', 'darah tinggi',
        'kolesterol', 'asam urat', 'kista', 'miom', 'gagal ginjal', 'batu ginjal', 'asma', 'gout',
        'osteoporosis', 'rematik', 'artritis', 'autoimun', 'lupus', 'alzheimer', 'demensia', 'parkinson',
        'epilepsi', 'amandel', 'sinusitis', 'varises', 'hernia', 'bakteri', 'virus', 'kronis',
    
        # --- KESEHATAN ORGAN & SPESIALISTIK ---
        # Pencernaan & Ekskresi
        'lambung', 'maag', 'gerd', 'usus buntu', 'wasir', 'ambeyen', 'lever', 'sirosis',
        # Mata, THT, & Gigi
        'mata', 'katarak', 'glaukoma', 'minus', 'telinga', 'hidung', 'tenggorokan', 'gigi', 'gusi', 'karies',
        # Kulit & Kelamin
        'kulit', 'dermatitis', 'eksim', 'jerawat', 'kurap', 'kutil', 'kelamin', 'sipilis', 'gonore',
    
        # --- KESEHATAN REPRODUKSI, IBU, & ANAK ---
        'kehamilan', 'hamil', 'janin', 'kandungan', 'melahirkan', 'persalinan', 'nifas', 'asi', 'menyusui',
        'kb', 'kontrasepsi', 'kespro', 'menstruasi', 'haid', 'pms', 'kesuburan', 'infertil', 'pcos',
        'pediatri', 'tumbuh kembang', 'imunisasi', 'vaksin',
    
        # --- KESEHATAN MENTAL & JIWA ---
        'mental', 'otak', 'jiwa', 'depresi', 'stres', 'anxiety', 'kecemasan', 'trauma', 'skizofrenia',
        'bipolar', 'autisme', 'adhd', 'insomnia', 'gangguan tidur', 'panic attack', 'halusinasi',
    
        # --- FARMAKOLOGI & SUPLEMENTASI ---
        'obat', 'vitamin', 'suplemen', 'antibiotik', 'analgesik', 'paracetamol', 'antiseptik', 'salep',
        'sirup obat', 'kapsul', 'tablet', 'dosis', 'resep dokter', 'herbal', 'jamu',
    
        # --- GIZI, DIET, & GAYA HIDUP SEHAT ---
        'gizi', 'nutrisi', 'diet', 'kalori', 'obesitas', 'kegemukan', 'karbohidrat', 'protein', 'lemak',
        'serat', 'hidrasi', 'kebugaran', 'fitness', 'aerobik', 'detoks', 'sanitasi', 'higiene'
    
        # Padanan Bahasa Inggris (Untuk Jurnal / Medical Xpress)
        'health', 'healthy', 'doctor', 'hospital', 'medicine', 'drug', 'disease', 
        'illness', 'treatment', 'therapy', 'virus', 'bacteria', 'vaccine', 
        'nutrition', 'cancer', 'diabetes', 'heart', 'cardiac', 'stroke', 
        'hypertension', 'mental', 'depression', 'stress', 'clinic', 'medical', 
        'patient', 'infection', 'fever', 'flu', 'covid', 'tumor', 'skin', 
        'dental', 'sleep', 'symptom', 'injury', 'exercise', 'clinical', 'trial',
        'study shows', 'researchers find', 'blood pressure', 'brain'
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
        {
            "name": "Liputan6",
            "url": "https://feed.liputan6.com/rss/kesehatan"
        },
        {
            "name": "Detik Health",
            "url": "https://health.detik.com/sexual-health"
        },
        {
            "name": "Detik Health",
            "url": "https://health.detik.com/berita-detikhealth/rss"
        },
        {
            "name": "Medical Xpress",
            "url": "https://medicalxpress.com/rss-feed/"
        },
                {
            "name": "ScienceDaily",
            "url": "https://www.sciencedaily.com/rss/top/health.xml"
        },
                {
            "name": "Sindonews Health",
            "url": "https://lifestyle.sindonews.com/rss"
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
                
                # --- TAMBAHKAN FILTER INI UNTUK SINDONEWS ---
                if src['name'] == "Sindonews Health":
                    categories = [t.get('term', '').lower() for t in entry.get('tags', []) if t.get('term')]
                    if not any(cat in ['health', 'kesehatan'] for cat in categories):
                        continue
                # ---------------------------------------------
                
                # Tangani summary jika kosong dari RSS
                raw_summary = entry.get('summary', '').strip() or entry.get('description', '').strip()
                summary = re.sub('<[^<]+?>', '', raw_summary)
                if len(summary) > 250:
                    summary = summary[:250] + "..."
                
                # Jika ringkasan benar-benar kosong dari sumbernya, biarkan string kosong (agar frontend bisa skip)
                if not summary:
                    summary = ""

                # Ambil gambar thumbnail dengan fallback yang lebih agresif
                image_url = ""
                
                # 1. Cek media_thumbnail langsung
                if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
                    image_url = entry.media_thumbnail[0].get('url', '')
                
                # 2. Cek apakah tersimpan di dalam entry.links (biasanya feedparser naruh tipe gambar di sini)
                if not image_url and hasattr(entry, 'links'):
                    for link in entry.links:
                        if 'image' in link.get('type', ''):
                            image_url = link.get('href', '')
                            break
            
                # 3. Cek media_content standar
                if not image_url and hasattr(entry, 'media_content') and entry.media_content:
                    image_url = entry.media_content[0].get('url', '')
                    
                # 4. Cek enclosures
                if not image_url and hasattr(entry, 'enclosures') and entry.enclosures:
                    image_url = entry.enclosures[0].get('href', '')
                    
                # 5. Ekstraksi manual dari teks description/summary jika masih kosong
                if not image_url and ('summary' in entry or 'description' in entry):
                    import re
                    raw_html = entry.get('summary', '') or entry.get('description', '')
                    img_match = re.search(r'<img[^>]+src="([^">]+)"', raw_html)
                    if img_match:
                        image_url = img_match.group(1)

                # --- TAMBAHKAN INI DI BAWAHNYA UTK UPGRADE KE HD ---
                if "scx1.b-cdn.net" in image_url and "/tmb/" in image_url:
                    image_url = image_url.replace("/tmb/", "/")

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
