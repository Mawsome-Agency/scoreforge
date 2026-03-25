"""Generate visual HTML comparison reports for ScoreForge runs."""
import base64
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


def generate_report(
    original_image_path: str,
    iterations: list[dict],
    output_path: str,
    title: str = "ScoreForge Conversion Report",
) -> str:
    """Generate a self-contained HTML report with visual comparisons.

    Each iteration dict should contain:
        - musicxml: str (the MusicXML content)
        - match_score: int or None
        - pixel_diff_pct: float or None
        - differences: list[dict] (from comparator)
        - note_count: int or None
        - measure_count: int or None
    """
    # Encode original image
    with open(original_image_path, "rb") as f:
        img_data = base64.b64encode(f.read()).decode()

    suffix = Path(original_image_path).suffix.lower().lstrip(".")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(suffix, "image/png")
    original_data_url = f"data:{mime};base64,{img_data}"

    report = {
        "source": "scoreforge",
        "title": title,
        "timestamp": datetime.utcnow().isoformat(),
        "original_image": original_data_url,
        "original_path": str(original_image_path),
        "iterations": iterations,
    }

    # Also save JSON for the web viewer
    json_path = str(Path(output_path).with_suffix(".json"))
    with open(json_path, "w") as f:
        json.dump(report, f)

    # Generate self-contained HTML
    html = _build_html(report)
    with open(output_path, "w") as f:
        f.write(html)

    return output_path


def _build_html(report: dict) -> str:
    """Build a self-contained HTML report."""
    report_json = json.dumps(report)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{report.get('title', 'ScoreForge Report')}</title>
<script src="https://www.verovio.org/javascript/develop/verovio-toolkit-wasm.js" defer></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0f0f0f; color: #e0e0e0;
}}
.report-header {{
    background: #1a1a2e; padding: 20px 24px;
    border-bottom: 2px solid #e94560;
}}
.report-header h1 {{ font-size: 22px; color: #e94560; margin-bottom: 4px; }}
.report-header .meta {{ font-size: 13px; color: #888; }}
.iteration-section {{
    border: 1px solid #222; margin: 16px;
    border-radius: 8px; overflow: hidden;
}}
.iteration-header {{
    background: #16213e; padding: 12px 16px;
    display: flex; align-items: center; justify-content: space-between;
    cursor: pointer;
}}
.iteration-header h2 {{ font-size: 16px; }}
.iteration-header .score {{
    padding: 4px 12px; border-radius: 12px;
    font-weight: 700; font-size: 14px;
}}
.score.low {{ background: #ef444433; color: #ef4444; }}
.score.mid {{ background: #f59e0b33; color: #f59e0b; }}
.score.high {{ background: #4ade8033; color: #4ade80; }}
.comparison {{
    display: flex; min-height: 400px;
}}
.side {{
    flex: 1; padding: 12px; display: flex;
    flex-direction: column; align-items: center;
}}
.side + .side {{ border-left: 1px solid #222; }}
.side-label {{
    font-size: 12px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.5px;
    margin-bottom: 8px; color: #888;
}}
.side img {{ max-width: 100%; border-radius: 4px; }}
.verovio-render {{
    background: #fff; border-radius: 4px;
    padding: 8px; width: 100%;
}}
.verovio-render svg {{ width: 100%; height: auto; }}
.diff-summary {{
    padding: 12px 16px; background: #111;
    border-top: 1px solid #222;
    display: flex; gap: 20px; flex-wrap: wrap;
    font-size: 13px;
}}
.diff-summary .label {{ color: #888; }}
.diff-summary .val {{ font-weight: 700; }}
.diff-list {{
    padding: 12px 16px; border-top: 1px solid #222;
}}
.diff-item {{
    background: #1a1a2e; border-radius: 4px;
    padding: 8px 12px; margin-bottom: 6px;
    border-left: 3px solid #333; font-size: 13px;
}}
.diff-item.critical {{ border-left-color: #ef4444; }}
.diff-item.major {{ border-left-color: #f59e0b; }}
.diff-item.minor {{ border-left-color: #3b82f6; }}
</style>
</head>
<body>
<div class="report-header">
    <h1>{report.get('title', 'ScoreForge Report')}</h1>
    <div class="meta">
        Generated: {report.get('timestamp', 'unknown')} |
        Source: {report.get('original_path', 'unknown')} |
        Iterations: {len(report.get('iterations', []))}
    </div>
</div>
<div id="iterations"></div>
<script>
const REPORT = {report_json};

document.addEventListener('DOMContentLoaded', async () => {{
    let vrvToolkit = null;
    try {{
        const VerovioModule = await verovio.module;
        vrvToolkit = new verovio.toolkit();
        vrvToolkit.setOptions({{
            scale: 35, pageWidth: 2200, pageHeight: 3000,
            adjustPageHeight: true, breaks: 'auto',
        }});
    }} catch (e) {{ console.error('Verovio init failed:', e); }}

    const container = document.getElementById('iterations');
    REPORT.iterations.forEach((iter, i) => {{
        const section = document.createElement('div');
        section.className = 'iteration-section';

        const score = iter.match_score;
        const scoreClass = score >= 90 ? 'high' : score >= 60 ? 'mid' : 'low';
        const scoreText = score !== null ? score + '/100' : 'N/A';

        let svgContent = '<p style="color:#999;padding:20px;">Loading Verovio...</p>';
        if (vrvToolkit && iter.musicxml) {{
            try {{
                vrvToolkit.loadData(iter.musicxml);
                svgContent = vrvToolkit.renderToSVG(1);
            }} catch (e) {{
                svgContent = '<p style="color:#ef4444;padding:20px;">Render error: ' + e.message + '</p>';
            }}
        }}

        let diffHtml = '';
        if (iter.differences && iter.differences.length > 0) {{
            diffHtml = '<div class="diff-list">';
            iter.differences.forEach(d => {{
                diffHtml += '<div class="diff-item ' + (d.severity || 'minor') + '">' +
                    '<strong>' + (d.severity || 'info') + '</strong> ' +
                    (d.measure ? '[M' + d.measure + '] ' : '') +
                    (d.description || d.type || '') + '</div>';
            }});
            diffHtml += '</div>';
        }}

        section.innerHTML = `
            <div class="iteration-header">
                <h2>Iteration ${{i + 1}}</h2>
                <span class="score ${{scoreClass}}">${{scoreText}}</span>
            </div>
            <div class="comparison">
                <div class="side">
                    <div class="side-label">Original Sheet Music</div>
                    <img src="${{REPORT.original_image}}" alt="Original">
                </div>
                <div class="side">
                    <div class="side-label">MusicXML Render (Verovio)</div>
                    <div class="verovio-render" id="vrv-${{i}}">${{svgContent}}</div>
                </div>
            </div>
            <div class="diff-summary">
                <div><span class="label">Match Score:</span> <span class="val">${{scoreText}}</span></div>
                <div><span class="label">Pixel Diff:</span> <span class="val">${{iter.pixel_diff_pct !== null ? iter.pixel_diff_pct + '%' : 'N/A'}}</span></div>
                <div><span class="label">Notes:</span> <span class="val">${{iter.note_count || 'N/A'}}</span></div>
                <div><span class="label">Measures:</span> <span class="val">${{iter.measure_count || 'N/A'}}</span></div>
                <div><span class="label">Differences:</span> <span class="val">${{iter.differences ? iter.differences.length : 0}}</span></div>
            </div>
            ${{diffHtml}}
        `;
        container.appendChild(section);
    }});
}});
</script>
</body>
</html>"""
