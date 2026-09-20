import * as git from "isomorphic-git";
import http from "isomorphic-git/http/web";

export const oidPattern = /^[0-9a-f]{40}$/;
const utf8 = new TextEncoder();
const decode = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true });
const hex = (bytes) =>
  Array.from(bytes, (x) => x.toString(16).padStart(2, "0")).join("");
export const bytesText = (bytes) => decode.decode(bytes);
const MAX_OBJECT = 32 * 1024 * 1024;

// Only object storage is needed: there is no checkout, executable file, or persistent database.
class MemoryFS {
  constructor() {
    this.files = new Map();
    this.dirs = new Set(["/"]);
    this.bytes = 0;
    this.promises = this;
  }
  path(path) {
    const parts = [];
    for (const p of path.split("/")) {
      if (!p || p === ".") continue;
      if (p === "..") parts.pop();
      else parts.push(p);
    }
    return "/" + parts.join("/");
  }
  error(code, path) {
    return Object.assign(new Error(code + ": " + path), { code });
  }
  async mkdir(path) {
    path = this.path(path);
    if (this.dirs.has(path)) throw this.error("EEXIST", path);
    this.dirs.add(path);
  }
  async readFile(path, options) {
    path = this.path(path);
    if (!this.files.has(path)) throw this.error("ENOENT", path);
    const b = this.files.get(path);
    return typeof options === "string" || options?.encoding ? bytesText(b) : b;
  }
  async writeFile(path, value) {
    path = this.path(path);
    const b =
      typeof value === "string" ? utf8.encode(value) : new Uint8Array(value);
    this.bytes += b.length - (this.files.get(path)?.length || 0);
    if (this.bytes > 512 * 1024 * 1024)
      throw Error("Git download exceeds this viewer’s 512 MiB memory limit.");
    this.files.set(path, b);
  }
  async stat(path) {
    path = this.path(path);
    const file = this.files.has(path),
      dir = this.dirs.has(path);
    if (!file && !dir) throw this.error("ENOENT", path);
    return {
      isFile: () => file,
      isDirectory: () => dir,
      isSymbolicLink: () => false,
      size: this.files.get(path)?.length || 0,
      mode: dir ? 0o40755 : 0o100644,
      mtimeMs: 0,
      ctimeMs: 0,
      uid: 0,
      gid: 0,
      ino: 0,
    };
  }
  async lstat(path) {
    return this.stat(path);
  }
  async readdir(path) {
    path = this.path(path);
    if (!this.dirs.has(path)) throw this.error("ENOENT", path);
    const prefix = path === "/" ? "/" : path + "/";
    return [
      ...new Set(
        [...this.files.keys(), ...this.dirs]
          .filter((p) => p.startsWith(prefix) && p !== path)
          .map((p) => p.slice(prefix.length))
          .filter((p) => !p.includes("/")),
      ),
    ];
  }
  async unlink(path) {
    path = this.path(path);
    if (!this.files.has(path)) throw this.error("ENOENT", path);
    this.bytes -= this.files.get(path).length;
    this.files.delete(path);
  }
  async rmdir(path) {
    this.dirs.delete(this.path(path));
  }
  async readlink(path) {
    throw this.error("ENOENT", path);
  }
  async symlink() {
    throw this.error("ENOSYS", "symlinks are not used by the object reader");
  }
  async chmod() {}
}

function remoteURL(value) {
  let url;
  try {
    url = new URL(value);
  } catch {
    throw Error(
      "Use an HTTPS Git remote or CAOS server URL. SSH and filesystem paths are not accessible to a hosted page.",
    );
  }
  if (
    !["https:", "http:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  )
    throw Error(
      "Use an HTTP(S) URL without credentials, query parameters, or a fragment.",
    );
  if (
    location.protocol === "https:" &&
    url.protocol === "http:" &&
    !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)
  )
    throw Error(
      "This HTTPS page needs an HTTPS remote. Browsers block insecure HTTP connections.",
    );
  return url.href.replace(/\/$/, "");
}
async function readLimited(response, limit = MAX_OBJECT) {
  if (Number(response.headers.get("content-length")) > limit)
    throw Error(
      "Download exceeds the " +
        Math.round(limit / 1024 / 1024) +
        " MiB inspection limit.",
    );
  const reader = response.body.getReader(),
    parts = [];
  let length = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.length;
      if (length > limit)
        throw Error("Download exceeds the inspection size limit.");
      parts.push(value);
    }
  } catch (e) {
    await reader.cancel();
    throw e;
  }
  const out = new Uint8Array(length);
  let pos = 0;
  for (const part of parts) {
    out.set(part, pos);
    pos += part.length;
  }
  return out;
}

