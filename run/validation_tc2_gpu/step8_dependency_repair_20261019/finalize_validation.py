"""Bind the completed local supplement checks without claiming remote repair."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json

audit=Path(__file__).resolve().parent
root=audit.parents[2]
helper=Path(r'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest().upper()
before=json.loads((audit/'before_scope.json').read_bytes())
reports={}
for name in ('dependency_python_validation.json','dependency_transport_validation.json','helper_ast_validation.json','independent_review.json','scope_validation.json','shell_syntax_validation.json'):
    value=json.loads((audit/name).read_text(encoding='utf-8-sig'))
    assert value['status'] in ('passed','approved','no_blocking_findings'),(name,value.get('status'))
    reports[name]={'sha256':sha(audit/name)}
python=json.loads((audit/'dependency_python_validation.json').read_bytes())
transport=json.loads((audit/'dependency_transport_validation.json').read_text(encoding='utf-8-sig'))
assert python['helper_sha256']==sha(helper)
assert python['passed']==29 and python['unavailable']==8
assert all(item['status']=='passed' or (item['status']=='unavailable' and item['name'].startswith(('actual_hardlink_','actual_symlink_'))) for item in python['cases'])
assert all(item['status']=='passed' for item in transport['cases'])
assert all(sha(root/name)==expected for name,expected in before['analysis_sources'].items())
status={'status':'local_supplement_verified_awaiting_remote_dependency_repair','created_utc':datetime.now(timezone.utc).isoformat(),
    'workflow_id':'tc2_gpu','step_8_complete':False,'remote_dependency_repair_performed':False,
    'approved_scope':['External helper RepairAnalysisDependency action','Two read-only RunAnalysis preflight dependency checks','README English recovery instructions','New validation evidence only'],
    'helper_sha256':sha(helper),'readme_sha256':sha(root/'README.md'),'analysis_sources_unchanged':before['analysis_sources'],
    'accepted_dependency_sha256':'09AC7432F8F6BCE36F95EAEFF15D44A19F7852781A19FE65E5E573239E445967',
    'remote_source':'scripts/collect_experiments_loco_tc2_gpu_09ac7432f8f6bce3.py',
    'remote_target':'scripts/collect_experiments_loco_tc2_gpu.py',
    'dependency_logic_cases_passed':python['passed'],'native_link_cases_unavailable':python['unavailable'],'helper_transport_cases':len(transport['cases']),
    'link_test_boundary':'Native Windows link creation was unavailable; link-specific guard branches were exercised using explicit simulations recorded in the Python test report.',
    'validation_reports':reports,'failed_job_record':'job_44271_failure_verification.json',
    'next_user_terminal_command':'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "'+str(helper)+'" -Action RepairAnalysisDependency',
    'next_acceptance':['User executes dependency-only repair','Verify returned SHA-bound JSON receipt and terminal output','Only after repair acceptance provide RunAnalysis submission command'],
    'repair_action_slurm_submissions':0,'repair_action_uploads':0,'repair_action_model_calls':0,
    'actual_agent_tc2_connections':0,'actual_agent_slurm_submissions':0,'actual_agent_model_calls':0}
with (audit/'setup_status.json').open('x',encoding='utf-8') as stream:json.dump(status,stream,indent=2);stream.write('\n')
print(json.dumps({'status':status['status'],'dependency_cases_passed':python['passed'],'native_link_cases_unavailable':python['unavailable'],'transport_cases':len(transport['cases']),'seven_analysis_sources_unchanged':True,'step_8_complete':False}))
