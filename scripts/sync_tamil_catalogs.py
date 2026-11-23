import os
import json
import urllib.request
import psycopg2
from datetime import datetime, timezone

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://mfuser:XJrLkD7Uj3X0IT2c2938awzFJ8CqNbr2@dpg-dc1uapp42hec738fnmd0-a.oregon-postgres.render.com:5432/mediafusion_dcb0"
)

# Public metadata feeds to sync
CATALOGS = {
    "tamil_hdrip": "https://mediafusion.elfhosted.com/catalog/movie/tamil_hdrip.json",
    "tamil_tcrip": "https://mediafusion.elfhosted.com/catalog/movie/tamil_tcrip.json",
    "tamil_dubbed": "https://mediafusion.elfhosted.com/catalog/movie/tamil_dubbed.json",
    "tamil_old": "https://mediafusion.elfhosted.com/catalog/movie/tamil_old.json",
}

def resolve_poster(imdb_id: str, upstream_poster: str | None) -> str:
    """
    Multi-tier resilient poster resolver:
    1. Official Stremio Cinemeta CDN (fast, consistent aspect ratio, highly available).
    2. Upstream feed poster (Amazon/IMDb CDN, TMDB, Metahub).
    3. Direct Metahub CDN by IMDb ID.
    """
    # Tier 1: Cinemeta
    try:
        url = f"https://v3-cinemeta.strem.io/meta/movie/{imdb_id}.json"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            p = data.get("meta", {}).get("poster")
            if p and "placeholder" not in p and p.startswith("http"):
                return p
    except Exception:
        pass

    # Tier 2: Upstream poster
    if upstream_poster and "placeholder" not in upstream_poster and upstream_poster.startswith("http"):
        return upstream_poster

    # Tier 3: Direct Metahub fallback
    return f"https://images.metahub.space/poster/medium/{imdb_id}/img"

def sync():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute("SELECT name, id FROM catalog;")
    cat_map = {name: cid for name, cid in cur.fetchall()}
    print(f"Loaded Catalogs: {cat_map}")

    imdb_provider_id = 1
    total_synced = 0
    now = datetime.now(timezone.utc)

    for cat_name, feed_url in CATALOGS.items():
        cat_id = cat_map.get(cat_name)
        if not cat_id:
            print(f"Skipping unknown catalog {cat_name}")
            continue

        print(f"Fetching {cat_name} from feed...")
        req = urllib.request.Request(feed_url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
        except Exception as e:
            print(f"Failed to fetch {feed_url}: {e}")
            continue

        metas = data.get("metas", [])
        print(f"Processing {len(metas)} items for {cat_name}...")

        for item in metas:
            imdb_id = item.get("id")
            if not imdb_id or not imdb_id.startswith("tt"):
                continue

            title = item.get("name") or "Untitled"
            desc = item.get("description") or ""
            release_info = item.get("releaseInfo")
            year = None
            if release_info and release_info.isdigit():
                year = int(release_info)

            # Resolve resilient poster
            poster_url = resolve_poster(imdb_id, item.get("poster"))

            cur.execute(
                "SELECT media_id FROM media_external_id WHERE provider = 'imdb' AND external_id = %s;",
                (imdb_id,)
            )
            row = cur.fetchone()
            if row:
                media_id = row[0]
                # Update poster if missing
                cur.execute(
                    """
                    INSERT INTO media_image (media_id, provider_id, image_type, url, is_primary, display_order)
                    VALUES (%s, %s, 'poster', %s, true, 0)
                    ON CONFLICT DO NOTHING;
                    """,
                    (media_id, imdb_provider_id, poster_url)
                )
            else:
                cur.execute(
                    """
                    INSERT INTO media (
                        created_at, updated_at, type, title, year, description,
                        adult, is_user_created, is_public, nudity_status, is_blocked,
                        total_streams, last_stream_added, is_keyword_blocked,
                        is_add_title_to_poster, poster_nsfw_flagged, poster_nsfw_reviewed,
                        keyword_block_override
                    ) VALUES (
                        %s, %s, 'MOVIE', %s, %s, %s,
                        false, false, true, 'NONE', false,
                        1, %s, false,
                        false, false, false,
                        false
                    ) RETURNING id;
                    """,
                    (now, now, title, year, desc, now)
                )
                media_id = cur.fetchone()[0]

                cur.execute(
                    """
                    INSERT INTO media_external_id (created_at, media_id, provider, external_id)
                    VALUES (%s, %s, 'imdb', %s)
                    ON CONFLICT (provider, external_id) DO NOTHING;
                    """,
                    (now, media_id, imdb_id)
                )

                cur.execute(
                    """
                    INSERT INTO media_image (media_id, provider_id, image_type, url, is_primary, display_order)
                    VALUES (%s, %s, 'poster', %s, true, 0)
                    ON CONFLICT DO NOTHING;
                    """,
                    (media_id, imdb_provider_id, poster_url)
                )

            cur.execute(
                """
                INSERT INTO media_catalog_link (media_id, catalog_id)
                VALUES (%s, %s)
                ON CONFLICT (media_id, catalog_id) DO NOTHING;
                """,
                (media_id, cat_id)
            )
            total_synced += 1

        conn.commit()

    cur.close()
    conn.close()
    print(f"Sync complete. Successfully refreshed {total_synced} catalog items.")

if __name__ == "__main__":
    sync()
