"""Render the measured cases as a plain, script-free article."""
import html
import json
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent


def href(value):
    if urlsplit(value).scheme not in ("", "http", "https"):
        raise ValueError("unsupported link scheme")
    return html.escape(value, quote=True)


def render(report, path, asset_prefix=None):
    articles = json.loads((ROOT / "articles.json").read_text())
    prefix = report.get("asset_prefix", "") if asset_prefix is None else asset_prefix
    items = []
    toc = []
    for index, demo in enumerate(report["demos"], 1):
        article = articles[demo["id"]]
        title = str(index) + ". " + article["title"]
        identity = html.escape(demo["id"], quote=True)
        toc.append('<li><a href="#' + identity + '">' + html.escape(article["title"]) + '</a></li>')
        items.append('<article id="' + identity + '"><h2>' + html.escape(title) + '</h2>')
        items.extend("<p>" + html.escape(paragraph) + "</p>" for paragraph in article["paragraphs"])
        if article.get("links"):
            items.append('<p class="meta">' + " · ".join('<a href="' + href(link["url"]) + '">' +
                          html.escape(link["label"]) + "</a>" for link in article["links"]) + "</p>")
        rows = demo["raw"]["cases"] if demo["id"] == "execution" else demo["cases"]
        if demo["id"] == "execution":
            items.append('<p class="meta">The caller’s acceptance or rejection concerns the response, not whether the attack succeeded. Read it alongside the observed effect and displayed output. A rejected response can follow an unauthorized effect; an accepted response can contain an inline forgery that the caller ignored.</p>')
        items.append("<details class=\"cases\"><summary>Inspect the " + str(len(rows)) + " measured cases</summary>")
        for row in rows:
            label = row.get("label", row.get("name", "")).replace("-", " ")
            verdict = row.get("verdict", "Caller accepted response" if row.get("accepted") else "Caller rejected response")
            if demo["id"] == "execution":
                if row.get("actual_canary") is True:
                    verdict += "; canary present in observed result"
                elif row.get("actual_canary") is False:
                    verdict += "; no canary in observed result"
                else:
                    verdict += "; no worker result observed"
                if row.get("name") == "inline-output":
                    verdict += "; forged inline output ignored"
            items.append('<details class="case"><summary>' + html.escape(label + ": " + verdict) +
                         "</summary><pre>" + html.escape(json.dumps(row, indent=2)) + "</pre></details>")
        if demo["id"] == "execution":
            items.append("<details><summary>The three live handler experiments</summary><pre>" +
                         html.escape(json.dumps(demo["raw"]["os_experiment"], indent=2)) + "</pre></details>")
        items.append("</details></article>")
    content = "<nav aria-label=\"Contents\"><ol>" + "".join(toc) + "</ol></nav>" + "".join(items)
    meta = '<p><a href="' + href(prefix + "evidence.bundle") + '">Download the evidence bundle</a> · <a href="' + href(prefix + "report.json") + '">Read the raw results</a></p>'
    meta += '<p><a href="https://github.com/nishu-builder/caos-execution-integrity/blob/main/REPRODUCE.md">Rerun from Git objects</a> · <a href="https://nishu-builder.github.io/caos-execution-integrity/rerun/requests.bundle">Download complete worker objects</a></p>'
    meta += "<p>Run " + html.escape(report["run_id"]) + ". Source " + html.escape(report["source_commit"]) + ". Caos " + html.escape(report["caos_revision"]) + ".</p>"
    meta += "<p>Offline verification checks retained objects and published observations. It does not independently attest that the operator, runner, or external service was honest. See the repository for the precise limits of each experiment.</p>"
    template = (ROOT / "blog.html").read_text()
    Path(path).write_text(template.replace("<!--CONTENT-->", content).replace("<!--META-->", meta))
