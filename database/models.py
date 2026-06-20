SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS Topics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL UNIQUE,
    keywords        TEXT    NOT NULL,
    sources         TEXT    NOT NULL,
    interval_minutes INTEGER NOT NULL DEFAULT 60,
    enabled         INTEGER NOT NULL DEFAULT 1,
    last_fetched_at TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS Articles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id        INTEGER NOT NULL,
    title           TEXT    NOT NULL,
    url             TEXT    NOT NULL,
    source          TEXT    NOT NULL,
    author          TEXT,
    summary         TEXT,
    content         TEXT,
    published_at    TEXT,
    fetched_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    simhash         TEXT,
    relevance_score REAL    NOT NULL DEFAULT 0.0,
    status          TEXT    NOT NULL DEFAULT 'unread',
    FOREIGN KEY (topic_id) REFERENCES Topics(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS UserActions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id      INTEGER NOT NULL,
    action          TEXT    NOT NULL,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (article_id) REFERENCES Articles(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_articles_topic      ON Articles(topic_id);
CREATE INDEX IF NOT EXISTS idx_articles_simhash    ON Articles(simhash);
CREATE INDEX IF NOT EXISTS idx_articles_status     ON Articles(status);
CREATE INDEX IF NOT EXISTS idx_articles_fetched    ON Articles(fetched_at);
CREATE INDEX IF NOT EXISTS idx_actions_article     ON UserActions(article_id);
"""

VALID_STATUSES = ("unread", "read", "starred", "later")
VALID_ACTIONS = ("read", "starred", "unstarred", "later", "deleted")
