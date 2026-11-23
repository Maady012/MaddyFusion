import psycopg2
import urllib.request
import json
import redis
import concurrent.futures
import time

DB_URL = "postgresql://mfuser:XJrLkD7Uj3X0IT2c2938awzFJ8CqNbr2@dpg-dc1uapp42hec738fnmd0-a.oregon-postgres.render.com/mediafusion_dcb0"
REDIS_URL = "rediss://red-dc1uarl6e07s73ee2o20:7JHwCk3aYgmkLj5DZI473E9e6LfhRLhe@oregon-keyvalue.render.com:6379"

def check_url(url):
    if not url:
        return False
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=4) as resp:
            return resp.status == 200
    except Exception:
        return False

def resolve_fallback_poster(title, year, imdb_id):
    # Try 1: Cinemeta direct
    if imdb_id and imdb_id.startswith('tt'):
        candidate = f"https://images.metahub.space/poster/small/{imdb_id}/img"
        if check_url(candidate):
            return candidate

    # Try 2: Cinemeta title search
    query = urllib.parse.quote(title)
    search_url = f"https://v3-cinemeta.strem.io/catalog/movie/top/search={query}.json"
    try:
        req = urllib.request.Request(search_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            for m in data.get('metas', []):
                p = m.get('poster')
                if p and check_url(p):
                    return p
    except Exception:
        pass

    return None

def run():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    cur.execute("""
        SELECT m.id, m.title, m.year, mei.external_id, mi.id, mi.url
        FROM media m
        JOIN media_catalog_link mcl ON mcl.media_id = m.id
        JOIN catalog c ON c.id = mcl.catalog_id AND c.name = 'tamil_hdrip'
        LEFT JOIN media_external_id mei ON mei.media_id = m.id AND mei.provider = 'imdb'
        LEFT JOIN LATERAL (
            SELECT id, url FROM media_image
            WHERE media_id = m.id AND image_type = 'poster'
            ORDER BY is_primary DESC, id DESC
            LIMIT 1
        ) mi ON true
        ORDER BY m.id DESC
    """)
    movies = cur.fetchall()
    print(f"Total Tamil HD movies to audit: {len(movies)}")

    fixed_count = 0
    for m_id, title, year, imdb_id, img_id, current_url in movies:
        is_valid = check_url(current_url) if current_url else False
        if not is_valid:
            print(f"[DEAD/MISSING] {title} ({year}) | current: {current_url}")
            new_poster = resolve_fallback_poster(title, year, imdb_id)
            if new_poster:
                print(f"  -> FIXED with: {new_poster}")
                # Delete dead images for this movie
                cur.execute("DELETE FROM media_image WHERE media_id = %s AND image_type = 'poster'", (m_id,))
                cur.execute("""
                    INSERT INTO media_image (media_id, provider_id, image_type, url, is_primary)
                    VALUES (%s, 1, 'poster', %s, true)
                """, (m_id, new_poster))
                conn.commit()
                fixed_count += 1
            else:
                print(f"  -> Could not resolve poster for {title}")
        else:
            # Current poster is 200 OK
            pass

    print(f"Audit complete! Fixed {fixed_count} broken/missing posters.")
    conn.close()

    # Flush Redis
    r = redis.from_url(REDIS_URL)
    r.flushall()
    print("Redis cache flushed completely!")

if __name__ == '__main__':
    import urllib.parse
    run()
