#!/usr/bin/env python3
"""
Einthusan -> MaddyFusion & Nuvio Live Pipeline Bridge.
Injects decoded HTTP stream records with automatic header proxying and geoblock bypass
directly into MaddyFusion PostgreSQL database for instant 1-click playback on Nuvio.
"""

import os
import json
import psycopg2
from datetime import datetime, timezone

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://mfuser:XJrLkD7Uj3X0IT2c2938awzFJ8CqNbr2@dpg-dc1uapp42hec738fnmd0-a.oregon-postgres.render.com:5432/mediafusion_dcb0"
)

def register_einthusan_stream(imdb_id: str, title: str, direct_stream_url: str):
    """
    Registers an extracted Einthusan stream into MaddyFusion so Nuvio
    and Stremio immediately see 'Einthusan [Direct 1080p]' in stream options.
    """
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()
    now = datetime.now(timezone.utc)

    # 1. Resolve media_id for the IMDb ID
    cur.execute(
        "SELECT media_id FROM media_external_id WHERE provider = 'imdb' AND external_id = %s;",
        (imdb_id,)
    )
    row = cur.fetchone()
    if not row:
        print(f"[-] IMDb {imdb_id} not in catalog. Creating media entry...")
        cur.execute(
            """
            INSERT INTO media (
                created_at, updated_at, type, title, adult, is_user_created,
                is_public, nudity_status, is_blocked, total_streams, last_stream_added,
                is_keyword_blocked, is_add_title_to_poster, poster_nsfw_flagged,
                poster_nsfw_reviewed, keyword_block_override
            ) VALUES (
                %s, %s, 'MOVIE', %s, false, false,
                true, 'NONE', false, 1, %s,
                false, false, false, false, false
            ) RETURNING id;
            """,
            (now, now, title, now)
        )
        media_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO media_external_id (created_at, media_id, provider, external_id)
            VALUES (%s, %s, 'imdb', %s);
            """,
            (now, media_id, imdb_id)
        )
    else:
        media_id = row[0]

    # 2. Insert into stream base table
    cur.execute(
        """
        INSERT INTO stream (
            created_at, updated_at, stream_type, is_active, is_blocked,
            is_public, is_dubbed, is_subbed, is_remastered, is_upscaled, is_proper,
            is_repack, is_extended, is_complete, playback_count,
            name, source, resolution, quality
        ) VALUES (
            %s, %s, 'HTTP', true, false,
            true, false, false, false, false, false,
            false, false, true, 0,
            %s, 'Einthusan', '1080p', 'HD'
        ) RETURNING id;
        """,
        (now, now, f"Einthusan [Direct 1080p] {title}")
    )
    stream_id = cur.fetchone()[0]

    # 3. Behavior hints with spoofed headers for 1-click Nuvio playback
    behavior_hints = json.dumps({
        "notWebReady": False,
        "proxyHeaders": {
            "request": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://einthusan.tv/",
                "Origin": "https://einthusan.tv"
            }
        }
    })

    # 4. Insert into http_stream
    cur.execute(
        """
        INSERT INTO http_stream (
            stream_id, url, format, extractor_name, behavior_hints
        ) VALUES (
            %s, %s, 'mp4', 'Einthusan', %s
        );
        """,
        (stream_id, direct_stream_url, behavior_hints)
    )

    # 5. Link stream to media
    cur.execute(
        """
        INSERT INTO stream_media_link (
            stream_id, media_id, is_primary, is_verified, created_at, filename
        )
        VALUES (%s, %s, true, true, %s, %s)
        ON CONFLICT DO NOTHING;
        """,
        (stream_id, media_id, now, f"{title}.1080p.Einthusan.mp4")
    )

    # 6. Increment total_streams on media
    cur.execute(
        "UPDATE media SET total_streams = total_streams + 1, last_stream_added = %s WHERE id = %s;",
        (now, media_id)
    )

    conn.commit()
    cur.close()
    conn.close()
    print(f"[+] Successfully bridged Einthusan stream for '{title}' ({imdb_id}) -> stream_id: {stream_id}")
    return stream_id

if __name__ == "__main__":
    # Test bridging a sample entry to verify DB transaction integrity
    test_imdb = "tt15354916" # Leo
    test_stream = "https://cdn.einthusan.tv/videos/sample_leo_stream.mp4"
    print("[*] Testing Einthusan -> MaddyFusion Database stream bridge...")
    sid = register_einthusan_stream(test_imdb, "Leo", test_stream)
    print(f"[+] Magic Complete! Stream active and ready in MaddyFusion for Nuvio.")
