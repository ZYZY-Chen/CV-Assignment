"""Offline dependency safety fixtures; executes only extracted dependency Python."""
from pathlib import Path
from unittest.mock import patch
import contextlib, hashlib, io, json, os, re, stat, sys, uuid
AUDIT=Path(__file__).parent
HELPER=Path(r'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1')
CODE=Path(r'C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code')
FIXTURES=HELPER.parent/('s8_dependency_'+uuid.uuid4().hex[:8])
FIXTURES.mkdir()
source=HELPER.read_text(encoding='utf-8-sig')
script=source.split("<<'ANALYSIS_DEPENDENCY_PY'\n",1)[1].split('\nANALYSIS_DEPENDENCY_PY',1)[0]
compiled=compile(script,'<extracted ANALYSIS_DEPENDENCY_PY>','exec')
run_id='20261019_220000_1234abcd'
source_name='scripts/collect_experiments_loco_tc2_gpu_09ac7432f8f6bce3.py'
target_name='scripts/collect_experiments_loco_tc2_gpu.py'
base_name='scripts/collect_experiments_tc2_gpu.py'
accepted=(CODE/target_name).read_bytes(); base=(CODE/base_name).read_bytes()
sha=lambda data: hashlib.sha256(data).hexdigest().upper()
assert sha(accepted)=='09AC7432F8F6BCE36F95EAEFF15D44A19F7852781A19FE65E5E573239E445967'
assert sha(base)=='AC61772F65C9F2C4124761D2361E0A85E9F65DBCF4DF5BAB3E939B5111466010'
cases=[]
def fixture(name,target=False):
    root=FIXTURES/name; (root/'scripts').mkdir(parents=True); (root/'run/validation_tc2_gpu').mkdir(parents=True)
    (root/source_name).write_bytes(accepted); (root/base_name).write_bytes(base)
    if target: (root/target_name).write_bytes(accepted)
    return root

def execute(root,mode='repair',rid=run_id,opening=None):
    out=io.StringIO(); error=None
    manager=patch.object(Path,'open',opening) if opening else contextlib.nullcontext()
    with patch.object(sys,'argv',['-',str(root),mode,rid]),contextlib.redirect_stdout(out),manager:
        try: exec(compiled,{'__name__':'__main__'})
        except BaseException as exc: error=exc
    return out.getvalue(),error

def record(name,root,mode='repair',rid=run_id,expect_error=True,opening=None):
    before={str(p.relative_to(root)):sha(p.read_bytes()) for p in root.rglob('*') if p.is_file() and not p.is_symlink()}
    out,error=execute(root,mode,rid,opening)
    if expect_error:
        assert error is not None,(name,out)
        for key,value in before.items():
            p=root/key
            assert p.is_file() and sha(p.read_bytes())==value,(name,'overwrote',key)
        assert not (root/'run/validation_tc2_gpu'/('analysis_dependency_repair_'+rid)/'repair.json').exists(),name
    else:
        assert error is None,(name,repr(error))
    cases.append({'name':name,'status':'passed','error':type(error).__name__ if error else None,'detail':str(error) if error else out.strip()})
    return out,error

root=fixture('created'); out,_=record('created',root,expect_error=False)
assert (root/target_name).read_bytes()==accepted
line=next(v for v in out.splitlines() if v.startswith('ANALYSIS_DEPENDENCY_REPAIR_JSON=')); receipt=json.loads(line.split('=',1)[1]); payload=(json.dumps(receipt,sort_keys=True,separators=(',',':'))+'\n').encode()
assert receipt['outcome']=='created' and (root/receipt['record_path']).read_bytes()==payload
assert ('ANALYSIS_DEPENDENCY_REPAIR_SHA256='+sha(payload)) in out
root=fixture('already',True); out,_=record('already_exact',root,expect_error=False); assert 'already_exact' in out
root=fixture('check',True); before=set(root.rglob('*')); out,_=record('read_only_check',root,'check',expect_error=False); assert before==set(root.rglob('*')) and 'ANALYSIS_DEPENDENCY_CHECK_SHA256=' in out
root=fixture('missing_target'); record('check_missing_target_cannot_repair',root,'check'); assert not(root/target_name).exists()
for name,target in [('missing_source',False),('missing_source_exact_target',True)]:
    root=fixture(name,target); (root/source_name).unlink(); record(name,root); assert not(root/target_name).exists() if not target else True
