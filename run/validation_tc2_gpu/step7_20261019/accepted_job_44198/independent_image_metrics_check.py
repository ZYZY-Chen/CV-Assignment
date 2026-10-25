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
if prior: assert prior['status']=='passed'
prior_records={row['identity_sha256']:row for row in prior['results']} if prior else {}
rows=[]; seen=set(); reused=0
for page in sorted(base.glob('page_*')):
    folder=page/'run/tc2_gpu/results'
    if not folder.is_dir(): continue
    for directory in sorted(folder.iterdir()):
        config=read(directory/'config.yaml')
        if config['stage']!=stage: continue
        assert directory.name not in seen,directory.name
        seen.add(directory.name)
        hashes={name:sha(directory/name) for name in ['predictions.npz','samples.json','metrics.json','artifacts.sha256']}
        if directory.name in prior_records:
            old=prior_records[directory.name]
            assert hashes==old['artifact_hashes'],directory.name
            assert old['rule_count']==5 and old['max_abs_error']<=1e-12
            row=dict(old); row['page']=page.name
            row['validation_mode']='Reused independent CPU recomputation after final byte-for-byte artifact fingerprint match'
            row['prior_evidence']={'path':str(prior_path),'sha256':sha(prior_path),'identity_sha256':directory.name}
            rows.append(row); reused+=1; continue
        groups=read(directory/'samples.json')
        saved=read(directory/'metrics.json')
        metrics={}; errors={}; loaded=[]
        with np.load(directory/'predictions.npz',allow_pickle=False) as archive:
            for role in ('dev','test'):
                for suffix,field in [('paths','path'),('labels','label'),('defect_types','defect_type')]:
                    key=role+'_'+suffix
                    assert np.array_equal(archive[key],np.array([row[field] for row in groups[role]])),key
                    loaded.append(key)
            labels=np.array([row['label'] for row in groups['test']],dtype=np.uint8)
            defects=[row['defect_type'] for row in groups['test']]
            for rule in saved['image']:
                test_key='test_score_'+rule; dev_key='dev_score_'+rule
                test=archive[test_key]; dev=archive[dev_key]
                assert test.dtype==np.float32 and dev.dtype==np.float32
                assert np.isfinite(test).all() and np.isfinite(dev).all()
                metrics[rule]=reference(labels,test,dev,defects)
                errors.update(compare(metrics[rule],saved['image'][rule],rule))
                loaded.extend([test_key,dev_key])
        assert len(metrics)==5
        rows.append({'identity_sha256':directory.name,'run_key_fields':config,'page':page.name,'relative_path':'run/tc2_gpu/results/'+directory.name,'artifact_hashes':hashes,'rule_count':5,'max_abs_error':max(errors.values()),'field_abs_errors':errors,'recomputed_image_metrics':metrics,'prediction_fields_loaded':loaded,'dev_image_count':len(groups['dev']),'test_image_count':len(groups['test']),'validation_mode':'Independent CPU recomputation from saved score vectors'})
assert len(rows)==int(expected),(len(rows),expected)
audit={'status':'passed','stage_id':stage,'snapshot_path':str(base),'result_count':len(rows),'rule_count':sum(row['rule_count'] for row in rows),'maximum_absolute_error':max(row['max_abs_error'] for row in rows),'tolerance':1e-12,'auroc_reference':'Positive-negative pairwise comparisons with half credit for ties','ap_reference':'Unique descending score thresholds, precision weighted by recall increments','threshold_reference':'NumPy 1.26 linear percentile arithmetic with FP32 adjacent difference and explicit FP64 interpolation','prediction_maps_loaded':False,'feature_arrays_loaded':False,'torch_imported':False,'pixel_metrics_recomputed':False,'prior_recomputation_reused_after_exact_hash_match':reused,'newly_recomputed_from_final_snapshot':len(rows)-reused,'results':rows}
index_path=base.parent/'experiments-index.json'
index=read(index_path)
design_paths=list(base.glob('page_*/configs/experiments_tc2_gpu.json'))
assert design_paths and len({sha(path) for path in design_paths})==1
audit.update({'job_id':index['job_id'],'index_sha256':sha(index_path),'design_sha256':sha(design_paths[0]),'audit_script_sha256':sha(Path(__file__))})
out.parent.mkdir(parents=True,exist_ok=True)
assert not out.exists(),str(out)
out.write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'passed','result_count':len(rows),'rule_count':audit['rule_count'],'max_abs_error':audit['maximum_absolute_error'],'path':str(out),'sha256':sha(out),'results':[(row['run_key_fields']['category'],row['run_key_fields']['method'],row['identity_sha256']) for row in rows]}))
