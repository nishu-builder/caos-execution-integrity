import { createTwoFilesPatch } from "diff";
import { bytesText } from "./objects.js";
const record = () => Object.create(null);

export class Exporter {
  constructor(objects) {
    this.o = objects;
    this.blobs = record();
    this.snapshots = record();
    this.requests = record();
    this.conversations = record();
    this.source_commits = record();
  }
  async blob(oid) {
    if (!this.blobs[oid]) {
      const { kind, body } = await this.o.get(oid);
      if (kind !== "blob") throw Error("Expected blob: " + oid);
      let text = null;
      try {
        text = bytesText(body);
        if (text.includes("\0")) text = null;
      } catch {}
      this.blobs[oid] = { size: body.length, binary: text === null, text };
    }
    return this.blobs[oid];
  }
  async snapshot(tree) {
    if (this.snapshots[tree]) return this.snapshots[tree];
    const files = record(),
      sources = record();
    const walk = async (oid, prefix = "", depth = 0) => {
      if (depth > 32) throw Error("Excessive tree nesting.");
      for (const e of await this.o.tree(oid)) {
        if (!prefix && e.name === ".caos") continue;
        const path = prefix + e.name;
        if (e.mode === "40000") await walk(e.oid, path + "/", depth + 1);
        else if (e.mode === "160000") {
          const c = await this.o.commit(e.oid);
          sources[path] = e.oid;
          this.source_commits[e.oid] = {
            oid: c.oid,
            tree: c.tree,
            parents: c.parents,
            message: c.message,
          };
          await walk(c.tree, path + "/", depth + 1);
        } else {
          await this.blob(e.oid);
          files[path] = { oid: e.oid, mode: e.mode };
        }
      }
    };
    await walk(tree);
    return (this.snapshots[tree] = { files, sources });
  }
  async transcript(tree) {
    const root = await this.o.at(tree, ".caos/transcript");
    if (!root) return [];
    const entries = (await this.o.tree(root))
      .filter((e) => e.mode !== "40000")
      .sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    const values = [];
    for (const e of entries)
      values.push(JSON.parse((await this.blob(e.oid)).text));
    return values;
  }
  async payload(tree, path, payloads) {
    if (path && typeof path === "object") path = path.path;
    if (!path) return null;
    let body = payloads.get(path);
    if (!body) {
      const oid = await this.o.at(tree, path);
      if (oid) body = (await this.o.get(oid)).body;
    }
    if (!body) return { missing: path };
    const text = new TextDecoder().decode(body);
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }
  async request(oid) {
    if (this.requests[oid]) return;
    const rows = [];
    for (const e of await this.o.tree(oid)) {
      const row = { ...e };
      if (!["40000", "160000"].includes(e.mode))
        Object.assign(row, await this.blob(e.oid));
      else if (["in", "head"].includes(e.name)) {
        const value = await this.o.get(e.oid),
          tree =
            value.kind === "commit" ? (await this.o.commit(e.oid)).tree : e.oid;
        row.snapshot = tree;
        await this.snapshot(tree);
      }
      rows.push(row);
    }
    this.requests[oid] = { oid, entries: rows, image_contents_included: false };
  }
  diff(before, after) {
    const a = before ? this.snapshots[before].files : {},
      b = this.snapshots[after].files,
      result = [];
    for (const path of [
      ...new Set([...Object.keys(a), ...Object.keys(b)]),
    ].sort()) {
      const old = a[path] || null,
        next = b[path] || null;
      if (old?.oid === next?.oid && old?.mode === next?.mode) continue;
      const oldText = old ? this.blobs[old.oid].text : "",
        newText = next ? this.blobs[next.oid].text : "";
      let patch = null;
      if (oldText !== null && newText !== null) {
        patch = createTwoFilesPatch(
          "before/" + path,
          "after/" + path,
          oldText,
          newText,
          undefined,
          undefined,
          { context: 3 },
        );
        patch = patch.slice(patch.indexOf("--- "));
      }
      result.push({ path, before: old, after: next, patch });
    }
    return result;
  }
  async conversation(head, depth = 0) {
    if (depth > 64) throw Error("Excessive child conversation nesting.");
    const identityOid = await this.o.at(
      (await this.o.commit(head)).tree,
      ".caos/identity.json",
    );
    if (!identityOid)
      throw Error(
        "This is not a CAOS conversation commit. Use the conversation head, not a source-code commit.",
      );
    const identity = JSON.parse(
        bytesText((await this.o.get(identityOid)).body),
      ),
      cid = identity.id;
    if (this.conversations[cid]) {
      if (this.conversations[cid].head !== head)
        throw Error(
          "The captured graph names different heads for one conversation.",
        );
      return cid;
    }
    const chain = [];
    let current = head;
    while (true) {
      if (chain.length >= 10000)
        throw Error("Conversation exceeds the 10,000-commit inspection limit.");
      const commit = await this.o.commit(current);
      chain.push(commit);
      if (commit.kind === "conversation.root") break;
      if (commit.parents.length !== 1)
        throw Error("Malformed conversation parent count at " + current);
      current = commit.parents[0];
    }
    chain.reverse();
    const rootTree = chain.at(-1).tree,
      titleOid = await this.o.at(rootTree, ".caos/title");
    const result = {
      id: cid,
      title: titleOid
        ? bytesText((await this.o.get(titleOid)).body).trim()
        : cid,
      head,
      identity,
      events: [],
      children: [],
    };
    this.conversations[cid] = result;
    const payloads = new Map(),
      known = new Set(),
      children = new Map();
    let previous = null;
    for (const [ordinal, c] of chain.entries()) {
      await this.snapshot(c.tree);
      for (const e of c.events)
        if (e.event === "payload")
          payloads.set(e.value.path, Uint8Array.from(e.value.bytes));
      const messages = [];
      for (const message of await this.transcript(c.tree)) {
        if (known.has(message.message_id)) continue;
        known.add(message.message_id);
        const enriched = { ...message, blocks: [] };
        for (const raw of message.blocks) {
          const block = { ...raw };
          if (block.type === "tool_use" || "arguments" in block)
            block.resolved_arguments = await this.payload(
              c.tree,
              block.arguments,
              payloads,
            );
          enriched.blocks.push(block);
        }
        messages.push(enriched);
      }
      const records = [];
      for (const e of c.events) {
        if (e.event === "payload") continue;
        const value = e.value,
          r = { type: e.event, ...value };
        if (e.event === "tool") {
          const outcome = value.result || {};
          r.observation = await this.payload(
            c.tree,
            outcome.observation || outcome.error,
            payloads,
          );
          if (value.task) await this.request(value.task);
        }
        if (e.event === "child") children.set(value.id, value);
        if (e.event === "request") await this.request(value.id);
        records.push(r);
      }
      result.events.push({
        oid: c.oid,
        parent: c.parents[0] || null,
        kind: c.kind,
        ordinal,
        tree: c.tree,
        before_tree: previous,
        messages,
        records,
        changes: this.diff(previous, c.tree),
      });
      previous = c.tree;
    }
    result.children = [...children.values()];
    for (const child of children.values())
      await this.conversation(
        child.terminal_head || child.initial_head,
        depth + 1,
      );
    return cid;
  }
  async export(head, source) {
    const root = await this.conversation(head);
    return {
      schema: 1,
      id: "live",
      title: this.conversations[root].title,
      description: `Loaded in your browser from ${source} at ${head}. Child conversations follow the heads recorded at this commit.`,
      root,
      runtime: "not supplied",
      conversations: Object.values(this.conversations),
      snapshots: this.snapshots,
      blobs: this.blobs,
      requests: this.requests,
      source_commits: this.source_commits,
      evidence: {
        objects: [...this.o.cache.keys()].sort(),
        hash_algorithm: "sha1",
        scope:
          "Captured conversation records, workspace files and request arguments. Worker image closures are not included; this is an inspection package, not a standalone runtime.",
      },
    };
  }
}
