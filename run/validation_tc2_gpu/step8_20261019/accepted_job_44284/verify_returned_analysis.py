"""Verify the completed collection without fitting, extraction, or source edits."""
from pathlib import Path
from datetime import datetime,timezone
import gzip,hashlib,json,re,sys

root=Path(r'C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code')
output=Path(r'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup_20261019_220347_4dc4d911')
audit=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'scripts'))
import collect_analysis_tc2_gpu as collector
import analyze_results_tc2_gpu as analysis

expected='3450A62EDD4BEAAF026DD1EA5326CC827020219F6424FC0F744958FFE8D11079'
sha=lambda b:hashlib.sha256(b).hexdigest().upper()
log=(output/'terminal.txt').read_text(encoding='utf-8-sig')
assert re.findall(r'^ANALYSIS_INDEX_SHA256=([A-F0-9]{64})\r?$',log,re.M)==[expected]
assert re.search(r'^44284\s+\S+\s+COMPLETED\s+0:0\s+00:02:01\s+TC2N07\s+2\s+8G',log,re.M)
verified_index=collector.verify_index(output/'analysis-index.json',expected,'44284')
index=json.loads((output/'analysis-index.json').read_bytes())
assert index['partial'] is False and index['page_count']==1
archive_checks=[]
for page in index['pages']:
    archive=output/page['name']
    assert archive.stat().st_size==page['bytes'] and sha(archive.read_bytes())==page['sha256']
    length=0
    with gzip.open(archive,'rb') as stream:
        while True:
            block=stream.read(1024*1024)
            if not block:break
            length+=len(block);assert length<=536870912
    archive_checks.append({'name':page['name'],'bytes':page['bytes'],'decompressed_bytes':length,'sha256':page['sha256']})
collection=collector.verify_collection(output/'analysis-index.json',output/'remote','44284')
assert collection['partial'] is False and collection['stage_complete'] is True and collection['file_count']==199
page_root=output/'remote/page_001'
directory=analysis.inside(page_root,index['analysis_path'])
core_verification=analysis.verify_output(directory)
state=json.loads(analysis.inside(page_root,'run/validation_tc2_gpu/step8_job_44284/setup_status.json').read_bytes())
tests=json.loads(analysis.inside(page_root,'run/validation_tc2_gpu/step8_job_44284/tests/test_report.json').read_bytes())
assert state['status']=='passed' and state['step_8_complete'] is True and tests['tests_run']==29 and tests['status']=='passed'
assert tests['failures']==tests['errors']==tests['skipped']==0 and tests['full_plot_render_passed'] is True
assert not tests['torch_imported'] and not tests['gpu_or_models_executed']
registry=json.loads((directory/'inputs.json').read_bytes())
assert sha((directory/'inputs.json').read_bytes())==state['inputs_sha256']=='59F8F62DA7E14B2F1710F8EBE43ABF2A64D42B3B2A878B5677607D7FE4C06454'
assert registry['analysis_sources']==state['sources']
for name,fingerprint in state['sources'].items():assert analysis.sha(root/name)==fingerprint
for name,fingerprint in registry['protected_sources'].items():assert analysis.sha(root/name)==fingerprint
figures=json.loads((directory/'plot_manifest.json').read_bytes())
assert figures['figure_count']==15 and len(figures['figures'])==15
assert all(item['alignment_status'] in ('passed','not_applicable') for item in figures['figures'])
assert 'torch' not in sys.modules
record={'status':'verified_completed_outputs_pending_visual_acceptance','job_id':'44284','verified_at_utc':datetime.now(timezone.utc).isoformat(),
 'slurm_state':'COMPLETED','exit_code':'0:0','elapsed':'00:02:01','node':'TC2N07','cpus':2,'requested_memory':'8G','slurm_batch_max_rss_kib':884096,
 'source_directory':str(output),'page_root':str(page_root),'analysis_path':index['analysis_path'],'identity_sha256':state['identity_sha256'],
 'index_sha256':expected,'archive_checks':archive_checks,'collection_verification':collection,'core_output_verification':core_verification,
 'remote_full_tests_passed':29,'published_figures':15,'selected_cases':16,'source_results':66,'saved_score_rows':108,'unique_pc_source_rules':90,
 'analysis_sources_unchanged':7,'protected_sources_unchanged':44,'local_step_8_complete':False,
 'completion_boundary':'Collection/scientific output checks are independent from final visual QA. Remote completion alone does not establish local step-8 acceptance.',
 'actual_agent_tc2_connections':0,'actual_agent_slurm_submissions':0,'actual_agent_model_calls':0}
(audit/'returned_analysis_verification.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'status':record['status'],'files':199,'figures':15,'full_tests':29,'local_step_8_complete':False}))
