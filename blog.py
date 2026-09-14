"""Render the three core arguments and optional recorded experiment evidence."""
import html
import json
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
INTRO = "CAOS represents programs, inputs, and results as Git objects. That makes three different checks possible: repeat work on another runner, inspect the code behind a name, and detect changes or gaps in a saved history. The METR investigation supplies concrete examples of why each matters."


def href(value):
    if urlsplit(value).scheme not in ("", "http", "https"):
        raise ValueError("unsupported link scheme")
    return html.escape(value, quote=True)


def prose(value):
    # Only inline code is formatted; every piece remains HTML-escaped.
    return "".join("<code>" + html.escape(part) + "</code>" if i % 2
                   else html.escape(part) for i, part in enumerate(value.split("`")))


def render_evidence(report):
    items = ['<section id="experiments"><h2>Recorded experiments</h2>']
    for demo in report["demos"]:
        rows = demo["raw"]["cases"] if demo["id"] == "execution" else demo["cases"]
        identity = html.escape(demo["id"], quote=True)
        title = demo.get("title", demo["id"])
        items.append('<details class="cases" id="evidence-' + identity + '"><summary>' +
                     html.escape(title) + ": " + str(len(rows)) + " recorded cases</summary>")
        for row in rows:
            label = row.get("label", row.get("name", "")).replace("-", " ")
            verdict = row.get("verdict", "Caller accepted response" if row.get("accepted") else "Caller rejected response")
            items.append('<details class="case"><summary>' + html.escape(label + ": " + verdict) +
                         "</summary><pre>" + html.escape(json.dumps(row, indent=2)) + "</pre></details>")
        items.append("</details>")
    items.append("</section>")
    return "".join(items)


def render(report, path, asset_prefix=None, include_evidence=False):
    articles = json.loads((ROOT / "articles.json").read_text())
    prefix = report.get("asset_prefix", "") if asset_prefix is None else asset_prefix
    # Validate even when this presentation doesn't expose the evidence links.
    href(prefix + "report.json")
    items, toc = [], []
    # The article's structure is independent of the experiments in a run.
    for index, (key, article) in enumerate(articles.items(), 1):
        title = str(index) + ". " + article["title"]
        identity = html.escape(key, quote=True)
        toc.append('<li><a href="#' + identity + '">' + html.escape(article["title"]) + "</a></li>")
        for alias in article.get("aliases", []):
            items.append('<span id="' + html.escape(alias, quote=True) + '"></span>')
        items.append('<article id="' + identity + '"><h2>' + html.escape(title) + "</h2>")
        items.append("<h3>Problem</h3>")
        items.extend("<p>" + prose(p) + "</p>" for p in article["problem"])
        if article.get("problem_examples"):
            items.append("<ul>" + "".join("<li>" + prose(p) + "</li>" for p in article["problem_examples"]) + "</ul>")
        items.extend("<p>" + prose(p) + "</p>" for p in article.get("problem_explanation", []))
        items.append('<p class="meta">' + " · ".join(
            '<a href="' + href(link["url"]) + '">' + html.escape(link["label"]) + "</a>"
            for link in article["sources"]) + "</p>")
        items.append("<h3>CAOS</h3>")
        items.extend("<p>" + prose(p) + "</p>" for p in article["caos"])
        items.append("</article>")
    content = '<nav aria-label="Contents"><ol>' + "".join(toc) + "</ol></nav>" + "".join(items)
    if include_evidence:
        content += render_evidence(report)
    meta = '<p><a href="https://github.com/nishu-builder/caos-execution-integrity">Repository</a> · <a href="https://github.com/nishu-builder/caos-execution-integrity/blob/main/NOTES.md">Markdown version</a></p>'
    if include_evidence:
        meta += '<p><a href="' + href(prefix + 'evidence.bundle') + '">Recorded objects</a> · <a href="' + href(prefix + 'report.json') + '">Raw results</a></p>'
    template = (ROOT / "blog.html").read_text()
    Path(path).write_text(template.replace("<!--INTRO-->", html.escape(INTRO)).replace("<!--CONTENT-->", content).replace("<!--META-->", meta))


def markdown():
    articles = json.loads((ROOT / "articles.json").read_text())
    parts = ["# CAOS and the METR incident", "", INTRO, ""]
    for index, article in enumerate(articles.values(), 1):
        parts += ["## " + str(index) + ". " + article["title"], "", "### Problem", ""]
        for paragraph in article["problem"]:
            parts += [paragraph, ""]
        for example in article.get("problem_examples", []):
            parts += ["- " + example, ""]
        for paragraph in article.get("problem_explanation", []):
            parts += [paragraph, ""]
        parts += [" · ".join("[" + l["label"] + "](" + l["url"] + ")" for l in article["sources"]), "", "### CAOS", ""]
        for paragraph in article["caos"]:
            parts += [paragraph, ""]
    parts += ["## Rerun the saved work", "",
              "The repository includes Git objects for 32 worker jobs: their tool code, input files, worker image, and recorded results. Send them to your own CAOS runner and compare what it returns. [Reproduction guide](REPRODUCE.md).", "",
              "```sh", "python3 reproduce.py run --server http://localhost:9090", "```", "",
              "The command uses fresh cache keys by default. The guide also shows how to fetch the objects with Git and submit the saved requests directly.", ""]
    return "\n".join(parts)