for name,target in [('mutated_source',False),('mutated_source_exact_target',True)]:
    root=fixture(name,target); (root/source_name).write_bytes(accepted+b'changed'); record(name,root)
root=fixture('wrong_base'); (root/base_name).write_bytes(base+b'changed'); record('wrong_base',root); assert not(root/target_name).exists()
root=fixture('conflict',True); (root/target_name).write_bytes(b'conflicting target'); record('conflicting_target',root)
root=fixture('directory'); (root/target_name).mkdir(); record('nonregular_target_directory',root)
root=fixture('record_conflict'); (root/'run/validation_tc2_gpu'/('analysis_dependency_repair_'+run_id)).mkdir(); record('existing_record_conflict',root); assert not(root/target_name).exists()
root=fixture('record_file_conflict'); (root/'run/validation_tc2_gpu'/('analysis_dependency_repair_'+run_id)).write_bytes(b'existing'); record('existing_record_file_conflict',root); assert not(root/target_name).exists()
for mode in ['bad','REPAIR','']:
    root=fixture('mode_'+(mode or 'empty')); record('invalid_mode_'+repr(mode),root,mode)
for rid in ['bad','20261019_220000_1234ABCD','../../elsewhere','20261019_220000_1234abcde']:
    root=fixture('id_'+str(len(cases))); record('invalid_run_id_'+repr(rid),root,rid=rid)
for what in ['source','target','base']:
    root=fixture('hardlink_'+what,True); victim=root/{'source':source_name,'target':target_name,'base':base_name}[what]; other=root/('hardlink_'+what)
    try: os.link(victim,other)
    except OSError as exc:
        cases.append({'name':'actual_hardlink_'+what,'status':'unavailable','reason':str(exc)})
        observed_inode=victim.stat().st_ino; original_fstat=os.fstat
        def simulated_fstat(fd):
            value=original_fstat(fd)
            if value.st_ino==observed_inode:
                fields=list(value); fields[3]=2; return os.stat_result(fields)
            return value
        with patch('os.fstat',simulated_fstat): record('simulated_hardlink_'+what,root)
    else: record('hardlink_'+what,root)
# The target appears immediately before the exclusive creation call.
root=fixture('exclusive_race'); original_open=Path.open
raced=[False]
def race(path,*args,**kwargs):
    if path==root/target_name and args and args[0]=='xb' and not raced[0]:
        raced[0]=True
        with original_open(path,'xb') as stream: stream.write(b'concurrent writer')
    return original_open(path,*args,**kwargs)
record('exclusive_creation_race',root,opening=race); assert (root/target_name).read_bytes()==b'concurrent writer'
# Symlink fixtures are meaningful where Windows enables unprivileged symlink creation.
for what in ['source','target','base','scripts_ancestor','record_ancestor']:
    root=fixture('link_'+what,True)
    try:
        if what in ['source','target','base']:
            victim=root/{'source':source_name,'target':target_name,'base':base_name}[what]; dest=root/('real_'+what); victim.rename(dest); victim.symlink_to(dest)
        elif what=='scripts_ancestor':
            dest=root/'real_scripts'; (root/'scripts').rename(dest); (root/'scripts').symlink_to(dest,target_is_directory=True)
        else:
            dest=root/'real_validation'; (root/'run/validation_tc2_gpu').rename(dest); (root/'run/validation_tc2_gpu').symlink_to(dest,target_is_directory=True)
    except OSError as exc:
        cases.append({'name':'actual_symlink_'+what,'status':'unavailable','reason':str(exc)})
        victim=root/({'source':source_name,'target':target_name,'base':base_name,'scripts_ancestor':'scripts','record_ancestor':'run/validation_tc2_gpu'}[what])
        original_is_symlink=Path.is_symlink
        def simulated_link(path): return path==victim or original_is_symlink(path)
        with patch.object(Path,'is_symlink',simulated_link): record('simulated_symlink_'+what,root)
        continue
    record('symlink_'+what,root)
report={'status':'passed','fixture_root':str(FIXTURES),'helper_sha256':sha(HELPER.read_bytes()),'python_dependency_sha256':sha(script.encode()),'accepted_loco_sha256':sha(accepted),'base_sha256':sha(base),'cases':cases,'passed':sum(v['status']=='passed' for v in cases),'unavailable':sum(v['status']=='unavailable' for v in cases),'actual_network_calls':0,'actual_submissions':0,'actual_models':0}
(AUDIT/'dependency_python_validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
