"""Демо: записать события в pgvector и найти ближайшие к запросу.

Установка:
    pip install "psycopg[binary]" pgvector sentence-transformers

Запуск (порт 5433 нужно временно открыть в compose.yaml):
    PGVECTOR_DSN="postgresql://USER:PASSWORD@localhost:5433/DB" python demo_query.py
"""
import os

import psycopg
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer

DSN = os.environ["PGVECTOR_DSN"]
MODEL_NAME = "intfloat/multilingual-e5-small"  # даёт векторы размерности 384

EVENTS = [
    ("Ищем четвёртого поиграть в теннис", "Сегодня вечером, корты у метро"),
    ("Настольные игры на 6 человек", "Играем в Каркассон и Мафию"),
    ("Концерт джаз-оркестра", "Большой зал филармонии"),
    ("Кто хочет вместе помыть пол", "Генеральная уборка, нужна компания"),
]

model = SentenceTransformer(MODEL_NAME)


def embed(texts, kind):
    # kind: "passage" для событий, "query" для поискового запроса (требование E5)
    return model.encode([f"{kind}: {t}" for t in texts], normalize_embeddings=True)


with psycopg.connect(DSN) as conn:
    register_vector(conn)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS demo_events "
        "(id serial PRIMARY KEY, title text, embedding vector(384))"
    )
    conn.execute("TRUNCATE demo_events")

    vectors = embed([f"{title}. {desc}" for title, desc in EVENTS], "passage")
    for (title, _), vec in zip(EVENTS, vectors):
        conn.execute(
            "INSERT INTO demo_events (title, embedding) VALUES (%s, %s)", (title, vec)
        )

    query_vec = embed(["хочу сыграть в теннис"], "query")[0]
    rows = conn.execute(
        """
        SELECT title, 1 - (embedding <=> %s) AS similarity
        FROM demo_events
        ORDER BY embedding <=> %s
        LIMIT 3
        """,
        (query_vec, query_vec),
    ).fetchall()

    for title, similarity in rows:
        print(f"{similarity:.3f}  {title}")