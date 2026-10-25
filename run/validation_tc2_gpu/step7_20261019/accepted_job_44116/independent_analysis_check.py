from pathlib import Path
import json, hashlib, csv, sys
import numpy as np

analysis_dir=Path(sys.argv[1])
ledger_path=Path(sys.argv[2])
code_root=Path(sys.argv[3])
out=Path(sys.argv[4])
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''): h.update(block)
    return h.hexdigest().upper()
def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)
def digest(value): return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest().upper()
def read(path): return json.loads(path.read_text(encoding='utf-8'))
def extended(path):
    value=str(path)
    return Path(value if value.startswith('\\\\?\\') else '\\\\?\\'+value)
def metrics(labels,scores,dev,defects):
    positive=scores[labels==1]; negative=scores[labels==0]
    auroc=float(((positive[:,None]>negative[None,:]).sum()+.5*(positive[:,None]==negative[None,:]).sum())/(positive.size*negative.size))
    ap=0.; previous=0.
    for value in sorted(set(map(float,scores)),reverse=True):
        selected=scores>=value
        tp=int((selected & (labels==1)).sum())
        recall=tp/positive.size
        ap+=(recall-previous)*tp/int(selected.sum())
        previous=recall
    ordered=np.sort(dev)
    position=np.float64(len(ordered)-1)*np.float64(.95)
    lower=int(np.floor(position)); upper=min(lower+1,len(ordered)-1)
    fraction=np.float64(position-lower)
    difference=np.float64(np.subtract(ordered[upper],ordered[lower]))
    threshold=float(np.float64(ordered[lower])+difference*fraction if fraction<.5 else np.float64(ordered[upper])-difference*(np.float64(1)-fraction))
    prediction=scores>threshold
    return {'image_auroc':auroc,'image_ap':ap,'threshold_95pct':threshold,'normal_fpr':float(prediction[labels==0].mean()),'anomaly_recall':float(prediction[labels==1].mean()),'per_defect_recall':{kind:float(prediction[np.array(defects)==kind].mean()) for kind in sorted(set(defects)-{'good'})}}
def compare(expected,actual,path='',errors=None):
    if errors is None: errors={}
    if isinstance(expected,dict):
        assert isinstance(actual,dict) and set(expected)==set(actual),(path,set(expected),set(actual))
        for name,value in expected.items(): compare(value,actual[name],path+'.'+name if path else name,errors)
    elif isinstance(expected,float):
        assert isinstance(actual,(float,int)) and not isinstance(actual,bool)
        error=abs(expected-actual); assert error<=1e-12,(path,expected,actual,error)
        errors[path]=float(error)
    else: assert type(expected) is type(actual) and expected==actual,(path,expected,actual)
    return errors
analysis=read(analysis_dir/'analysis.json')
evidence=read(analysis_dir/'evidence.json')
identity=evidence['identity']
ledger=read(ledger_path)
design=read(code_root/'configs/experiments_tc2_gpu.json')
stage=analysis['stage']
selected=[value for value in design['stages'] if value['stage_id']==stage]
assert len(selected)==1
selected=selected[0]
assert stage=='I1_seed17'
assert analysis['identity_sha256']==analysis_dir.name==digest(identity)
assert identity['rows_sha256']==digest(analysis['rows'])
assert analysis['source_count']==6 and analysis['row_count']==18 and len(analysis['rows'])==18
assert analysis['score_rules']==selected['score_rules']==['native','max','top_0.01']
assert [source['run_key'] for source in identity['sources']]==selected['source_run_keys']
for relative,expected in identity['analysis_sources'].items(): assert sha(code_root/relative)==expected,relative
manifest_rows=(analysis_dir/'analysis.sha256').read_text(encoding='utf-8').splitlines()
assert len(manifest_rows)==3
for line in manifest_rows:
    expected,name=line.split('  ',1); assert name in ['analysis.json','analysis.csv','evidence.json'] and sha(analysis_dir/name)==expected
