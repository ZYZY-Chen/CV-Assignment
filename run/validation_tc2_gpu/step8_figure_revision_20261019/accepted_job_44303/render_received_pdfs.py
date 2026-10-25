"""Read-only Poppler rendering of all fifteen unchanged returned PDFs."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import subprocess

from PIL import Image
from pypdf import PdfReader


def extended(path):
    value = str(Path(path).resolve())
    return Path(value if value.startswith('\\\\?\\') else '\\\\?\\' + value)


audit = Path(__file__).resolve().parent
source = extended(r'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup_20261019_223751_f596114b\remote\page_001\run\tc2_gpu\summaries\figure_revision\F8FBEF088CF879DE093C89009081CAD00B4698BB99BC3A6A080C748AFA4AA636\figures')
qa = Path(r'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_figures_qa_44303_223751')
qa.mkdir(exist_ok=True)
binary = Path(r'C:\Users\mhjv_\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin')
sha = lambda data: hashlib.sha256(data).hexdigest().upper()


def render(original):
    data = original.read_bytes()
    copy = qa / original.name
    with copy.open('xb') as stream:
        stream.write(data)
    assert copy.read_bytes() == data
    reader = PdfReader(copy)
    assert not reader.is_encrypted and len(reader.pages) == 1
    info = subprocess.run([str(binary / 'pdfinfo.exe'), str(copy)], capture_output=True, text=True,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=30)
    assert info.returncode == 0, (original.name, info.stderr)
    prefix = qa / original.stem
    result = subprocess.run([str(binary / 'pdftoppm.exe'), '-png', '-singlefile', '-r', '130', str(copy), str(prefix)],
                            capture_output=True, text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=45)
    assert result.returncode == 0, (original.name, result.stderr)
    png = prefix.with_suffix('.png')
    with Image.open(png) as image:
        image.load()
        dimensions = list(image.size)
    assert original.read_bytes() == data
    return {'pdf': original.name, 'source_sha256': sha(data), 'qa_copy': str(copy), 'copy_bytes_identical': True,
            'page_count': 1, 'pdfinfo_stdout': info.stdout, 'pdfinfo_stderr': info.stderr,
            'pdftoppm_stderr': result.stderr, 'rendered_png': str(png), 'rendered_dimensions': dimensions,
            'rendered_png_sha256': sha(png.read_bytes())}


files = sorted(source.glob('*.pdf'))
assert len(files) == 15
with ThreadPoolExecutor(max_workers=3) as pool:
    rows = list(pool.map(render, files))
record = {'status': 'rendered_for_visual_review', 'job_id': '44303', 'renderer': 'bundled Poppler pdftoppm',
          'dpi': 130, 'figure_count': 15, 'all_pdfinfo_checks_passed': True, 'all_pdfs_reopened': True,
          'all_preview_pngs_reopened': True, 'all_copies_byte_identical': True, 'original_files_modified': False,
          'qa_directory': str(qa), 'figures': rows}
with (audit / 'pdf_render_verification.json').open('x', encoding='utf-8') as stream:
    json.dump(record, stream, indent=2)
    stream.write('\n')
print(json.dumps({'status': record['status'], 'figures': len(rows), 'qa_directory': str(qa)}))
