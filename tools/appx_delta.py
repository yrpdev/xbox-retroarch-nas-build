#!/usr/bin/env python3
"""Transport a signed Appx byte-for-byte against a pinned baseline; never repack it."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import zipfile

import bsdiff4

LIMIT = 450_000_000
CHUNK = 1024 * 1024


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def spans(path):
    """Return raw ZIP records, including headers, data descriptors and final directory."""
    with zipfile.ZipFile(path) as z:
        items = sorted(z.infolist(), key=lambda x: x.header_offset)
        names = [x.filename for x in items]
        if len(names) != len(set(names)):
            raise ValueError('Duplicate ZIP member names')
        rows = []
        first = items[0].header_offset if items else z.start_dir
        if first:
            rows.append(('@prefix', 0, first))
        for i, item in enumerate(items):
            end = items[i + 1].header_offset if i + 1 < len(items) else z.start_dir
            rows.append(('member:' + item.filename, item.header_offset, end - item.header_offset))
        rows.append(('@directory', z.start_dir, Path(path).stat().st_size - z.start_dir))
        return rows


def read_at(f, offset, length):
    f.seek(offset)
    data = f.read(length)
    if len(data) != length:
        raise ValueError('Truncated input')
    return data


def create(base, target, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    payload_path = directory / 'package-delta.bin'
    manifest_path = directory / 'package-delta.json'
    old_spans = {name: (offset, size) for name, offset, size in spans(base)}
    manifest = dict(format='appx-raw-zip-records-bsdiff4-v1',
                    base_sha256=sha256(base), base_bytes=Path(base).stat().st_size,
                    target_sha256=sha256(target), target_bytes=Path(target).stat().st_size,
                    bsdiff4_version='1.3.2', records=[])
    with open(base, 'rb') as source, open(target, 'rb') as result, payload_path.open('xb') as payload:
        for name, new_offset, new_size in spans(target):
            new = read_at(result, new_offset, new_size)
            old_offset, old_size = old_spans.get(name, (0, 0))
            old = read_at(source, old_offset, old_size)
            row = dict(name=name, target_bytes=new_size)
            if old == new:
                row.update(kind='copy', base_offset=old_offset, base_bytes=old_size)
            else:
                patch = bsdiff4.diff(old, new) if old else b''
                use_patch = bool(patch) and len(patch) < len(new)
                data = patch if use_patch else new
                row.update(kind='bsdiff' if use_patch else 'literal',
                           payload_offset=payload.tell(), payload_bytes=len(data))
                if row['kind'] == 'bsdiff':
                    row.update(base_offset=old_offset, base_bytes=old_size)
                payload.write(data)
                if payload.tell() >= LIMIT:
                    raise ValueError('Delta exceeds the 450 MB artifact cap; nothing may be uploaded')
            manifest['records'].append(row)
    manifest['payload_sha256'] = sha256(payload_path)
    manifest['payload_bytes'] = payload_path.stat().st_size
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in manifest.items() if k != 'records'}))


def apply(base, directory, output):
    directory, output = Path(directory), Path(output)
    manifest = json.loads((directory / 'package-delta.json').read_text(encoding='utf-8'))
    if manifest['format'] != 'appx-raw-zip-records-bsdiff4-v1':
        raise ValueError('Unsupported delta format')
    payload_path = directory / 'package-delta.bin'
    if sha256(base) != manifest['base_sha256'] or Path(base).stat().st_size != manifest['base_bytes']:
        raise ValueError('Baseline Appx SHA256 or size mismatch')
    if sha256(payload_path) != manifest['payload_sha256'] or payload_path.stat().st_size != manifest['payload_bytes']:
        raise ValueError('Delta payload SHA256 or size mismatch')
    if output.exists():
        raise FileExistsError('Output already exists; no file was changed')
    partial = output.with_name(output.name + '.partial')
    with open(base, 'rb') as source, payload_path.open('rb') as payload, partial.open('xb') as result:
        try:
            for row in manifest['records']:
                if row['kind'] == 'copy':
                    data = read_at(source, row['base_offset'], row['base_bytes'])
                elif row['kind'] == 'literal':
                    data = read_at(payload, row['payload_offset'], row['payload_bytes'])
                elif row['kind'] == 'bsdiff':
                    old = read_at(source, row['base_offset'], row['base_bytes'])
                    patch = read_at(payload, row['payload_offset'], row['payload_bytes'])
                    data = bsdiff4.patch(old, patch)
                else:
                    raise ValueError('Unknown delta record')
                if len(data) != row['target_bytes']:
                    raise ValueError('Reconstructed ZIP record size mismatch')
                result.write(data)
            result.flush()
            os.fsync(result.fileno())
            if result.tell() != manifest['target_bytes'] or sha256(partial) != manifest['target_sha256']:
                raise ValueError('Reconstructed Appx SHA256 or size mismatch')
        except Exception:
            result.close()
            partial.unlink(missing_ok=True)
            raise
    # The full signed container, including its signature, is now byte-identical to CI's output.
    partial.rename(output)
    print(json.dumps(dict(output=str(output), bytes=output.stat().st_size, sha256=sha256(output))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('create')
    p.add_argument('base'); p.add_argument('target'); p.add_argument('directory')
    p = sub.add_parser('apply')
    p.add_argument('base'); p.add_argument('directory'); p.add_argument('output')
    args = parser.parse_args()
    if args.command == 'create':
        create(args.base, args.target, args.directory)
    else:
        apply(args.base, args.directory, args.output)


if __name__ == '__main__':
    main()
