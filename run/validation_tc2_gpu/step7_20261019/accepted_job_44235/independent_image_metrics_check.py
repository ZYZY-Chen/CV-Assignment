from pathlib import Path
import json, hashlib, sys
import numpy as np

snapshot, output, stage, expected = sys.argv[1:5]
base=Path(snapshot)
out=Path(output)
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''): h.update(block)
    return h.hexdigest().upper()
def read(path): return json.loads(path.read_text(encoding='utf-8'))
def reference(labels,scores,dev,defects):
    positive=scores[labels==1]; negative=scores[labels==0]
    auroc=float(((positive[:,None]>negative[None,:]).sum()+.5*(positive[:,None]==negative[None,:]).sum())/(positive.size*negative.size))
    ap=0.; previous=0.
    for threshold in sorted(set(map(float,scores)),reverse=True):
        selected=scores>=threshold
        true_positive=int((selected & (labels==1)).sum())
        recall=true_positive/positive.size
        ap+=(recall-previous)*true_positive/int(selected.sum())
        previous=recall
    ordered=np.sort(dev)
    position=np.float64(len(ordered)-1)*np.float64(.95)
    lower=int(np.floor(position)); upper=min(lower+1,len(ordered)-1)
    fraction=np.float64(position-lower)
    difference=np.float64(np.subtract(ordered[upper],ordered[lower]))
    threshold=float(np.float64(ordered[lower])+difference*fraction if fraction<.5 else np.float64(ordered[upper])-difference*(np.float64(1)-fraction))
    prediction=scores>threshold
    return {'image_auroc':auroc,'image_ap':ap,'threshold_95pct':threshold,'normal_fpr':float(prediction[labels==0].mean()),'anomaly_recall':float(prediction[labels==1].mean()),'per_defect_recall':{kind:float(prediction[np.array(defects)==kind].mean()) for kind in sorted(set(defects)-{'good'})}}
def compare(expected,actual,prefix='',errors=None):
    if errors is None: errors={}
    assert set(expected)==set(actual),(prefix,set(expected),set(actual))
    for name,value in expected.items():
        key=prefix+'.'+name if prefix else name
        if isinstance(value,dict): compare(value,actual[name],key,errors)
        else:
            error=abs(value-actual[name])
            assert error<=1e-12,(key,value,actual[name],error)
            errors[key]=float(error)
    return errors
prior_path=Path(sys.argv[5]) if len(sys.argv)>5 else None
prior=read(prior_path) if prior_path else None
if prior:
    assert sha(prior_path)=='0DE0BC7B45075C7BE73783BB1851593D35BA1736053E1C220F19052834E44B93'
    assert prior['status']=='passed' and prior['job_id']=='44235' and prior['stage_id']=='B0_LOCO'
    assert prior['result_count']==3 and prior['scope_rule_evaluations']==45
    assert prior['index_sha256']=='C89F4E77B61756F7F397613A0CBD614AC99BB562BC45FE0745EB85BC79186DE9'
    assert prior['audit_script_sha256']==sha(prior_path.with_name('independent_image_metrics_check.py'))=='075B816AB6A10AC9AC7D6686228AFEE01A68CC46575A809C3A14B151C484A86A'
