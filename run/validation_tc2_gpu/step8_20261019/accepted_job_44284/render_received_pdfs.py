"""Render unchanged returned PDFs with bundled Poppler for read-only visual QA."""
from pathlib import Path
import hashlib,json,subprocess

audit=Path(__file__).resolve().parent
report=json.loads((audit/'returned_analysis_verification.json').read_bytes())
source=Path('\\\\?\\'+str(Path(report['page_root'])/report['analysis_path']/'figures'))
qa=Path(r'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_figures_qa_44284_220347')
qa.mkdir()
binary=Path(r'C:\Users\mhjv_\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin\pdftoppm.exe')
sha=lambda data:hashlib.sha256(data).hexdigest().upper()
rows=[]
for original in sorted(source.glob('*.pdf')):
    data=original.read_bytes()
    copy=qa/original.name
    with copy.open('xb') as stream:stream.write(data)
    assert sha(copy.read_bytes())==sha(data)
    prefix=qa/original.stem
    result=subprocess.run([str(binary),'-png','-singlefile','-r','120',str(copy),str(prefix)],capture_output=True,text=True,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=45)
    assert result.returncode==0,(original.name,result.stderr)
    png=prefix.with_suffix('.png')
    assert png.is_file()
    rows.append({'pdf':original.name,'source_sha256':sha(data),'qa_copy':str(copy),'rendered_png':str(png),'rendered_png_sha256':sha(png.read_bytes()),'stderr':result.stderr})
assert len(rows)==15
record={'status':'rendered_for_visual_review','renderer':'bundled Poppler pdftoppm','dpi':120,'figure_count':15,
    'qa_directory':str(qa),'original_files_modified':False,'figures':rows}
(audit/'pdf_render_verification.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'status':record['status'],'figures':15,'qa_directory':str(qa)}))