assert read(analysis_dir/'SUCCESS')=={'status':'passed','namespace':'formal','identity_sha256':analysis_dir.name,'analysis_manifest_sha256':sha(analysis_dir/'analysis.sha256')}
assert ledger['status']=='passed' and ledger['job_id']=='44053' and ledger['stage_id']=='B0' and ledger['stage_complete']
records={row['run_key']:row for row in ledger['results']}
fit_specs={row['run_key']:row['configuration'] for row in design['fits']}
source_checks=[]; expected_rows=[]; errors={}; loaded_fields=[]
for source in identity['sources']:
    key=source['run_key']; record=records[key]
    assert source['identity_sha256']==record['identity_sha256'] and source['path']==record['path']
    directory=extended(ledger['result_page_locations'][key])/source['path']
    cfg=read(directory/'config.yaml')
    assert cfg==source['configuration']==fit_specs[key]
    assert cfg['method']=='patchcore' and cfg['stage']=='B0' and cfg['run_seed']==17 and cfg['normal_train_n']==100
    assert source['artifacts_sha256']==sha(directory/'artifacts.sha256')
    input_hashes={}
    for name,expected in source['artifact_hashes'].items():
        actual=sha(directory/name); assert actual==expected,(key,name)
        input_hashes[name]=actual
    assert set(input_hashes)=={'config.yaml','samples.json','predictions.npz','metrics.json','evidence.json','validation.json'}
    groups=read(directory/'samples.json')
    saved_metrics=read(directory/'metrics.json')
    labels=np.array([row['label'] for row in groups['test']],dtype=np.uint8)
    defects=[row['defect_type'] for row in groups['test']]
    observed={}
    with np.load(directory/'predictions.npz',allow_pickle=False) as archive:
        for role in ('dev','test'):
            for suffix,field in [('paths','path'),('labels','label'),('defect_types','defect_type')]:
                field_name=role+'_'+suffix
                assert np.array_equal(archive[field_name],np.array([row[field] for row in groups[role]]))
                loaded_fields.append({'run_key':key,'field':field_name})
        for rule in analysis['score_rules']:
            test_name='test_score_'+rule; dev_name='dev_score_'+rule
            scores=archive[test_name]; dev=archive[dev_name]
            assert scores.dtype==np.float32 and dev.dtype==np.float32 and np.isfinite(scores).all() and np.isfinite(dev).all()
            observed[rule]=metrics(labels,scores,dev,defects)
            compare(observed[rule],saved_metrics['image'][rule],key+'.'+rule+'.source_metrics',errors)
            loaded_fields.extend([{'run_key':key,'field':name} for name in (test_name,dev_name)])
    native=observed['native']
    for rule in analysis['score_rules']:
        metric=observed[rule]
        expected_rows.append({'stage':stage,'run_key':key,'dataset':cfg['dataset'],'category':cfg['category'],'method':cfg['method'],'run_seed':cfg['run_seed'],'score_rule':rule,'n_dev':len(groups['dev']),'n_good':int((labels==0).sum()),'n_anomaly':int((labels==1).sum()),**metric,**{'delta_'+name+'_vs_native':metric[name]-native[name] for name in ('image_auroc','image_ap','normal_fpr','anomaly_recall')},'result_path':source['path'],'result_identity_sha256':source['identity_sha256'],'pixel_metrics_reference':{'path':source['path']+'/metrics.json','sha256':input_hashes['metrics.json'],'field':'pixel','validation_path':source['path']+'/validation.json','validation_sha256':input_hashes['validation.json'],'recomputed_by_analysis':False}})
    source_checks.append({'run_key':key,'identity_sha256':source['identity_sha256'],'directory':str(directory),'configuration':cfg,'artifact_hashes':input_hashes,'artifacts_sha256':source['artifacts_sha256'],'source_fingerprint_exact_match':True})
with (analysis_dir/'analysis.csv').open('r',encoding='utf-8',newline='') as stream:
    reader=csv.DictReader(stream)
    csv_rows=list(reader)
assert len(csv_rows)==18
for number,(expected,actual,csv_row) in enumerate(zip(expected_rows,analysis['rows'],csv_rows)):
    compare(expected,actual,'row_'+str(number),errors)
    assert set(csv_row)==set(actual)
    parsed={}
    for field,value in actual.items():
        text=csv_row[field]
        if isinstance(value,dict): parsed[field]=json.loads(text)
        elif isinstance(value,int): parsed[field]=int(text)
        elif isinstance(value,float): parsed[field]=float(text)
        else: parsed[field]=text
    compare(actual,parsed,'csv_row_'+str(number),errors)
audit={'status':'passed','stage_id':stage,'analysis_identity_sha256':analysis_dir.name,'analysis_directory':str(analysis_dir),'source_acceptance_ledger':{'path':str(ledger_path),'sha256':sha(ledger_path)},'analysis_artifact_hashes':{name:sha(analysis_dir/name) for name in ['analysis.json','analysis.csv','evidence.json','analysis.sha256','SUCCESS']},'source_count':6,'row_count':18,'source_image_rules_checked':18,'csv_rows_checked':18,'counts_checked':True,'delta_vs_native_checked':True,'source_id_and_hash_bindings_exact':True,'maximum_absolute_error':max(errors.values()),'tolerance':1e-12,'auroc_reference':'Positive-negative pairwise comparisons with half credit for ties','ap_reference':'Unique descending score thresholds, precision weighted by recall increments','threshold_reference':'NumPy 1.26 linear percentile arithmetic with FP32 adjacent difference and explicit FP64 interpolation','prediction_maps_loaded':False,'feature_arrays_loaded':False,'torch_imported':False,'pixel_metrics_recomputed':False,'sources':source_checks,'field_absolute_errors':errors,'prediction_fields_loaded':loaded_fields}
out.parent.mkdir(parents=True,exist_ok=True); assert not out.exists()
out.write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'passed','sources':6,'rows':18,'csv_rows':18,'max_abs_error':audit['maximum_absolute_error'],'analysis_identity_sha256':analysis_dir.name,'path':str(out),'sha256':sha(out)}))
