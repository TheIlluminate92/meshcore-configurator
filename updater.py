"""Explicit GitHub release downloads; never touch profiles or radios."""
import hashlib
import json
import re
import uuid
import urllib.request
import urllib.error
from pathlib import Path
from app_version import VERSION
REPO = 'TheIlluminate92/meshcore-configurator'
API = 'https://api.github.com/repos/' + REPO
ASSET = 'MeshCore-Configurator.exe'

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        from urllib.parse import urlsplit
        parsed=urlsplit(newurl)
        if parsed.scheme!='https' or parsed.port not in (None,443) or parsed.username or parsed.password or parsed.hostname not in ('api.github.com','release-assets.githubusercontent.com','objects.githubusercontent.com'):
            raise ValueError('Unexpected update download destination.')
        result=super().redirect_request(req,fp,code,msg,headers,newurl)
        if result and parsed.hostname!='api.github.com':result.remove_header('Authorization')
        return result

def request(url, binary=False):
    headers={'Accept':'application/octet-stream' if binary else 'application/vnd.github+json','User-Agent':'MeshCore-Configurator','X-GitHub-Api-Version':'2022-11-28'}
    return urllib.request.build_opener(SafeRedirect()).open(urllib.request.Request(url,headers=headers),timeout=30)

def version(value):
    if not re.fullmatch(r'v?\d+\.\d+\.\d+',value):raise ValueError('Unsupported release version.')
    return tuple(map(int,value.lstrip('v').split('.')))

def check():
    try:
        with request(API+'/releases/latest') as response:release=json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code==404:raise ValueError('No published release is available yet. Try again after the release build finishes.') from None
        if exc.code in (403,429):raise ValueError('GitHub temporarily limited update checks. Please try again later.') from None
        raise ValueError('GitHub update check failed. Try again later.') from None
    if release.get('draft') or release.get('prerelease'):raise ValueError('Not a stable published release.')
    installed = version(VERSION.removesuffix('-dev'))
    available = version(release['tag_name'])
    if available < installed or (available == installed and not VERSION.endswith('-dev')):return None
    asset=next((a for a in release.get('assets',[]) if a['name']==ASSET),None)
    if not asset or not re.fullmatch(r'sha256:[a-f0-9]{64}',asset.get('digest') or ''):raise ValueError('Release has no verified Windows executable yet.')
    if type(asset.get('id')) is not int or asset['id']<=0 or type(asset.get('size')) is not int or not 0<asset['size']<=150*1024*1024:raise ValueError('Invalid update asset.')
    return {'version':release['tag_name'],'asset':asset,'notes':(release.get('body') or 'No release notes provided.')[:30000] if isinstance(release.get('body'),str) else 'No release notes provided.'}

def download(release,folder):
    asset=release['asset'];folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    ident=uuid.uuid4().hex
    path=folder/('download-'+ident+'.tmp');digest=hashlib.sha256();total=0
    try:
        with request(API+'/releases/assets/'+str(asset['id']),binary=True) as source,path.open('wb') as out:
            while chunk:=source.read(1024*1024):
                total+=len(chunk)
                if total>asset['size']:raise ValueError('Update exceeds its expected size.')
                digest.update(chunk);out.write(chunk)
        if total!=asset['size'] or 'sha256:'+digest.hexdigest()!=asset['digest']:raise ValueError('Update checksum mismatch. Nothing was installed.')
        with path.open('rb') as stream:
            if stream.read(2)!=b'MZ':raise ValueError('Downloaded file is not a Windows executable.')
        target=folder/('ready-'+ident+'.exe');path.replace(target);return target
    finally:path.unlink(missing_ok=True)

def schedule_install(staged,executable,parent_pid,expected_digest):
    """Wait for the app to exit before replacing the EXE, retaining a backup."""
    import base64,subprocess,os
    staged=Path(staged).resolve();executable=Path(executable).resolve()
    if staged.parent != executable.parent/'User Data'/'Updates' or not re.fullmatch(r'ready(?:-[a-f0-9]{32})?\.exe',staged.name) or executable.suffix.lower()!='.exe':
        raise ValueError('Invalid portable update location.')
    if not re.fullmatch(r'sha256:[a-f0-9]{64}',expected_digest or '') or 'sha256:'+hashlib.sha256(staged.read_bytes()).hexdigest()!=expected_digest:
        raise ValueError('Staged update changed after download. Check for updates again.')
    payload=base64.b64encode(json.dumps({'staged':str(staged),'exe':str(executable),'pid':parent_pid,'hash':expected_digest[7:]}).encode()).decode()
    script="""$ErrorActionPreference='Stop'
$d = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('PAYLOAD')) | ConvertFrom-Json
$log = Join-Path ([IO.Path]::GetDirectoryName($d.staged)) 'update.log'
try {
 $p=Get-Process -Id $d.pid -ErrorAction SilentlyContinue
 if ($p -and !$p.WaitForExit(60000)) { throw 'App still running; update cancelled.' }
 $sha=[Security.Cryptography.SHA256]::Create()
 $stream=[IO.File]::OpenRead($d.staged)
 try { $actual=[BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
 finally { $stream.Dispose(); $sha.Dispose() }
 if ($actual -ne $d.hash) { throw 'Staged checksum mismatch; update cancelled.' }
 $backup=Join-Path ([IO.Path]::GetDirectoryName($d.staged)) ('previous-'+[guid]::NewGuid().ToString()+'.exe')
 for ($attempt=0; $attempt -lt 30; $attempt++) {
  try { [IO.File]::Replace($d.staged,$d.exe,$backup); break }
  catch { if ($attempt -eq 29) { throw }; Start-Sleep -Seconds 1 }
 }
 Start-Process -FilePath $d.exe -WorkingDirectory ([IO.Path]::GetDirectoryName($d.exe))
 [IO.File]::WriteAllText($log,'Update installed.')
} catch { [IO.File]::WriteAllText($log,$_.Exception.Message) }
""".replace('PAYLOAD',payload)
    encoded=base64.b64encode(script.encode('utf-16-le')).decode()
    # A restarted one-file app must unpack a fresh runtime after its parent exits.
    # Otherwise PyInstaller treats it as a worker reusing deleted temporary files.
    environment=dict(os.environ)
    environment['PYINSTALLER_RESET_ENVIRONMENT']='1'
    return subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-WindowStyle','Hidden','-EncodedCommand',encoded],env=environment,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),close_fds=True)