export class Objects {
  constructor({ kind, source, proxy = "", token = "", progress = () => {} }) {
    this.kind = kind;
    this.source = remoteURL(source);
    this.proxy = proxy ? remoteURL(proxy) : undefined;
    this.token = token;
    this.progress = progress;
    this.cache = new Map();
    this.trees = new Map();
    this.commits = new Map();
    this.bytes = 0;
    this.fs = new MemoryFS();
    this.gitCache = {};
    this.gitReady = null;
    this.inflight = new Map();
    this.packObjects = null;
    this.activeReads = 0;
    this.readQueue = [];
    this.gitFetch = Promise.resolve();
  }
  async response(path) {
    let response;
    try {
      response = await fetch(this.source + path, {
        credentials: "omit",
        headers: this.token ? { Authorization: "Bearer " + this.token } : {},
        signal: AbortSignal.timeout(60000),
        redirect: "error",
      });
    } catch {
      throw Error(
        "The browser could not read this remote. Check its address, HTTPS and CORS settings. It must allow this page’s origin; Git remotes can also use a relay you configure.",
      );
    }
    if (!response.ok)
      throw Error(
        `Remote returned HTTP ${response.status} for ${path}. Check access and that the referenced object is present.`,
      );
    if (response.headers.get("content-type")?.includes("text/html"))
      throw Error("This endpoint returned a web page, not Git objects.");
    return response;
  }
  async initGit() {
    if (!this.gitReady)
      this.gitReady = (async () => {
        await git.init({ fs: this.fs, dir: "/run", defaultBranch: "main" });
        await git.addRemote({
          fs: this.fs,
          dir: "/run",
          remote: "origin",
          url: this.source,
        });
      })();
    await this.gitReady;
  }
  async readGit(oid) {
    return git.readObject({
      fs: this.fs,
      dir: "/run",
      oid,
      format: "content",
      cache: this.gitCache,
    });
  }
  async fetchRaw(oid) {
    if (this.packObjects?.has(oid)) {
      const object = await this.readGit(oid);
      const header = utf8.encode(
        object.type + " " + object.object.length + "\0",
      );
      const raw = new Uint8Array(header.length + object.object.length);
      raw.set(header);
      raw.set(object.object, header.length);
      return raw;
    }
    if (this.kind === "server")
      return readLimited(await this.response("/object/" + oid));
    if (this.kind === "loose") {
      const response = await this.response(
        "/objects/" + oid.slice(0, 2) + "/" + oid.slice(2),
      );
      return readLimited(
        new Response(
          response.body.pipeThrough(new DecompressionStream("deflate")),
        ),
      );
    }
    return this.serialGit(async () => {
      await this.initGit();
      let object;
      try {
        object = await this.readGit(oid);
      } catch {
        this.progress("Fetching Git objects…");
        try {
          await git.fetch({
            fs: this.fs,
            http,
            dir: "/run",
            url: this.source,
            corsProxy: this.proxy,
            ref: oid,
            singleBranch: true,
            tags: false,
            cache: this.gitCache,
            onAuth: () =>
              this.token
                ? { username: "x-access-token", password: this.token }
                : { cancel: true },
            onProgress: (e) =>
              this.progress(
                `${e.phase}: ${e.loaded}${e.total ? " / " + e.total : ""}`,
              ),
          });
          object = await this.readGit(oid);
        } catch (e) {
          if (e.message?.includes("memory limit")) throw e;
          throw Error(
            "Git fetch failed. Check access, that the remote permits fetching this hash, and that it allows browser requests (CORS). Otherwise use an explicit Git CORS relay or a static Git object URL.",
          );
        }
      }
      if (object.object.length > MAX_OBJECT)
        throw Error("Object exceeds the 32 MiB inspection limit.");
      const header = utf8.encode(`${object.type} ${object.object.length}\0`),
        raw = new Uint8Array(header.length + object.object.length);
      raw.set(header);
      raw.set(object.object, header.length);
      return raw;
    });
  }
  serialGit(action) {
    const next = this.gitFetch.catch(() => {}).then(action);
    this.gitFetch = next;
    return next;
  }
  async loadPack(head) {
    let response;
    try {
      response = await this.response("/packs/" + head + ".pack");
    } catch {
      return false;
    } // Optional extension; normal Git/CAOS paths still work.
    const indexPromise = this.response("/packs/" + head + ".idx")
      .catch(() => null)
      .then((r) => (r ? readLimited(r, 8 * 1024 * 1024) : null))
      .then(
        (value) => ({ value }),
        (error) => ({ error }),
      );
    const raw = await readLimited(response, 128 * 1024 * 1024);
    if (bytesText(raw.subarray(0, 4)) !== "PACK")
      throw Error("Invalid Git pack header.");
    const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
    if (
      raw.length < 32 ||
      ![2, 3].includes(view.getUint32(4)) ||
      view.getUint32(8) > 20000
    )
      throw Error("Invalid or oversized Git pack.");
    if (
      hex(
        new Uint8Array(
          await crypto.subtle.digest("SHA-1", raw.subarray(0, -20)),
        ),
      ) !== hex(raw.subarray(-20))
    )
      throw Error("Git pack hash mismatch.");
    this.progress("Reading packed Git objects…");
    await this.initGit();
    const filepath =
      ".git/objects/pack/pack-" + hex(raw.subarray(-20)) + ".pack";
    await this.fs.writeFile("/run/" + filepath, raw);
    const indexResult = await indexPromise;
    if (indexResult.error) throw indexResult.error;
    const index = indexResult.value;
    if (index) {
      const idx = new DataView(
        index.buffer,
        index.byteOffset,
        index.byteLength,
      );
      if (
        index.length < 1072 ||
        idx.getUint32(0) !== 0xff744f63 ||
        idx.getUint32(4) !== 2
      )
        throw Error("Invalid Git pack index.");
      const count = idx.getUint32(1028);
      if (count !== view.getUint32(8) || index.length < 1072 + count * 28)
        throw Error("Invalid Git pack index length.");
      if (
        hex(
          new Uint8Array(
            await crypto.subtle.digest("SHA-1", index.subarray(0, -20)),
          ),
        ) !== hex(index.subarray(-20)) ||
        hex(index.subarray(-40, -20)) !== hex(raw.subarray(-20))
      )
        throw Error("Git pack index hash mismatch.");
      await this.fs.writeFile(
        "/run/" + filepath.replace(/\.pack$/, ".idx"),
        index,
      );
      this.packObjects = new Set(
        Array.from({ length: count }, (_, i) =>
          hex(index.subarray(1032 + i * 20, 1052 + i * 20)),
        ),
      );
    } else {
      const result = await git.indexPack({
        fs: this.fs,
        dir: "/run",
        filepath,
        cache: this.gitCache,
      });
      this.packObjects = new Set(result.oids);
    }
    if (!this.packObjects.has(head))
      throw Error("Git pack does not contain the requested conversation.");
    return true;
  }
  async get(oid) {
    if (this.cache.has(oid)) return this.cache.get(oid);
    if (this.inflight.has(oid)) return this.inflight.get(oid);
    const pending = this.readBounded(oid);
    this.inflight.set(oid, pending);
    try {
      return await pending;
    } finally {
      this.inflight.delete(oid);
    }
  }
  async readBounded(oid) {
    if (this.activeReads >= 8)
      await new Promise((resolve) => this.readQueue.push(resolve));
    else this.activeReads++;
    try {
      return await this.readVerified(oid);
    } finally {
      const next = this.readQueue.shift();
      if (next) next();
      else this.activeReads--;
    }
  }
  async readVerified(oid) {
    if (!oidPattern.test(oid))
      throw Error("Invalid Git object hash: " + String(oid));
    if (this.cache.has(oid)) return this.cache.get(oid);
    if (this.cache.size >= 20000)
      throw Error("This run exceeds the 20,000-object inspection limit.");
    const raw = await this.fetchRaw(oid);
    if (raw.length > MAX_OBJECT)
      throw Error("Object exceeds the 32 MiB inspection limit.");
    if (hex(new Uint8Array(await crypto.subtle.digest("SHA-1", raw))) !== oid)
      throw Error("Git object hash mismatch: " + oid);
    const nul = raw.indexOf(0);
    if (nul < 0) throw Error("Invalid Git object header.");
    const match = bytesText(raw.subarray(0, nul)).match(
        /^(blob|tree|commit|tag) (\d+)$/,
      ),
      body = raw.subarray(nul + 1);
    if (!match || body.length !== Number(match[2]))
      throw Error("Invalid Git object length or type: " + oid);
    this.bytes += raw.length;
    if (this.bytes > 256 * 1024 * 1024)
      throw Error("Captured objects exceed the 256 MiB inspection limit.");
    const value = { kind: match[1], body, raw };
    this.cache.set(oid, value);
    this.progress(`Verified ${this.cache.size} Git objects`);
    return value;
  }
  async tree(oid) {
    if (this.trees.has(oid)) return this.trees.get(oid);
    const { kind, body } = await this.get(oid);
    if (kind !== "tree") throw Error("Expected Git tree: " + oid);
    const entries = [];
    let pos = 0;
    while (pos < body.length) {
      const nul = body.indexOf(0, pos);
      if (nul < 0 || nul + 21 > body.length) throw Error("Malformed Git tree.");
      const head = bytesText(body.subarray(pos, nul)),
        space = head.indexOf(" ");
      entries.push({
        mode: head.slice(0, space),
        name: head.slice(space + 1),
        oid: hex(body.subarray(nul + 1, nul + 21)),
      });
      pos = nul + 21;
    }
    this.trees.set(oid, entries);
    return entries;
  }
  async commit(oid) {
    if (this.commits.has(oid)) return this.commits.get(oid);
    const { kind, body } = await this.get(oid);
    if (kind !== "commit") throw Error("Expected conversation commit: " + oid);
    const text = bytesText(body),
      split = text.indexOf("\n\n");
    if (split < 0) throw Error("Malformed Git commit.");
    const headers = text.slice(0, split).split("\n"),
      message = text.slice(split + 2),
      boundary = message.indexOf("\n\n");
    const fields = Object.create(null);
    for (const line of headers) {
      const i = line.indexOf(" ");
      (fields[line.slice(0, i)] ??= []).push(line.slice(i + 1));
    }
    const eventBody = boundary < 0 ? "" : message.slice(boundary + 2),
      eventKind = (boundary < 0 ? message : message.slice(0, boundary)).trim();
    const value = {
      oid,
      tree: fields.tree[0],
      parents: fields.parent || [],
      kind: eventKind,
      events: eventBody.trim().startsWith("{")
        ? JSON.parse(eventBody).events || []
        : [],
      message,
    };
    this.commits.set(oid, value);
    return value;
  }
  async at(tree, path) {
    for (const part of path.split("/")) {
      const e = (await this.tree(tree)).find((e) => e.name === part);
      if (!e) return null;
      tree = e.oid;
    }
    return tree;
  }
}

export async function openObjects(options) {
  // Explicit Git uses its own smart-HTTP pack exchange. Static/CAOS publishers
  // may provide a pack for a conversation to avoid hundreds of round trips.
  if (options.kind !== "remote") {
    const packed = new Objects({
      ...options,
      kind: options.kind === "auto" ? "loose" : options.kind,
    });
    if (await packed.loadPack(options.head)) {
      await packed.get(options.head);
      return packed;
    }
  }
  if (options.kind !== "auto") return new Objects(options);
  const order = [
    ...new Set(
      [
        options.preferred,
        ...(options.source.endsWith(".git") ? ["remote"] : []),
        "server",
        "loose",
        "remote",
      ].filter(Boolean),
    ),
  ];
  for (const kind of order) {
    options.progress("Detecting how to read this remote…");
    const objects = new Objects({ ...options, kind });
    try {
      await objects.get(options.head);
      return objects;
    } catch (error) {
      // Never hide a failed integrity check by trying another endpoint.
      if (/hash mismatch|inspection.*limit|memory limit/.test(error.message))
        throw error;
    }
  }
  throw Error(
    "Could not read this hash from the remote. Check the URL, access and CORS settings. Connection options can set a type or Git relay.",
  );
}
