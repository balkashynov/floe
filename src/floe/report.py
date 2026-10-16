"""Self-contained report. Escape all notebook-controlled text."""

import html
import json


def render(result):
    def esc(value):
        return html.escape(str(value))

    rows = []
    for f in result["findings"]:
        differences = "".join(
            f"<tr><td><code>{esc(d['path'])}</code></td><td>{esc(d['reason'])}</td>"
            f"<td><pre>{esc(json.dumps(d['reference'], indent=2))}</pre></td>"
            f"<td><pre>{esc(json.dumps(d['candidate'], indent=2))}</pre></td></tr>"
            for d in f.get("differences", [])
        )
        rows.append(
            f"<article><div class='status {esc(f['status'])}'>{esc(f['status'])}</div>"
            f"<h2>{esc(f['name'])}</h2><p>After cell <code>{esc(f['cell'])}</code>, "
            f"observe <code>{esc(f['variable'])}</code>.</p><p>{esc(f['reason'])}</p>"
            f"<p>{f.get('difference_count', 0)} differences; showing at most 12.</p>"
            f"<div class='scroll'><table><thead><tr><th>Path</th><th>Change</th><th>Reference</th><th>Candidate</th></tr></thead>"
            f"<tbody>{differences}</tbody></table></div><details><summary>Policy and observations</summary>"
            f"<pre>{esc(json.dumps(f, indent=2))}</pre></details></article>"
        )
    evidence = esc(
        json.dumps({k: v for k, v in result.items() if k not in ("findings", "runs")}, indent=2)
    )
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(result["title"])} | Floe</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f2f5f3;color:#153a35;font:16px/1.6 system-ui,sans-serif}}main{{max-width:1100px;margin:auto;padding:48px 24px}}h1{{font-size:clamp(32px,6vw,60px);line-height:1.1}}article{{padding:24px;margin:24px 0;background:white;border:1px solid #cadad3;border-radius:12px}}.status{{display:inline-block;border-radius:4px;padding:3px 10px;background:#dfe8e3;text-transform:uppercase;font:12px monospace}}.changed{{background:#ffe4c8;color:#8a4100}}.match{{background:#d7eee1}}.inconclusive{{background:#ede7fc}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{text-align:left;border-bottom:1px solid #ddd;padding:10px;vertical-align:top}}.scroll{{overflow:auto}}details{{margin-top:20px}}code{{overflow-wrap:anywhere}}a{{color:inherit}}footer{{margin-top:40px}}</style>
<main><a href="report.json">Download full JSON evidence</a><p>FLOE / NOTEBOOK UPGRADE EVIDENCE</p><h1>{esc(result["title"])}</h1>
<p>Verdict: <strong>{esc(result["verdict"])}</strong>. {esc(result.get("scope", ""))}</p>
<p>Recorded kernel execution. This page does not execute a notebook. Values may contain your input data.</p>
{"".join(rows)}<details><summary>Provenance and execution failures</summary><pre>{evidence}</pre></details>
<footer>Fresh kernels establish repeat evidence, not deterministic behavior for all future runs. A change needs human interpretation.</footer></main></html>"""
