import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { after, test } from "node:test";
import ts from "typescript";

const output = mkdtempSync(join(tmpdir(), "dvizh-api-test-"));
writeFileSync(join(output, "package.json"), '{"type":"commonjs"}');
for (const name of ["client", "events"]) {
    const source = readFileSync(new URL(`../src/api/${name}.ts`, import.meta.url), "utf8");
    const { outputText } = ts.transpileModule(source, {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    });
    writeFileSync(join(output, `${name}.js`), outputText);
}
const require = createRequire(import.meta.url);
const api = require(join(output, "events.js"));
const { ApiError } = require(join(output, "client.js"));
const originalWindow = globalThis.window;
globalThis.window = { location: { origin: "http://localhost:8080" } };
after(() => {
    if (originalWindow === undefined) delete globalThis.window;
    else globalThis.window = originalWindow;
    assert.equal(dirname(output), resolve(tmpdir()));
    assert.ok(basename(output).startsWith("dvizh-api-test-"));
    rmSync(output, { recursive: true, force: true });
});

test("event edits and deletion send actor_id without adding it to the DTO", async (t) => {
    const calls = [];
    t.mock.method(globalThis, "fetch", async (url, options) => {
        calls.push({ url, options });
        return options.method === "DELETE"
            ? new Response(null, { status: 204 })
            : Response.json({ id: "event-1" });
    });
    const body = { title: "Updated event" };
    await api.updateEvent("event-1", body, "owner-1");
    assert.equal(await api.deleteEvent("event-1", "owner-1"), undefined);
    assert.equal(calls.length, 2);
    for (const { url } of calls) {
        assert.equal(url.pathname, "/api/events/event-1");
        assert.equal(url.searchParams.get("actor_id"), "owner-1");
    }
    assert.equal(calls[0].options.method, "PUT");
    assert.deepEqual(JSON.parse(calls[0].options.body), body);
    assert.equal(calls[1].options.method, "DELETE");
});

test("event details and feed carry viewer_id; anonymous requests omit it", async (t) => {
    const urls = [];
    const state = { is_favorite: true, is_dismissed: false, participation_status: "GOING" };
    t.mock.method(globalThis, "fetch", async (url) => {
        urls.push(url);
        return Response.json({ cover_url: "/api/media/cover-1/content", personal_state: state });
    });
    const event = await api.getEvent("draft-1", "viewer-1");
    await api.listEvents({ viewerId: "viewer-1", friendsOf: "friend-1", limit: 20 });
    await api.getEvent("event-1", null);
    assert.equal(urls[0].searchParams.get("viewer_id"), "viewer-1");
    assert.equal(urls[1].searchParams.get("viewer_id"), "viewer-1");
    assert.equal(urls[1].searchParams.get("friends_of"), "friend-1");
    assert.equal(urls[1].searchParams.get("limit"), "20");
    assert.equal(urls[2].searchParams.has("viewer_id"), false);
    assert.deepEqual(event.personal_state, state);
    assert.equal(event.cover_url, "/api/media/cover-1/content");
});

test("denied event mutations preserve backend errors", async (t) => {
    t.mock.method(globalThis, "fetch", async () =>
        Response.json({ detail: "User cannot manage this event" }, { status: 403 }));
    await assert.rejects(api.deleteEvent("event-1", "stranger-1"), (error) =>
        error instanceof ApiError && error.status === 403 && error.message.includes("cannot manage"));
});
