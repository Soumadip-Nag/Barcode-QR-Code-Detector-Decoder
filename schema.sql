-- MySQL schema for Barcode & QR Code Detector/Decoder
CREATE DATABASE IF NOT EXISTS barcode_db CHARACTER SET utf8mb4;
USE barcode_db;

CREATE TABLE IF NOT EXISTS scans (
  id INT AUTO_INCREMENT PRIMARY KEY,
  filename VARCHAR(255) DEFAULT '',
  image_path VARCHAR(512) DEFAULT '',
  codes_found INT DEFAULT 0,
  barcodes INT DEFAULT 0,
  qr_codes INT DEFAULT 0,
  engine VARCHAR(64) DEFAULT 'ZXing-Java engine',
  ml_error TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS scan_results (
  id INT AUTO_INCREMENT PRIMARY KEY,
  scan_id INT NOT NULL,
  code_index INT DEFAULT 1,
  code_type VARCHAR(32) DEFAULT 'BARCODE',
  code_format VARCHAR(64) DEFAULT 'Barcode',
  data TEXT,
  valid TINYINT(1) DEFAULT 0,
  note VARCHAR(255) DEFAULT '',
  confidence FLOAT DEFAULT 0,
  FOREIGN KEY (scan_id) REFERENCES scans(id) ON DELETE CASCADE,
  INDEX idx_scan (scan_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS products (
  id INT AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(255) UNIQUE NOT NULL,
  name VARCHAR(255) DEFAULT '',
  brand VARCHAR(255) DEFAULT '',
  category VARCHAR(255) DEFAULT '',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

INSERT IGNORE INTO products (code, name, brand, category) VALUES
  ('0128016691675', 'Demo Milk 1L', 'Demo Dairy', 'Grocery'),
  ('4606453849072', 'Demo Biscuits 400g', 'Demo Foods', 'Grocery');
