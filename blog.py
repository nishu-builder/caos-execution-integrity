"""Render METR problems and CAOS approaches, with optional recorded examples."""
import html
import json
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent


def href(value):
    if urlsplit(value).scheme not in ("", "http", "https"):
        raise ValueError("unsupported link scheme")
    return html.escape(value, quote=True)


def prose(value):
    # Only inline code is formatted; every piece remains HTML-escaped.
    return "".join("<code>" + html.escape(part) + "</code>" if i % 2
                   else html.escape(part) for i, part in enumerate(value.split("`")))


def render(report, path, asset_prefix=None, include_evidence=False):
    articles = json.loads((ROOT / "articles.json").read_text())
    prefix = report.get("asset_prefix", "") if asset_prefix is None else asset_prefix
    # Validate even when this presentation doesn't expose the evidence links.
    href(prefix + "report.json")
    items, toc = [], []
    for index, demo in enumerate(report["demos"], 1):
        article = articles[demo["id"]]
        title = str(index) + ". " + article["title"]
        identity = html.escape(demo["id"], quote=True)
        toc.append('<li><a href="#' + identity + '">' + html.escape(article["title"]) + '</a></li>')
        items.append('<article id="' + identity + '"><h2>' + html.escape(title) + '</h2>')
        items.append("<h3>Problem</h3>")
        items.extend("<p>" + prose(p) + "</p>" for p in article["problem"])
        items.append('<p class="meta">' + " · ".join(
            '<a href="' + href(link["url"]) + '">' + html.escape(link["label"]) + "</a>"
            for link in article["sources"]) + "</p>")
        items.append("<h3>CAOS</h3>")
        items.extend("<p>" + prose(p) + "</p>" for p in article["caos"])
        if include_evidence:
            rows = demo["raw"]["cases"] if demo["id"] == "execution" else demo["cases"]
            items.append('<details class="cases"><summary>Related implementation: ' + str(len(rows)) + ' recorded cases</summary>')
            for row in rows:
                label = row.get("label", row.get("name", "")).replace("-", " ")
                verdict = row.get("verdict", "Caller accepted response" if row.get("accepted") else "Caller rejected response")
                items.append('<details class="case"><summary>' + html.escape(label + ": " + verdict) +
                             "</summary><pre>" + html.escape(json.dumps(row, indent=2)) + "</pre></details>")
            items.append("</details>")
        items.append("</article>")
    content = '<nav aria-label="Contents"><ol>' + "".join(toc) + "</ol></nav>" + "".join(items)
    meta = '<p><a href="https://github.com/nishu-builder/caos-execution-integrity">Repository</a> · <a href="https://github.com/nishu-builder/caos-execution-integrity/blob/main/NOTES.md">Markdown version</a></p>'
    if include_evidence:
        meta += '<p><a href="' + href(prefix + "evidence.bundle") + '">Recorded objects</a> · <a href="' + href(prefix + "report.json") + '">Raw results</a></p>'
    template = (ROOT / "blog.html").read_text()
    Path(path).write_text(template.replace("<!--CONTENT-->", content).replace("<!--META-->", meta))


def markdown():
    articles = json.loads((ROOT / "articles.json").read_text())
    parts = ["# CAOS and the METR incident", "",
             "CAOS represents tools, inputs, and results as Git objects. Each section starts with something agents did in the METR incident, then describes how that representation could support a different approach.", ""]
    for index, article in enumerate(articles.values(), 1):
        parts += ["## " + str(index) + ". " + article["title"], "", "### Problem", ""]
        for paragraph in article["problem"]:
            parts += [paragraph, ""]
        parts += [" · ".join("[" + l["label"] + "](" + l["url"] + ")" for l in article["sources"]), "", "### CAOS", ""]
        for paragraph in article["caos"]:
            parts += [paragraph, ""]
    parts += ["## Related runnable examples", "",
              "The repository includes 32 worker jobs for exploring these mechanisms. [Reproduction guide](REPRODUCE.md).", "",
              "```sh", "python3 reproduce.py run --server http://localhost:9090", "```", ""]
    return "\n".join(parts)
