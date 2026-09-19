import { Buffer } from "buffer";
import { Objects, oidPattern } from "./objects.js";
import { Exporter } from "./exporter.js";
self.Buffer = Buffer;
self.onmessage = async ({ data: options }) => {
  let last = 0;
  const progress = (message) => {
    const now = performance.now();
    if (now - last > 100) {
      last = now;
      self.postMessage({ type: "progress", message });
    }
  };
  try {
    if (!oidPattern.test(options.head))
      throw Error("Enter a full 40-character conversation commit hash.");
    if (!["server", "remote", "loose"].includes(options.kind))
      throw Error("Unknown remote type.");
    const objects = new Objects({ ...options, progress });
    const data = await new Exporter(objects).export(
      options.head,
      objects.source,
    );
    const raw = [...objects.cache].map(([oid, value]) => ({
      oid,
      bytes: value.raw,
    }));
    self.postMessage({ type: "result", data, objects: raw }, [
      ...new Set(raw.map((o) => o.bytes.buffer)),
    ]);
  } catch (error) {
    self.postMessage({
      type: "error",
      message: error.message || "Could not read the conversation.",
    });
  }
};
