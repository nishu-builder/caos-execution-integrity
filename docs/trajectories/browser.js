"use strict";
const $ = (id) => document.getElementById(id);
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const icon = (name) =>
  `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const short = (oid) => (oid ? oid.slice(0, 10) : "—");
const pretty = (value) => JSON.stringify(value, null, 2);
let data,
  conversation,
  event,
  tab = "activity",
  side = "after",
  file = "",
  fileQuery = "",
  loadVersion = 0,
  liveSource = null,
  downloadURL = null;
const detectedSources = new Map();
let activeWorker = null,
  rejectWorker = null;
const objectURLs = new Map();
function clearObjects() {
  for (const url of objectURLs.values()) URL.revokeObjectURL(url);
  objectURLs.clear();
}
function cancelLoad() {
  if (activeWorker) {
    activeWorker.terminate();
    activeWorker = null;
    const reject = rejectWorker;
    rejectWorker = null;
    reject?.(Error("Loading cancelled."));
  }
}
const objectLink = (oid, compact = false) =>
  data.evidence.objects.includes(oid)
    ? `<a href="${esc(objectURLs.get(oid) || (data.object_base || "data/objects/") + oid)}" download="${esc(oid)}.git-object" title="${esc(oid)}">${esc(compact ? short(oid) : oid)}</a>`
    : esc(oid);
const code = (text) => `<pre>${esc(text)}</pre>`;
function numberedCode(text) {
  const lines = text.split("\n");
  if (lines.length > 1 && lines.at(-1) === "") lines.pop();
  return `<pre class="code-lines">${lines.map((line, i) => `<span class="code-line" data-line="${i + 1}">${esc(line)}</span>`).join("")}</pre>`;
}
function argumentsHTML(args) {
  if (args && typeof args === "object" && typeof args.content === "string") {
    const { content, ...rest } = args;
    return (
      code(pretty(rest)) + "<h3>File content supplied</h3>" + code(content)
    );
  }
  if (args && typeof args.command === "string") {
    const { command, ...rest } = args;
    return code(command) + (Object.keys(rest).length ? code(pretty(rest)) : "");
  }
  return code(pretty(args));
}
const toolRecords = (entry) => entry.records.filter((r) => r.type === "tool");
function label(entry) {
  const tools = toolRecords(entry);
  if (tools.length) return tools.map((t) => t.name).join(", ");
  if (entry.messages.length)
    return entry.messages
      .map((m) =>
        m.role === "user"
          ? "User message"
          : m.blocks.some((b) => b.type === "tool_use")
            ? "Agent requests tools"
            : "Agent response",
      )
      .join(", ");
  return (
    {
      "conversation.root": "Conversation created",
      "request.admit": "Turn queued",
      "request.claim": "Turn started",
      "request.terminal": "Turn finished",
      "subagent.terminal": "Child finished",
      "conversation.fork": "Conversation forked",
    }[entry.kind] || entry.kind
  );
}
function messageText(message) {
  return message.blocks
    .map((b) => b.text || b.thinking || b.name || "")
    .join("\n");
}
function snippet(entry) {
  const tool = toolRecords(entry)[0];
  if (tool)
    return tool.observation ? observationText(tool.observation) : tool.status;
  return (
    entry.messages.map(messageText).join("\n") ||
    entry.changes.map((c) => c.path).join(", ")
  );
}
function observationText(value) {
  if (typeof value === "string") return value;
  if (value?.content)
    return value.content.map((x) => x.text || pretty(x)).join("\n");
  return pretty(value);
}
function updateURL() {
  const u = new URL(location.href);
  for (const key of ["server", "remote", "loose", "head", "transport"])
    u.searchParams.delete(key);
  if (liveSource) {
    u.searchParams.set("remote", liveSource.source);
    if (liveSource.override !== "auto")
      u.searchParams.set("transport", liveSource.override);
    u.searchParams.set("head", liveSource.head);
  }
  for (const [k, v] of Object.entries({
    example: liveSource ? null : data.id,
    conversation: conversation.id,
    event: event.oid,
    tab,
    file: file || null,
  })) {
    if (v) u.searchParams.set(k, v);
    else u.searchParams.delete(k);
  }
  history.replaceState(null, "", u);
}
function selectConversation(id, oid) {
  conversation =
    data.conversations.find((c) => c.id === id) ||
    data.conversations.find((c) => c.id === data.root);
  event =
    conversation.events.find((e) => e.oid === oid) ||
    [...conversation.events]
      .reverse()
      .find((e) => e.changes.length && e.kind !== "conversation.root") ||
    conversation.events.at(-1);
  file = "";
  side = "after";
  $("search").value = "";
  render();
  const active = document.querySelector("#events .event.active"),
    container = document.querySelector(".timeline");
  if (active && matchMedia("(min-width:801px)").matches)
    container.scrollTop +=
      active.getBoundingClientRect().top -
      container.getBoundingClientRect().top -
      document.querySelector(".timeline-top").offsetHeight -
      8;
}
function renderConversations() {
  $("conversation-count").textContent = data.conversations.length;
  const roots = data.conversations.filter(
    (c) =>
      !c.identity.owner ||
      !data.conversations.some((x) => x.id === c.identity.owner.parent),
  );
  function node(c) {
    const children = data.conversations.filter(
      (x) => x.identity.owner?.parent === c.id,
    );
    const agentName =
      c.id === data.root
        ? "Main conversation"
        : "Child " +
          (data.conversations
            .filter((x) => x.id !== data.root)
            .findIndex((x) => x.id === c.id) +
            1);
    const toolCount = c.events.reduce(
      (n, e) => n + toolRecords(e).filter((t) => t.status !== "started").length,
      0,
    );
    return `<div><button data-conversation="${esc(c.id)}" title="${esc(c.title)}" class="${c.id === conversation.id ? "active" : ""}" aria-current="${c.id === conversation.id ? "true" : "false"}"><span class="agent-label">${icon(c.id === data.root ? "message" : "branch")}${esc(agentName)}</span><span class="agent-description">${esc(c.title)}</span><small>${toolCount} tool results</small></button>${children.length ? `<div class="child">${children.map(node).join("")}</div>` : ""}</div>`;
  }
  $("conversations").innerHTML = roots.map(node).join("");
  $("conversations")
    .querySelectorAll("button")
    .forEach(
      (b) => (b.onclick = () => selectConversation(b.dataset.conversation)),
    );
}
function visibleEvents() {
  const q = $("search").value.toLowerCase(),
    filter = $("filter").value;
  return conversation.events.filter(
    (e) =>
      (filter === "all" ||
        (filter === "changes" && e.changes.length) ||
        (filter === "activity" &&
          (e.messages.length ||
            e.records.some((r) => r.type === "tool" || r.type === "child")))) &&
      (
        label(e) +
        " " +
        snippet(e) +
        " " +
        pretty(e.changes) +
        " " +
        pretty(e.messages)
      )
        .toLowerCase()
        .includes(q),
  );
}
function renderEvents() {
  $("conversation-title").textContent = conversation.title;
  const visible = visibleEvents();
  $("event-count").textContent = visible.length;
  $("events").innerHTML = visible.length
    ? visible
        .map(
          (e) =>
            `<button role="listitem" class="event ${event.oid === e.oid ? "active" : ""}" data-event="${esc(e.oid)}"><div class="event-meta"><span>Commit ${e.ordinal + 1}</span><span>${esc(short(e.oid))}</span></div><div class="event-label">${icon(toolRecords(e).length ? "code" : e.messages.length ? "message" : "commit")}${esc(label(e))}${e.changes.length ? `<span class="badge">${e.changes.length} file${e.changes.length === 1 ? "" : "s"}</span>` : ""}</div><div class="event-snippet">${esc(snippet(e).slice(0, 280))}</div></button>`,
        )
        .join("")
    : '<p class="empty">No matching events.</p>';
  $("events")
    .querySelectorAll("button")
    .forEach(
      (b) =>
        (b.onclick = () => {
          event = conversation.events.find((e) => e.oid === b.dataset.event);
          file = "";
          side = "after";
          renderEvents();
          renderDetail();
          updateURL();
        }),
    );
}
function diffHTML(change) {
  const status = !change.before
    ? "Added"
    : !change.after
      ? "Deleted"
      : "Modified";
  let oldLine = 0,
    newLine = 0,
    added = 0,
    removed = 0,
    inHunk = false;
  const lines = (change.patch || "").split("\n");
  if (lines.at(-1) === "") lines.pop();
  const rows = lines.map((line) => {
    let old = "",
      next = "",
      kind = "";
    const hunk = line.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
    if (hunk) {
      oldLine = Number(hunk[1]);
      newLine = Number(hunk[2]);
      kind = "location";
      inHunk = true;
    } else if (!inHunk && (line.startsWith("---") || line.startsWith("+++")))
      kind = "meta";
    else if (line.startsWith("+")) {
      kind = "add";
      next = newLine++;
      added++;
    } else if (line.startsWith("-")) {
      kind = "remove";
      old = oldLine++;
      removed++;
    } else if (line.startsWith(" ")) {
      old = oldLine++;
      next = newLine++;
    }
    return `<span class="diff-line ${kind}"><span class="line-number" aria-hidden="true">${old}</span><span class="line-number" aria-hidden="true">${next}</span><span class="diff-text">${esc(line)}</span></span>`;
  });
  const body =
    change.patch === null
      ? '<p class="hint">Binary content or mode change. Open the file to inspect its recorded identity.</p>'
      : `<div class="diff-wrap"><pre class="diff">${rows.join("")}</pre></div>`;
  return `<section class="file-diff"><div class="diff-header">${icon("file")}<button data-file="${esc(change.path)}">${esc(change.path)}</button><span class="badge">${status}</span><span class="diff-stat" aria-label="${added} additions, ${removed} deletions"><span class="added">+${added}</span><span class="removed">−${removed}</span></span></div>${body}</section>`;
}
function activity() {
  let out = event.changes.length
    ? `<h3>${event.kind === "conversation.root" ? "Initial files" : "Files changed"} <span class="counter">${event.changes.length}</span></h3>${event.changes.map(diffHTML).join("")}`
    : "";
  for (const m of event.messages) {
    out += `<div class="role">${icon("message")}${esc(m.role)}${m.model ? " · " + esc(m.model) : ""}</div>`;
    for (const b of m.blocks) {
      if (b.text || b.thinking)
        out += `<div class="prose">${esc(b.text || b.thinking)}</div>`;
      else if (b.type === "tool_use")
        out += `<div class="block"><div class="block-heading">${icon("code")}<strong>${esc(b.name)}</strong></div><div class="hash">${esc(b.id)}</div>${argumentsHTML(b.resolved_arguments)}</div>`;
      else out += code(pretty(b));
    }
  }
  for (const r of event.records) {
    if (r.type === "tool") {
      const declaration = conversation.events
        .flatMap((e) => e.messages)
        .flatMap((m) => m.blocks)
        .find((b) => b.type === "tool_use" && b.id === r.id);
      out += `<div class="block"><div class="block-heading">${icon("code")}<strong>${esc(r.name)}</strong><span class="badge ${r.status === "complete" ? "complete" : ""}">${esc(r.status)}</span></div>${declaration ? argumentsHTML(declaration.resolved_arguments) : ""}${r.task ? `<p><button data-open-request>Inspect recorded compute request</button></p>` : ""}${r.observation !== null && r.observation !== undefined ? `<h3>Recorded tool output</h3>${code(observationText(r.observation))}` : ""}</div>`;
    } else if (r.type === "child") {
      const child = data.conversations.find((c) => c.id === r.id);
      out += `<div class="block"><strong>${r.status === "running" ? "Child started" : "Child finished"}</strong><p>${esc(child?.title || r.id)}</p><button data-child="${esc(r.id)}">Open child conversation</button></div>`;
    } else if (r.type === "request")
      out += `<p class="hint">Turn status: ${esc(r.status)}${r.model ? " · " + esc(r.model) : ""}</p>`;
  }
  return (
    out ||
    '<p class="empty">This commit records lifecycle metadata. Open the raw record for its details.</p>'
  );
}
function filesView() {
  const tree = side === "before" ? event.before_tree : event.tree;
  const snapshot = tree && data.snapshots[tree];
  const paths = Object.keys(snapshot?.files || {}).sort();
  if (!paths.includes(file))
    file =
      paths.find((p) => event.changes.some((c) => c.path === p)) ||
      paths[0] ||
      "";
  const info = snapshot?.files[file],
    blob = info && data.blobs[info.oid];
  const source = Object.keys(snapshot?.sources || {})
    .sort((a, b) => b.length - a.length)
    .find((p) => file.startsWith(p + "/"));
  const filtered = paths.filter((p) =>
    p.toLowerCase().includes(fileQuery.toLowerCase()),
  );
  return `<div class="file-toolbar"><label>Snapshot <select id="side"><option value="after" ${side === "after" ? "selected" : ""}>After this event</option><option value="before" ${side === "before" ? "selected" : ""}>Before this event</option></select></label><span>${paths.length} files</span></div><p class="hash">Conversation tree: ${tree ? objectLink(tree) : "No previous snapshot"}</p><div class="file-browser"><div class="file-list"><input id="file-search" aria-label="Filter filenames" placeholder="Filter files" value="${esc(fileQuery)}">${filtered.map((p) => `<button class="${p === file ? "active" : ""}" data-file="${esc(p)}">${icon("file")}<span>${esc(p)}</span></button>`).join("")}</div><div class="file-content">${info ? `<strong>${esc(file)}</strong><p class="hash">Blob: ${objectLink(info.oid)} · ${blob.size} bytes${info.mode === "120000" ? " · symlink target" : ""}</p>${source ? `<p class="hash">Source commit: ${objectLink(snapshot.sources[source])}</p>` : ""}${blob.binary ? "<p>Binary file. Download the original Git object using its hash above.</p>" : numberedCode(blob.text)}` : '<p class="empty">No files in this snapshot.</p>'}</div></div>`;
}
function requestsView() {
  const ids = [
    ...new Set(
      event.records.flatMap((r) =>
        r.type === "tool" && r.task
          ? [r.task]
          : r.type === "request"
            ? [r.id]
            : [],
      ),
    ),
  ];
  if (!ids.length)
    return '<p class="empty">No compute request is attached to this event. Select a task-start or task-completion commit.</p>';
  return ids
    .map((id) => {
      const req = data.requests[id];
      if (!req) return `<p>Request ${esc(id)} was not exported.</p>`;
      return `<h3>Recorded request</h3><p class="hash">${objectLink(id)}</p>${req.entries
        .map(
          (row) =>
            `<div class="request-row"><strong>${esc(row.name)}</strong><span class="badge">${row.mode === "40000" ? "tree" : row.mode === "160000" ? "commit" : "file"}</span><div class="hash">${objectLink(row.oid)}</div>${row.text !== undefined && row.text !== null ? code(row.text) : ""}${
              row.snapshot
                ? `<details><summary>Captured input files</summary>${Object.keys(
                    data.snapshots[row.snapshot].files,
                  )
                    .sort()
                    .map(
                      (p) =>
                        `<div class="hash">${esc(p)} · ${esc(short(data.snapshots[row.snapshot].files[p].oid))}</div>`,
                    )
                    .join("")}</details>`
                : ""
            }</div>`,
        )
        .join(
          "",
        )}<p class="hint">The request identifies the worker image by hash. Image layers are not included in this browser export. Source files and command arguments captured here are available in full.</p>`;
    })
    .join("");
}
function renderDetail() {
  const shown = visibleEvents(),
    position = shown.findIndex((e) => e.oid === event.oid);
  $("previous-event").disabled = position <= 0;
  $("next-event").disabled = position >= shown.length - 1;
  $("event-heading").innerHTML =
    `<h2>${icon("commit")}${esc(label(event))}</h2><div class="hash">${esc(event.kind)} · ${objectLink(event.oid, true)}</div>`;
  document.querySelectorAll("[data-tab]").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === tab);
    b.setAttribute("aria-pressed", b.dataset.tab === tab ? "true" : "false");
  });
  $("detail").innerHTML =
    tab === "files"
      ? filesView()
      : tab === "request"
        ? requestsView()
        : tab === "record"
          ? `<p>Parsed directly from the recorded Git commit. Download the original object using the commit hash above.</p>${code(pretty(event))}`
          : activity();
  $("detail")
    .querySelectorAll("[data-child]")
    .forEach((b) => (b.onclick = () => selectConversation(b.dataset.child)));
  $("detail")
    .querySelectorAll("[data-file]")
    .forEach(
      (b) =>
        (b.onclick = () => {
          file = b.dataset.file;
          tab = "files";
          if (!data.snapshots[event.tree].files[file]) side = "before";
          renderDetail();
          updateURL();
        }),
    );
  $("detail")
    .querySelectorAll("[data-open-request]")
    .forEach(
      (b) =>
        (b.onclick = () => {
          tab = "request";
          renderDetail();
          updateURL();
        }),
    );
  const selectedFile = $("detail").querySelector(".file-list button.active");
  const fileList = $("detail").querySelector(".file-list");
  if (selectedFile && fileList.scrollHeight > fileList.clientHeight) {
    const selected = selectedFile.getBoundingClientRect(),
      bounds = fileList.getBoundingClientRect();
    fileList.scrollTop +=
      Math.max(0, selected.bottom - bounds.bottom) +
      Math.min(0, selected.top - bounds.top);
  }
  if ($("side"))
    $("side").onchange = () => {
      side = $("side").value;
      renderDetail();
    };
  if ($("file-search"))
    $("file-search").oninput = () => {
      const input = $("file-search");
      fileQuery = input.value;
      const pos = input.selectionStart;
      renderDetail();
      $("file-search").focus();
      $("file-search").setSelectionRange(pos, pos);
    };
}
function render() {
  renderConversations();
  renderEvents();
  renderDetail();
  updateURL();
}
function showRun(loaded, fromURL) {
  data = loaded;
  $("run-title").textContent = data.title;
  $("run-summary").hidden = false;
  document.querySelector(".example-links").open = false;
  const q = new URLSearchParams(location.search);
  tab =
    fromURL && ["activity", "files", "request", "record"].includes(q.get("tab"))
      ? q.get("tab")
      : "activity";
  $("description").textContent =
    "Conversation and child heads recorded at this commit.";
  $("loaded-source").textContent = liveSource.source + " · " + liveSource.head;
  const count = data.conversations.reduce((n, c) => n + c.events.length, 0),
    calls = data.conversations.reduce(
      (n, c) =>
        n +
        c.events.reduce(
          (n, e) =>
            n + toolRecords(e).filter((r) => r.status !== "started").length,
          0,
        ),
      0,
    );
  $("facts").innerHTML =
    `<span>${icon("branch")}<span><strong>${data.conversations.length}</strong> conversations</span></span><span>${icon("commit")}<span><strong>${count}</strong> commits</span></span><span>${icon("code")}<span><strong>${calls}</strong> tool results</span></span><span>${icon("box")}<span><strong>${data.evidence.objects.length}</strong> Git objects</span></span>`;
  if (downloadURL) URL.revokeObjectURL(downloadURL);
  downloadURL = null;
  downloadURL = URL.createObjectURL(
    new Blob([JSON.stringify(data)], { type: "application/json" }),
  );
  $("download").href = downloadURL;
  $("download").download = "conversation-" + liveSource.head + ".json";
  $("notice").hidden = true;
  $("browser").hidden = false;
  selectConversation(
    fromURL && q.get("conversation") ? q.get("conversation") : data.root,
    fromURL && q.get("event") ? q.get("event") : undefined,
  );
  if (fromURL && q.get("file")) {
    file = q.get("file");
    renderDetail();
    updateURL();
  }
}
function browserRead(options, version) {
  return new Promise((resolve, reject) => {
    const worker = new Worker("remote-worker.js?v=browser-3");
    activeWorker = worker;
    rejectWorker = reject;
    worker.onmessage = ({ data: message }) => {
      if (message.type === "progress") {
        if (version === loadVersion) $("notice").textContent = message.message;
        return;
      }
      worker.terminate();
      if (activeWorker === worker) {
        activeWorker = null;
        rejectWorker = null;
      }
      if (message.type === "error") reject(Error(message.message));
      else resolve(message);
    };
    worker.onerror = () => {
      worker.terminate();
      if (activeWorker === worker) {
        activeWorker = null;
        rejectWorker = null;
      }
      reject(
        Error(
          "The browser reader stopped. Try a smaller run or reload the page.",
        ),
      );
    };
    worker.postMessage(options);
  });
}
async function localRead(kind, source, head) {
  if (!["localhost", "127.0.0.1"].includes(location.hostname))
    throw Error(
      "Use an HTTPS clone URL. SSH and filesystem paths require the optional local viewer.",
    );
  const response = await fetch("/api/load", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, source, head }),
  });
  if (!response.ok) {
    let error;
    try {
      error = (await response.json()).error;
    } catch {}
    throw Error(
      error || "A filesystem or SSH remote requires the optional local viewer.",
    );
  }
  return { data: await response.json(), objects: [] };
}
async function loadRemote(kind, source, head, fromURL = false) {
  cancelLoad();
  const version = ++loadVersion;
  if (!fromURL) {
    const u = new URL(location.href);
    for (const key of [
      "example",
      "transport",
      "server",
      "remote",
      "loose",
      "head",
      "conversation",
      "event",
      "tab",
      "file",
    ])
      u.searchParams.delete(key);
    u.searchParams.set("remote", source);
    if (kind !== "auto") u.searchParams.set("transport", kind);
    u.searchParams.set("head", head);
    history.replaceState(null, "", u);
  }
  $("source-kind").value = kind;
  $("source-url").value = source;
  $("source-head").value = head;
  $("notice").hidden = false;
  $("browser").hidden = true;
  $("run-summary").hidden = true;
  $("cancel-load").hidden = false;
  $("notice").textContent = "Reading Git objects in your browser…";
  try {
    if (!/^[0-9a-f]{40}$/.test(head))
      throw Error("Enter a full 40-character conversation commit hash.");
    if (!source.trim()) throw Error("Enter a server URL or Git remote.");
    const options = {
      kind,
      source,
      head,
      proxy: !fromURL ? $("source-proxy").value.trim() : "",
      preferred: detectedSources.get(source),
      token: fromURL ? "" : $("source-token").value,
    };
    const localMode =
      kind !== "loose" &&
      ["localhost", "127.0.0.1"].includes(location.hostname) &&
      new URLSearchParams(location.search).get("reader") === "local";
    const useLocal =
      localMode ||
      (["remote", "auto"].includes(kind) && !/^https?:\/\//i.test(source));
    if (useLocal) {
      $("cancel-load").hidden = true;
      $("notice").textContent = "Reading through the local viewer…";
    }
    const loaded = useLocal
      ? await localRead(kind === "auto" ? "remote" : kind, source, head)
      : await browserRead(options, version);
    if (version !== loadVersion) return;
    clearObjects();
    for (const object of loaded.objects)
      objectURLs.set(
        object.oid,
        URL.createObjectURL(
          new Blob([object.bytes], { type: "application/octet-stream" }),
        ),
      );
    detectedSources.set(source, loaded.kind || kind);
    liveSource = { kind: loaded.kind || kind, override: kind, source, head };
    showRun(loaded.data, fromURL);
  } catch (error) {
    if (version === loadVersion) {
      $("notice").textContent = error.message;
      $("browser").hidden = true;
    }
  } finally {
    if (version === loadVersion) $("cancel-load").hidden = true;
  }
}
$("cancel-load").onclick = cancelLoad;
$("load-run").onsubmit = (e) => {
  e.preventDefault();
  loadRemote(
    $("source-kind").value,
    $("source-url").value.trim(),
    $("source-head").value.trim(),
  );
};
$("search").oninput = () => {
  renderEvents();
  renderDetail();
};
$("filter").onchange = () => {
  renderEvents();
  renderDetail();
};
function moveEvent(direction) {
  const shown = visibleEvents(),
    i = shown.findIndex((e) => e.oid === event.oid),
    next = shown[i + direction];
  if (next) {
    event = next;
    file = "";
    side = "after";
    render();
    document
      .querySelector("#events .event.active")
      ?.scrollIntoView({ block: "nearest" });
  }
}
$("previous-event").onclick = () => moveEvent(-1);
$("next-event").onclick = () => moveEvent(1);
document.querySelectorAll("[data-panel]").forEach(
  (button) =>
    (button.onclick = () => {
      const open = document
        .querySelector("." + button.dataset.panel)
        .classList.toggle("mobile-open");
      button.setAttribute("aria-expanded", String(open));
      button.textContent = open ? "Hide" : "Show";
    }),
);
$("copy-link").onclick = async () => {
  try {
    await navigator.clipboard.writeText(location.href);
    $("copy-status").textContent = "Link copied.";
    $("copy-link").querySelector("span").textContent = "Copied!";
    setTimeout(
      () => ($("copy-link").querySelector("span").textContent = "Copy link"),
      1800,
    );
  } catch {
    $("copy-status").textContent = "Copy the link from your address bar.";
  }
};
document.querySelectorAll("[data-tab]").forEach(
  (b) =>
    (b.onclick = () => {
      tab = b.dataset.tab;
      renderDetail();
      updateURL();
    }),
);

const examples = new Map();
document.querySelectorAll("[data-example]").forEach((link) => {
  const source = new URL("git", location.href).href,
    head = link.dataset.head;
  const url = new URL(location.pathname, location.origin);
  url.searchParams.set("remote", source);
  url.searchParams.set("head", head);
  link.href = url.href;
  examples.set(link.dataset.example, { source, head });
  link.onclick = (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    // Example links never reuse credentials intended for another remote.
    $("source-token").value = "";
    $("source-proxy").value = "";
    const current = new URL(location.href);
    current.searchParams.delete("reader");
    history.replaceState(null, "", current);
    loadRemote("auto", source, head);
  };
});
(async () => {
  const q = new URLSearchParams(location.search);
  if (q.has("server") || q.has("remote") || q.has("loose")) {
    const kind = q.has("server")
      ? "server"
      : q.has("loose")
        ? "loose"
        : q.get("transport") || "auto";
    await loadRemote(
      kind,
      q.get("server") || q.get("remote") || q.get("loose"),
      q.get("head") || "",
      true,
    );
  } else if (q.has("example")) {
    const entry = examples.get(q.get("example"));
    if (entry) await loadRemote("auto", entry.source, entry.head, true);
    else
      $("notice").textContent =
        "Unknown example. Enter a remote URL and conversation hash.";
  }
})();
