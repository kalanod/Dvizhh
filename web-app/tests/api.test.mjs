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
for (const name of ["components/ui/Button/Button", "components/pages/EventFormPage/formState", "api/paging", "api/client", "api/personal", "api/events", "api/media", "api/eventCover", "api/profileImage", "utils/media", "utils/format", "components/widgets/EventCard/EventCoverMicro", "components/ui/Avatar/Avatar"]) {
    const extension = name.startsWith("components/") && !name.endsWith("formState") ? "tsx" : "ts";
    const source = readFileSync(new URL(`../src/${name}.${extension}`, import.meta.url), "utf8");
    const { outputText } = ts.transpileModule(source, {
        fileName: `${name}.${extension}`,
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
    });
    const target = join(output, `${name}.js`);
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, outputText);
}
const require = createRequire(import.meta.url);
const personal = require(join(output, "api/personal.js"));
const api = require(join(output, "api/events.js"));
const media = require(join(output, "api/media.js"));
const { createEventSaver } = require(join(output, "api/eventCover.js"));
const { createAvatarSaver } = require(join(output, "api/profileImage.js"));
const { Avatar } = require(join(output, "components/ui/Avatar/Avatar.js"));
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
        const event = { cover_url: "/api/media/cover-1/content", personal_state: state };
        return Response.json(url.pathname === "/api/events" ? [event] : event);
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

test("avatar assignment and removal return the updated profile", async (t) => {
    const ids = [];
    t.mock.method(globalThis, "fetch", async (url, options) => {
        assert.equal(url.pathname, "/api/users/owner-1/avatar");
        assert.equal(options.method, "PUT");
        const id = JSON.parse(options.body).media_id;
        ids.push(id);
        return Response.json({ id: "owner-1", avatar_url: id ? `/api/media/${id}/content` : null });
    });
    assert.equal((await media.setAvatar("owner-1", "photo-1")).avatar_url, "/api/media/photo-1/content");
    assert.equal((await media.setAvatar("owner-1", null)).avatar_url, null);
    assert.deepEqual(ids, ["photo-1", null]);
});

test("retrying an avatar assignment reuses its uploaded image", async (t) => {
    const calls = [];
    let fail = true;
    t.mock.method(globalThis, "fetch", async (url, options) => {
        calls.push(url.pathname);
        if (url.pathname === "/api/media") return Response.json({ id: "photo-1" });
        if (fail) {
            fail = false;
            return Response.json({ detail: "Temporarily unavailable" }, { status: 503 });
        }
        const id = JSON.parse(options.body).media_id;
        return Response.json({ id: "owner-1", avatar_media_id: id, avatar_url: id ? `/api/media/${id}/content` : null });
    });
    const save = createAvatarSaver("owner-1");
    const selection = { kind: "file", file: new File(["image"], "avatar.png") };
    await assert.rejects(save(selection), (error) => error.status === 503);
    const updated = await save(selection);
    assert.equal(updated.avatar_url, "/api/media/photo-1/content");
    assert.equal(calls.filter((path) => path === "/api/media").length, 1);
    assert.equal((await save({ kind: "remove" })).avatar_url, null);
    assert.equal(calls.filter((path) => path === "/api/media").length, 1);
});

test("failed avatar uploads do not replace the current profile image", async (t) => {
    const calls = [];
    t.mock.method(globalThis, "fetch", async (url) => {
        calls.push(url.pathname);
        return Response.json({ detail: "Invalid or corrupt image" }, { status: 415 });
    });
    const save = createAvatarSaver("owner-1");
    await assert.rejects(save({ kind: "file", file: new File(["bad"], "avatar.png") }), (error) => error.status === 415);
    assert.deepEqual(calls, ["/api/media"]);
});

