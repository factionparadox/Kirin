import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('image_contract', ROOT / 'scripts/check-image-contract.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ContractTests(unittest.TestCase):
    def test_upstream_models_must_be_gone(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for rel in ('usr/share/kylin-ai/asr.onnx', 'usr/share/viewer/matting.onnx'):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_bytes(b'model')
            inv = root / 'inventory.json'
            inv.write_text(json.dumps({'usr/share/kylin-ai/asr.onnx': '0' * 64, 'usr/share/viewer/matting.onnx': '1' * 64}))
            owners = root / 'owners.json'
            owners.write_text(json.dumps({'usr/share/kylin-ai/asr.onnx': {'package': 'kylin-speech-asr-model-onnx'},
                                          'usr/share/viewer/matting.onnx': {'package': 'kylin-photo-viewer'}}))
            kept = root / 'kept.txt'; kept.write_text('kylin-photo-viewer\n')
            problems, notes = module.verify_models_removed(inv, owners, kept, root)
            self.assertEqual(problems, ['openKylin AI model still present: usr/share/kylin-ai/asr.onnx (kylin-speech-asr-model-onnx)'])
            self.assertEqual(notes, ['kept inside kylin-photo-viewer: usr/share/viewer/matting.onnx'])
            (root / 'usr/share/kylin-ai/asr.onnx').unlink()
            self.assertEqual(module.verify_models_removed(inv, owners, kept, root)[0], [])

    def test_on_demand_needs_no_coding_model(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); inv = root / 'inventory.json'; inv.write_text('{}')
            self.assertEqual(module.main(['--upstream-inventory', str(inv), '--candidate-root', str(root)]), 0)

    def test_verify_coder_payload(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); blobs=root/'blobs'; blobs.mkdir()
            content=b'example fake digest, never an actual release model'
            sha=hashlib.sha256(content).hexdigest()
            (blobs/('sha256-'+sha)).write_bytes(content)
            index=root/'index.json'
            index.write_text(json.dumps({'model':module.MODEL_TAG,'blobs':[{'sha256':sha,'size':len(content)}]}))
            self.assertTrue(any('under 4 GB' in reason for reason in module.verify_qwen(index, blobs)))
            (blobs/('sha256-'+sha)).write_bytes(b'bad')
            self.assertTrue(module.verify_qwen(index, blobs))
    def test_reject_path_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); inv=root/'inventory.json'
            inv.write_text(json.dumps({'../private': '0'*64}))
            self.assertTrue(module.verify_models_removed(inv, None, None, root)[0])

if __name__ == '__main__': unittest.main()
