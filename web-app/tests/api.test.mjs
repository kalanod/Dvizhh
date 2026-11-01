import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { after, test } from "node:test";
import ts from "typescript";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

const testRoot = fileURLToPath(new URL("../node_modules/.tmp/", import.meta.url));
mkdirSync(testRoot, { recursive: true });
const output = mkdtempSync(join(testRoot, "dvizh-api-test-"));
writeFileSync(join(output, "package.json"), '{"type":"commonjs"}');
for (const name of ["api/client", "api/events", "api/media", "api/eventCover", "utils/media", "utils/format", "components/widgets/EventCard/EventCoverMicro"]) {
    const extension = name.startsWith("components/") ? "tsx" : "ts";
    const source = readFileSync(new URL(`../src/${name}.${extension}`, import.meta.url), "utf8");
    const { outputText } = ts.transpileModule(source, {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
    });
    const target = join(output, `${name}.js`);
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, outputText);
}
const require = createRequire(import.meta.url);
const api = require(join(output, "api/events.js"));
const media = require(join(output, "api/media.js"));
const { createEventSaver } = require(join(output, "api/eventCover.js"));
const { mediaContentUrl, validateCoverFile } = require(join(output, "utils/media.js"));
const { EventCoverMicro, EventCoverMain } = require(join(output, "components/widgets/EventCard/EventCoverMicro.js"));
const { ApiError } = require(join(output, "api/client.js"));
const originalWindow = globalThis.window;
globalThis.window = { location: { origin: "http://localhost:8080" } };
after(() => {
    if (originalWindow === undefined) delete globalThis.window;
    else globalThis.window = originalWindow;
    assert.equal(dirname(output), resolve(testRoot));
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

test("image uploads send raw file bytes and an encoded filename", async (t) => {
    const file = new File([new Uint8Array([1, 2, 3])], "Обложка & фото.png", { type: "image/png" });
    t.mock.method(globalThis, "fetch", async (url, options) => {
        assert.equal(url.pathname, "/api/media");
        assert.equal(url.searchParams.get("user_id"), "owner-1");
        assert.equal(url.searchParams.get("filename"), file.name);
        assert.equal(options.headers["Content-Type"], "application/octet-stream");
        assert.equal(options.body, file);
        assert.deepEqual(new Uint8Array(await options.body.arrayBuffer()), new Uint8Array([1, 2, 3]));
        return Response.json({ id: "media-1" }, { status: 201 });
    });
    assert.equal((await media.uploadImage("owner-1", file)).id, "media-1");
});

test("cover assignment and removal preserve actor and nullable media id", async (t) => {
    const values = [];
    t.mock.method(globalThis, "fetch", async (url, options) => {
        assert.equal(url.pathname, "/api/events/event-1/cover");
        assert.equal(url.searchParams.get("actor_id"), "owner-1");
        assert.equal(options.method, "PUT");
        values.push(JSON.parse(options.body));
        return Response.json({ id: "event-1" });
    });
    await media.setEventCover("event-1", "owner-1", "media-1");
    await media.setEventCover("event-1", "owner-1", null);
    assert.deepEqual(values, [{ media_id: "media-1" }, { media_id: null }]);
});

test("image selection follows server size and format limits", () => {
    const config = { max_bytes: 4, formats: ["JPEG", "PNG", "WEBP"] };
    assert.equal(validateCoverFile(new File(["1234"], "cover.png", { type: "image/png" }), config), null);
    assert.equal(validateCoverFile(new File(["1"], "COVER.JPG"), config), null);
    assert.match(validateCoverFile(new File(["12345"], "cover.png", { type: "image/png" }), config), /не больше/);
    assert.match(validateCoverFile(new File(["<svg/>"], "cover.svg", { type: "image/svg+xml" }), config), /JPEG/);
    assert.match(validateCoverFile(new File([], "cover.png", { type: "image/png" }), config), /пустой/);
});

test("event covers render images with viewer access and keep the date fallback", () => {
    assert.equal(mediaContentUrl(null, "owner-1"), null);
    assert.equal(mediaContentUrl("/api/media/one/content"), "/api/media/one/content");
    for (const Cover of [EventCoverMicro, EventCoverMain]) {
        const props = { startsAt: "2026-11-01T10:00:00Z", timeZone: "UTC" };
        const image = renderToStaticMarkup(createElement(Cover, {
            ...props, coverUrl: "/api/media/one/content", viewerId: "owner-1",
        }));
        assert.match(image, /<img/);
        assert.match(image, /\/api\/media\/one\/content\?viewer_id=owner-1/);
        assert.match(image, /object-cover/);
        const fallback = renderToStaticMarkup(createElement(Cover, props));
        assert.doesNotMatch(fallback, /<img/);
        assert.match(fallback, />1<\//);
    }
});

test("new events publish only after upload and cover assignment", async (t) => {
    const calls = [];
    t.mock.method(globalThis, "fetch", async (url, options) => {
        calls.push(url.pathname);
        if (url.pathname === "/api/media") return Response.json({ id: "media-1" });
        if (url.pathname.endsWith("/publish")) {
            assert.deepEqual(JSON.parse(options.body), { actor_id: "owner-1" });
            return Response.json({ id: "event-1", status: "PUBLISHED", cover_media_id: "media-1" });
        }
        return Response.json({ id: "event-1", status: "DRAFT" });
    });
    const save = createEventSaver("owner-1");
    const event = await save({ title: "Event" }, { kind: "file", file: new File(["image"], "cover.png") });
    assert.deepEqual(calls, ["/api/events/drafts", "/api/media", "/api/events/event-1/cover", "/api/events/event-1/publish"]);
    assert.equal(event.status, "PUBLISHED");
    assert.equal(event.cover_media_id, "media-1");
});

test("retry after cover failure reuses the draft and uploaded image", async (t) => {
    const calls = [];
    let fail = true;
    t.mock.method(globalThis, "fetch", async (url) => {
        calls.push(url.pathname);
        if (url.pathname === "/api/media") return Response.json({ id: "media-1" });
        if (url.pathname.endsWith("/cover") && fail) {
            fail = false;
            return Response.json({ detail: "Storage unavailable" }, { status: 503 });
        }
        return Response.json({ id: "event-1" });
    });
    const save = createEventSaver("owner-1");
    const cover = { kind: "file", file: new File(["image"], "cover.png") };
    await assert.rejects(save({ title: "Event" }, cover), /пока не опубликовано/);
    assert.equal(calls.some((path) => path.endsWith("/publish")), false);
    await save({ title: "Corrected event" }, cover);
    assert.equal(calls.filter((path) => path === "/api/events/drafts").length, 1);
    assert.equal(calls.filter((path) => path === "/api/media").length, 1);
    assert.equal(calls.at(-1), "/api/events/event-1/publish");
});

test("editing keeps an unchanged cover and removes it only on explicit request", async (t) => {
    const calls = [];
    t.mock.method(globalThis, "fetch", async (url, options) => {
        calls.push({ path: url.pathname, body: JSON.parse(options.body) });
        return Response.json({ id: "event-1", cover_media_id: url.pathname.endsWith("/cover") ? null : "original" });
    });
    const save = createEventSaver("owner-1", "event-1");
    assert.equal((await save({ title: "Edit" }, { kind: "keep" })).cover_media_id, "original");
    assert.equal(calls.length, 1);
    assert.equal((await save({ title: "Edit" }, { kind: "remove" })).cover_media_id, null);
    assert.deepEqual(calls.at(-1), { path: "/api/events/event-1/cover", body: { media_id: null } });
    assert.equal(calls.some(({ path }) => path.endsWith("/publish")), false);
});

test("a rejected upload leaves a reusable draft that can be published without an image", async (t) => {
    const calls = [];
    t.mock.method(globalThis, "fetch", async (url) => {
        calls.push(url.pathname);
        if (url.pathname === "/api/media") {
            return Response.json({ detail: "Invalid or corrupt image" }, { status: 415 });
        }
        return Response.json({ id: "event-1" });
    });
    const save = createEventSaver("owner-1");
    await assert.rejects(save({ title: "Event" }, {
        kind: "file", file: new File(["bad image"], "cover.png"),
    }), /пока не опубликовано/);
    assert.equal(calls.some((path) => path.endsWith("/publish")), false);
    await save({ title: "Event" }, { kind: "remove" });
    assert.equal(calls.filter((path) => path === "/api/events/drafts").length, 1);
    assert.equal(calls.filter((path) => path === "/api/media").length, 1);
    assert.equal(calls.at(-1), "/api/events/event-1/publish");
});
