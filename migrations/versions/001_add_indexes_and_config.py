"""Add missing indexes and btc_config table."""

description = "Add indexes on date columns and create btc_config table"


def upgrade(conn):
    # Indexes on frequently joined date columns
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_btc_market_features_date
        ON btc_market_features(date)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_btc_astro_history_date
        ON btc_astro_history(date)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_btc_astro_history_split
        ON btc_astro_history(sample_split)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_btc_astro_calendar_date
        ON btc_astro_calendar(date)
    """)

    # Config table for thresholds
    conn.execute("""
        CREATE TABLE IF NOT EXISTS btc_config (
            category VARCHAR NOT NULL,
            key VARCHAR NOT NULL,
            value DOUBLE NOT NULL,
            description VARCHAR DEFAULT '',
            updated_at VARCHAR NOT NULL,
            PRIMARY KEY (category, key)
        )
    """)


def downgrade(conn):
    conn.execute("DROP INDEX IF EXISTS idx_btc_market_features_date")
    conn.execute("DROP INDEX IF EXISTS idx_btc_astro_history_date")
    conn.execute("DROP INDEX IF EXISTS idx_btc_astro_history_split")
    conn.execute("DROP INDEX IF EXISTS idx_btc_astro_calendar_date")
    conn.execute("DROP TABLE IF EXISTS btc_config")
