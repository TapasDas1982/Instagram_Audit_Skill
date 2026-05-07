-- Instagram Audit Skill — MySQL schema
-- Database: ig_audit
--
-- Apply on a fresh MySQL 8 install:
--     mysql -u root -p < db/schema.sql
--
-- Then create the application user (run separately, replace STRONG_PASSWORD):
--     CREATE USER 'ig_audit_user'@'localhost' IDENTIFIED BY 'STRONG_PASSWORD';
--     GRANT ALL PRIVILEGES ON ig_audit.* TO 'ig_audit_user'@'localhost';
--     FLUSH PRIVILEGES;

CREATE DATABASE IF NOT EXISTS ig_audit
    DEFAULT CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE ig_audit;

-- accounts: every IG handle the system knows about — owned, peer, or teacher
CREATE TABLE IF NOT EXISTS accounts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ig_user_id VARCHAR(64) UNIQUE,           -- IG numeric ID, NULL until API connected
    username VARCHAR(128) NOT NULL UNIQUE,
    display_name VARCHAR(255),
    studio_location VARCHAR(64),             -- e.g. 'ballygunge', 'new_alipore', 'new_town'
    account_type ENUM('owned','peer','teacher') DEFAULT 'owned',
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_account_type (account_type),
    INDEX idx_studio_location (studio_location)
) ENGINE=InnoDB;

-- audits: one row per audit run, stores the full normalized snapshot for re-scoring
CREATE TABLE IF NOT EXISTS audits (
    id INT AUTO_INCREMENT PRIMARY KEY,
    account_id INT NOT NULL,
    audit_date DATE NOT NULL,
    source ENUM('csv','api') NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    overall_score DECIMAL(5,2),              -- 0.00–100.00
    raw_data_json LONGTEXT,                  -- normalized AuditInput snapshot
    scores_json TEXT,                        -- per-dimension scores
    findings_json TEXT,                      -- generated findings/actions
    report_path VARCHAR(512),                -- absolute path to generated .docx
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    INDEX idx_audit_date (audit_date),
    INDEX idx_account_date (account_id, audit_date DESC)
) ENGINE=InnoDB;

-- audit_history: long-form per-dimension metric log for trend charts in the admin panel
CREATE TABLE IF NOT EXISTS audit_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    account_id INT NOT NULL,
    audit_id INT NOT NULL,
    dimension VARCHAR(32) NOT NULL,
    score DECIMAL(5,2),
    metric_name VARCHAR(64),
    metric_value DECIMAL(15,4),
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    FOREIGN KEY (audit_id) REFERENCES audits(id),
    INDEX idx_dim_date (dimension, recorded_at)
) ENGINE=InnoDB;
