import hashlib
import importlib.util
import io
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import tempfile
import unittest

BUILD = Path(__file__).resolve().parents[1] / 'scripts/build'


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), BUILD / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


inventory = load('inventory-models')
qwen = load('qwen-index')
removal = load('check-removal')
recovery = load('recover-squashfs')


def quiet(fn, *args):
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return fn(*args)


class TempRoot(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'root'
        self.root.mkdir()

    def put(self, rel, size, data=b'\0'):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((data * size)[:size])
        return path


class TestInventory(TempRoot):
    def test_finds_strong_and_keyword_files_only(self):
        self.put('opt/kylin-ai/asr/encoder.onnx', 8192)
        self.put('usr/share/kylinbot/models/weights.bin', 2 << 20)
        self.put('usr/share/doc/random.bin', 2 << 20)               # weak suffix, no AI path
        self.put('usr/lib/firmware/model.onnx', 8192)               # firmware skipped
        self.put('home/user/private.gguf', 8192)                    # home skipped
        self.put('opt/kylin-ai/tiny.onnx', 100)                     # too small
        self.put('usr/share/vim/vim91/tutor/tutor1.pt', 37094)      # language code, not PyTorch
        self.put('usr/share/vim/vim91/tutor/tutor1.nb', 35531)
        self.put('usr/share/kylin-ai-python-env/lib/torch/lib/libtorch_cpu.so', 300 << 20)
        self.put('usr/share/kylin-ai/llm/weights', 300 << 20)       # large, AI path, no suffix
        found = dict(inventory.scan(self.root))
        self.assertEqual(set(found), {'opt/kylin-ai/asr/encoder.onnx', 'usr/share/kylinbot/models/weights.bin',
                                      'usr/share/kylin-ai/llm/weights'})

    def test_does_not_follow_symlinks(self):
        outside = Path(self.temp.name) / 'outside'
        outside.mkdir()
        (outside / 'm.gguf').write_bytes(b'x' * 8192)
        (self.root / 'opt').mkdir()
        (self.root / 'opt/link').symlink_to(outside, target_is_directory=True)
        (self.root / 'opt/file.gguf').symlink_to(outside / 'm.gguf')
        self.assertEqual(inventory.scan(self.root), [])

    def test_writes_contract_inventory_and_owners(self):
        model = self.put('opt/kylin-ai/m.gguf', 8192, b'a')
        info = self.root / 'var/lib/dpkg/info'
        info.mkdir(parents=True)
        (info / 'kylin-ai-runtime:amd64.list').write_text('/opt/kylin-ai/m.gguf\n')
        out, owners_out = Path(self.temp.name) / 'inv.json', Path(self.temp.name) / 'own.json'
        code = quiet(inventory.main, ['--root', str(self.root), '--out', str(out), '--owners-out', str(owners_out)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.read_text()), {'opt/kylin-ai/m.gguf': hashlib.sha256(model.read_bytes()).hexdigest()})
        self.assertEqual(json.loads(owners_out.read_text())['opt/kylin-ai/m.gguf']['package'], 'kylin-ai-runtime')

    def test_empty_scan_stops_build(self):
        code = quiet(inventory.main, ['--root', str(self.root), '--out', str(Path(self.temp.name) / 'i.json'),
                                      '--owners-out', str(Path(self.temp.name) / 'o.json')])
        self.assertEqual(code, 3)

    def test_refuses_live_root(self):
        code = quiet(inventory.main, ['--root', '/', '--out', '/dev/null', '--owners-out', '/dev/null'])
        self.assertEqual(code, 2)


class TestQwenIndex(TempRoot):
    def make_model(self, corrupt=False):
        models = self.root
        layers = []
        for content in (b'weights' * 100, b'template'):
            sha = hashlib.sha256(content).hexdigest()
            blob = models / 'blobs' / f'sha256-{sha}'
            blob.parent.mkdir(parents=True, exist_ok=True)
            blob.write_bytes(content if not corrupt else content[::-1])
            layers.append({'digest': f'sha256:{sha}', 'size': len(content), 'mediaType': 'x'})
        manifest = models / 'manifests/registry.ollama.ai/library/qwen2.5-coder/7b-instruct'
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({'config': layers[1], 'layers': [layers[0]]}))
        return models

    def test_indexes_verified_blobs(self):
        index, problems = qwen.build_index(self.make_model(), qwen.DEFAULT_TAG)
        self.assertEqual(problems, [])
        self.assertEqual(index['model'], 'qwen2.5-coder:7b-instruct')
        self.assertEqual(len(index['blobs']), 2)

    def test_rejects_corrupt_blob(self):
        _, problems = qwen.build_index(self.make_model(corrupt=True), qwen.DEFAULT_TAG)
        self.assertTrue(problems and all('mismatch' in p for p in problems))

    def test_missing_manifest_writes_nothing(self):
        out = Path(self.temp.name) / 'q.json'
        self.assertEqual(quiet(qwen.main, ['--models', str(self.root), '--out', str(out)]), 2)
        self.assertFalse(out.exists())


