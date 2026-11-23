import psycopg2
import urllib.request
import json
import redis
import concurrent.futures

DB_URL = "postgresql://mfuser:XJrLkD7Uj3X0IT2c2938awzFJ8CqNbr2@dpg-dc1uapp42hec738fnmd0-a.oregon-postgres.render.com/mediafusion_dcb0"
REDIS_URL = "rediss://red-dc1uarl6e07s73ee2o20:7JHwCk3aYgmkLj5DZI473E9e6LfhRLhe@oregon-keyvalue.render.com:6379"

def check_image(url):
    if not url: return False
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False

def get_best_poster(imdb_id, title):
    # 1. Cinemeta Meta (Most reliable for Stremio / Nuvio - official Metahub CDN)
    if imdb_id and imdb_id.startswith('tt'):
        try:
            url = f"https://v3-cinemeta.strem.io/meta/movie/{imdb_id}.json"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                p = data.get('meta', {}).get('poster')
                if p and check_image(p):
                    return p
        except Exception:
            pass

    # 2. TMDB via Cinemeta Search
    try:
        query = urllib.parse.quote(title)
        url = f"https://v3-cinemeta.strem.io/catalog/movie/top/search={query}.json"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            for m in data.get('metas', [])[:3]:
                p = m.get('poster')
                if p and check_image(p):
                    return p
    except Exception:
        pass

    return None

def process_item(item):
    m_id, title, imdb_id, current_url = item
    if current_url and check_image(current_url):
        return (m_id, title, None, "ALREADY_VALID")
    
    # Needs replacement
    best = get_best_poster(imdb_id, title)
    return (m_id, title, best, "UPDATED" if best else "FAILED")

def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    cur.execute("""
        SELECT m.id, m.title, mei.external_id, mi.url
        FROM media m
        JOIN media_catalog_link mcl ON mcl.media_id = m.id
        JOIN catalog c ON c.id = mcl.catalog_id AND c.name = 'tamil_hdrip'
        LEFT JOIN media_external_id mei ON mei.media_id = m.id AND mei.provider = 'imdb'
        LEFT JOIN LATERAL (
            SELECT url FROM media_image
            WHERE media_id = m.id AND image_type = 'poster'
            ORDER BY is_primary DESC, id DESC
            LIMIT 1
        ) mi ON true
        ORDER BY m.id DESC
    """)
    rows = cur.fetchall()
    print(f"Auditing {len(rows)} movies in parallel with 15 workers...")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(process_item, r) for r in rows]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    updated = 0
    for m_id, title, new_url, status in results:
        if status == "UPDATED" and new_url:
            print(f"✓ Fixed [{title}] -> {new_url}")
            cur.execute("DELETE FROM media_image WHERE media_id = %s AND image_type = 'poster'", (m_id,))
            cur.execute("""
                INSERT INTO media_image (media_id, provider_id, image_type, url, is_primary)
                VALUES (%s, 1, 'poster', %s, true)
            """, (m_id, new_url))
            updated += 1
        elif status == "ALREADY_VALID":
            pass
        else:
            print(f"✗ Could not find reliable poster for [{title}]")

    conn.commit()
    conn.close()
    print(f"Done! Updated {updated} posters in database.")

    # Flush Redis
    r = redis.from_url(REDIS_URL)
    r.flushall()
    print("Flushed Redis cache!")

if __name__ == '__main__':
    import urllib.parse
    main()
