"""Одноразовая миграция: колонки users/fragments под новые модели + бэкфилл контента."""
import asyncio

import asyncpg

DSN = "postgresql://bashkar:bashkar@127.0.0.1:5432/bashkar"


async def main() -> None:
    conn = await asyncpg.connect(DSN)
    try:
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(200)")
        await conn.execute("ALTER TABLE fragments ADD COLUMN IF NOT EXISTS source_id INTEGER")
        await conn.execute("ALTER TABLE fragments ADD COLUMN IF NOT EXISTS lang_pair VARCHAR(16)")
        await conn.execute("ALTER TABLE fragments ADD COLUMN IF NOT EXISTS auto_translation TEXT")
        await conn.execute("ALTER TABLE fragments ADD COLUMN IF NOT EXISTS order_index INTEGER DEFAULT 0")

        # Бэкфилл: все импортированные фрагменты — башкирско-русские
        await conn.execute("UPDATE fragments SET lang_pair = 'ba-ru' WHERE lang_pair IS NULL")
        await conn.execute(
            """
            UPDATE fragments f SET auto_translation = sub.translation
            FROM (
                SELECT DISTINCT ON (t.fragment_id) t.fragment_id, t.translation
                FROM translations t
                JOIN lang_pairs lp ON lp.id = t.lang_pair_id
                WHERE lp.code = 'ba-ru'
                ORDER BY t.fragment_id, t.id
            ) sub
            WHERE sub.fragment_id = f.id AND f.auto_translation IS NULL
            """
        )
        updated = await conn.fetchval("SELECT count(*) FROM fragments WHERE lang_pair = 'ba-ru'")
        print(f"Фрагментов с ba-ru: {updated}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
    print("MIGRATION_DONE")
