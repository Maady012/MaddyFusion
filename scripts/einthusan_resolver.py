#!/usr/bin/env python3
"""
Einthusan Stream Resolver (Zero-cost, Free Proxy / CF Edge integration).
Decodes the reversed Base64 stream token and formats for MaddyFusion/Nuvio playback.
"""

import sys
import re
import base64
import html
import json
import urllib.request
import urllib.parse
import ssl

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def decode_einthusan_token(token_str):
    """
    Decodes the Einthusan video token:
    1. Unescape HTML
    2. Reverse string
    3. Pad Base64
    4. Decode UTF-8 and clean slashes
    """
    try:
        clean_token = html.unescape(token_str).strip()
        reversed_token = clean_token[::-1]
        padded = reversed_token + "=" * (-len(reversed_token) % 4)
        decoded = base64.b64decode(padded).decode("utf-8")
        decoded = decoded.replace("\\/", "/")
        if decoded.startswith("//"):
            decoded = "https:" + decoded
        if decoded.lstrip().startswith("{"):
            data = json.loads(decoded)
            return data.get("url") or data.get("mp4") or data.get("hls")
        return decoded
    except Exception as e:
        return None

def test_resolver():
    # Known test case sample from yt-dlp / einthusan test suites
    sample_url = "https://einthusan.tv/movie/watch/9097/"
    print(f"[*] Testing Einthusan Token Decryption Logic...")
    # Verify mock reversed token decoding
    test_stream = "https://cdn.einthusan.tv/videos/test_movie.mp4"
    test_b64 = base64.b64encode(test_stream.encode("utf-8")).decode("utf-8")
    test_reversed = test_b64[::-1]
    
    resolved = decode_einthusan_token(test_reversed)
    if resolved == test_stream:
        print("[+] Decrypt unit test passed: Successfully decoded reversed Base64 token.")
        print(f"    Expected: {test_stream}")
        print(f"    Decoded:  {resolved}")
        return True
    else:
        print("[-] Unit test failed.")
        return False

if __name__ == "__main__":
    test_resolver()
