import io
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import github_transfer as transfer
from package_public import PUBLIC


class TransferTests(unittest.TestCase):
    def test_allowlists_and_standalone_bats_match(self):
        self.assertEqual(transfer.PUBLIC_FILES,PUBLIC)
        source=(ROOT/'github_transfer.py').read_text(encoding='utf-8')
        for name in ('github_upload.bat','company_download.bat'):
            embedded=(ROOT/name).read_text(encoding='utf-8').split('# === PYTHON PAYLOAD ===\n',1)[1]
            self.assertEqual(embedded,source)
            compile(embedded,name,'exec')

    def test_download_ignores_private_files_and_preserves_local_data(self):
        buffer=io.BytesIO()
        with ZipFile(buffer,'w') as z:
            for name in PUBLIC:z.writestr('repo-root/'+name,('PUBLIC = '+repr(PUBLIC+['app/new_feature.py']) if name=='package_public.py' else 'new '+name).encode())
            z.writestr('repo-root/app/new_feature.py','new feature')
            z.writestr('repo-root/data/state.json','private')
            z.writestr('repo-root/../../escape.txt','escape')
        files=transfer.source_archive(buffer.getvalue())
        self.assertEqual(set(files),set(PUBLIC+['app/new_feature.py']))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'data').mkdir();state=root/'data/state.json';state.write_text('old data')
            transfer.install_sources(root,files)
            self.assertEqual(state.read_text(),'old data')
            self.assertEqual((root/'README.md').read_text(),'new README.md')

    def test_incomplete_archive_and_unlisted_write_rejected(self):
        buffer=io.BytesIO()
        with ZipFile(buffer,'w') as z:z.writestr('root/README.md','partial')
        with self.assertRaises(ValueError):transfer.source_archive(buffer.getvalue())
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):transfer.install_sources(Path(directory),{'data/state.json':b'bad'})


if __name__=='__main__':unittest.main()
