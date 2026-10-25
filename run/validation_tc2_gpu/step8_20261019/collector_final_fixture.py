import copy,csv,hashlib,io,json,pathlib,shutil,struct,sys,tempfile,zlib
from unittest.mock import patch
root=pathlib.Path.cwd()
sys.path.insert(0,str(root/'scripts'))
import collect_analysis_tc2_gpu as c
J='99881'; passed=[]
def enc(v): return (json.dumps(v,sort_keys=True,ensure_ascii=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def h(b): return hashlib.sha256(b).hexdigest().upper()
def write(base,name,data):
 p=base/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(enc(data) if isinstance(data,(dict,list)) else data);return p
def png():
 def chunk(n,b): return struct.pack('>I',len(b))+n+b+struct.pack('>I',zlib.crc32(n+b)&0xffffffff)
 return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',2,2,8,0,0,0,0))+chunk(b'IDAT',zlib.compress(b'\0\xff\xff\0\xff\xff'))+chunk(b'IEND',b'')
def npy():
 header=repr({'descr':'<f4','fortran_order':False,'shape':(256,256)});size=16*((10+len(header)+1+15)//16)-10
 b=(header+' '*(size-len(header)-1)+'\n').encode()
 return b'\x93NUMPY\x01\x00'+struct.pack('<H',len(b))+b+bytes(256*256*4)
def fails(name,fn):
 try:fn()
 except (ValueError,OSError,KeyError,TypeError) as e:passed.append({'check':name,'status':'passed','rejection':str(e)[:150]});return
 raise AssertionError('Mutation accepted: '+name)
with tempfile.TemporaryDirectory(prefix='collector-fixture-',dir=root) as t:
 base=c._extended(t);src=base/'root';src.mkdir()
 registry=json.loads((root/'run/validation_tc2_gpu/step8_20261019/validated_inputs.json').read_text(encoding='utf-8'))
 design=json.loads((root/c.EXPERIMENT_CONFIG).read_text(encoding='utf-8'))
 for name in set(registry['protected_sources'])|c.SOURCES:
  out=src/name;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/name,out)
 image=png();image_sha=h(image);mapbytes=npy();manifests={}
 for name in c.MANIFESTS:
  value=json.loads((root/name).read_text(encoding='utf-8'));manifests[name]=value
  for row in value['test']['good']+value['test']['anomalies']:
   row['sha256']=image_sha
   for m in row.get('masks',[]):m['sha256']=image_sha
  write(src,name,value);design['scientific_source_hashes'][name]=h((src/name).read_bytes())
 write(src,c.EXPERIMENT_CONFIG,design);fixture_design_sha=h((src/c.EXPERIMENT_CONFIG).read_bytes())
 old={**c.OLD_SOURCES,c.EXPERIMENT_CONFIG:fixture_design_sha}
 registry['design_sha256']=fixture_design_sha
 registry['analysis_sources']={name:h((src/name).read_bytes()) for name in c.SOURCES}
 registry['protected_sources']={**design['scientific_source_hashes'],**design['pilot_source_hashes'],**old}
 inputs=enc(registry);config=(src/c.CONFIG).read_bytes()
 identity={'schema_version':'1.0','workflow_id':'tc2_gpu','stage':'analysis','job_id':J,'protocol_sha256':c.PROTOCOL_SHA256,'design_sha256':fixture_design_sha,'inputs_sha256':h(inputs),'analysis_config_sha256':h(config),'sources':registry['analysis_sources']}
 identity_sha=c._digest(identity);relative='run/tc2_gpu/summaries/analysis/'+identity_sha;out=src/relative;out.mkdir(parents=True)
 state={'mode':'tc2_gpu_analysis','stage_id':'analysis','job_id':J,'status':'passed','step_8_complete':True,'analysis_path':relative,'identity_sha256':identity_sha,'inputs_sha256':h(inputs),'config_sha256':h(config),'protocol_sha256':c.PROTOCOL_SHA256,'sources':registry['analysis_sources'],'results_count':66,'analysis_rows':108}
 names={'baseline','baseline_macro','baseline_summary','category_summary','improvement','paired_improvement','paired_improvement_summary','sampling_paired','sampling_summary','ablations','loco','image_metrics','pixel_metrics','resources','size_recall','shared_extraction','mask_areas'}
 counts={'baseline':180,'baseline_macro':30,'baseline_summary':10,'improvement':90,'image_metrics':370,'pixel_metrics':74,'loco':60,'resources':66}
 tables={n:[{'ordinal':i} for i in range(counts.get(n,1))] for n in names}
 tables['shared_extraction']=[{'dataset':v['dataset'],'category':v['category'],'cache_path':v['path'],'metadata_sha256':v['files']['metadata.json']} for v in registry['caches']]
 tables['mask_areas']=[{'dataset':dataset,'category':category,'path':a['path'],'area_pixels':1,'original_pixels':4,'area_fraction':.25,'size_group':'middle'} for dataset,categories in c.CATEGORIES.items() for category in categories for a in manifests['manifests/manifest_'+dataset+'_'+category+'.json']['test']['anomalies']]
 metricrefs=[];cases=[]
 for dataset,categories in c.CATEGORIES.items():
  for category in categories:
   m=manifests['manifests/manifest_'+dataset+'_'+category+'.json']
   selected=[m['test']['good'][0],m['test']['anomalies'][0]] if dataset=='mvtec_ad' else [next(a for a in m['test']['anomalies'] if a['defect_type']==g) for g in ('logical_anomalies','structural_anomalies')]
   pair={v['configuration']['method']:v['identity_sha256'] for v in registry['results'] if v['configuration']['dataset']==dataset and v['configuration']['category']==category and v['configuration']['run_seed']==17 and v['configuration']['normal_train_n']==100 and v['configuration']['stage']==('B0' if dataset=='mvtec_ad' else 'B0_LOCO')}
   for method,rule in (('padim','native'),('patchcore','native'),('patchcore','top_0.01')):
    metricrefs.append({'result_identity_sha256':pair[method],'score_rule':rule,'group':'pooled','threshold_95pct':.5,'ordinal':len(metricrefs)})
   for a in selected:
    cid='%03d'%(len(cases)+1);folder='cases/'+cid;label=int(a in m['test']['anomalies']);defect=a.get('defect_type','good')
    scores=[{'dataset':dataset,'category':category,'path':a['path'],'label':label,'defect_type':defect,'method':method,'score_rule':rule,'run_seed':17,'role':'test','score':.75 if label else .25,'threshold':.5,'prediction':bool(label),'result_identity_sha256':pair[method]} for method,rule in (('padim','native'),('patchcore','native'),('patchcore','top_0.01'))]
    masks=[{**m,'output_path':folder+'/masks/%03d.png'%(i+1)} for i,m in enumerate(a.get('masks',[]))]
    case={'dataset':dataset,'category':category,'path':a['path'],'label':label,'defect_type':defect,'group':defect,'case_id':cid,'image_path':folder+'/image.png','mask_path':folder+'/mask_union.png','raw_image_sha256':image_sha,'mask_sources':masks,'maps':{method:{'path':folder+'/'+method+'_map.npy','display_min':0,'display_max':1,'display_calibration':'normal development maps, percentile 99.5','same_map_for_native_and_top_0.01':True} for method in pair},'source_result_ids':pair,'scores':scores,'is_real_failure':False,'is_normal_false_positive':False}
    cases.append(case)
    for n in ('image.png','mask_union.png'):write(out,folder+'/'+n,image)
    for method in pair:write(out,folder+'/'+method+'_map.npy',mapbytes)
    for mask in masks:write(out,mask['output_path'],image)
    write(out,folder+'/case.json',case)
 tables['image_metrics']=metricrefs+[{'result_identity_sha256':'placeholder_%03d'%i,'score_rule':'native','group':'pooled','threshold_95pct':.5,'ordinal':i} for i in range(370-len(metricrefs))]
 for name,rows in tables.items():
  buf=io.StringIO(newline='');w=csv.DictWriter(buf,fieldnames=list(rows[0]));w.writeheader()
  for row in rows:w.writerow({k:json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True) if isinstance(v,(dict,list)) or v is None else str(v) for k,v in row.items()})
  write(out,'tables/'+name+'.csv',buf.getvalue().encode())
 provenance={'identity':identity,'source_artifacts_verified':True,'pixel_metrics_recomputed':False,'runtime':{'device':'cpu'}}
 figure_names=['F1_methods','baseline_comparison','F3_hyperparameters','F3_components','F3_fewshot','F4_improvement','F4_q_sensitivity','F4_score_distributions','F4_defect_size','F5_resources','loco_extension']+['F2_cases_%02d'%i for i in range(1,5)]
 figures=[]
 for n in figure_names:
  assets={'figures/'+n+'.png':image,'figures/'+n+'.pdf':b'%PDF-1.4\nsynthetic transport fixture\n','source_data/'+n+'.json':enc({'question':n,'rows':[],'rendering_changes_metrics':False}),'qa/'+n+'.alignment.json':enc({'status':'passed'})}
  for path,data in assets.items():write(out,path,data)
  figures.append({'name':n,'question':n,'dpi':300,'source_row_count':0,'alignment_status':'passed','files':{p:{'sha256':h(b),'bytes':len(b)} for p,b in assets.items()}})
 write(out,'inputs.json',inputs);write(out,'analysis_config.json',config);write(out,'provenance.json',provenance);write(out,'tables.json',tables)
 write(out,'cases.json',{'schema_version':'1.0','selection_policy':json.loads(config)['case_policy'],'cases':cases})
 write(out,'plot_manifest.json',{'status':'passed','figure_count':len(figures),'figures':figures,'plot_source_sha256':registry['analysis_sources']['scripts/plot_results_tc2_gpu.py'],'input_provenance':provenance,'metrics_changed_by_plotting':False})
 write(out,'verification.json',{'status':'passed','result_count':66,'analysis_rows':108,'unique_pc_analysis_rows':90,'case_count':16,'tables_verified':True,'figures_verified':True,'source_artifacts_verified':True,'pixel_metrics_recomputed':False})
 jobprefix='run/validation_tc2_gpu/step8_job_'+J
 write(src,jobprefix+'/setup_status.json',state);write(src,jobprefix+'/analysis_inputs.json',inputs)
 write(src,jobprefix+'/tests/tests_summary.json',{'status':'passed','full_plot_render_passed':True})
 write(src,jobprefix+'/tests/full_plot_fixture/DO_NOT_EXPORT.txt',b'excluded fixture tree')
 def rehash():
  files=sorted(p for p in out.rglob('*') if p.is_file() and p.name not in ('artifacts.sha256','SUCCESS'))
  write(out,'artifacts.sha256',''.join(h(p.read_bytes())+'  '+p.relative_to(out).as_posix()+'\n' for p in files).encode())
  write(out,'SUCCESS',{'status':'passed','namespace':'analysis','job_id':J,'identity_sha256':identity_sha,'artifacts_sha256':h((out/'artifacts.sha256').read_bytes())})
 rehash()
 with patch.object(c,'DESIGN_SHA256',fixture_design_sha),patch.object(c,'OLD_SOURCES',old),patch.object(c,'LIMIT',4*1024*1024):
  export=c.export_pages(src,J,base/'export');assert export['page_count']>1
  c.verify_index(export['index_path'],export['index_sha256'],J)
  dest=base/'download';dest.mkdir()
  for page in export['pages']:c.verify_archive(base/'export'/page['name'],page['sha256'],J,dest/('page_%03d'%page['page_number']),export['index_path'])
  receipt=c.verify_collection(export['index_path'],dest,J);assert receipt['step_8_complete'] is True and receipt['page_count']>1 and receipt['visual_review_performed'] is False
  idx=json.loads(c._extended(export['index_path']).read_text(encoding='utf-8'));assert not any('full_plot_fixture' in p for p in idx['all_artifact_paths']);assert all(p in idx['all_artifact_paths'] for p in c.MANIFESTS)
  passed.append({'check':'final multi-page export/index/archive/all-pages collection','status':'passed','pages':receipt['page_count'],'files':receipt['file_count'],'selected_cases':16,'source_fits':66,'analysis_rows':108,'eight_manifests':True,'test_fixture_tree_exported':False})
  fails('wrong index job',lambda:c.verify_index(export['index_path'],export['index_sha256'],'99882'))
  fails('wrong index SHA',lambda:c.verify_index(export['index_path'],'0'*64,J))
  first=export['pages'][0]
  fails('wrong archive SHA',lambda:c.verify_archive(base/'export'/first['name'],'0'*64,J,base/'bad-archive',export['index_path']))
  selected=cases[1];rawmask=out/selected['mask_sources'][0]['output_path'];original=rawmask.read_bytes();rawmask.write_bytes(b'altered mask');rehash()
  fails('rehash cannot relabel original mask bytes',lambda:c.export_pages(src,J,base/'bad-mask'));rawmask.write_bytes(original);rehash()
  imagepath=out/cases[0]['image_path'];imagepath.write_bytes(b'altered original image');rehash()
  fails('rehash cannot relabel original image bytes',lambda:c.export_pages(src,J,base/'bad-image'));imagepath.write_bytes(image);rehash()
  mapfile=out/cases[0]['maps']['padim']['path'];mapfile.write_bytes(mapbytes[:-4]+struct.pack('<f',float('nan')));rehash()
  fails('rehash cannot publish NaN selected map',lambda:c.export_pages(src,J,base/'bad-map'));mapfile.write_bytes(mapbytes);rehash()
  csvpath=out/'tables/baseline.csv';original=csvpath.read_bytes();csvpath.write_bytes(original.replace(b'179',b'999',1));rehash()
  fails('rehash cannot change CSV values',lambda:c.export_pages(src,J,base/'bad-csv'));csvpath.write_bytes(original);rehash()
  original=(src/jobprefix/'setup_status.json').read_bytes();badstate=copy.deepcopy(state);badstate['inputs_sha256']='0'*64;write(src,jobprefix+'/setup_status.json',badstate)
  fails('different input snapshot rejected',lambda:c.export_pages(src,J,base/'bad-state'));write(src,jobprefix+'/setup_status.json',original)
  path=dest/'page_001'/first['files'][0]['path'];original=path.read_bytes();path.write_bytes(original+b'\n')
  fails('post-extraction mutation rejected',lambda:c.verify_collection(export['index_path'],dest,J));path.write_bytes(original)
  missing=dest/('page_%03d'%len(export['pages']));renamed=dest/'held-last-page';missing.rename(renamed)
  fails('omitted page cannot complete',lambda:c.verify_collection(export['index_path'],dest,J));renamed.rename(missing)
 report={'status':'passed','collector_sha256':c._provenance()['collector_sha256'],'checks':passed,'fixture_boundary':'Synthetic image, masks, map arrays, tables and figure bytes; only fixture manifest/design SHA pins substituted with unittest.mock. The real 66-fit frozen configurations and accepted registry layout are retained. Transport and publication-contract check only; no scientific recomputation or PDF visual QA.','model_or_network_execution':False}
 write(root,'run/validation_tc2_gpu/step8_20261019/collector_final_fixture_validation.json',report)
 print(json.dumps(report,indent=2))

