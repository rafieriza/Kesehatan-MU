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
