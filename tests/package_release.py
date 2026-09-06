"""Build a release only after tests; re-extract and run the full gate again."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from quality_gate import ROOT, fingerprint

ROOT_FILES={'index.html','app.js','search-core.js','style.css','local_preview.py','실행.bat','실행.command','requirements.txt','requirements-dev.txt','runtime.txt','.python-version','.env.example','.gitignore','.vercelignore','vercel.json','README.md','PRD.md','PROJECT_HANDOFF.md','CODEX_TASK.md','IMPLEMENTATION_NOTES.md','QUALITY_REPORT.md','SOURCE_AUDIT.json','QUALITY_GATE_RESULTS.json','REVIEW_RESULTS.json','BACKTEST_RESULTS.json','E2E_RESULTS.json'}
FOLDERS={'api','css','js','data','tests'}

def run(script,root=ROOT):
    p=subprocess.run([sys.executable,'-X','utf8',script],cwd=root,timeout=420)
    if p.returncode:raise RuntimeError(f'{script} failed; release is not published')

def release_files():
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file():continue
        rel=p.relative_to(ROOT)
        if p.is_symlink():raise RuntimeError('Symlinks are not packaged')
        if '__pycache__' in rel.parts or p.suffix in ('.pyc','.zip') or '.git' in rel.parts:continue
        if len(rel.parts)==1 and p.name in ROOT_FILES:yield p
        elif len(rel.parts)>1 and rel.parts[0] in FOLDERS:yield p

def main():
    os.environ['PYTHONUTF8']='1';os.environ['PYTHONDONTWRITEBYTECODE']='1'
    run('tests/quality_gate.py')
    run('tests/write_report.py')
    gate=json.loads((ROOT/'QUALITY_GATE_RESULTS.json').read_text(encoding='utf-8'))
    if not gate['ok'] or gate['fingerprint']!=fingerprint():raise RuntimeError('Sources changed after quality gate')
    parent=ROOT.parent.resolve()
    candidate=parent/'hwaseong-life-navi-candidate.zip'
    final=parent/'hwaseong-life-navi-production.zip'
    files=list(release_files())
    with zipfile.ZipFile(candidate,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for p in files:
            name='hwaseong-life-navi/'+p.relative_to(ROOT).as_posix()
            info=zipfile.ZipInfo(name);info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=(0o100755 if p.suffix=='.command' else 0o100644)<<16
            archive.writestr(info,p.read_bytes())
    verify_dir=Path(tempfile.mkdtemp(prefix='.release-verify-',dir=parent)).resolve()
    if verify_dir.parent!=parent:raise RuntimeError('Unexpected verification directory')
    with zipfile.ZipFile(candidate) as archive:
        if archive.testzip() is not None:raise RuntimeError('ZIP CRC check failed')
        for item in archive.infolist():
            rel=PurePosixPath(item.filename)
            if rel.is_absolute() or '..' in rel.parts or not rel.parts or rel.parts[0]!='hwaseong-life-navi':raise RuntimeError('Unsafe ZIP path')
            target=(verify_dir/Path(*rel.parts)).resolve()
            if not target.is_relative_to(verify_dir):raise RuntimeError('ZIP traversal')
            if '__pycache__' in rel.parts or '.git' in rel.parts or rel.suffix=='.pyc':raise RuntimeError('Excluded file included')
        archive.extractall(verify_dir)
    extracted=verify_dir/'hwaseong-life-navi'
    if fingerprint(extracted)!=gate['fingerprint']:raise RuntimeError('Extracted source fingerprint mismatch')
    print('[VERIFY] full quality gate on extracted ZIP',flush=True)
    run('tests/quality_gate.py',extracted)
    verified=json.loads((extracted/'QUALITY_GATE_RESULTS.json').read_text(encoding='utf-8'))
    if not verified['ok']:raise RuntimeError('Extracted verification failed')
    sha=hashlib.sha256(candidate.read_bytes()).hexdigest()
    candidate.replace(final)
    (parent/(final.name+'.sha256')).write_text(f'{sha}  {final.name}\n',encoding='utf-8')
    result={'ok':True,'zip':final.name,'sha256':sha,'zip_crc':'PASS','reextracted_quality_gate':'PASS','source_fingerprint':gate['fingerprint'],'files':len(files),'bytes':final.stat().st_size,'git_metadata':False,'python_cache':False,'secrets_detected':0,'verification_directory':verify_dir.name}
    (parent/'PACKAGE_RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report=(ROOT/'QUALITY_REPORT.md').read_text(encoding='utf-8')
    report+=f'\n## 최종 ZIP 검증 결과\n\n- ZIP CRC: PASS\n- ZIP 재해제 전체 품질게이트: PASS\n- 파일 수: {len(files)}\n- ZIP 크기: {final.stat().st_size:,} bytes\n- 최종 ZIP SHA-256: `{sha}`\n'
    (parent/'QUALITY_REPORT.md').write_text(report,encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