test("avatars render profile photos at every size and fall back to initials", () => {
    for (const size of ["sm", "md", "lg"]) {
        const image = renderToStaticMarkup(createElement(Avatar, {
            name: "Анна", size, src: "/api/media/photo-1/content",
        }));
        assert.match(image, /<img/);
        assert.match(image, /\/api\/media\/photo-1\/content/);
        assert.match(image, /object-cover/);
        const initial = renderToStaticMarkup(createElement(Avatar, { name: "  Анна", size }));
        assert.doesNotMatch(initial, /<img/);
        assert.match(initial, />А<\//);
    }
    assert.match(renderToStaticMarkup(createElement(Avatar, { name: "" })), />\?<\//);
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
    await api.createDraftEvent({ title: "Draft", organizer_id: "owner-1" });
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
    const uploaded = await media.uploadImage("user-1", file);
    await media.setEventCover("event-1", "owner-1", null);
    assert.equal(uploaded.id, "media-1");
    assert.equal(calls[0].url.searchParams.get("user_id"), "user-1");
    assert.equal(calls[0].url.searchParams.get("filename"), "photo.png");
    assert.equal(calls[0].options.headers["Content-Type"], "application/octet-stream");
    assert.equal(calls[0].body, file);
    assert.equal(calls[1].url.searchParams.get("actor_id"), "owner-1");
    assert.deepEqual(JSON.parse(calls[1].body), { media_id: null });
    assert.equal(mediaContentUrl("/api/media/m/content", "u 1"), "/api/media/m/content?viewer_id=u%201");
    assert.equal(mediaContentUrl(null, "u"), null);
});

test("oversized upload gets a readable message", async (t) => {
    recordFetch(t, () => new Response("<html>413</html>", { status: 413 }));
    const file = new File([new Uint8Array([1])], "big.png");
    await assert.rejects(media.uploadImage("user-1", file), (error) =>
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


test("draft save does not publish, retry can publish the same draft", async (t) => {
    const calls = recordFetch(t, (url) => Response.json({ id: "draft-1", status: url.pathname.endsWith("/publish") ? "PUBLISHED" : "DRAFT" }));
    const save = createEventSaver("owner-1");
    const draft = await save({ title: "Draft" }, { kind: "keep" }, false);
    assert.equal(draft.status, "DRAFT");
    assert.deepEqual(calls.map(({ url }) => url.pathname), ["/api/events/drafts"]);
    await save({ title: "Final" }, { kind: "keep" }, true);
    assert.deepEqual(calls.map(({ url }) => url.pathname), ["/api/events/drafts", "/api/events/draft-1", "/api/events/draft-1/publish"]);
});

test("lists cross the 100 record boundary with bounded pages", async (t) => {
    const calls = recordFetch(t, (url) => {
        const offset = Number(url.searchParams.get("offset"));
        const limit = Number(url.searchParams.get("limit"));
        return Response.json(Array.from({ length: Math.min(limit, Math.max(0, 125 - offset)) }, (_, i) => ({ id: offset + i })));
    });
    for (const load of [() => api.listEvents({ limit: 140 }), () => personal.listFavorites("user-1", { limit: 140 })]) {
        const items = await load();
        assert.equal(items.length, 125);
        assert.equal(items.at(-1).id, 124);
    }
    assert.deepEqual(calls.map(({ url }) => [url.searchParams.get("offset"), url.searchParams.get("limit")]), [["0", "100"], ["100", "40"], ["0", "100"], ["100", "40"]]);
});

test("invitation expiry, revocation, sent list and rejection reason follow the API contract", async (t) => {
    const calls = recordFetch(t, () => Response.json([]));
    await api.inviteToEvent("event-1", { actor_id: "owner-1", invitee_id: "stranger-1", message: "Hello", expires_at: "2030-01-01T00:00:00Z" });
    await personal.listEventInvitations("event-1", "owner-1", { offset: 100, limit: 20 });
    await personal.revokeInvitation("inv-1", "owner-1");
    await api.reviewParticipation("event-1", "user-1", "owner-1", false, "No places");
    assert.equal(JSON.parse(calls[0].body).expires_at, "2030-01-01T00:00:00Z");
    assert.equal(calls[1].url.searchParams.get("actor_id"), "owner-1");
    assert.equal(calls[1].url.searchParams.get("offset"), "100");
    assert.equal(calls[2].options.method, "DELETE");
    assert.equal(calls[2].url.searchParams.get("actor_id"), "owner-1");
    assert.equal(JSON.parse(calls[3].body).reason, "No places");
});

test("event wall times use the selected zone and reject DST gaps", () => {
    const { fromDateTimeLocal, toDateTimeLocal } = require(join(output, "utils/format.js"));
    assert.equal(fromDateTimeLocal("2030-01-01T12:00", "Asia/Tokyo"), "2030-01-01T03:00:00.000Z");
    assert.equal(toDateTimeLocal("2030-01-01T03:00:00Z", "Asia/Tokyo"), "2030-01-01T12:00");
    assert.equal(fromDateTimeLocal("2026-07-01T12:00", "America/New_York"), "2026-07-01T16:00:00.000Z");
    assert.throws(() => fromDateTimeLocal("2026-03-08T02:30", "America/New_York"));
});


test("event edits preserve currency and local time in a different zone", () => {
    const { emptyForm, formToInput, formFromEvent, validateForm } = require(join(output, "components/pages/EventFormPage/formState.js"));
    const original = { ...formToInput({ ...emptyForm(), title: "Tokyo", startsAt: "2030-01-01T12:00", timezone: "Asia/Tokyo", currency: "JPY", priceMin: "500" }), price_type: "PAID" };
    const form = formFromEvent(original);
    assert.equal(form.startsAt, "2030-01-01T12:00");
    assert.equal(form.currency, "JPY");
    assert.equal(validateForm(form), null);
    assert.equal(formToInput(form).currency, "JPY");
    assert.equal(formToInput(form).starts_at, original.starts_at);
    assert.notEqual(validateForm({ ...form, timezone: "Invalid/Zone" }), null);
    assert.notEqual(validateForm({ ...form, currency: "XX" }), null);
});

test("draft submit button passes its action to the native button", () => {
    const { Button } = require(join(output, "components/ui/Button/Button.js"));
    const html = renderToStaticMarkup(createElement(Button, { type: "submit", action: "draft" }, "Save draft"));
    assert.match(html, /data-action="draft"/);
    assert.match(html, /type="submit"/);
});
