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
    def test_preserve_upstream(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root/'usr/share/ai/model').parent.mkdir(parents=True)
            (root/'usr/share/ai/model').write_bytes(b'kept')
            sha = hashlib.sha256(b'kept').hexdigest()
            inv = root/'inventory.json'; inv.write_text(json.dumps({'usr/share/ai/model':sha}))
            self.assertEqual(module.verify_existing_models(inv,root), [])
            (root/'usr/share/ai/model').write_bytes(b'changed')
            self.assertTrue(module.verify_existing_models(inv,root))
    def test_verify_coder_payload(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); blobs=root/'blobs'; blobs.mkdir()
            content=b'example fake digest, never an actual release model'
            sha=hashlib.sha256(content).hexdigest()
            (blobs/('sha256-'+sha)).write_bytes(content)
            index=root/'index.json'
            index.write_text(json.dumps({'model':module.MODEL_TAG,'blobs':[{'sha256':sha,'size':len(content)}]}))
            self.assertEqual(module.verify_qwen(index, blobs), [])
            (blobs/('sha256-'+sha)).write_bytes(b'bad')
            self.assertTrue(module.verify_qwen(index, blobs))
    def test_reject_path_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); inv=root/'inventory.json'
            inv.write_text(json.dumps({'../private': '0'*64}))
            self.assertTrue(module.verify_existing_models(inv,root))

if __name__ == '__main__': unittest.main()
