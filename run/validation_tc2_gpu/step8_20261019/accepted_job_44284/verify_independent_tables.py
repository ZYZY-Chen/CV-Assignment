"""Independently validate step 8 tables against the accepted step 7 metadata.

Uses only the standard library. Does not import production analysis code, read
prediction arrays, execute models, or write outside the selected audit directory.
"""
import argparse
import collections
import csv
import hashlib
import json
import math
import pathlib
import statistics


def extended(path):
    value = str(path.resolve())
    return pathlib.Path(value if value.startswith('\\\\?\\') else '\\\\?\\' + value)


def read(path):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            assert key not in value, ('duplicate JSON key', str(path), key)
            value[key] = item
        return value
    return json.loads(extended(path).read_text(encoding='utf-8'), object_pairs_hook=unique)


def sha(path):
    return hashlib.sha256(extended(path).read_bytes()).hexdigest().upper()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True, type=pathlib.Path)
    parser.add_argument('--analysis', required=True, type=pathlib.Path)
    parser.add_argument('--output', required=True, type=pathlib.Path)
    args = parser.parse_args()
    registry, tables = read(args.analysis/'inputs.json'), read(args.analysis/'tables.json')
    config = read(args.analysis/'analysis_config.json')
    categories, seeds, rules = config['main_categories'], config['seeds'], config['score_rules']
    metrics = ['image_auroc', 'image_ap', 'normal_fpr', 'anomaly_recall', 'pixel_auroc', 'pixel_ap']
    checked, maximum_error = 0, 0.0

    def equal(actual, expected, where):
        nonlocal checked, maximum_error
        checked += 1
        if isinstance(expected, float):
            assert math.isfinite(actual) and math.isfinite(expected), where
            error = abs(actual-expected)
            maximum_error = max(maximum_error, error)
            assert math.isclose(actual, expected, rel_tol=2e-14, abs_tol=2e-14), (where, actual, expected)
        else:
            assert actual == expected, (where, actual, expected)

    accepted, pages, result_pages = {}, {}, {}
    for stage in registry['stages']:
        path = args.root/stage['acceptance_record']
        equal(sha(path), stage['acceptance_sha256'], 'acceptance hash')
        acceptance = read(path)
        assert acceptance['status'] == 'passed' and acceptance['stage_complete']
        accepted[stage['stage_id']] = acceptance
        pages[stage['stage_id']] = sorted(extended(pathlib.Path(acceptance['source_directory'])/'remote').glob('page_*'))
        result_pages.update({key: pathlib.Path(value) for key, value in acceptance.get('result_page_locations', {}).items()})

    def locate(stage_id, relative, run_key=None):
        candidates = [result_pages[run_key]] if run_key in result_pages else pages[stage_id]
        found = [p/relative for p in candidates if extended(p/relative).is_file()]
        assert found, ('accepted payload absent', stage_id, relative)
        assert len({sha(p) for p in found}) == 1, ('conflicting accepted payload', relative)
        return found[0]

    records = {}
    for entry in registry['results']:
        c = entry['configuration']
        record = {'configuration': c, 'entry': entry}
        for name in ['metrics.json', 'evidence.json', 'samples.json']:
            p = locate(c['stage'], entry['path']+'/'+name, entry['run_key'])
            equal(sha(p), entry['files'][name], 'source '+entry['run_key']+'/'+name)
            record[name[:-5]] = read(p)
        equal(record['evidence']['identity']['configuration'], c, 'configuration')
        records[entry['run_key']] = record
    assert len(records) == 66

    # Verify every image and pixel row directly from its immutable metrics file.
    expected_image_keys, expected_pixel_keys = set(), set()
    for key, r in records.items():
        groups = {'pooled': r['metrics']}
        if r['configuration']['dataset'] == 'mvtec_loco':
            groups.update(r['metrics']['groups'])
        for group, value in groups.items():
            expected_pixel_keys.add((key, group))
            for rule in rules:
                expected_image_keys.add((key, group, rule))
    equal(len(tables['image_metrics']), 370, 'image row count')
    equal(len(tables['pixel_metrics']), 74, 'pixel row count')
    equal({(r['run_key'], r['group'], r['score_rule']) for r in tables['image_metrics']}, expected_image_keys, 'image row keys')
    equal({(r['run_key'], r['group']) for r in tables['pixel_metrics']}, expected_pixel_keys, 'pixel row keys')
    for row in tables['image_metrics']:
        r = records[row['run_key']]
        group = r['metrics'] if row['group']=='pooled' else r['metrics']['groups'][row['group']]
        for key, value in {**group['image'][row['score_rule']], **group['pixel']}.items():
            equal(row[key], value, 'image source '+key)
    for row in tables['pixel_metrics']:
        r = records[row['run_key']]
        group = r['metrics'] if row['group']=='pooled' else r['metrics']['groups'][row['group']]
        for key, value in group['pixel'].items():
            equal(row[key], value, 'pixel source '+key)
    for table_name in ['baseline','ablations','loco','improvement']:
        for row in tables[table_name]:
            r=records[row['run_key']]
            group=r['metrics'] if row['group']=='pooled' else r['metrics']['groups'][row['group']]
            equal(row['result_identity_sha256'],r['entry']['identity_sha256'],'table source identity')
            for key,value in {**group['image'][row['score_rule']],**group['pixel']}.items():
                equal(row[key],value,table_name+' source '+key)
            for key in ['dataset','category','method','run_seed','normal_train_n','stage','layers']:
                equal(row[key],r['configuration'][key],table_name+' configuration '+key)
    equal(collections.Counter((r['stage'],r['run_seed']) for r in tables['ablations']),{
        ('B0',17):20,('R0',29):20,('R0',43):20,('H1',17):20,
        ('H2',17):20,('C1',17):10,('C1R',29):10,('C1R',43):10,
        ('C2',17):20,('F1',17):40},'ablation coverage')
    equal({r['category'] for r in tables['ablations']},{'cable','screw'},'ablation categories')

    baseline = {key:r for key,r in records.items() if r['configuration']['stage'] in ['B0','R0']}
    equal(len(baseline), 36, 'baseline fits')
    equal({(r['configuration']['category'], r['configuration']['method'], r['configuration']['run_seed']) for r in baseline.values()}, {(c,m,s) for c in categories for m in ['padim','patchcore'] for s in seeds}, 'baseline design')
    equal(len(tables['baseline']), 180, 'baseline rows')
    for row in tables['baseline']:
        assert row['run_key'] in baseline and row['group']=='pooled'
    macro_expected = {}
    for method in ['padim','patchcore']:
        for rule in rules:
            for seed in seeds:
                selected=[r for r in baseline.values() if r['configuration']['method']==method and r['configuration']['run_seed']==seed]
                assert len(selected)==6
                macro_expected[method,rule,seed] = {metric:statistics.mean(r['metrics']['image'][rule][metric] if metric.startswith('image') or metric in ['normal_fpr','anomaly_recall'] else r['metrics']['pixel'][metric] for r in selected) for metric in metrics}
    equal(len(tables['baseline_macro']),30,'macro rows')
    for row in tables['baseline_macro']:
        equal(row['n_categories'],6,'macro categories')
        for metric,value in macro_expected[row['method'],row['score_rule'],row['run_seed']].items():
            equal(row[metric],value,'macro '+metric)
    for row in tables['baseline_summary']:
        equal(row['n_seeds'],3,'summary seeds'); equal(row['ddof'],1,'summary ddof')
        for metric in metrics:
            values=[macro_expected[row['method'],row['score_rule'],seed][metric] for seed in seeds]
            equal(row[metric+'_mean'],statistics.mean(values),'summary mean '+metric)
            equal(row[metric+'_std'],statistics.stdev(values),'summary SD '+metric)
    for row in tables['category_summary']:
        selected=[r for r in baseline.values() if r['configuration']['category']==row['category'] and r['configuration']['method']==row['method']]
        equal(len(selected),3,'category seeds'); equal(row['ddof'],1,'category ddof')
        for metric in metrics:
            values=[r['metrics']['image'][row['score_rule']][metric] if metric.startswith('image') or metric in ['normal_fpr','anomaly_recall'] else r['metrics']['pixel'][metric] for r in selected]
            equal(row[metric+'_mean'],statistics.mean(values),'category mean '+metric)
            equal(row[metric+'_std'],statistics.stdev(values),'category SD '+metric)

    # Paired score deltas preserve the same category and same fitted seed.
    pc={key:r for key,r in baseline.items() if r['configuration']['method']=='patchcore'}
    paired_expected={}
    equal(len(tables['improvement']),90,'PC unique rows')
    for row in tables['improvement']:
        r=pc[row['run_key']]
        for reference in ['native','max']:
            for metric in metrics[:4]:
                expected=r['metrics']['image'][row['score_rule']][metric]-r['metrics']['image'][reference][metric]
                equal(row['delta_'+metric+'_vs_'+reference],expected,'paired per fit '+metric)
    for row in tables['paired_improvement']:
        selected=[r for r in pc.values() if r['configuration']['run_seed']==row['run_seed']]
        equal(len(selected),6,'paired macro categories'); equal(row['n_categories'],6,'paired macro label')
        key=row['score_rule'],row['reference_rule'],row['run_seed']
        paired_expected[key]={metric:statistics.mean(r['metrics']['image'][row['score_rule']][metric]-r['metrics']['image'][row['reference_rule']][metric] for r in selected) for metric in metrics[:4]}
        for metric,value in paired_expected[key].items(): equal(row[metric],value,'paired macro '+metric)
    for row in tables['paired_improvement_summary']:
        equal(row['n_seeds'],3,'paired seeds'); equal(row['ddof'],1,'paired ddof')
        for metric in metrics[:4]:
            values=[paired_expected[row['score_rule'],row['reference_rule'],s][metric] for s in seeds]
            equal(row[metric+'_mean'],statistics.mean(values),'paired summary mean')
            equal(row[metric+'_std'],statistics.stdev(values),'paired summary SD')

    # Check 108 checkpoint rows are lineage, with 18 exact overlapping observations.
    checkpoints={}
    for entry in registry['analyses']:
        p=locate(entry['stage_id'],entry['path']+'/analysis.json')
        equal(sha(p),entry['files']['analysis.json'],'checkpoint hash')
        value=read(p);equal(len(value['rows']),entry['rows'],'checkpoint rows')
        checkpoints[entry['stage_id']]=value['rows']
    equal(sum(map(len,checkpoints.values())),108,'lineage source rows')
    def identity(row): return row['result_identity_sha256'],row['score_rule']
    overlap={identity(r):r for r in checkpoints['I1_all_seeds']}
    for row in checkpoints['I1_seed17']:
        other=overlap[identity(row)]
        for metric in metrics[:4]+['threshold_95pct','per_defect_recall']:
            equal(row[metric],other[metric],'checkpoint overlap '+metric)
    unique={identity(r) for values in checkpoints.values() for r in values}
    equal(len(unique),90,'unique checkpoint rows')
    equal(unique,{(r['result_identity_sha256'],r['score_rule']) for r in tables['improvement']},'checkpoint canonical identity')

    # Random sampling comparisons use two matched categories for each seed.
    sampling_expected={}
    for row in tables['sampling_paired']:
        selected=[r for r in records.values() if r['configuration']['stage'] in ['C1','C1R'] and r['configuration']['run_seed']==row['run_seed']]
        equal(len(selected),2,'sampling categories'); equal(row['n_categories'],2,'sampling count label')
        equal({r['configuration']['category'] for r in selected},{'cable','screw'},'sampling categories identity')
        values={}
        for metric in metrics:
            differences=[]
            for random in selected:
                c=random['configuration']
                coreset=next(r for r in pc.values() if r['configuration']['category']==c['category'] and r['configuration']['run_seed']==c['run_seed'])
                field='image' if metric in metrics[:4] else 'pixel'
                left=random['metrics'][field][row['score_rule']][metric] if field=='image' else random['metrics'][field][metric]
                right=coreset['metrics'][field][row['score_rule']][metric] if field=='image' else coreset['metrics'][field][metric]
                differences.append(left-right)
            values[metric]=statistics.mean(differences)
            equal(row[metric],values[metric],'sampling pair '+metric)
        sampling_expected[row['score_rule'],row['run_seed']]=values
    for row in tables['sampling_summary']:
        equal(row['n_seeds'],3,'sampling seeds'); equal(row['n_categories'],2,'sampling category label'); equal(row['ddof'],1,'sampling ddof')
        for metric in metrics:
            values=[sampling_expected[row['score_rule'],s][metric] for s in seeds]
            equal(row[metric+'_mean'],statistics.mean(values),'sampling mean')
            equal(row[metric+'_std'],statistics.stdev(values),'sampling SD')

    equal(len(tables['loco']),60,'LOCO rows')
    assert all(r['dataset']=='mvtec_loco' and r['run_seed']==17 for r in tables['loco'])
    equal(collections.Counter(r['group'] for r in tables['loco']),{'logical_anomalies':20,'structural_anomalies':20,'pooled':20},'LOCO separate groups')
    assert not any('std' in key for row in tables['loco']+tables['ablations'] for key in row), 'single-seed table invented SD'
    assert all(r['dataset']=='mvtec_ad' for r in tables['baseline']), 'LOCO mixed with AD'

    # Model-only cached dev+test timing, analytical FP32 tensor storage and GPU peaks.
    equal(len(tables['resources']),66,'resource rows')
    for row in tables['resources']:
        r=records[row['run_key']];e,s=r['evidence'],r['samples'];d=e['method_detail']
        for key,value in e['timings'].items():equal(row[key],value,'timing '+key)
        count=len(s['dev'])+len(s['test'])
        equal(row['dev_image_count'],len(s['dev']),'dev count'); equal(row['test_image_count'],len(s['test']),'test count')
        equal(row['prediction_image_count'],count,'prediction denominator')
        equal(row['predict_ms_per_image'],1000*e['timings']['predict_seconds']/count,'prediction latency')
        if row['method']=='padim':
            h,w=d['model_grid_hw'];dim=d['n_dims'];storage=4*h*w*(dim+dim*dim)+8*dim
        else:
            equal(d['embedding_channels'],384,'PatchCore embedding channels');storage=4*d['memory_bank_kept']*384
            equal(row['memory_bank_kept'],d['memory_bank_kept'],'bank kept')
        equal(row['model_tensor_bytes'],storage,'storage estimate')
        equal(row['model_storage_estimated'],True,'storage label')
        equal(row['warmup_iterations'],20,'warmup');equal(row['prediction_batch_size'],1,'batch size')
        equal(row['gpu_peak_allocated_mib'],e['gpu_peak_allocated_bytes']/1048576,'GPU allocated')
        equal(row['gpu_peak_reserved_mib'],e['gpu_peak_reserved_bytes']/1048576,'GPU reserved')
        assert 'dev plus test' in row['prediction_scope'] and 'excludes' in row['prediction_scope']
        assert 'no extraction' in row['gpu_memory_scope'] and 'excludes Python metadata' in row['storage_scope']

    # CSV numbers must round-trip to the exact JSON double, not display rounding.
    csv_cells=0
    for name, values in tables.items():
        with extended(args.analysis/'tables'/(name+'.csv')).open(encoding='utf-8',newline='') as stream:
            rows=list(csv.DictReader(stream))
        equal(len(rows),len(values),'CSV count '+name)
        for i,(actual,expected) in enumerate(zip(rows,values)):
            equal(set(actual),set(expected),'CSV columns '+name)
            for key,value in expected.items():
                cell=actual[key];csv_cells+=1
                where=f'CSV {name}/{i}/{key}'
                if value is None: equal(cell,'null',where)
                elif isinstance(value,bool): equal(cell,str(value),where)
                elif isinstance(value,float):
                    assert float(cell)==value,(where,cell,value)
                elif isinstance(value,int): equal(int(cell),value,where)
                elif isinstance(value,(dict,list)): equal(json.loads(cell),value,where)
                else: equal(cell,value,where)

    summary={
      'status':'passed','job_id':'44284','analysis_identity':args.analysis.name,
      'analysis_directory':str(args.analysis),'scope':'Independent standard-library arithmetic over accepted step 7 metrics/evidence/samples; no arrays, images, models or production aggregate imports.',
      'accepted_stages':len(accepted),'result_metadata_sets':len(records),'source_metadata_files_sha256_checked':198,
      'baseline_fits':36,'baseline_category_count':6,'baseline_seed_count':3,'baseline_rule_count':5,
      'checkpoint_source_rows':108,'checkpoint_duplicate_rows':18,'checkpoint_unique_rows':90,
      'sampling_categories':['cable','screw'],'sampling_seeds':seeds,
      'loco_fits':4,'loco_formal_group_rows':40,'loco_pooled_auxiliary_rows':20,
      'resource_rows':66,'resource_prediction_denominator':'len(dev)+len(test)',
      'storage_formula_padim':'4*H*W*(d+d*d)+8*d','storage_formula_patchcore':'4*memory_bank_kept*384',
      'comparison_assertions':checked,'csv_cells_roundtripped':csv_cells,'maximum_independent_absolute_error':maximum_error,
      'baseline_summary':tables['baseline_summary'],'paired_improvement_summary':tables['paired_improvement_summary'],
      'sampling_summary':tables['sampling_summary'],'material_issues':[],
      'limitations':['Raw original-resolution pixel metrics were previously accepted remotely and are referenced; this audit does not recompute pixels.','Timing is cached model computation over dev plus test, not end-to-end inference or isolated rule overhead.','LOCO and exploratory single-seed ablations do not estimate seed standard deviations.']}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    extended(args.output).write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({key:summary[key] for key in ['status','result_metadata_sets','comparison_assertions','csv_cells_roundtripped','maximum_independent_absolute_error']}))


if __name__=='__main__':
    main()