prior_records={row['identity_sha256']:row for row in prior['results']} if prior else {}
rows=[]; seen=set(); reused=0
scopes=('pooled','logical_anomalies','structural_anomalies')
for page in sorted(base.glob('page_*')):
    folder=page/'run/tc2_gpu/results'
    if not folder.is_dir(): continue
    for directory in sorted(folder.iterdir()):
        config=read(directory/'config.yaml')
        if config['stage']!=stage: continue
        assert stage=='B0_LOCO' and config['dataset']=='mvtec_loco'
        assert config['category'] in ('juice_bottle','screw_bag') and config['run_seed']==17 and config['normal_train_n']==100
        assert directory.name not in seen
        seen.add(directory.name)
        hashes={name:sha(directory/name) for name in ['predictions.npz','samples.json','metrics.json','artifacts.sha256']}
        if directory.name in prior_records:
            old=prior_records[directory.name]
            assert hashes==old['artifact_hashes']
            assert config==old['run_key_fields'] and directory.name==old['identity_sha256']
            evidence=read(directory/'evidence.json')
            encoded=json.dumps(evidence['identity'],sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('utf-8')
            assert hashlib.sha256(encoded).hexdigest().upper()==directory.name
            assert evidence['identity']['configuration']==config
            assert old['scope_rule_evaluations']==15 and old['max_abs_error']<=1e-12
            row=dict(old); row['page']=page.name
            row['validation_mode']='Reused independent CPU recomputation after final byte-for-byte artifact fingerprint match'
            row['prior_evidence']={'path':str(prior_path),'sha256':sha(prior_path),'identity_sha256':directory.name}
            rows.append(row); reused+=1; continue
        groups=read(directory/'samples.json')
        saved=read(directory/'metrics.json')
        assert set(saved)=={'image','pixel','metric_policy','groups','pixel_note'}
        assert set(saved['groups'])==set(scopes[1:])
        metrics={scope:{} for scope in scopes}; errors={}; loaded=[]
        labels=np.array([row['label'] for row in groups['test']],dtype=np.uint8)
        defects=[row['defect_type'] for row in groups['test']]
        scope_indices={'pooled':np.arange(len(labels))}
        for group in scopes[1:]:
            scope_indices[group]=np.array([i for i,item in enumerate(groups['test']) if item['defect_type']=='good']+[i for i,item in enumerate(groups['test']) if item['defect_type']==group],dtype=np.int64)
            subset=labels[scope_indices[group]]
            assert type(saved['groups'][group]['n_good']) is int and saved['groups'][group]['n_good']==int((subset==0).sum())
            assert type(saved['groups'][group]['n_anomaly']) is int and saved['groups'][group]['n_anomaly']==int((subset==1).sum())
        with np.load(directory/'predictions.npz',allow_pickle=False) as archive:
            for role in ('dev','test'):
                for suffix,field in [('paths','path'),('labels','label'),('defect_types','defect_type')]:
                    key=role+'_'+suffix
                    assert np.array_equal(archive[key],np.array([row[field] for row in groups[role]])),key
                    loaded.append(key)
            assert set(saved['image'])=={'native','max','top_0.001','top_0.01','top_0.05'}
            for rule in saved['image']:
                test_key='test_score_'+rule; dev_key='dev_score_'+rule
                test=archive[test_key]; dev=archive[dev_key]
                assert test.dtype==np.float32 and dev.dtype==np.float32
                assert np.isfinite(test).all() and np.isfinite(dev).all()
                for scope in scopes:
                    indices=scope_indices[scope]
                    metrics[scope][rule]=reference(labels[indices],test[indices],dev,[defects[i] for i in indices])
                    saved_scope=saved['image'] if scope=='pooled' else saved['groups'][scope]['image']
                    errors.update(compare(metrics[scope][rule],saved_scope[rule],scope+'.'+rule))
                loaded.extend([test_key,dev_key])
        rows.append({'identity_sha256':directory.name,'run_key_fields':config,'page':page.name,'relative_path':'run/tc2_gpu/results/'+directory.name,'artifact_hashes':hashes,'scoring_rule_count':5,'scope_rule_evaluations':15,'scopes':list(scopes),'max_abs_error':max(errors.values()),'field_abs_errors':errors,'recomputed_image_metrics':metrics,'prediction_fields_loaded':loaded,'dev_image_count':len(groups['dev']),'scope_counts':{scope:{'n_good':int((labels[indices]==0).sum()),'n_anomaly':int((labels[indices]==1).sum())} for scope,indices in scope_indices.items()},'test_image_count':len(groups['test']),'validation_mode':'Independent CPU recomputation from saved score vectors'})
assert len(rows)==int(expected)
index_path=base.parent/'experiments-index.json'
index=read(index_path)
assert index['stage_id']==stage and index['job_id']=='44235'
design_paths=list(base.glob('page_*/configs/experiments_tc2_gpu.json'))
assert design_paths and len({sha(path) for path in design_paths})==1
provenance=index['collector_provenance']
assert provenance['base_collector_sha256']=='AC61772F65C9F2C4124761D2361E0A85E9F65DBCF4DF5BAB3E939B5111466010'
assert provenance['collector_sha256']=='09AC7432F8F6BCE36F95EAEFF15D44A19F7852781A19FE65E5E573239E445967'
assert sha(index_path)=='DA890F4A554ED43009D7AA903A81A809FC5A009DB277234B800A342CA3B9D857'
assert index['snapshot_status']['stage_complete'] is True
if prior:
    assert prior['design_sha256']==sha(design_paths[0])
    assert prior['collector_provenance']==provenance
    assert prior['experiment_sources']==index['snapshot_status']['experiment_sources']
    assert reused==3 and len(rows)-reused==1
audit={'status':'passed','stage_id':stage,'job_id':index['job_id'],'snapshot_path':str(base),'index_sha256':sha(index_path),'design_sha256':sha(design_paths[0]),'experiment_sources':index['snapshot_status']['experiment_sources'],'collector_provenance':provenance,'audit_script_sha256':sha(Path(__file__)),'result_count':len(rows),'scoring_rule_evaluations':sum(row['scoring_rule_count'] for row in rows),'scope_rule_evaluations':sum(row['scope_rule_evaluations'] for row in rows),'prior_recomputation_reused_after_exact_hash_match':reused,'newly_recomputed_from_snapshot':len(rows)-reused,'maximum_absolute_error':max(row['max_abs_error'] for row in rows),'tolerance':1e-12,'auroc_reference':'Positive-negative pairwise comparisons with half credit for ties','ap_reference':'Unique descending score thresholds, precision weighted by recall increments','threshold_reference':'NumPy 1.26 linear percentile arithmetic with FP32 adjacent difference and explicit FP64 interpolation','prediction_maps_loaded':False,'feature_arrays_loaded':False,'torch_imported':False,'pixel_metrics_recomputed':False,'remote_stage_complete':index['snapshot_status']['stage_complete'],'stage_acceptance_granted_by_this_audit':False,'completion_scope':'Image metrics only; complete paged collection and stage/dependency acceptance are separate','results':rows}
out.parent.mkdir(parents=True,exist_ok=True)
assert not out.exists()
out.write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'passed','job_id':audit['job_id'],'stage_id':stage,'result_count':len(rows),'scope_rule_evaluations':audit['scope_rule_evaluations'],'maximum_absolute_error':audit['maximum_absolute_error'],'remote_stage_complete':audit['remote_stage_complete'],'reused_results':reused,'newly_recomputed_results':len(rows)-reused,'stage_acceptance_granted_by_this_audit':False,'path':str(out),'sha256':sha(out),'script_sha256':audit['audit_script_sha256'],'identities':[row['identity_sha256'] for row in rows]}))
