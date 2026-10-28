#!/usr/bin/env python3
"""Publish verified build assets through CNB's release API; never print credentials."""
from pathlib import Path
import hashlib
import http.client
import json
import os
import urllib.error
import urllib.parse
import urllib.request

API = 'https://api.cnb.cool'
REPO = 'Anyin123f/recovery'


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as src:
        while block := src.read(8*1024**2): h.update(block)
    return h.hexdigest()


class ApiError(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__('CNB API request failed with HTTP %s; credentials were not logged' % status)


class Client:
    def __init__(self):
        self.token = os.environ.get('CNB_TOKEN', '')
        if not self.token:
            raise RuntimeError('CNB_TOKEN is unavailable. Source/tag can be preserved, but Release upload needs the current CNB IDE token.')

    def request(self, method, path, data=None):
        url = urllib.parse.urljoin(API, path)
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or parsed.netloc != 'api.cnb.cool' or not parsed.path.startswith('/'+REPO+'/-/releases'):
            raise RuntimeError('Refusing to send CNB authorization outside the expected release API')
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, method=method, headers={
            'Authorization':'Bearer '+self.token, 'Accept':'application/json',
            'Content-Type':'application/json', 'User-Agent':'PCHM30-source-freeze-v2'})
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                result = response.read()
                return json.loads(result) if result.strip() else None
        except urllib.error.HTTPError as error:
            raise ApiError(error.code) from None
        except Exception:
            raise RuntimeError('CNB release request failed; no authorization or signed URL was logged') from None

    def release(self, tag, commit, description):
        path = '/'+REPO+'/-/releases/tags/'+urllib.parse.quote(tag, safe='')
        try:
            result = self.request('GET', path)
        except ApiError as error:
            if error.status != 404: raise
            self.request('POST', '/'+REPO+'/-/releases', {
                'tag_name':tag, 'target_commitish':commit,
                'name':'PCHM30 LOS23.2 source stable V2 (cutout fixed)',
                'body':description, 'draft':False, 'prerelease':False, 'make_latest':'false'})
            result = self.request('GET', path)
        if result.get('tag_name') != tag or not result.get('id'):
            raise RuntimeError('Unexpected CNB release response')
        return result

    def put(self, url, path):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise RuntimeError('Invalid signed upload destination')
        connection = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=120)
        request_path = parsed.path + ('?'+parsed.query if parsed.query else '')
        size = path.stat().st_size
        try:
            connection.putrequest('PUT', request_path)
            connection.putheader('Content-Type', 'application/octet-stream')
            connection.putheader('Content-Length', str(size))
            connection.endheaders()
            sent = 0; next_progress = 128*1024**2
            with path.open('rb') as src:
                while block := src.read(4*1024**2):
                    connection.send(block); sent += len(block)
                    if sent >= next_progress:
                        print('Uploading %s: %d / %d MiB' % (path.name, sent//2**20, size//2**20), flush=True)
                        next_progress += 128*1024**2
            response = connection.getresponse()
            status = response.status; response.read(65536)
            if status not in (200,201,204):
                raise RuntimeError('CNB asset storage returned HTTP %s' % status)
        except Exception as error:
            if isinstance(error, RuntimeError): raise
            raise RuntimeError('CNB asset upload interrupted; retry the freeze command. Signed URL was not logged.') from None
        finally:
            connection.close()

    @staticmethod
    def validate_asset(asset, path, expected):
        if asset.get('name') != path.name or int(asset.get('size', -1)) != path.stat().st_size:
            raise RuntimeError('Release asset size/name differs: '+path.name)
        algo = str(asset.get('hash_algo','')).lower().replace('-','')
        if algo not in ('sha256','md5','sha1','sha512'):
            raise RuntimeError('Release asset does not expose a supported server hash: '+path.name)
        if algo == 'sha256':
            if asset.get('hash_value') != expected:
                raise RuntimeError('Release asset SHA256 differs: '+path.name)
        else:
            h = hashlib.new(algo)
            with path.open('rb') as src:
                while b := src.read(8*1024**2): h.update(b)
            if asset.get('hash_value') != h.hexdigest():
                raise RuntimeError('Release asset hash differs: '+path.name)

    def upload(self, release, tag, path):
        expected = sha256(path)
        current = self.request('GET', '/'+REPO+'/-/releases/tags/'+urllib.parse.quote(tag,safe=''))
        same = [asset for asset in current.get('assets',[]) if asset.get('name') == path.name]
        if same:
            if len(same) != 1: raise RuntimeError('Duplicate release asset: '+path.name)
            # Never overwrite an existing immutable stable asset without a server hash.
            if not same[0].get('hash_value'):
                raise RuntimeError('Existing asset has no server hash; preserve it and verify manually: '+path.name)
            self.validate_asset(same[0], path, expected)
            print('Existing release asset verified:',path.name,flush=True)
            return
        endpoint = '/'+REPO+'/-/releases/'+urllib.parse.quote(str(release['id']),safe='')+'/asset-upload-url'
        ticket = self.request('POST', endpoint, {'asset_name':path.name,'size':path.stat().st_size,'overwrite':False,'ttl':0})
        upload = ticket.get('upload_url'); verify = ticket.get('verify_url')
        if not upload or not verify: raise RuntimeError('CNB did not return an upload/confirmation ticket')
        # Validate the confirmation destination before sending any file bytes.
        verification = urllib.parse.urlsplit(urllib.parse.urljoin(API,verify))
        if verification.scheme != 'https' or verification.netloc != 'api.cnb.cool' or '/asset-upload-confirmation/' not in verification.path:
            raise RuntimeError('Unexpected CNB upload confirmation destination')
        self.put(upload,path)
        query = urllib.parse.parse_qsl(verification.query,keep_blank_values=True)
        query = [(k,v) for k,v in query if k != 'ttl'] + [('ttl','0')]
        verification_url = urllib.parse.urlunsplit(verification._replace(query=urllib.parse.urlencode(query)))
        self.request('POST',verification_url)
        current = self.request('GET', '/'+REPO+'/-/releases/tags/'+urllib.parse.quote(tag,safe=''))
        same = [a for a in current.get('assets',[]) if a.get('name') == path.name]
        if len(same) != 1: raise RuntimeError('Upload confirmation did not produce the expected release asset')
        self.validate_asset(same[0],path,expected)
        print('CNB release asset confirmed:',path.name,flush=True)
