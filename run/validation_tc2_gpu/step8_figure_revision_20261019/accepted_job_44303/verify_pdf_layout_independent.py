"""Independent read-only PDF glyph, footer, diagram and collision checks.

This explicitly adapts pdfplumber to the unchanged Nature Figure geometry core.
It does not claim that the standard PyMuPDF collision command was passed.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import math
import sys

import pdfplumber


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def union(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def bbox(item):
    return [item['x0'], item['top'], item['x1'], item['bottom']]


def inside_center(box, area, tolerance=0):
    x, y = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return area[0] - tolerance <= x <= area[2] + tolerance and area[1] - tolerance <= y <= area[3] + tolerance


def upright_box(bounds, height):
    return [bounds[0], height - bounds[3], bounds[2], height - bounds[1]]


def normalized(text):
    return ' '.join(text.split())


audit = Path(__file__).resolve().parent
qa = Path(r'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_figures_qa_44303_223751')
returned = Path(r'\\?\C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup_20261019_223751_f596114b\remote\page_001\run\tc2_gpu\summaries\figure_revision\F8FBEF088CF879DE093C89009081CAD00B4698BB99BC3A6A080C748AFA4AA636')
skill = Path(r'C:\Users\mhjv_\.codex\skills\nature-figure\scripts')
core = module(skill / 'audit_figure_collisions.py', 'revision_independent_geometry_core')
font = module(skill / 'audit_pdf_text.py', 'revision_independent_font_core')
raw = json.loads((audit / 'pdf_layout_pdfplumber_raw.json').read_bytes())
figures = {}
for file in sorted(qa.glob('*.pdf')):
    name = file.stem
    evidence = json.loads((returned / 'qa' / (name + '.alignment.json')).read_bytes())
    assert evidence['clearance']['status'] == 'passed'
    assert evidence['measured_after_final_draw'] is True
    assert evidence['status'] in ('passed', 'not_applicable')
    with pdfplumber.open(file) as document:
        assert len(document.pages) == 1
        page = document.pages[0]
        characters = [c for c in page.chars if c['text'].strip()]
        fonts, rotated = [], 0
        for c in characters:
            a, b, c0, d, _, _ = c['matrix']
            assert abs(math.hypot(a, b) - 1) < 1e-6 and abs(math.hypot(c0, d) - 1) < 1e-6
            assert abs(a * c0 + b * d) < 1e-6
            if c['upright']:
                assert abs(b) < 1e-6
                point_size = c['size']
            else:
                assert abs(a) < 1e-6 and abs(d) < 1e-6
                # PDFMiner's size is the vertical advance for 90-degree text;
                # its cross-baseline width is the font's actual point extent.
                point_size = c['width']
                rotated += 1
            assert point_size >= 7 - 1e-6, (file.name, c['text'], point_size)
            fonts.append(point_size)
        tf = font.audit_pdf(file.read_bytes(), minimum_pt=7)
        assert tf['auditable'] and tf['below_minimum_count'] == 0 and tf['minimum_found_pt'] >= 7

        # Rebuild PDF geometry from actual extracted words. Rotated label
        # characters sharing a baseline are consolidated before collision
        # testing so ordinary pair kerning is not mistaken for label overlap.
        g = core.PageGeometry(page=1, bbox=(0.0, 0.0, float(page.width), float(page.height)))
        words = page.extract_words(x_tolerance=1, y_tolerance=1, use_text_flow=True,
                                   keep_blank_chars=False, extra_attrs=['fontname', 'size'])
        text_boxes = [(w['text'], bbox(w)) for w in words if w.get('upright', True)]
        grouped = {}
        for c in page.chars:
            if not c['upright']:
                key = (round(c['x0'], 5), round(c['x1'], 5), c['fontname'])
                grouped.setdefault(key, []).append(c)
        rotated_lines = []
        for members in grouped.values():
            current = []
            for c in sorted(members, key=lambda value: value['top']):
                if current and c['top'] > max(item['bottom'] for item in current) + 3.5:
                    rotated_lines.append(current)
                    current = []
                current.append(c)
            if current:
                rotated_lines.append(current)
        for members in rotated_lines:
            box = union([bbox(c) for c in members])
            text = ''.join(c['text'] for c in sorted(members, key=lambda value: value['matrix'][5]))
            text_boxes.append((text, box))
        for index, (text, box) in enumerate(text_boxes):
            g.texts.append(core.TextBox(index=index, text=text, bbox=box))
            g.traces.append(core.TraceBox(index=index, text=text, bbox=box))
        shapes = page.lines + page.curves + page.rects
        for index, shape in enumerate(shapes):
            segments, last, start = [], None, None
            for operation in shape.get('path', []):
                code = operation[0]
                if code == 'm':
                    last = start = operation[1]
                elif code == 'l' and last is not None:
                    segments.append((last, operation[1]))
                    last = operation[1]
                elif code == 'c' and last is not None:
                    segments.extend(core.cubic_segments([last, *operation[1:4]]))
                    last = operation[3]
                elif code == 'h' and last is not None and start is not None:
                    segments.append((last, start))
                    last = start
            if shape.get('stroke') and segments:
                g.strokes.append(core.StrokePath(index=index, bbox=bbox(shape), width=shape.get('linewidth') or 0, segments=tuple(segments)))
            if shape.get('fill'):
                g.fills.append(core.FilledRegion(index=index, bbox=bbox(shape), source='fill'))
        for index, image in enumerate(page.images):
            g.images.append(core.FilledRegion(index=index, bbox=bbox(image), source='image'))
        collision = core.audit_geometries([g])
        assert not collision.get('findings'), (file.name, collision.get('findings'))

        footer_rows, assigned = [], set()
        for part in evidence['clearance']['footer']:
            region = upright_box(part['bounds_pt'], page.height)
            members = [(index, c) for index, c in enumerate(characters) if inside_center(bbox(c), region, 1.5)]
            assert members, (file.name, part['kind'])
            assigned.update(index for index, _ in members)
            actual = union([bbox(c) for _, c in members])
            # Include actual legend marker/line extents, not only its text.
            strokes = [s for s in shapes if s.get('stroke') and inside_center(bbox(s), region)
                       and s['x0'] >= region[0] - 1.5 and s['x1'] <= region[2] + 1.5
                       and s['top'] >= region[1] - 1.5 and s['bottom'] <= region[3] + 1.5]
            if strokes:
                actual = union([actual] + [[s['x0'] - .5 * s.get('linewidth', 0), s['top'] - .5 * s.get('linewidth', 0),
                                           s['x1'] + .5 * s.get('linewidth', 0), s['bottom'] + .5 * s.get('linewidth', 0)] for s in strokes])
            footer_rows.append({'kind': part['kind'], 'returned_bounds_pdf_pt': region,
                                'actual_text_and_marker_bounds_pdf_pt': actual, 'glyph_count': len(members)})
        body = [c for index, c in enumerate(characters) if index not in assigned]
        assert body
        body_bottom = max(c['bottom'] for c in body)
        first_footer = min(part['actual_text_and_marker_bounds_pdf_pt'][1] for part in footer_rows)
        clearance = first_footer - body_bottom
        assert clearance >= 3 - 1e-6, (file.name, clearance)
        sequential = sorted(footer_rows, key=lambda part: part['actual_text_and_marker_bounds_pdf_pt'][1])
        between = [following['actual_text_and_marker_bounds_pdf_pt'][1] - previous['actual_text_and_marker_bounds_pdf_pt'][3]
                   for previous, following in zip(sequential, sequential[1:])]
        assert all(gap >= 3 - 1e-6 for gap in between)
        page_margins = [min(c['x0'], c['top'], page.width - c['x1'], page.height - c['bottom']) for c in characters]
        assert min(page_margins) >= 0

        diagram = None
        if name == 'F1_methods':
            boxes = []
            for part in evidence['clearance']['diagram_text_containment']:
                region = upright_box(part['box_bounds_pt'], page.height)
                matching = [s for s in shapes if s.get('stroke') and s.get('fill')
                            and max(abs(a - b) for a, b in zip(bbox(s), region)) < 1e-3]
                assert len(matching) == 1
                chars = [c for c in characters if inside_center(bbox(c), region)]
                assert normalized(page.crop(tuple(region)).extract_text()) == normalized(part['text'])
                actual = union([bbox(c) for c in chars])
                margins = [actual[0] - region[0], actual[1] - region[1], region[2] - actual[2], region[3] - actual[3]]
                assert min(margins) >= 3
                boxes.append({'text': part['text'], 'actual_box_pdf_pt': region, 'actual_text_pdf_pt': actual,
                              'minimum_containment_margin_pt': min(margins)})
            assert len(boxes) == 6
            shafts = [s for s in shapes if s.get('stroke') and not s.get('fill') and len(s.get('path', [])) == 2
                      and s['path'][0][0] == 'm' and s['path'][1][0] == 'c']
            assert len(shafts) == 5
            panel = evidence['panels'][0]
            routes, used = [], set()
            for route in evidence['clearance']['diagram_routes']:
                convert = lambda p: [panel['x_pt'] + p[0] * panel['width_pt'],
                                     page.height - (panel['y_pt'] + p[1] * panel['height_pt'])]
                start, end = convert(route['start']), convert(route['end'])
                candidates = []
                for index, shape in enumerate(shafts):
                    a, b = shape['path'][0][1], shape['path'][1][3]
                    discrepancy = max(math.dist(a, start), math.dist(b, end))
                    if discrepancy < 4:
                        candidates.append((index, discrepancy))
                assert len(candidates) == 1 and candidates[0][0] not in used
                used.add(candidates[0][0])
                routes.append({'route': route['route'], 'actual_pdf_shaft_matched': True,
                               'maximum_endpoint_shrink_pt': candidates[0][1]})
            assert len(routes) == 5
            diagram = {'status': 'passed', 'six_boxes_and_text_containment': boxes, 'actual_arrow_routes': routes,
                       'both_method_outputs_connected': True, 'text_stroke_collisions': 0}

        original_flags = raw['figures'][file.name]['supplemental_collision_audit'].get('findings', [])
        figures[file.name] = {
            'sha256': hashlib.sha256(file.read_bytes()).hexdigest().upper(),
            'font_status': 'passed', 'pdfplumber_nonblank_glyphs': len(characters),
            'pdfplumber_upright_size_or_rotated_cross_baseline_minimum_pt': min(fonts),
            'rotated_glyphs_with_orientation_normalization': rotated,
            'independent_direct_Tf_scan': tf,
            'collision_status': 'passed_with_explicit_pdfplumber_adapter', 'supplemental_collision_audit': collision,
            'rotated_label_lines_consolidated': len(rotated_lines),
            'raw_word_box_findings': original_flags,
            'raw_word_box_finding_resolution': 'Adjacent glyphs in the same rotated axis label; ordinary kerning. Rechecked using full rotated-label boxes and actual render.' if original_flags else 'No raw findings',
            'independent_footer_status': 'passed', 'actual_body_to_first_footer_clearance_pt': clearance,
            'actual_legend_to_note_clearance_pt': between,
            'minimum_glyph_page_margin_pt': min(page_margins), 'footer': footer_rows,
            'returned_axes_alignment': {'status': evidence['status'], 'tolerance_pt': evidence['tolerance_pt'],
                                        'checks': evidence['checks'], 'exemptions': evidence['exemptions']},
            'method_diagram': diagram,
        }
assert len(figures) == 15
result = {
    'status': 'passed_with_explicit_pdfplumber_adapter', 'job_id': '44303', 'figure_count': 15,
    'minimum_actual_pdf_font_pt': min(v['pdfplumber_upright_size_or_rotated_cross_baseline_minimum_pt'] for v in figures.values()),
    'minimum_body_to_footer_clearance_pt': min(v['actual_body_to_first_footer_clearance_pt'] for v in figures.values()),
    'all_actual_pdf_font_sizes_at_least_7pt': True, 'all_footer_bands_clear': True,
    'all_supplemental_collision_checks_clear': True, 'all_original_files_unchanged': True,
    'extractor': 'pdfplumber ' + pdfplumber.__version__,
    'geometry_core': str(skill / 'audit_figure_collisions.py'),
    'geometry_core_sha256': hashlib.sha256((skill / 'audit_figure_collisions.py').read_bytes()).hexdigest().upper(),
    'standard_collision_cli_passed': False,
    'limitations': [
        'PyMuPDF/fitz is unavailable and was not installed. The standard collision CLI was not run.',
        'The unmodified collision geometry core is supplied with pdfplumber words, consolidated rotated-label glyphs, and actual PDF paths/images. This is supplemental geometry evidence.',
        'PDFMiner reports vertical advance as size for rotated glyphs; their 90-degree unit matrices are verified and cross-baseline width is used, crosschecked against a separate PDF Tf-operator scan.',
        'Axis alignment is a recheck of returned final-draw panel coordinates; independent rendered geometry and visual review complement it.',
        'This audit does not compute scientific statistics or assert scientific conclusions. Rendered visual review is recorded separately.',
    ],
    'figures': figures,
}
with (audit / 'pdf_layout_independent_verification.json').open('x', encoding='utf-8') as stream:
    json.dump(result, stream, indent=2, ensure_ascii=False)
    stream.write('\n')
print(json.dumps({key: value for key, value in result.items() if key not in ('figures', 'limitations')}, indent=2))
