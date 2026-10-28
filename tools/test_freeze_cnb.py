from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import freeze_cnb
from cnb_release import Client


class FreezeTests(unittest.TestCase):
    def test_publish_preserves_active_branch_and_staged_change_and_stable_tag(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);remote=base/'remote.git';workspace=base/'workspace';archive=base/'archive'
            def run(*args):return subprocess.check_output(['git',*map(str,args)],stderr=subprocess.DEVNULL,text=True).strip()
            run('init','--bare',remote);run('init',workspace)
            run('-C',workspace,'config','user.name','Fixture');run('-C',workspace,'config','user.email','fixture@example.invalid')
            run('-C',workspace,'config','core.autocrlf','false')
            (workspace/'README').write_text('Existing repository\n')
            run('-C',workspace,'add','.');run('-C',workspace,'commit','-m','Initial')
            run('-C',workspace,'branch','-M','los');run('-C',workspace,'remote','add','origin',remote)
            run('-C',workspace,'push','origin','los');run('-C',workspace,'switch','-c','axion')
            (workspace/'unrelated.txt').write_text('Keep this staged change\n')
            run('-C',workspace,'add','unrelated.txt')
            before=run('-C',workspace,'diff','--cached');head=run('-C',workspace,'rev-parse','HEAD')
            archive.mkdir();(archive/'TESTED-SOURCE-V2.json').write_text('{"fixture":true}\n')
            files={'TESTED-SOURCE-V2.json':hashlib.sha256((archive/'TESTED-SOURCE-V2.json').read_bytes()).hexdigest()}
            (archive/'FILES.json').write_text(json.dumps(files))
            with patch.object(freeze_cnb,'ORIGIN_URLS',{str(remote)}):
                commit,publish=freeze_cnb.publish_code(workspace,archive)
                self.assertEqual(run('-C',workspace,'branch','--show-current'),'axion')
                self.assertEqual(run('-C',workspace,'rev-parse','HEAD'),head)
                self.assertEqual(run('-C',workspace,'diff','--cached'),before)
                self.assertEqual(run('--git-dir',remote,'rev-parse','refs/heads/los'),commit)
                self.assertEqual(run('--git-dir',remote,'rev-parse','refs/tags/'+freeze_cnb.TAG+'^{commit}'),commit)
                repeated,_=freeze_cnb.publish_code(workspace,archive)
                self.assertEqual(repeated,commit)
                (archive/'TESTED-SOURCE-V2.json').write_text('{"different":true}\n')
                files['TESTED-SOURCE-V2.json']=hashlib.sha256((archive/'TESTED-SOURCE-V2.json').read_bytes()).hexdigest()
                (archive/'FILES.json').write_text(json.dumps(files))
                with self.assertRaisesRegex(RuntimeError,'not overwritten'):
                    freeze_cnb.publish_code(workspace,archive)
                self.assertEqual(run('--git-dir',remote,'rev-parse','refs/tags/'+freeze_cnb.TAG+'^{commit}'),commit)
            # Test-created worktree can leave Git administrative paths for tempfile cleanup.
            run('-C',workspace,'worktree','remove',publish)

    def test_release_upload_confirmation_and_permanent_retention_contract(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ,{'CNB_TOKEN':'test-not-a-real-token'}):
            path=Path(temporary)/'source.zip';path.write_bytes(b'fixture')
            asset={'name':path.name,'size':path.stat().st_size,'hash_algo':'sha256','hash_value':hashlib.sha256(path.read_bytes()).hexdigest()}
            client=Client();calls=[];state={'uploaded':False}
            def request(method,url,data=None):
                calls.append((method,url,data))
                if method=='GET':return {'assets':[asset] if state['uploaded'] else []}
                if url.endswith('/asset-upload-url'):
                    self.assertFalse(data['overwrite']);self.assertEqual(data['ttl'],0)
                    return {'upload_url':'https://cdn.example.invalid/file?signed=not-real','verify_url':'/Anyin123f/recovery/-/releases/1/asset-upload-confirmation/token/file'}
                self.assertIn('ttl=0',url);state['uploaded']=True
            with patch.object(client,'request',side_effect=request),patch.object(client,'put') as put:
                client.upload({'id':'1'},'fixture-tag',path)
                put.assert_called_once()
                client.upload({'id':'1'},'fixture-tag',path)
                put.assert_called_once()
            self.assertTrue(state['uploaded'])
            asset['hash_value']='0'*64
            with self.assertRaisesRegex(RuntimeError,'SHA256 differs'):
                Client.validate_asset(asset,path,'expected')


if __name__=='__main__':unittest.main()
