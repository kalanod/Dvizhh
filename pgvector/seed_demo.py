"""Заполнить event_embeddings демо-событиями и проверить поиск."""
import hashlib
import os
import uuid

import psycopg
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer

DSN = os.environ["PGVECTOR_DSN"]
MODEL_NAME = "intfloat/multilingual-e5-small"

EVENTS = [
    ("Ищем четвёртого поиграть в теннис", "Сегодня вечером, корты у метро"),
    ("Настольные игры на 6 человек", "Играем в Каркассон и Мафию"),
    ("Концерт джаз-оркестра", "Большой зал филармонии"),
    ("Кто хочет вместе помыть пол", "Генеральная уборка, нужна компания"),
]
ids = [uuid.uuid5(uuid.NAMESPACE_DNS, title) for title, _ in EVENTS]
titles = dict(zip(ids, (t for t, _ in EVENTS)))

model = SentenceTransformer(MODEL_NAME)
texts = [f"passage: {t}. {d}" for t, d in EVENTS]
vectors = model.encode(texts, normalize_embeddings=True)

with psycopg.connect(DSN) as conn:
    register_vector(conn)
    for event_id, text, vec in zip(ids, texts, vectors):
        conn.execute(
            """
            INSERT INTO event_embeddings
                (event_id, embedding, model_name, content_hash,
                 is_candidate, last_ends_at, source_updated_at)
            VALUES (%s, %s, %s, %s, true, now() + interval '7 days', now())
            ON CONFLICT (event_id) DO UPDATE
                SET embedding = EXCLUDED.embedding, indexed_at = now()
            """,
            (event_id, vec, MODEL_NAME, hashlib.sha256(text.encode()).hexdigest()),
        )

    for query in ["хочу сыграть в падел", "что-нибудь послушать вечером"]:
        q = model.encode([f"query: {query}"], normalize_embeddings=True)[0]
        rows = conn.execute(
            """
            SELECT event_id, 1 - (embedding <=> %s) AS similarity
            FROM event_embeddings
            WHERE is_candidate AND last_ends_at > now()
            ORDER BY embedding <=> %s
            LIMIT 3
            """,
            (q, q),
        ).fetchall()
        print(f"\nЗапрос: {query}")
        for event_id, sim in rows:
            print(f"  {sim:.3f}  {titles[event_id]}")