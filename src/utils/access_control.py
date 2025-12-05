# src\utils\access_control.py
import base64
import csv
import os
from typing import List, Iterable, Union

def _xor_bytes(data: bytes, key: bytes) -> bytes:
    """XOR data with repeating key bytes (reversible)."""
    if not key:
        raise ValueError("Key must be a non-empty bytes object")
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))

def encode(*access_codes: Union[str, Iterable[str]],
           key: str = "default_secret",
           csv_path: str = "src/data/access.csv") -> List[str]:
    """
    Encode one or more access codes and append their encoded strings to csv_path.
    """
    # Accept either varargs or a single iterable/list argument
    codes = []
    if len(access_codes) == 1 and isinstance(access_codes[0], (list, tuple, set)):
        codes = list(access_codes[0])
    else:
        codes = list(access_codes)

    if not codes:
        return []

    key_bytes = key.encode("utf-8")
    encoded_list = []

    # Ensure directory exists
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    # read existing encoded values to avoid duplicates
    existing = set()
    if os.path.exists(csv_path):
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if row:
                    existing.add(row[0].strip())

    # append new encoded codes
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for code in codes:
            if code is None:
                continue
            raw = str(code).encode("utf-8")
            xored = _xor_bytes(raw, key_bytes)
            encoded = base64.urlsafe_b64encode(xored).decode("ascii")
            # avoid duplicates in file
            if encoded not in existing:
                writer.writerow([encoded])
                existing.add(encoded)
            encoded_list.append(encoded)

    return encoded_list

def check_access(access_code: str, key: str = "default_secret", csv_path: str = "src/data/access.csv") -> bool:
    """
    Log / verify access code:
    - encode access_code using the same method/key
    - check whether encoded string is present in csv_path
    """
    if not access_code:
        return False

    key_bytes = key.encode("utf-8")
    raw = str(access_code).encode("utf-8")
    xored = _xor_bytes(raw, key_bytes)
    encoded = base64.urlsafe_b64encode(xored).decode("ascii")

    # read csv and check membership
    if os.path.exists(csv_path):
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if row and row[0].strip() == encoded:
                    return True
    return False