SIM = """Reading package lists...
The following packages will be REMOVED:
  openkylin-token-center*
Purg openkylin-token-center [1.0]
Purg kylin-software-center:amd64 [2.0]
"""


class TestRemoval(unittest.TestCase):
    def test_exact_transaction_passes(self):
        self.assertEqual(removal.review(SIM, {'openkylin-token-center', 'kylin-software-center'}, set(), set()), [])

    def test_unrequested_removal_fails_until_allowed(self):
        sim = SIM + 'Remv openkylin-desktop-meta [1]\n'
        req = {'openkylin-token-center', 'kylin-software-center'}
        self.assertTrue(removal.review(sim, req, set(), set()))
        self.assertEqual(removal.review(sim, req, {'openkylin-desktop-meta'}, set()), [])

    def test_protected_packages_always_fail(self):
        req = {'openkylin-token-center', 'kylin-software-center'}
        for victim in ('ukui-control-center', 'apt', 'kylin-os-installer', 'flatpak'):
            sim = SIM + f'Remv {victim} [1]\n'
            self.assertTrue(removal.review(sim, req, {victim}, set()), victim)

    def test_model_owner_is_protected(self):
        sim = SIM + 'Remv kylin-ai-runtime [1]\n'
        req = {'openkylin-token-center', 'kylin-software-center'}
        self.assertTrue(removal.review(sim, req, {'kylin-ai-runtime'}, {'kylin-ai-runtime'}))

    def test_requested_but_not_removed_fails(self):
        self.assertTrue(removal.review(SIM, {'openkylin-token-center', 'kylin-software-center', 'ghost'}, set(), set()))


def fake_squashfs(size):
    import os, struct
    body = bytearray(os.urandom(size))
    body[:4] = b'hsqs'
    struct.pack_into('<Q', body, 40, size)
    return bytes(body)


class TestRecovery(TempRoot):
    WRAP = 64 * 1024

    def make(self, size=300 * 1024, before=37 * 2048, decoy=True):
        import os
        full = fake_squashfs(size)
        padded = full + b'\0' * (-len(full) % 4096)
        lead = bytearray(os.urandom(before))
        if decoy:   # another squashfs-looking sector that is not this file
            lead[2048:2052] = b'hsqs'
        iso = self.root / 'test.iso'
        iso.write_bytes(bytes(lead) + padded + os.urandom(5000))
        extracted = self.root / 'filesystem.squashfs'
        extracted.write_bytes(padded[:len(padded) % self.WRAP])
        return iso, extracted, padded

    def test_recovers_wrapped_file(self):
        iso, extracted, padded = self.make()
        self.assertIn('recovered', recovery.recover(iso, extracted, self.WRAP))
        self.assertEqual(extracted.read_bytes(), padded)
        self.assertFalse((self.root / 'filesystem.squashfs.part').exists())

    def test_finds_file_across_read_chunks(self):
        old = recovery.CHUNK
        recovery.CHUNK = 4096 + 3          # force the magic to straddle chunk boundaries
        self.addCleanup(setattr, recovery, 'CHUNK', old)
        iso, extracted, padded = self.make(before=50 * 2048)
        recovery.recover(iso, extracted, self.WRAP)
        self.assertEqual(extracted.read_bytes(), padded)

    def test_complete_file_is_left_alone(self):
        iso, extracted, padded = self.make()
        extracted.write_bytes(padded)
        self.assertEqual(recovery.recover(iso, extracted, self.WRAP), 'already complete')

    def test_inconsistent_size_is_refused(self):
        iso, extracted, padded = self.make()
        extracted.write_bytes(padded[:len(padded) % self.WRAP - 4096])
        with self.assertRaises(ValueError):
            recovery.recover(iso, extracted, self.WRAP)

    def test_mismatching_iso_is_refused_and_file_untouched(self):
        iso, extracted, padded = self.make()
        before = extracted.read_bytes()
        data = bytearray(iso.read_bytes())
        start = data.find(padded[:4096])
        data[start + 9000] ^= 0xFF           # corrupt a byte inside the already-extracted part
        iso.write_bytes(bytes(data))
        with self.assertRaises(ValueError):
            recovery.recover(iso, extracted, self.WRAP)
        self.assertEqual(extracted.read_bytes(), before)

    def test_not_squashfs_is_refused(self):
        iso, extracted, _ = self.make()
        extracted.write_bytes(b'x' * 8192)
        with self.assertRaises(ValueError):
            recovery.recover(iso, extracted, self.WRAP)


if __name__ == '__main__':
    unittest.main()
