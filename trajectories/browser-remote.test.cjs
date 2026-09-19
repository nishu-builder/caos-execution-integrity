const assert = require("node:assert/strict");
const { chromium } = require("playwright");
const base = process.env.BROWSER_URL || "http://127.0.0.1:18184/trajectories/";
const remote = process.env.TEST_REMOTE_URL || "http://127.0.0.1:18191";
const head = "845c4cd46019a73064cbe3c9d4927a668046d315";
(async () => {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    const requests = [];
    page.on("request", (r) => requests.push(r.url()));
    await page.route("**/api/**", (route) => route.abort());
    await page.goto(base);
    await page.waitForSelector("#browser:not([hidden])");
    // Compare the independently reconstructed objects and records, allowing diff presentation differences.
    async function checkWorker(
      kind,
      source,
      expected = "repair",
      commit = head,
    ) {
      return page.evaluate(
        async ({ kind, source, head, expected }) => {
          const result = await new Promise((resolve, reject) => {
            const w = new Worker("remote-worker.js?v=browser-1");
            w.onmessage = ({ data }) => {
              if (data.type === "result") {
                w.terminate();
                resolve(data);
              }
              if (data.type === "error") {
                w.terminate();
                reject(Error(data.message));
              }
            };
            w.onerror = (e) => reject(Error(e.message));
            w.postMessage({ kind, source, head });
          });
          const recorded = await (
            await fetch("data/" + expected + ".json")
          ).json();
          const canonical = (v) =>
            Array.isArray(v)
              ? v.map(canonical)
              : v && typeof v === "object"
                ? Object.fromEntries(
                    Object.keys(v)
                      .filter((k) => k !== "patch")
                      .sort()
                      .map((k) => [k, canonical(v[k])]),
                  )
                : v;
          for (const key of [
            "root",
            "conversations",
            "snapshots",
            "blobs",
            "requests",
            "source_commits",
            "evidence",
          ])
            if (
              JSON.stringify(canonical(recorded[key])) !==
              JSON.stringify(canonical(result.data[key]))
            )
              throw Error("Browser export differs: " + key);
          return {
            conversations: result.data.conversations.length,
            objects: result.objects.length,
          };
        },
        { kind, source, head: commit, expected },
      );
    }
    console.log(
      "CAOS object parity:",
      await checkWorker("server", remote + "/caos"),
    );
    console.log(
      "Loose Git object parity:",
      await checkWorker("loose", remote + "/loose"),
    );
    console.log(
      "Cleanup record parity:",
      await checkWorker(
        "server",
        remote + "/caos",
        "cleanup",
        "60da0990f42ccb58bbe0bc67c591bb42b0d74012",
      ),
    );
    if (process.env.TEST_LIVE_GIT)
      console.log(
        "Real CAOS smart Git parity:",
        await checkWorker("remote", remote + "/live"),
      );
    const fixture = await (
      await page.request.get(remote + "/fixture.json")
    ).json();
    requests.length = 0;
    await page.goto(
      base +
        "?" +
        new URLSearchParams({
          remote: remote + "/smart/fresh.git",
          head: fixture.first,
        }),
    );
    await page
      .waitForSelector("#browser:not([hidden])", { timeout: 60000 })
      .catch(async () => {
        throw Error(await page.locator("#notice").innerText());
      });
    assert.match(
      await page.locator("#description").innerText(),
      /Loaded in your browser/,
    );
    await page.click('[data-tab="files"]');
    assert.match(
      await page.locator(".file-content").innerText(),
      /First snapshot/,
    );
    assert.match(
      await page.locator("#event-heading a").getAttribute("href"),
      /^blob:/,
    );
    await page.locator(".connection-options").evaluate((e) => (e.open = true));
    await page.fill("#source-token", "test-token-stays-in-this-tab");
    await page.fill("#source-head", fixture.second);
    await page.click('#load-run button[type="submit"]');
    await page.waitForFunction(
      (h) => document.querySelector("#description").textContent.includes(h),
      fixture.second,
    );
    await page.click('[data-tab="files"]');
    assert.match(
      await page.locator(".file-content").innerText(),
      /Second snapshot/,
    );
    await page.selectOption("#side", "before");
    assert.match(
      await page.locator(".file-content").innerText(),
      /First snapshot/,
    );
    assert.ok(!page.url().includes("test-token-stays-in-this-tab"));
    const exported = await page.evaluate(
      async () =>
        await (await fetch(document.querySelector("#download").href)).text(),
    );
    assert.ok(!exported.includes("test-token-stays-in-this-tab"));
    await page.reload();
    await page.waitForSelector(".file-content");
    assert.match(
      await page.locator(".file-content").innerText(),
      /Second snapshot/,
    );
    assert.ok(
      !requests.some((u) => u.includes("/api/")),
      "browser load called a helper API",
    );
    assert.ok(
      !requests.some(
        (u) =>
          u.includes("/data/repair.json") || u.includes("/data/cleanup.json"),
      ),
      "remote load used a saved example",
    );
    // Actual browser CORS enforcement, and a successful HTTP response carrying corrupted bytes.
    for (const [path, match] of [
      ["blocked", /CORS/],
      ["corrupt", /hash mismatch/],
    ]) {
      await page.goto(
        base + "?" + new URLSearchParams({ server: remote + "/" + path, head }),
      );
      await page.waitForFunction(
        () => document.querySelector("#cancel-load").hidden,
      );
      assert.match(await page.locator("#notice").innerText(), match);
      assert.equal(await page.locator("#browser").isVisible(), false);
    }
    // The standalone site's published object layout is readable with no helper at all.
    await page.goto(base);
    await page.waitForSelector("#browser:not([hidden])");
    await page.click("#open-run-button");
    await page.click("#try-remote");
    await page.waitForFunction(
      () =>
        document
          .querySelector("#description")
          .textContent.startsWith("Loaded in your browser"),
      null,
      { timeout: 60000 },
    );
    assert.match(await page.locator("#facts").innerText(), /3 conversations/);
    assert.equal(
      new URL(page.url()).searchParams.get("loose"),
      new URL("git", base).href,
    );
    await page.fill("#source-head", head);
    await page.click('#load-run button[type="submit"]');
    await page.click("#cancel-load");
    await page.waitForFunction(
      () =>
        document.querySelector("#notice").textContent === "Loading cancelled.",
    );
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
      false,
      "remote form overflows mobile viewport",
    );
    if (process.env.SCREENSHOT_DIR)
      await page.screenshot({
        path: process.env.SCREENSHOT_DIR + "/remote-mobile.png",
        fullPage: true,
      });
    await page.setViewportSize({ width: 1440, height: 1000 });
    if (process.env.SCREENSHOT_DIR)
      await page.screenshot({
        path: process.env.SCREENSHOT_DIR + "/remote-desktop.png",
        fullPage: true,
      });
    console.log(
      "Passed: independent record parity, fresh smart Git remote, new commit, before/after, reload, no helper or fixture fetches, CORS failure, corrupt-object rejection, published Git objects, cancellation.",
    );
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
