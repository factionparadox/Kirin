#!/usr/bin/env python3
"""Check that an OpenPGP key file's primary key has an expected fingerprint.

Reads an ASCII-armoured or binary key file, finds every primary public key
packet (tag 6) and computes its v4 (SHA-1) or v6 (SHA-256) fingerprint. Exits 0
only if the file contains exactly the expected primary keys. Needs no GnuPG.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
from pathlib import Path
import re
import sys


def dearmor(data: bytes) -> bytes:
    text = data.decode('ascii', 'strict')
    blocks = re.findall(r'-----BEGIN PGP PUBLIC KEY BLOCK-----\r?\n(.*?)-----END PGP PUBLIC KEY BLOCK-----',
                        text, re.S)
    if not blocks:
        raise ValueError('no armoured public key block')
    out = b''
    for block in blocks:
        _, _, body = block.partition('\n\n') if '\n\n' in block else ('', '', block)
        lines = [l.strip() for l in body.replace('\r', '').splitlines() if l.strip()]
        lines = [l for l in lines if not l.startswith('=')]          # drop CRC-24 checksum line
        out += base64.b64decode(''.join(lines), validate=True)
    return out


def packets(data: bytes):
    i = 0
    while i < len(data):
        tag_byte = data[i]
        if not tag_byte & 0x80:
            raise ValueError(f'invalid packet header at byte {i}')
        if tag_byte & 0x40:                                           # new format
            tag = tag_byte & 0x3F
            first = data[i + 1]
            if first < 192:
                length, hdr = first, 2
            elif first < 224:
                length, hdr = ((first - 192) << 8) + data[i + 2] + 192, 3
            elif first == 255:
                length, hdr = int.from_bytes(data[i + 2:i + 6], 'big'), 6
            else:
                raise ValueError('partial body lengths are not valid in key packets')
        else:                                                         # old format
            tag = (tag_byte >> 2) & 0x0F
            ltype = tag_byte & 0x03
            size = {0: 1, 1: 2, 2: 4}.get(ltype)
            if size is None:
                raise ValueError('indeterminate packet length')
            length, hdr = int.from_bytes(data[i + 1:i + 1 + size], 'big'), 1 + size
        body = data[i + hdr:i + hdr + length]
        if len(body) != length:
            raise ValueError('truncated packet')
        yield tag, body
        i += hdr + length


def fingerprint(body: bytes) -> str:
    version = body[0]
    if version == 4:
        return hashlib.sha1(b'\x99' + len(body).to_bytes(2, 'big') + body).hexdigest().upper()
    if version == 6:
        return hashlib.sha256(b'\x9b' + len(body).to_bytes(4, 'big') + body).hexdigest().upper()
    raise ValueError(f'unsupported key version {version}')


def binary(data: bytes) -> bytes:
    return dearmor(data) if data.lstrip().startswith(b'-----BEGIN') else data


def primary_fingerprints(data: bytes) -> list[str]:
    return [fingerprint(body) for tag, body in packets(binary(data)) if tag == 6]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('key', type=Path)
    ap.add_argument('--expect', action='append', required=True, help='fingerprint (spaces allowed); repeatable')
    ap.add_argument('--binary-out', type=Path, help='after verifying, write the key as a binary keyring here')
    args = ap.parse_args(argv)
    try:
        found = primary_fingerprints(args.key.read_bytes())
    except (OSError, ValueError, UnicodeError, IndexError) as exc:
        print(f'KEY REJECTED: {args.key}: {exc}', file=sys.stderr)
        return 2
    expected = sorted(e.replace(' ', '').upper() for e in args.expect)
    if sorted(found) != expected:
        print(f'KEY REJECTED: {args.key}: has {found or "no keys"}, expected {expected}', file=sys.stderr)
        return 1
    if args.binary_out:
        args.binary_out.write_bytes(binary(args.key.read_bytes()))
    print(f'{args.key.name}: fingerprint verified')
    return 0


if __name__ == '__main__':
    sys.exit(main())
