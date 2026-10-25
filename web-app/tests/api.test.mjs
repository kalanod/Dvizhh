import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { after, test } from "node:test";
import ts from "typescript";

const output = mkdtempSync(join(tmpdir(), "dvizh-api-test-"));
writeFileSync(join(output, "package.json"), '{"type":"commonjs"}');
for (const name of ["client", "events", "media", "personal"]) {
    const source = readFileSync(new URL(`../src/api/${name}.ts`, import.meta.url), "utf8");
    const { outputText } = ts.transpileModule(source, {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    });
    writeFileSync(join(output, `${name}.js`), outputText);
}
const require = createRequire(import.meta.url);
const api = require(join(output, "events.js"));
const { ApiError } = require(join(output, "client.js"));
const media = require(join(output, "media.js"));
const personal = require(join(output, "personal.js"));
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

const recordFetch = (t, respond = () => Response.json({})) => {
    const calls = [];
    t.mock.method(globalThis, "fetch", async (url, options = {}) => {
        calls.push({ url, options, body: options.body === undefined ? undefined : options.body });
        return respond(url, options);
    });
    return calls;
};

test("lifecycle calls send actor_id in the body", async (t) => {
    const calls = recordFetch(t);
    await api.publishEvent("event-1", "owner-1");
    await api.cancelEvent("event-1", "owner-1");
    await api.createDraft({ title: "Draft", organizer_id: "owner-1" });
    assert.deepEqual(
        calls.map(({ url, options }) => [options.method, url.pathname]),
        [
            ["POST", "/api/events/event-1/publish"],
            ["POST", "/api/events/event-1/cancel"],
            ["POST", "/api/events/drafts"],
        ],
    );
    assert.deepEqual(JSON.parse(calls[0].body), { actor_id: "owner-1" });
    assert.deepEqual(JSON.parse(calls[1].body), { actor_id: "owner-1" });
});

test("favorites and dismissed toggle with PUT and DELETE", async (t) => {
    const calls = recordFetch(t);
    await personal.setFavorite("user-1", "event-1", true);
    await personal.setFavorite("user-1", "event-1", false);
    await personal.setDismissed("user-1", "event-1", true);
    await personal.setDismissed("user-1", "event-1", false);
    assert.deepEqual(
        calls.map(({ url, options }) => [options.method, url.pathname]),
        [
            ["PUT", "/api/users/user-1/favorites/event-1"],
            ["DELETE", "/api/users/user-1/favorites/event-1"],
            ["PUT", "/api/users/user-1/dismissed/event-1"],
            ["DELETE", "/api/users/user-1/dismissed/event-1"],
        ],
    );
});

test("notifications: unread filter, paging and mark read", async (t) => {
    const calls = recordFetch(t, () => Response.json([]));
    await personal.listNotifications("user-1", { unreadOnly: true, limit: 100 });
    await personal.listNotifications("user-1");
    await personal.markNotificationRead("user-1", "note-1");
    assert.equal(calls[0].url.pathname, "/api/users/user-1/notifications");
    assert.equal(calls[0].url.searchParams.get("unread_only"), "true");
    assert.equal(calls[0].url.searchParams.get("limit"), "100");
    assert.equal(calls[1].url.searchParams.has("unread_only"), false);
    assert.equal(calls[2].options.method, "PUT");
    assert.equal(calls[2].url.pathname, "/api/users/user-1/notifications/note-1/read");
});

test("personal lists and invitation answers use the backend contract", async (t) => {
    const calls = recordFetch(t, () => Response.json([]));
    await personal.listMyEvents("user-1", "requested", { limit: 20 });
    await personal.listFriendRequests("user-1", "outgoing");
    await personal.respondToInvitation("inv-1", "user-1", false);
    await api.inviteToEvent("event-1", { actor_id: "owner-1", invitee_id: "user-1", message: null });
    assert.equal(calls[0].url.searchParams.get("kind"), "requested");
    assert.equal(calls[1].url.searchParams.get("direction"), "outgoing");
    assert.equal(calls[2].options.method, "PATCH");
    assert.equal(calls[2].url.pathname, "/api/invitations/inv-1");
    assert.deepEqual(JSON.parse(calls[2].body), { user_id: "user-1", accept: false });
    assert.equal(calls[3].url.pathname, "/api/events/event-1/invitations");
    assert.deepEqual(JSON.parse(calls[3].body), { actor_id: "owner-1", invitee_id: "user-1", message: null });
});

test("media upload sends raw bytes, not JSON", async (t) => {
    const calls = recordFetch(t, () => Response.json({ id: "media-1" }, { status: 201 }));
    const file = new File([new Uint8Array([1, 2, 3])], "photo.png", { type: "image/png" });
    const uploaded = await media.uploadMedia("user-1", file);
    await media.setCover("event-1", "owner-1", null);
    assert.equal(uploaded.id, "media-1");
    assert.equal(calls[0].url.searchParams.get("user_id"), "user-1");
    assert.equal(calls[0].url.searchParams.get("filename"), "photo.png");
    assert.equal(calls[0].options.headers["Content-Type"], "application/octet-stream");
    assert.equal(calls[0].body, file);
    assert.equal(calls[1].url.searchParams.get("actor_id"), "owner-1");
    assert.deepEqual(JSON.parse(calls[1].body), { media_id: null });
    assert.equal(media.mediaSrc("/api/media/m/content", "u 1"), "/api/media/m/content?viewer_id=u%201");
    assert.equal(media.mediaSrc(null, "u"), null);
});

test("oversized upload gets a readable message", async (t) => {
    recordFetch(t, () => new Response("<html>413</html>", { status: 413 }));
    const file = new File([new Uint8Array([1])], "big.png");
    await assert.rejects(media.uploadMedia("user-1", file), (error) =>
        error instanceof ApiError && error.status === 413 && error.message === "Файл слишком большой.");
});

test("abort signal reaches fetch and stays out of the query", async (t) => {
    const calls = recordFetch(t, () => Response.json([]));
    const controller = new AbortController();
    await api.listEvents({ limit: 20 }, controller.signal);
    await personal.listNotifications("user-1", { unreadOnly: true, limit: 10, signal: controller.signal });
    for (const { url, options } of calls) {
        assert.equal(options.signal, controller.signal);
        assert.equal(url.searchParams.has("signal"), false);
    }
    assert.equal(calls[1].url.searchParams.get("limit"), "10");
});

test("aborted request is rethrown as AbortError, not a network error", async (t) => {
    t.mock.method(globalThis, "fetch", async (_url, { signal }) => {
        signal.throwIfAborted();
        return Response.json([]);
    });
    const controller = new AbortController();
    controller.abort();
    await assert.rejects(api.getEvent("event-1", null, controller.signal), (error) =>
        !(error instanceof ApiError) && error.name === "AbortError");
});
