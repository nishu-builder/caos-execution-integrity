import { build } from "esbuild";
import { readFile, readdir, writeFile } from "node:fs/promises";

// isomorphic-git 1.37.1 assumes every remote advertises HEAD, even for a
// fetch by object ID. CAOS stores need not have a default branch.
// Guard only that optional default-branch inference; object fetching and
// verification are unchanged. Fail the build if the pinned source changes.
const result = await build({
  metafile: true,
  entryPoints: ["browser/worker.js"],
  bundle: true,
  platform: "browser",
  target: "es2022",
  format: "iife",
  minify: true,
  legalComments: "linked",
  outfile: "../docs/trajectories/remote-worker.js",
  plugins: [
    {
      name: "allow-headless-git-store",
      setup(builder) {
        builder.onLoad(
          { filter: /isomorphic-git[\/]index\.(?:js|cjs)$/ },
          async ({ path }) => {
            const source = await readFile(path, "utf8");
            const before = "if (response.HEAD === undefined) {";
            if (source.split(before).length !== 2)
              throw Error(
                "Review the headless-remote compatibility fix after upgrading isomorphic-git.",
              );
            return {
              contents: source.replace(
                before,
                "if (response.HEAD === undefined && remoteRefs.has('HEAD')) {",
              ),
              loader: "js",
            };
          },
        );
      },
    },
  ],
});

// Keep the full license texts beside the distributed bundle.
const packages = new Set();
for (const file of Object.keys(result.metafile.inputs)) {
  const match = file.match(/^(node_modules\/(?:@[^/]+\/)?[^/]+)\//);
  if (match) packages.add(match[1]);
}
const notices = [
  "Third-party software in remote-worker.js",
  "Rebuild instructions and the compatibility change: ../../trajectories/build.mjs",
  "Locked original sources: ../../trajectories/package-lock.json",
  "The unmodified isomorphic-git source used by the build is also provided as isomorphic-git-source.cjs.",
];
for (const dir of [...packages].sort()) {
  const pkg = JSON.parse(await readFile(dir + "/package.json", "utf8"));
  notices.push("\n===== " + pkg.name + " " + pkg.version + " =====");
  const names = (await readdir(dir)).filter((name) =>
    /^(licen[cs]e|copying)([.-]|$)/i.test(name),
  );
  if (!names.length) {
    if (pkg.name === "diff3") {
      for (const name of ["diff3.js", "onp.js"])
        notices.push(
          (await readFile(dir + "/" + name, "utf8")).split("\n\n")[0],
        );
      continue;
    }
    if (pkg.license !== "Apache-2.0")
      throw Error("Missing license text for " + pkg.name);
    notices.push("Author: " + pkg.author + "; license: " + pkg.license);
    notices.push(
      await readFile("../docs/trajectories/licenses/Apache-2.0.txt", "utf8"),
    );
  }
  for (const name of names.sort())
    notices.push(await readFile(dir + "/" + name, "utf8"));
}
notices.push(
  "The path.join implementation inside isomorphic-git carries an LGPL-3.0-or-later notice. See licenses/LGPL-3.txt and licenses/GPL-3.txt. Its corresponding source is included in isomorphic-git-source.cjs; the build script can rebuild the bundle with changes.",
);
await writeFile(
  "../docs/trajectories/THIRD-PARTY.txt",
  notices.join("\n\n") + "\n",
);
await writeFile(
  "../docs/trajectories/isomorphic-git-source.cjs",
  await readFile("node_modules/isomorphic-git/index.cjs"),
);
