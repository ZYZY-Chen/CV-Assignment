"""Read-only PDF font/collision audit with an explicit pdfplumber adapter.

The unmodified Nature Figure geometry core is reused. PDF extraction differs
from its standard PyMuPDF extractor, so this is supplemental collision evidence,
not a claim that the standard collision command passed.
"""
import argparse
import collections
import dataclasses
import hashlib
import importlib.util
import json
import pathlib
import sys

import pdfplumber


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec)
    sys.modules[name]=value
    spec.loader.exec_module(value)
    return value


def ext(path):
    value=str(path.resolve())
    return pathlib.Path(value if value.startswith('\\\\?\\') else '\\\\?\\'+value)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--figures',required=True,type=pathlib.Path)
    parser.add_argument('--skill-scripts',required=True,type=pathlib.Path)
    parser.add_argument('--output',required=True,type=pathlib.Path)
    args=parser.parse_args()
    core=load(args.skill_scripts/'audit_figure_collisions.py','figure_collision_geometry')
    font=load(args.skill_scripts/'audit_pdf_text.py','figure_font_audit')
    output={
        'status':'supplemental_read_only_audit',
        'extractor':'pdfplumber '+pdfplumber.__version__,
        'standard_collision_extractor':'unavailable: neither pymupdf nor fitz is installed; no installation attempted',
        'geometry_core':str(args.skill_scripts/'audit_figure_collisions.py'),
        'geometry_core_sha256':hashlib.sha256((args.skill_scripts/'audit_figure_collisions.py').read_bytes()).hexdigest().upper(),
        'limitations':['Uses word boxes rather than PyMuPDF text-trace line boxes. Word extraction uses PDF text-flow order, so overlap findings require rendered inspection.','Only paths expressible as PDF line/cubic segments are tested. The original standard collision CLI was not passed.','No figure is modified, re-rendered or exported by this audit.'],
        'figures':{}}
    for file in sorted(ext(args.figures).glob('*.pdf')):
        geometry=[];raw_pages=[]
        with pdfplumber.open(file) as document:
            for page_index,page in enumerate(document.pages,1):
                g=core.PageGeometry(page=page_index,bbox=(0.0,0.0,float(page.width),float(page.height)))
                words=page.extract_words(x_tolerance=1,y_tolerance=1,use_text_flow=True,keep_blank_chars=False,extra_attrs=['fontname','size'])
                for index,w in enumerate(words):
                    box=(w['x0'],w['top'],w['x1'],w['bottom'])
                    g.texts.append(core.TextBox(index=index,text=w['text'],bbox=box))
                    g.traces.append(core.TraceBox(index=index,text=w['text'],bbox=box))
                shapes=page.lines+page.curves+page.rects
                for index,shape in enumerate(shapes):
                    bbox=(shape['x0'],shape['top'],shape['x1'],shape['bottom'])
                    segments=[];last=None;start=None
                    for operation in shape.get('path',[]):
                        code=operation[0]
                        if code=='m': last=operation[1];start=last
                        elif code=='l' and last is not None:
                            segments.append((last,operation[1]));last=operation[1]
                        elif code=='c' and last is not None:
                            segments.extend(core.cubic_segments([last,*operation[1:4]]));last=operation[3]
                        elif code=='h' and last is not None and start is not None:
                            segments.append((last,start));last=start
                    if shape.get('stroke') and segments:
                        g.strokes.append(core.StrokePath(index=index,bbox=bbox,width=shape.get('linewidth') or 0,segments=tuple(segments)))
                    if shape.get('fill'):
                        g.fills.append(core.FilledRegion(index=index,bbox=bbox,source='fill'))
                for index,image in enumerate(page.images):
                    g.images.append(core.FilledRegion(index=index,bbox=(image['x0'],image['top'],image['x1'],image['bottom']),source='image'))
                geometry.append(g)
                raw_pages.append({'page':page_index,'width_pt':page.width,'height_pt':page.height,
                  'words':[{'text':w['text'],'bbox':[w['x0'],w['top'],w['x1'],w['bottom']],'fontname':w['fontname'],'size_pt':w['size']} for w in words],
                  'stroke_paths':[dataclasses.asdict(x) for x in g.strokes],
                  'filled_regions':[dataclasses.asdict(x) for x in g.fills]})
        result=core.audit_geometries(geometry)
        output['figures'][file.name]={
            'sha256':hashlib.sha256(file.read_bytes()).hexdigest().upper(),
            'font_7pt_contract':font.audit_pdf(file.read_bytes(),minimum_pt=7),
            'font_5pt_skill_floor':font.audit_pdf(file.read_bytes(),minimum_pt=5),
            'supplemental_collision_audit':result,
            'raw_geometry':raw_pages}
    args.output.parent.mkdir(exist_ok=True,parents=True)
    ext(args.output).write_text(json.dumps(output,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    for name,figure in output['figures'].items():
        result=figure['supplemental_collision_audit']
        findings=result.get('findings',[])
        print(name,'min_font',figure['font_7pt_contract']['minimum_found_pt'],'verdict',result['verdict'],collections.Counter(f['kind'] for f in findings))
        for f in findings:
            if f['kind'] in ['text-text','text-stroke','text-page-clipping']:
                print('  ',f['kind'],repr(f['text']),repr(f.get('other_text')),f['text_bbox'],f.get('other_bbox'))


if __name__=='__main__':main()
