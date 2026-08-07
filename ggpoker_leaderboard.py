#!/usr/bin/env python3
"""
GGPoker Spin & Gold $50 leaderboard collector.

Every execution:
  1. Requests the public leaderboard endpoint.
  2. Reads the `milliseconds` response header.
  3. Recreates the CryptoJS passphrase: Number(milliseconds).toString(16)
  4. Decrypts the `data` field using CryptoJS/OpenSSL-compatible AES.
  5. Appends every ranked player to leaderboard_snapshots.csv.
  6. Saves the raw encrypted response for auditing.

Run once manually to test:
    python ggpoker_leaderboard.py

Then schedule it once per hour with cron / Task Scheduler.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

ENDPOINT = (
    "https://pml.good-game-service.com/lapi/leaderboard/223063/"
    "?limit=30&hasSummary=true&hasSummaryPaidPrizes=false"
    "&hasSummaryPrizeItem=false"
)

BASE_DIR = Path(__file__).resolve().parent
CSV_FILE = BASE_DIR / "leaderboard_snapshots.csv"
RAW_DIR = BASE_DIR / "raw_responses"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://ggpoker.com/",
}


def evp_bytes_to_key(password: bytes, salt: bytes, key_len: int, iv_len: int):
    """OpenSSL EVP_BytesToKey using MD5, matching CryptoJS's default KDF."""
    result = b""
    previous = b""
    while len(result) < key_len + iv_len:
        previous = hashlib.md5(previous + password + salt).digest()
        result += previous
    return result[:key_len], result[key_len:key_len + iv_len]


def decrypt_cryptojs_data(ciphertext: str, passphrase: str) -> dict:
    """Decrypt a CryptoJS AES ciphertext string using its OpenSSL-compatible format."""
    import base64

    raw = base64.b64decode(ciphertext)
    if raw[:8] != b"Salted__":
        raise ValueError("Unexpected ciphertext format: missing OpenSSL 'Salted__' header.")

    salt = raw[8:16]
    encrypted = raw[16:]

    key, iv = evp_bytes_to_key(
        passphrase.encode("utf-8"),
        salt,
        key_len=32,   # AES-256
        iv_len=16,
    )

    plaintext = unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(encrypted), AES.block_size)
    return json.loads(plaintext.decode("utf-8"))


def extract_rows(payload):
    """
    Try common leaderboard response shapes without assuming a single schema.
    The exact payload is preserved in raw JSON if GGPoker changes its structure.
    """
    candidates = []

    if isinstance(payload, list):
        candidates.append(payload)

    if isinstance(payload, dict):
        for key in ("leaderboard", "rankings", "players", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                candidates.append(value)

        # Some APIs wrap the ranking under a nested object.
        for value in payload.values():
            if isinstance(value, dict):
                for key in ("leaderboard", "rankings", "players", "items", "results"):
                    nested = value.get(key)
                    if isinstance(nested, list):
                        candidates.append(nested)

    for rows in candidates:
        normalized = []
        for i, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue

            rank = (
                row.get("rank")
                or row.get("position")
                or row.get("place")
                or row.get("ranking")
                or i
            )
            player = (
                row.get("nickname")
                or row.get("username")
                or row.get("player")
                or row.get("name")
                or row.get("nickName")
                or ""
            )
            points = (
                row.get("points")
                or row.get("score")
                or row.get("totalPoints")
                or row.get("total_points")
                or 0
            )

            normalized.append({
                "rank": rank,
                "player": player,
                "points": points,
            })

        if normalized:
            return normalized

    raise ValueError(
        "No leaderboard list was recognized. "
        "Check raw_responses/ for the decrypted payload and update extract_rows()."
    )


def main():
    RAW_DIR.mkdir(exist_ok=True)

    captured_at = datetime.now(timezone.utc)
    timestamp = captured_at.isoformat(timespec="seconds")

    response = requests.get(
        ENDPOINT,
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()

    try:
        encrypted = response.json()
    except Exception as exc:
        raise RuntimeError("Endpoint did not return valid JSON.") from exc

    data = encrypted.get("data")
    milliseconds = response.headers.get("milliseconds")

    if not data:
        raise RuntimeError("Response does not contain a `data` field.")

    if not milliseconds:
        raise RuntimeError(
            "Response does not contain the `milliseconds` header; "
            "the CryptoJS passphrase cannot be reconstructed."
        )

    # JavaScript equivalent:
    # Number(f.headers.get("milliseconds")).toString(16)
    passphrase = format(int(float(milliseconds)), "x")

    payload = decrypt_cryptojs_data(data, passphrase)
    rows = extract_rows(payload)

    raw_file = RAW_DIR / f"{captured_at.strftime('%Y%m%d_%H%M%S')}.json"
    raw_file.write_text(
        json.dumps(
            {
                "captured_at_utc": timestamp,
                "milliseconds_header": milliseconds,
                "passphrase_hex": passphrase,
                "endpoint": ENDPOINT,
                "payload": payload,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    new_file = not CSV_FILE.exists()
    with CSV_FILE.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "captured_at_utc",
                "date_utc",
                "time_utc",
                "rank",
                "player",
                "points",
            ],
        )
        if new_file:
            writer.writeheader()

        for row in rows:
            writer.writerow({
                "captured_at_utc": timestamp,
                "date_utc": captured_at.strftime("%Y-%m-%d"),
                "time_utc": captured_at.strftime("%H:%M:%S"),
                "rank": row["rank"],
                "player": row["player"],
                "points": row["points"],
            })

    print(f"OK: {len(rows)} leaderboard rows captured at {timestamp}")
    print(f"CSV: {CSV_FILE}")
    print(f"Raw: {raw_file}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
