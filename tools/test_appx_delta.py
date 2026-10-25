"""Round-trip container changes and reject corrupted or mismatched inputs."""
import contextlib
import io
import json
from pathlib import Path
import random
import tempfile
import unittest
import zipfile

import appx_delta


def container(path, members, year=2026, comment=b''):
    with zipfile.ZipFile(path, 'w') as z:
        z.comment = comment
        for name, data, method in members:
            info = zipfile.ZipInfo(name, (year, 1, 2, 3, 4, 6))
            info.compress_type = method
            z.writestr(info, data)


class ExactContainerDelta(unittest.TestCase):
    def test_round_trip_and_rejections(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            base, target, output = p / 'base.appx', p / 'target.appx', p / 'result.appx'
            random_data = random.Random(42).randbytes(512_000)
            original = [('unchanged.dll', random_data, zipfile.ZIP_DEFLATED),
                        ('changed.dll', b'A' * 100_000, zipfile.ZIP_STORED),
                        ('deleted', b'remove me', zipfile.ZIP_DEFLATED)]
            changed = [('changed.dll', b'A' * 50_000 + b'B' + b'A' * 49_999, zipfile.ZIP_STORED),
                       ('unchanged.dll', random_data, zipfile.ZIP_DEFLATED),
                       ('new', b'new file', zipfile.ZIP_DEFLATED),
                       ('empty', b'', zipfile.ZIP_STORED)]
            container(base, original)
            container(target, changed, comment=b'Changed directory and member order')
            with contextlib.redirect_stdout(io.StringIO()):
                appx_delta.create(base, target, p / 'delta')
                appx_delta.apply(base, p / 'delta', output)
            self.assertEqual(target.read_bytes(), output.read_bytes())
            m = json.loads((p / 'delta/package-delta.json').read_text())
            self.assertIn('copy', {r['kind'] for r in m['records']})
            self.assertIn('bsdiff', {r['kind'] for r in m['records']})
            self.assertIn('literal', {r['kind'] for r in m['records']})
            self.assertLess(m['payload_bytes'], 50_000)
            with self.assertRaises(FileExistsError):
                appx_delta.apply(base, p / 'delta', output)
            with self.assertRaisesRegex(ValueError, 'Baseline'):
                appx_delta.apply(target, p / 'delta', p / 'wrong-base.appx')
            payload = p / 'delta/package-delta.bin'
            payload.write_bytes(payload.read_bytes() + b'tamper')
            with self.assertRaisesRegex(ValueError, 'Delta payload'):
                appx_delta.apply(base, p / 'delta', p / 'tampered.appx')
            self.assertFalse((p / 'tampered.appx.partial').exists())

    def test_changed_headers_and_empty_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            for number, members in enumerate([[], [('x', b'x' * 10_000, zipfile.ZIP_DEFLATED)]]):
                base, target = p / f'base{number}', p / f'target{number}'
                container(base, members, year=2025)
                container(target, members, year=2026, comment=b'directory changed')
                with contextlib.redirect_stdout(io.StringIO()):
                    appx_delta.create(base, target, p / f'delta{number}')
                    appx_delta.apply(base, p / f'delta{number}', p / f'result{number}')
                self.assertEqual(target.read_bytes(), (p / f'result{number}').read_bytes())


if __name__ == '__main__':
    unittest.main()
