import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { after, test } from "node:test";
import ts from "typescript";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

const testRoot = fileURLToPath(new URL("../node_modules/.tmp/", import.meta.url));
mkdirSync(testRoot, { recursive: true });
const output = mkdtempSync(join(testRoot, "dvizh-api-test-"));
writeFileSync(join(output, "package.json"), '{"type":"commonjs"}');
for (const name of [
    "components/ui/Button/Button",
    "components/pages/EventFormPage/formState",
    "components/pages/EventFormPage/eventPlace",
    "api/paging",
    "api/client",
    "api/auth",
    "api/settings",
    "components/pages/AdminPanelPage/settingsState",
    "api/users",
    "api/registration",
    "api/profileAccount",
    "api/personal",
    "api/events",
    "api/tags",
    "api/media",
    "api/eventCover",
    "api/profileImage",
    "utils/media",
    "utils/format",
    "utils/tags",
    "utils/hashtags",
    "components/ui/EventTitle/EventTitle",
    "components/widgets/EventCard/EventCoverMicro",
    "components/ui/Avatar/Avatar",
    "api/maps",
    "api/discovery",
    "utils/discovery",
    "utils/discoveryCamera",
    "utils/mapMarkers",
    "utils/yandexMaps",
    "utils/geolocation",
    "components/widgets/SortMenu/SortMenu",
    "components/ui/Input/Input",
    "components/ui/ImageViewer/ImageViewer",
    "components/ui/FormField/context",
    "hooks/useFieldValidation",
]) {
    const extension = name.startsWith("components/") && !["formState", "settingsState", "eventPlace", "context"].some((suffix) => name.endsWith(suffix)) ? "tsx" : "ts";
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
const auth = require(join(output, "api/auth.js"));
const settings = require(join(output, "api/settings.js"));
const settingsState = require(join(output, "components/pages/AdminPanelPage/settingsState.js"));
const { registerProfile } = require(join(output, "api/registration.js"));
const { saveProfileWithAccount } = require(join(output, "api/profileAccount.js"));
const api = require(join(output, "api/events.js"));
const catalog = require(join(output, "api/tags.js"));
const { toggleEventTag, MAX_EVENT_TAGS, tagColorStyle } = require(join(output, "utils/tags.js"));
const { splitHashtags, isHashtag, hashtagSearchUrl } = require(join(output, "utils/hashtags.js"));
const { EventTitle } = require(join(output, "components/ui/EventTitle/EventTitle.js"));
const { formatEventDate } = require(join(output, "utils/format.js"));
const media = require(join(output, "api/media.js"));
const { createEventSaver } = require(join(output, "api/eventCover.js"));
const { createAvatarSaver } = require(join(output, "api/profileImage.js"));
const { Avatar } = require(join(output, "components/ui/Avatar/Avatar.js"));
const { mediaContentUrl, validateCoverFile } = require(join(output, "utils/media.js"));
const { EventCoverMicro, EventCoverMain } = require(join(output, "components/widgets/EventCard/EventCoverMicro.js"));
const { ApiError } = require(join(output, "api/client.js"));
const maps = require(join(output, "api/maps.js"));
const places = require(join(output, "components/pages/EventFormPage/eventPlace.js"));
const { currentCoordinates } = require(join(output, "utils/geolocation.js"));
const { SortMenu } = require(join(output, "components/widgets/SortMenu/SortMenu.js"));
const { Input } = require(join(output, "components/ui/Input/Input.js"));
const { locationCoordinates, loadYandexMaps, reportMapError } = require(join(output, "utils/yandexMaps.js"));
const { emptyForm, formToInput, formFromEvent, updateEventSchedule, validateForm, validateFormFields } = require(join(output, "components/pages/EventFormPage/formState.js"));

test("event validation associates simultaneous errors with fields and follows format changes", () => {
    const form = { ...emptyForm(), timezone: "Europe/Moscow" };
    assert.deepEqual(Object.keys(validateFormFields(form)), ["title", "startsAt", "place"]);
    const online = { ...form, title: "Meeting", startsAt: "2030-06-12T10:00", format: "ONLINE" };
    assert.deepEqual(Object.keys(validateFormFields(online)), ["onlineUrl"]);
    assert.deepEqual(validateFormFields({ ...online, onlineUrl: "https://example.com" }), {});
    const hybrid = { ...online, format: "HYBRID", endsAt: "2030-06-12T09:00" };
    assert.deepEqual(Object.keys(validateFormFields(hybrid)), ["endsAt", "place", "onlineUrl"]);
    const dstGap = { ...online, onlineUrl: "https://example.com", timezone: "Europe/Berlin", startsAt: "2030-03-31T02:30" };
    assert.deepEqual(Object.keys(validateFormFields(dstGap)), ["startsAt"]);
});
const originalWindow = globalThis.window;
globalThis.window = { location: { origin: "http://localhost:8080" } };
after(() => {
    if (originalWindow === undefined) delete globalThis.window;
    else globalThis.window = originalWindow;
    assert.equal(dirname(output), resolve(testRoot));
    assert.ok(basename(output).startsWith("dvizh-api-test-"));
    rmSync(output, { recursive: true, force: true });
});

test("title hashtags support Unicode, underscores, punctuation and safe search URLs", () => {
    const title = "Встреча (#испанские_слизни), #Music2026! #東京_2";
    const parts = splitHashtags(title);
    assert.equal(parts.join(""), title);
    assert.deepEqual(parts.filter(isHashtag), ["#испанские_слизни", "#Music2026", "#東京_2"]);
    assert.deepEqual(splitHashtags("слово#тег ##тег # !").filter(isHashtag), []);
    const url = new URL(hashtagSearchUrl("#испанские_слизни"), "http://localhost");
    assert.equal(url.searchParams.get("q"), "#испанские_слизни");
    assert.equal(url.hash, "");
});

test("event title renders real search links and escapes surrounding text", () => {
    const html = renderToStaticMarkup(createElement(MemoryRouter, null,
        createElement(EventTitle, { title: '<script> #испанские_слизни & #music' })));
    assert.ok(html.includes("&lt;script&gt;"));
    assert.equal((html.match(/<a /g) ?? []).length, 2);
    assert.ok(html.includes(`href="${hashtagSearchUrl("#испанские_слизни")}"`));
    assert.ok(html.includes("Найти события с хештегом #испанские_слизни"));
});

test("hashtag search is sent intact to the event feed", async (t) => {
    const calls = recordFetch(t, () => Response.json([]));
    await api.listEvents({ q: "#испанские_слизни" });
    assert.equal(calls[0].url.searchParams.get("q"), "#испанские_слизни");
    assert.equal(calls[0].url.hash, "");
});

test("event dates show years for future events and both ends of date ranges in the event zone", () => {
    const base = { starts_at: "2027-06-12T15:00:00Z", ends_at: null, is_all_day: false, timezone: "Europe/Moscow" };
    const single = formatEventDate(base);
    assert.match(single, /2027/);
    assert.match(single, /18:00/);
    const sameDay = formatEventDate({ ...base, ends_at: "2027-06-12T18:00:00Z" });
    assert.match(sameDay, /2027/);
    assert.match(sameDay, /18:00–21:00/);
    assert.match(formatEventDate({ ...base, is_all_day: true }), /2027.*весь день/);

    const yearBoundary = { ...base, starts_at: "2027-12-31T20:00:00Z", ends_at: "2027-12-31T22:00:00Z" };
    const timedRange = formatEventDate(yearBoundary);
    assert.match(timedRange, /2027.*23:00.*2028.*01:00/);
    assert.match(formatEventDate({ ...yearBoundary, is_all_day: true }), /2027.*2028/);
    // В UTC ещё 31 декабря, но местная дата начала уже в следующем году.
    assert.match(formatEventDate({ ...base, starts_at: "2027-12-31T22:00:00Z" }), /2028/);
});

test("password change delegates through backend with unchanged secrets and protected writes", async (t) => {
    const calls = recordFetch(t, () => new Response(null, { status: 204 }));
    await auth.changePassword({ current_password: " old password ", new_password: " new password " });
    assert.equal(calls[0].url.pathname, "/api/personal/password");
    assert.equal(calls[0].options.method, "POST");
    assert.equal(calls[0].options.headers["X-Dvizh-Account"], "1");
    assert.deepEqual(JSON.parse(calls[0].options.body), { current_password: " old password ", new_password: " new password " });
});

test("account API uses username or email login, optional email and protected updates", async (t) => {
    const calls = recordFetch(t, () => Response.json({ id: "u", username: "alice", email: null, role: "user" }));
    await auth.registerAccount({ username: " Alice ", email: "   ", password: "password" });
    await auth.registerAccount({ username: " Alice ", password: "password" });
    await auth.registerAccount({ username: " Alice ", email: " A@Example.COM ", password: "password" });
    await auth.loginAccount({ login: " ADMIN ", password: "admin" });
    await auth.loginAccount({ login: " A@Example.COM ", password: "password" });
    await auth.updateAccount({ username: " New_Name ", email: " " });
    assert.deepEqual(JSON.parse(calls[0].body), { username: "alice", email: null, password: "password" });
    assert.equal(JSON.parse(calls[1].body).email, null);
    assert.equal(JSON.parse(calls[2].body).email, "a@example.com");
    assert.deepEqual(JSON.parse(calls[3].body), { login: "admin", password: "admin" });
    assert.equal(JSON.parse(calls[4].body).login, "a@example.com");
    assert.equal(calls[5].options.method, "PATCH");
    assert.equal(calls[5].url.pathname, "/api/auth/me");
    assert.equal(calls[5].options.headers["X-Dvizh-Account"], "1");
    assert.equal(calls[5].options.headers["Content-Type"], "application/json");
    assert.equal(calls[5].options.credentials, "same-origin");
    assert.deepEqual(JSON.parse(calls[5].body), { username: "new_name", email: null });
});

test("partial registration resumes only after authenticating the desired username", async (t) => {
    const calls = recordFetch(t, (url, options) => {
        if (url.pathname === "/api/auth/register") return Response.json({ detail: "Username is already registered" }, { status: 409 });
        if (url.pathname === "/api/auth/login") return new Response(null, { status: 204 });
        if (url.pathname === "/api/auth/me") return Response.json({ id: "u", username: "alice", email: null, role: "user" });
        if (options.method === "GET") return Response.json({ detail: "Not found" }, { status: 404 });
        return Response.json({ id: "u", ...JSON.parse(options.body) }, { status: 201 });
    });
    const profile = await registerProfile({ username: " Alice ", email: "", password: "password" }, { display_name: "Alice", bio: null, city: null });
    assert.equal(profile.username, "alice");
    assert.equal(JSON.parse(calls[1].body).login, "alice");
    assert.equal(JSON.parse(calls[4].body).id, "u");
    assert.equal(JSON.parse(calls[4].body).username, "alice");
});

test("registration conflicts do not create a profile for another account", async (t) => {
    const calls = recordFetch(t, (url) => {
        if (url.pathname === "/api/auth/register") return Response.json({ detail: "Email is already registered" }, { status: 409 });
        return Response.json({ detail: "Invalid login or password" }, { status: 401 });
    });
    await assert.rejects(registerProfile({ username: "alice", email: "taken@example.com", password: "wrong" }, { display_name: "Alice", bio: null, city: null }), /email уже зарегистрирован/);
    assert.equal(calls.length, 2);
    t.mock.method(globalThis, "fetch", async (url) => {
        if (url.pathname === "/api/auth/register") return Response.json({ id: "u", username: "alice", email: null });
        if (url.pathname === "/api/auth/login") return new Response(null, { status: 204 });
        if (url.pathname === "/api/auth/me") return Response.json({ id: "other", username: "other", email: null, role: "user" });
        throw new Error("Must not access another profile");
    });
    await assert.rejects(registerProfile({ username: "alice", password: "password" }, { display_name: "Alice", bio: null, city: null }), /подтвердить никнейм/);
});

test("profile nickname updates auth first and retries only the unsaved profile", async (t) => {
    let currentUsername = "old_name";
    let profileAttempts = 0;
    const calls = recordFetch(t, (url, options) => {
        if (url.pathname === "/api/auth/me") {
            if (options.method === "PATCH") currentUsername = JSON.parse(options.body).username;
            return Response.json({ id: "u", username: currentUsername, email: null, role: "user" });
        }
        profileAttempts += 1;
        return profileAttempts === 1
            ? Response.json({ detail: "Try again" }, { status: 503 })
            : Response.json({ id: "u", ...JSON.parse(options.body) });
    });
    const input = { username: " New_Name ", display_name: "New name" };
    await assert.rejects(saveProfileWithAccount("u", "old_name", input), /Никнейм для входа уже изменён на «new_name»/);
    assert.equal(currentUsername, "new_name");
    const profile = await saveProfileWithAccount("u", "old_name", input);
    assert.equal(profile.username, "new_name");
    assert.equal(calls.filter((call) => call.url.pathname === "/api/auth/me" && call.options.method === "PATCH").length, 1);
    assert.deepEqual(calls.map((call) => [call.url.pathname, call.options.method]), [
        ["/api/auth/me", "GET"], ["/api/auth/me", "PATCH"], ["/api/users/u", "PATCH"],
        ["/api/auth/me", "GET"], ["/api/users/u", "PATCH"],
    ]);
});

test("failed auth rename never changes the profile", async (t) => {
    const calls = recordFetch(t, (_url, options) => options.method === "GET"
        ? Response.json({ id: "u", username: "old_name", email: null, role: "user" })
        : Response.json({ detail: "Username is already registered" }, { status: 409 }));
    await assert.rejects(saveProfileWithAccount("u", "old_name", { username: "taken" }), /никнейм уже занят/);
    assert.equal(calls.length, 2);
});

test("profile nickname conflict after auth rename asks for another nickname", async (t) => {
    let username = "old_name";
    recordFetch(t, (url, options) => {
        if (url.pathname === "/api/auth/me") {
            if (options.method === "PATCH") username = JSON.parse(options.body).username;
            return Response.json({ id: "u", username, email: null, role: "user" });
        }
        return Response.json({ detail: "Username already exists" }, { status: 409 });
    });
    await assert.rejects(saveProfileWithAccount("u", "old_name", { username: "orphan_name" }), (error) => {
        assert.match(error.message, /Никнейм для входа уже изменён на «orphan_name»/);
        assert.match(error.message, /Выберите другой никнейм/);
        assert.doesNotMatch(error.message, /Повторите сохранение/);
        return true;
    });
});

test("profile email clearing updates only auth and omitted email is preserved", async (t) => {
    let account = { id: "u", username: "alice", email: "old@example.com", role: "user" };
    const calls = recordFetch(t, (url, options) => {
        if (url.pathname === "/api/auth/me") {
            if (options.method === "PATCH") account = { ...account, ...JSON.parse(options.body) };
            return Response.json(account);
        }
        return Response.json({ id: "u", ...JSON.parse(options.body) });
    });
    await saveProfileWithAccount("u", "alice", { username: "alice", city: "City" }, " ");
    assert.equal(account.email, null);
    assert.deepEqual(JSON.parse(calls[1].body), { email: null });
    assert.equal("email" in JSON.parse(calls[2].body), false);
    account.email = "keep@example.com";
    await saveProfileWithAccount("u", "alice", { username: "bob" });
    assert.deepEqual(JSON.parse(calls[4].body), { username: "bob" });
    assert.equal(account.email, "keep@example.com");
});

test("email saved before a profile failure produces a recoverable partial-save message", async (t) => {
    let email = null;
    let attempts = 0;
    const calls = recordFetch(t, (url, options) => {
        if (url.pathname === "/api/auth/me") {
            if (options.method === "PATCH") email = JSON.parse(options.body).email;
            return Response.json({ id: "u", username: "alice", email, role: "user" });
        }
        attempts += 1;
        return attempts === 1
            ? Response.json({ detail: "Try again" }, { status: 503 })
            : Response.json({ id: "u", ...JSON.parse(options.body) });
    });
    await assert.rejects(saveProfileWithAccount("u", "alice", { username: "alice" }, "new@example.com"), /Данные аккаунта для входа сохранены/);
    await saveProfileWithAccount("u", "alice", { username: "alice" }, "new@example.com");
    assert.equal(email, "new@example.com");
    assert.equal(calls.filter((call) => call.url.pathname === "/api/auth/me" && call.options.method === "PATCH").length, 1);
});

test("tag selection limits new choices and allows removing inactive tags", () => {
    const category = { id: "category-1", name: "Nature", color: "#228844", sort_order: 0 };
    const tags = Array.from({ length: 6 }, (_, index) => ({
        id: `tag-${index}`, slug: `tag-${index}`, name: `Tag ${index}`, is_active: true, category,
    }));
    let selected = [];
    for (const tag of tags) selected = toggleEventTag(selected, tag);
    assert.equal(selected.length, MAX_EVENT_TAGS);
    assert.equal(selected.some((tag) => tag.id === tags[5].id), false);
    selected = toggleEventTag(selected, tags[0]);
    selected = toggleEventTag(selected, tags[5]);
    assert.equal(selected.length, MAX_EVENT_TAGS);
    assert.equal(selected.some((tag) => tag.id === tags[5].id), true);
    const inactive = { ...tags[0], is_active: false };
    assert.deepEqual(toggleEventTag([inactive], inactive), []);
    assert.deepEqual(toggleEventTag([], inactive), []);
    const form = { ...emptyForm(), title: "Meeting", startsAt: "2030-01-01T12:00", place: places.textPlace("Street"), tags };
    assert.match(validateForm(form), /пяти тематик/);
    const body = formToInput({ ...form, tags: [tags[0], tags[0], tags[1]] });
    assert.deepEqual(body.tag_ids, [tags[0].id, tags[1].id]);
    assert.equal("tags" in body, false);
    assert.deepEqual(formFromEvent({ ...body, tags: [inactive] }).tags, [inactive]);
    assert.deepEqual(tagColorStyle("not a color"), { backgroundColor: "#64748b20", borderColor: "#64748b" });
});

test("tag catalog and feed filter use stable IDs", async (t) => {
    const calls = recordFetch(t, () => Response.json([]));
    const controller = new AbortController();
    await catalog.listTags(controller.signal);
    await api.listEvents({ tagId: "tag-id", limit: 20 });
    assert.equal(calls[0].url.pathname, "/api/tags");
    assert.equal(calls[0].options.signal, controller.signal);
    assert.equal(calls[1].url.searchParams.get("tag_id"), "tag-id");
    assert.equal(calls[1].url.searchParams.has("tag"), false);
});

test("device geolocation returns map coordinates in longitude-latitude order", async (t) => {
    const descriptor = Object.getOwnPropertyDescriptor(navigator, "geolocation");
    t.after(() => {
        if (descriptor) Object.defineProperty(navigator, "geolocation", descriptor);
        else delete navigator.geolocation;
    });
    Object.defineProperty(navigator, "geolocation", { configurable: true, value: {
        getCurrentPosition(success, _failure, options) {
            assert.equal(options.enableHighAccuracy, true);
            assert.ok(options.timeout > 0);
            success({ coords: { longitude: 30.315868, latitude: 59.939095 } });
        },
    } });
    assert.deepEqual(await currentCoordinates(), [30.315868, 59.939095]);
});

test("geolocation denial, unavailable position and timeout produce readable errors", async (t) => {
    const descriptor = Object.getOwnPropertyDescriptor(navigator, "geolocation");
    t.after(() => {
        if (descriptor) Object.defineProperty(navigator, "geolocation", descriptor);
        else delete navigator.geolocation;
    });
    for (const [code, expected] of [[1, /Доступ.*запрещён/], [2, /Не удалось определить/], [3, /слишком много времени/]]) {
        Object.defineProperty(navigator, "geolocation", { configurable: true, value: {
            getCurrentPosition(_success, failure) { failure({ code }); },
        } });
        await assert.rejects(currentCoordinates(), expected);
    }
});

test("venue selection preserves latitude and longitude across API, form and map", () => {
    const form = { ...emptyForm(), title: "Встреча", startsAt: "2026-12-01T18:00" };
    assert.equal(places.placeCoordinates(form.place), null);
    assert.match(validateForm(form), /Укажите адрес/);
    form.place = places.placeFromGeocode({
        latitude: "59.9390954", longitude: "30.3158682",
        city: "Санкт-Петербург", address_line: "Невский проспект, 1", name: "Вход со двора",
    });
    assert.equal(validateForm(form), null);
    const body = formToInput(form);
    assert.deepEqual(body.location, {
        latitude: "59.939095", longitude: "30.315868", name: "Вход со двора",
        city: "Санкт-Петербург", address_line: "Невский проспект, 1",
    });
    assert.deepEqual(locationCoordinates(body.location.latitude, body.location.longitude), [30.315868, 59.939095]);
    const restored = formFromEvent(body);
    assert.deepEqual(places.placeToLocation(restored.place), body.location);
    assert.equal(restored.place.text, "Вход со двора, Невский проспект, 1, Санкт-Петербург");
    form.format = "ONLINE";
    form.onlineUrl = "https://example.org/meet";
    assert.equal(formToInput(form).location, null);
    assert.equal(places.placeCoordinates(formFromEvent(formToInput(form)).place), null);
    assert.equal(locationCoordinates("", ""), null);
    assert.equal(locationCoordinates("0", "0")[0], 0);
});

test("manual addresses remain valid without keys or when Yandex requests fail", async (t) => {
    const form = {
        ...emptyForm(), title: "Meeting", startsAt: "2026-12-01T18:00",
        place: places.textPlace("  Main street, 10  "),
    };
    const assertAddressOnly = () => {
        assert.equal(validateForm(form), null);
        const body = formToInput(form);
        assert.equal(body.location.address_line, "Main street, 10");
        assert.equal(body.location.latitude, null);
        assert.equal(body.location.longitude, null);
        const restored = formFromEvent(body);
        assert.equal(restored.place.text, "Main street, 10");
        assert.equal(places.placeCoordinates(restored.place), null);
        assert.equal(body.location.name, null);
        assert.equal(body.location.city, null);
    };
    t.mock.method(globalThis, "fetch", async () => Response.json({ api_key: "", search_enabled: false }));
    assert.equal((await maps.getMapsConfig()).api_key, "");
    assertAddressOnly();
    t.mock.method(globalThis, "fetch", async () => Response.json({ detail: "Provider unavailable" }, { status: 503 }));
    await assert.rejects(maps.suggestAddresses(form.place.text, "Test city"));
    await assert.rejects(maps.geocodeAddress(form.place.text));
    assertAddressOnly();
    form.format = "HYBRID";
    form.onlineUrl = "https://example.org/live";
    assertAddressOnly();
    form.place = places.textPlace("   ");
    assert.notEqual(validateForm(form), null);
});

test("address lookup sends the selected Yandex uri and abort signal", async (t) => {
    const urls = [];
    const controller = new AbortController();
    t.mock.method(globalThis, "fetch", async (url, options) => {
        urls.push(url);
        assert.equal(options.signal, controller.signal);
        return Response.json(url.pathname.endsWith("suggest") ? [] : { latitude: "59", longitude: "30" });
    });
    await maps.suggestAddresses("Невский, 1", "Санкт-Петербург", controller.signal, [30.31, 59.93]);
    await maps.geocodeAddress("Россия, Санкт-Петербург", "ymapsbm1://geo?data=a&b=c", controller.signal);
    assert.equal(urls[0].pathname, "/api/maps/suggest");
    assert.equal(urls[0].searchParams.get("text"), "Невский, 1");
    assert.equal(urls[0].searchParams.get("city"), "Санкт-Петербург");
    assert.equal(urls[0].searchParams.get("longitude"), "30.31");
    assert.equal(urls[0].searchParams.get("latitude"), "59.93");
    assert.equal(urls[1].pathname, "/api/maps/geocode");
    assert.equal(urls[1].searchParams.get("uri"), "ymapsbm1://geo?data=a&b=c");
});

test("free-form venue descriptions never invent city, name or coordinates", () => {
    const selected = places.placeFromGeocode({
        name: "Cafe", address_line: "Tokyo, Shibuya 1", city: "Tokyo",
        latitude: "35.6591", longitude: "139.7006",
    });
    assert.equal(selected.text, "Cafe, Tokyo, Shibuya 1");
    const changed = places.textPlace("  У входа в парк, рядом с кафе  ");
    assert.deepEqual(places.placeToLocation(changed), {
        name: null, city: null, address_line: "У входа в парк, рядом с кафе",
        latitude: null, longitude: null,
    });
    assert.equal(places.placeCoordinates(changed), null);
    assert.equal(places.placeContextUnchanged(changed, selected), false);
    assert.equal(places.placeToLocation(places.textPlace("59.9, 30.3")).latitude, null);
    assert.deepEqual(places.placeToLocation(places.pointPlace([30.315868, 59.939095])), {
        name: null, city: null, address_line: null, latitude: "59.939095", longitude: "30.315868",
    });
});

test("unchanged stored venue keeps metadata and instant; resolved timezone changes wall-clock conversion only on edit", () => {
    const form = { ...emptyForm(), title: "Meet", startsAt: "2030-01-01T10:00", endsAt: "2030-01-01T11:00",
        timezone: "Asia/Tokyo", place: places.placeFromGeocode({ name: "Cafe", city: "Tokyo",
            address_line: "Tokyo, Shibuya 1", latitude: "35.6591", longitude: "139.7006" }) };
    const original = formToInput(form);
    const restored = formFromEvent(original);
    assert.equal(places.placeContextUnchanged(restored.place, places.placeFromLocation(original.location)), true);
    assert.deepEqual(formToInput(restored).location, original.location);
    assert.equal(formToInput(restored).starts_at, "2030-01-01T01:00:00.000Z");
    assert.equal(formToInput(restored).timezone, "Asia/Tokyo");
    const moved = formToInput(restored, "Europe/Moscow");
    assert.equal(restored.startsAt, "2030-01-01T10:00");
    assert.equal(moved.starts_at, "2030-01-01T07:00:00.000Z");
    assert.equal(moved.timezone, "Europe/Moscow");
    assert.equal(moved.ends_at, "2030-01-01T08:00:00.000Z");
});

test("legacy timezone lookup sends actual device zone", async (t) => {
    const calls = recordFetch(t, () => Response.json({ timezone: "America/New_York", source: "device", city: null }));
    const signal = new AbortController().signal;
    const body = { place: { latitude: 35.6591, longitude: 139.7006 }, user_id: "actor", device_timezone: "America/New_York" };
    const result = await maps.resolveEventTimezone(body, signal);
    assert.equal(result.timezone, "America/New_York");
    assert.equal(calls[0].url.pathname, "/api/maps/timezone");
    assert.equal(calls[0].options.method, "POST");
    assert.deepEqual(JSON.parse(calls[0].body), body);
    assert.equal(calls[0].options.signal, signal);
    await maps.resolveEventTimezone({ place: null, user_id: null, device_timezone: "Pacific/Auckland" });
    assert.equal(JSON.parse(calls[1].body).device_timezone, "Pacific/Auckland");
});

test("malformed provider coordinates and overlong manual text cannot become a selected place", () => {
    assert.throws(() => places.placeFromGeocode({ city: null, address_line: "Street", latitude: "bad", longitude: "30" }), /точку/);
    const form = { ...emptyForm(), title: "Meet", startsAt: "2030-01-01T10:00", place: places.textPlace("x".repeat(501)) };
    assert.match(validateForm(form), /500/);
    assert.match(validateForm({ ...form, place: places.textPlace(" ") }), /Укажите адрес/);
});

test("Yandex SDK loads once and waits for API readiness", async (t) => {
    const originalDocument = globalThis.document;
    const scripts = [];
    let ready;
    const api = { ready: new Promise((resolve) => { ready = resolve; }) };
    globalThis.document = {
        createElement: () => ({}),
        head: { appendChild: (script) => scripts.push(script) },
    };
    t.after(() => {
        if (originalDocument === undefined) delete globalThis.document;
        else globalThis.document = originalDocument;
        delete globalThis.window.ymaps3;
    });
    const first = loadYandexMaps("public-key");
    assert.equal(loadYandexMaps("public-key"), first);
    assert.equal(scripts.length, 1);
    assert.equal(new URL(scripts[0].src).searchParams.get("apikey"), "public-key");
    globalThis.window.ymaps3 = api;
    scripts[0].onload();
    let finished = false;
    first.then(() => { finished = true; });
    await Promise.resolve();
    assert.equal(finished, false);
    ready();
    assert.equal(await first, api);
});

test("map errors reach backend and browser console with API keys removed", async (t) => {
    const sent = [];
    const logged = [];
    t.mock.method(console, "error", (...args) => logged.push(args));
    t.mock.method(globalThis, "fetch", async (url, options) => {
        assert.equal(url.pathname, "/api/maps/client-error");
        assert.equal(options.method, "POST");
        sent.push(JSON.parse(options.body));
        return new Response(null, { status: 204 });
    });
    reportMapError("sdk_ready", new Error("Failed apikey=secret-key&other=1 secret-key"), "secret-key");
    await Promise.resolve();
    assert.equal(sent[0].stage, "sdk_ready");
    assert.equal(JSON.stringify(sent).includes("secret-key"), false);
    assert.equal(JSON.stringify(logged).includes("secret-key"), false);
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

test("invitations without expiry, revocation, sent list and rejection reason follow the API contract", async (t) => {
    const calls = recordFetch(t, () => Response.json([]));
    await api.inviteToEvent("event-1", { actor_id: "owner-1", invitee_id: "stranger-1", message: "Hello" });
    await personal.listEventInvitations("event-1", "owner-1", { offset: 100, limit: 20 });
    await personal.revokeInvitation("inv-1", "owner-1");
    await api.reviewParticipation("event-1", "user-1", "owner-1", false, "No places");
    assert.equal(JSON.parse(calls[0].body).expires_at, undefined);
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


test("event edits use rubles and preserve local time in a different zone", () => {
    const { emptyForm, formToInput, formFromEvent, validateForm } = require(join(output, "components/pages/EventFormPage/formState.js"));
    const original = { ...formToInput({ ...emptyForm(), title: "Tokyo", place: places.textPlace("Tokyo, Shibuya"), startsAt: "2030-01-01T12:00", timezone: "Asia/Tokyo", price: "500" }), price_type: "PAID" };
    const form = formFromEvent(original);
    assert.equal(form.startsAt, "2030-01-01T12:00");
    assert.equal(validateForm(form), null);
    assert.equal(formToInput(form).currency, "RUB");
    assert.equal(formToInput(emptyForm()).currency, "RUB");
    assert.equal(form.price, "500");
    assert.equal(formToInput(form).price_min, "500");
    assert.equal(formToInput(form).price_max, null);
    const legacyRange = formFromEvent({ ...original, price_max: "900" });
    assert.equal(formToInput(legacyRange).price_min, "500");
    assert.equal(formToInput(legacyRange).price_max, null);
    assert.equal(formToInput(form).starts_at, original.starts_at);
    assert.notEqual(validateForm({ ...form, timezone: "Invalid/Zone" }), null);
});

function settingsDocument() {
    return { schema_version: 2, tabs: [{ id: "catalog", label: "Каталог", cards: [{ id: "catalog.edit", title: "Записи", actions: [
        { id: "save", type: "button", label: "Сохранить все", action_id: "tag.save", tone: "primary", validate_fields: true, rows: "changed" },
    ], rows: [{ id: "tag.one", elements: [
        { id: "title", type: "text", text: "Tag", tone: "normal" },
        { id: "name", type: "input", label: "Имя", input_type: "text", value: "Original", required: true, max_length: 120 },
        { id: "category", type: "select", label: "Категория", value: "a", required: true, options: [{ value: "a", label: "A" }, { value: "b", label: "B" }] },
        { id: "active", type: "toggle", label: "Активен", value: true },
        { id: "password", type: "input", label: "Пароль", input_type: "password", value: "", required: true, min_length: 8, max_length: 128 },
        { id: "confirmation", type: "input", label: "Подтверждение", input_type: "password", value: "", required: true, matches: "password" },
        { id: "delete", type: "button", label: "Удалить", action_id: "tag.delete.one", tone: "danger", validate_fields: false, rows: "all" },
    ] }] }] }] };
}

test("settings API validates cards and sends one versioned protected batch command", async (t) => {
    const document = settingsDocument();
    const calls = recordFetch(t, (url) => Response.json(url.pathname.includes("/actions/")
        ? { schema_version: 2, message: "Saved", document, applied_rows: ["tag.one"] } : document));
    const controller = new AbortController();
    assert.deepEqual(await settings.getSettingsDocument(controller.signal), document);
    const rows = { "tag.one": { password: " secret value ", confirmation: " secret value ", active: false } };
    const result = await settings.executeSettingsAction("tag.save", rows, controller.signal);
    assert.equal(result.message, "Saved");
    assert.deepEqual(result.applied_rows, ["tag.one"]);
    assert.equal(calls[0].url.pathname, "/api/settings");
    assert.equal(calls[1].url.pathname, "/api/settings/actions/tag.save");
    assert.equal(calls[1].options.method, "POST");
    assert.equal(calls[1].options.headers["X-Dvizh-Admin"], "1");
    assert.equal(calls[1].options.headers["X-Dvizh-Account"], "1");
    assert.deepEqual(JSON.parse(calls[1].body), { schema_version: 2, rows });
    assert.equal(calls[1].options.signal, controller.signal);
    assert.equal(calls[0].options.signal, controller.signal);
});

test("settings schema fails closed for unknown types, versions, duplicate IDs and leaked secrets", () => {
    const changes = [
        (doc) => { doc.schema_version = 1; },
        (doc) => { doc.schema_version = 3; },
        (doc) => { doc.tabs[0].cards[0].rows[0].elements[0].type = "html"; },
        (doc) => { doc.tabs.push(structuredClone(doc.tabs[0])); },
        (doc) => { doc.tabs[0].cards.push(structuredClone(doc.tabs[0].cards[0])); },
        (doc) => { doc.tabs[0].cards[0].rows.push(structuredClone(doc.tabs[0].cards[0].rows[0])); },
        (doc) => { doc.tabs[0].cards[0].rows[0].elements[1].id = "title"; },
        (doc) => { doc.tabs[0].cards[0].rows[0].elements[2].value = "not-an-option"; },
        (doc) => { doc.tabs[0].cards[0].rows[0].elements[4].value = "server-secret"; },
        (doc) => { doc.tabs[0].cards[0].rows[0].elements[5].matches = "missing"; },
        (doc) => { doc.tabs[0].cards[0].rows[0].elements[1].pattern = "["; },
        (doc) => { doc.tabs[0].cards[0].rows[0].elements[6].action_id = "https://evil.example"; },
        (doc) => { doc.tabs[0].cards[0].rows[0].elements[6].action_id = "tag.save"; },
        (doc) => { doc.tabs[0].cards[0].actions[0].rows = "unknown"; },
    ];
    for (const change of changes) {
        const doc = settingsDocument(); change(doc);
        assert.throws(() => settings.parseSettingsDocument(doc), settings.SettingsProtocolError);
    }
    assert.deepEqual(settings.parseSettingsDocument({ schema_version: 2, tabs: [] }).tabs, []);
    const emptyCard = settingsDocument(); emptyCard.tabs[0].cards[0].rows = [];
    assert.equal(settings.parseSettingsDocument(emptyCard).tabs[0].cards[0].rows.length, 0);
});

test("settings refresh retains unrelated drafts, removes stale selects and never retains password fields", () => {
    const document = settingsDocument();
    const row = document.tabs[0].cards[0].rows[0];
    document.tabs[0].cards[0].rows.push({ ...structuredClone(row), id: "tag.two" });
    const drafts = {
        "tag.one": { name: "Unsaved", category: "b", active: false, password: "must-not-retain", confirmation: "must-not-retain" },
        "tag.two": { name: "Completed" },
        removed: { name: "Removed" },
    };
    assert.deepEqual(settingsState.reconcileSettingsDrafts(document, drafts, ["tag.two"]), {
        "tag.one": { name: "Unsaved", category: "b", active: false },
    });
    row.elements.find((element) => element.id === "category").options.pop();
    assert.deepEqual(settingsState.reconcileSettingsDrafts(document, drafts, ["tag.two"]), {
        "tag.one": { name: "Unsaved", active: false },
    });
});

test("settings fields validate confirmations and toggle types without trimming passwords", () => {
    const row = settingsDocument().tabs[0].cards[0].rows[0];
    const values = { ...settingsState.rowValues(row), password: " secret value ", confirmation: " secret value " };
    assert.equal(settingsState.validateSettingsValues(row, values), null);
    assert.ok(settingsState.validateSettingsValues(row, { ...values, confirmation: "secret value" }));
    assert.ok(settingsState.validateSettingsValues(row, { ...values, active: "false" }));
    assert.ok(settingsState.validateSettingsValues(row, { ...values, password: "short" }));
});

test("card actions send only dirty rows, include full field sets and ignore reverted edits", () => {
    const card = settingsDocument().tabs[0].cards[0];
    card.rows.push({ ...structuredClone(card.rows[0]), id: "tag.two" });
    const action = card.actions[0];
    assert.deepEqual(settingsState.cardActionRows(card, action, {}), {});
    assert.deepEqual(settingsState.cardActionRows(card, action, { "tag.one": { name: "Original" } }), {});
    const changed = settingsState.cardActionRows(card, action, { "tag.two": { name: "Changed" }, foreign: { name: "Do not send" } });
    assert.deepEqual(Object.keys(changed), ["tag.two"]);
    assert.deepEqual(changed["tag.two"], { ...settingsState.rowValues(card.rows[1]), name: "Changed" });
    assert.deepEqual(Object.keys(settingsState.cardActionRows(card, { ...action, rows: "all" }, {})), ["tag.one", "tag.two"]);
});

test("batch response cannot acknowledge or clear unrelated drafts", async (t) => {
    recordFetch(t, () => Response.json({ schema_version: 2, message: "Saved", document: settingsDocument(), applied_rows: ["foreign"] }));
    await assert.rejects(settings.executeSettingsAction("tag.save", { "tag.one": { name: "Changed" } }), settings.SettingsProtocolError);
});

test("draft submit button passes its action to the native button", () => {
    const { Button } = require(join(output, "components/ui/Button/Button.js"));
    const html = renderToStaticMarkup(createElement(Button, { type: "submit", action: "draft" }, "Save draft"));
    assert.match(html, /data-action="draft"/);
    assert.match(html, /type="submit"/);
});

const discoveryApi = require(join(output, "api/discovery.js"));
const { DiscoveryCache, discoveryViewport, mergeDiscoveryEvents, discoveryEmptyText } = require(join(output, "utils/discovery.js"));
function discoveryQuery(q = "") {
    return { filters: { q, viewer_id: null }, viewport: null, sort: "novelty",
        selection_token: null, cursor: null, limit: 20, include_map: true };
}
function discoveryResult() {
    return { as_of: "2030-01-01T00:00:00Z", map: { items: [], total_events: 0 },
        feed: { items: [], total_events: 0, next_cursor: null } };
}

test("discovery sends one shared filter/viewport/selection contract and rejects over-cap maps", async (t) => {
    const body = { ...discoveryQuery("music"), selection_token: "signed-region",
        viewport: { west: 30, east: 31, south: 59, north: 60, zoom: 10, center: { longitude: 30.5, latitude: 59.5 } } };
    const signal = new AbortController().signal;
    const calls = recordFetch(t, () => Response.json(discoveryResult()));
    await discoveryApi.discoverEvents(body, signal);
    assert.equal(calls[0].url.pathname, "/api/events/discovery");
    assert.equal(calls[0].options.method, "POST");
    assert.equal(calls[0].options.signal, signal);
    assert.deepEqual(JSON.parse(calls[0].body), body);
    t.mock.method(globalThis, "fetch", async () => Response.json({ ...discoveryResult(), map: {
        total_events: 31, items: Array.from({ length: 31 }, (_, i) => ({ id: String(i), count: 1, latitude: 59, longitude: 30 })),
    } }));
    await assert.rejects(discoveryApi.discoverEvents(body), (error) => error.status === 502);
});

test("discovery cache expires, evicts by recency and separates viewer/filter contexts", async () => {
    let now = 0;
    let calls = 0;
    const cache = new DiscoveryCache(async () => { calls++; return discoveryResult(); }, 50, 2, () => now);
    const load = (body) => cache.get(body, new AbortController().signal);
    await load(discoveryQuery("a")); await load(discoveryQuery("b"));
    await load(discoveryQuery("a"));
    assert.equal(calls, 2);
    await load(discoveryQuery("c")); await load(discoveryQuery("b"));
    assert.equal(calls, 4);
    now = 51;
    await load(discoveryQuery("b"));
    assert.equal(calls, 5);
    await load({ ...discoveryQuery("b"), filters: { q: "b", viewer_id: "another-viewer" } });
    assert.equal(calls, 6);
});

test("discovery deduplicates in-flight queries without aborting another subscriber", async () => {
    let complete;
    let networkSignal;
    let calls = 0;
    const cache = new DiscoveryCache((_body, signal) => {
        calls++; networkSignal = signal;
        return new Promise((resolve) => { complete = resolve; });
    });
    const first = new AbortController(); const second = new AbortController();
    const abandoned = cache.get(discoveryQuery(), first.signal);
    const remaining = cache.get(discoveryQuery(), second.signal);
    const rejected = assert.rejects(abandoned, { name: "AbortError" });
    first.abort();
    await rejected;
    assert.equal(networkSignal.aborted, false);
    complete(discoveryResult());
    await remaining;
    await cache.get(discoveryQuery(), new AbortController().signal);
    assert.equal(calls, 1);
});

test("abandoned discovery responses cannot refill cache or replace a newer request", async () => {
    const entries = [];
    const cache = new DiscoveryCache((_body, signal) => new Promise((resolve) => entries.push({ signal, resolve })));
    const first = new AbortController();
    const abandoned = cache.get(discoveryQuery(), first.signal);
    const rejected = assert.rejects(abandoned, { name: "AbortError" });
    first.abort(); await rejected;
    assert.equal(entries[0].signal.aborted, true);
    const fresh = cache.get(discoveryQuery(), new AbortController().signal);
    entries[0].resolve({ ...discoveryResult(), as_of: "old" });
    entries[1].resolve({ ...discoveryResult(), as_of: "fresh" });
    assert.equal((await fresh).as_of, "fresh");
    assert.equal((await cache.get(discoveryQuery(), new AbortController().signal)).as_of, "fresh");
    assert.equal(entries.length, 2);
});

test("discovery viewports preserve the date-line crossing and event pages deduplicate recurring ids", () => {
    assert.deepEqual(discoveryViewport([[179, -10], [181, 10]], [180, 0], 5), {
        west: 179, east: -179, south: -10, north: 10, zoom: 5, center: { longitude: -180, latitude: 0 },
    });
    const world = discoveryViewport([[-200, -85], [200, 85]], [0, 0], 0);
    assert.equal(world.west, -180); assert.equal(world.east, 180);
    assert.equal(discoveryViewport([[0, 1], [0, 2]], [0, 1], 10), null);
    assert.equal(discoveryViewport([[0, 0], [1, 1]], [NaN, 0], 10), null);
    assert.deepEqual(mergeDiscoveryEvents([{ id: "one", title: "old" }], [{ id: "one", title: "new" }, { id: "two" }]),
        [{ id: "one", title: "new" }, { id: "two" }]);
});

test("clearing discovery cache prevents an older in-flight read from restoring stale data", async () => {
    const entries = [];
    const cache = new DiscoveryCache(() => new Promise((resolve) => entries.push(resolve)));
    const old = cache.get(discoveryQuery(), new AbortController().signal);
    cache.clear();
    const fresh = cache.get(discoveryQuery(), new AbortController().signal);
    entries[1]({ ...discoveryResult(), as_of: "fresh" });
    await fresh;
    entries[0]({ ...discoveryResult(), as_of: "old" });
    await old;
    assert.equal((await cache.get(discoveryQuery(), new AbortController().signal)).as_of, "fresh");
    assert.equal(entries.length, 2);
});

test("feed sends the chosen sort and point together with filters", async (t) => {
    const calls = recordFetch(t, () => Response.json([]));
    await api.listEvents({ sort: "distance", latitude: 59.93, longitude: 30.31, freeOnly: true, viewerId: "viewer-1", limit: 20 });
    await api.listEvents({ sort: "title", limit: 20 });
    await api.listEvents({ limit: 20 });
    const first = calls[0].url.searchParams;
    assert.equal(calls[0].url.pathname, "/api/events");
    assert.equal(first.get("sort"), "distance");
    assert.equal(first.get("latitude"), "59.93");
    assert.equal(first.get("longitude"), "30.31");
    assert.equal(first.get("free_only"), "true");
    assert.equal(calls[1].url.searchParams.get("sort"), "title");
    assert.equal(calls[1].url.searchParams.has("latitude"), false);
    // Without a sort the server keeps its default order.
    assert.equal(calls[2].url.searchParams.has("sort"), false);
});

test("sort menu names the current sort", () => {
    const markup = renderToStaticMarkup(createElement(SortMenu, { value: "distance", onChange: () => undefined }));
    assert.match(markup, /aria-label="Сортировка: По удалённости"/);
    assert.match(markup, /aria-haspopup="menu"/);
    assert.match(markup, /aria-expanded="false"/);
    const mapped = renderToStaticMarkup(createElement(SortMenu, {
        value: "distance", onChange: () => undefined, distanceLabel: "Ближе к центру карты",
    }));
    assert.match(mapped, /aria-label="Сортировка: Ближе к центру карты"/);
    const starts = renderToStaticMarkup(createElement(SortMenu, { value: "start", onChange: () => undefined }));
    assert.match(starts, /aria-label="Сортировка: По дате начала"/);
});

test("discovery shares all feed sorts and sends an explicit distance origin without a viewport", async (t) => {
    const calls = recordFetch(t, () => Response.json(discoveryResult()));
    for (const sort of ["relevance", "novelty", "title", "distance", "start"]) {
        await discoveryApi.discoverEvents({ ...discoveryQuery(), sort,
            origin: sort === "distance" ? { latitude: 59.93, longitude: 30.31 } : null });
    }
    assert.deepEqual(calls.map((call) => JSON.parse(call.body).sort), ["relevance", "novelty", "title", "distance", "start"]);
    const distance = JSON.parse(calls[3].body);
    assert.equal(distance.viewport, null);
    assert.deepEqual(distance.origin, { latitude: 59.93, longitude: 30.31 });
});

test("password inputs stay hidden and get a hold-to-reveal button; other inputs do not", () => {
    const password = renderToStaticMarkup(createElement(Input, { type: "password", value: "secret", onChange: () => undefined }));
    assert.match(password, /type="password"/);
    assert.match(password, /aria-label="Показать пароль, пока кнопка нажата"/);
    assert.match(password, /aria-pressed="false"/);
    const text = renderToStaticMarkup(createElement(Input, { value: "", onChange: () => undefined }));
    assert.match(text, /type="text"/);
    assert.doesNotMatch(text, /Показать пароль/);
});

test("empty discovery distinguishes area, group and filters without claiming the global catalog is empty", () => {
    assert.equal(discoveryEmptyText(true, false, false), "В этой области событий нет!");
    assert.equal(discoveryEmptyText(true, false, true), "В этой области нет событий, подходящих под выбранные фильтры.");
    assert.equal(discoveryEmptyText(false, false, false), "Сейчас нет доступных событий.");
    assert.equal(discoveryEmptyText(false, false, true), "Нет событий, подходящих под выбранные фильтры.");
    assert.equal(discoveryEmptyText(true, true, false), "В выбранной группе больше нет доступных событий.");
    assert.equal(discoveryEmptyText(true, true, true), "В выбранной группе нет событий, подходящих под выбранные фильтры.");
});

test("username availability normalizes the value and forwards cancellation without credentials", async () => {
    const originalFetch = globalThis.fetch;
    const controller = new AbortController();
    const calls = [];
    globalThis.fetch = async (url, options) => {
        calls.push({ url: String(url), options });
        return new Response(JSON.stringify({ username: "member", available: calls.length === 1 }), {
            headers: { "Content-Type": "application/json" },
        });
    };
    try {
        assert.equal(await auth.validateUsernameAvailability(" MEMBER ", controller.signal), null);
        assert.equal(await auth.validateUsernameAvailability("member", controller.signal), "Этот никнейм уже занят.");
        assert.equal(new URL(calls[0].url).searchParams.get("username"), "member");
        assert.equal(calls[0].options.method, "GET");
        assert.equal(calls[0].options.signal, controller.signal);
        assert.equal(calls[0].options.body, undefined);
    } finally { globalThis.fetch = originalFetch; }
});

test("all-day scheduling synchronizes the end time and follows one-day date changes", () => {
    let form = { ...emptyForm(), startsAt: "2030-06-12T10:00", timezone: "Asia/Tokyo" };
    form = updateEventSchedule(form, { field: "isAllDay", value: true });
    assert.equal(form.endsAt, "2030-06-12T23:59");
    assert.equal(form.startsAt, "2030-06-12T10:00");
    assert.equal(formToInput(form).ends_at, "2030-06-12T14:59:00.000Z");
    form = updateEventSchedule(form, { field: "startsAt", value: "2030-06-10T12:00" });
    assert.equal(form.endsAt, "2030-06-10T23:59");
    form = updateEventSchedule(form, { field: "endsAt", value: "2030-06-10T23:58" });
    assert.equal(form.isAllDay, false);
    form = updateEventSchedule(form, { field: "endsAt", value: "2030-06-13T23:59" });
    assert.equal(form.isAllDay, true);
    form = updateEventSchedule(form, { field: "startsAt", value: "2030-06-11T12:00" });
    assert.equal(form.endsAt, "2030-06-13T23:59");
    form = updateEventSchedule(form, { field: "isAllDay", value: false });
    assert.equal(form.endsAt, "");
    assert.equal(form.isAllDay, false);
});

test("all-day selection before a start date waits for that date and clearing the end disables it", () => {
    let form = updateEventSchedule(emptyForm(), { field: "isAllDay", value: true });
    assert.equal(form.endsAt, "");
    assert.equal(form.isAllDay, true);
    form = updateEventSchedule(form, { field: "startsAt", value: "2030-12-31T12:00" });
    assert.equal(form.endsAt, "2030-12-31T23:59");
    form = updateEventSchedule(form, { field: "startsAt", value: "2031-01-01T12:00" });
    assert.equal(form.endsAt, "2031-01-01T23:59");
    form = updateEventSchedule(form, { field: "endsAt", value: "" });
    assert.equal(form.isAllDay, false);
    assert.equal(form.endsAt, "");
    const timed = updateEventSchedule({ ...form, endsAt: "2031-01-01T18:00" }, { field: "startsAt", value: "2031-01-01T14:00" });
    assert.equal(timed.endsAt, "2031-01-01T18:00");
});

const { initialDiscoveryCamera } = require(join(output, "utils/discoveryCamera.js"));
test("initial camera keeps nearby users centered and fits distant anchors on desktop/mobile", () => {
    const project = ([lon, lat]) => [(lon + 180) / 360, (1 - Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360)) / Math.PI) / 2];
    const wrap = (x) => ((x + 1.5) % 1) - 0.5;
    for (const [width, height] of [[390, 330], [1100, 400]]) {
        for (const [user, event] of [
            [[30, 60], [30, 60]], [[30, 60], [30.00001, 60.00001]],
            [[30, 60], [50, 40]], [[179.8, 65], [-179.8, 66]], [[-120, -45], [140, 50]],
        ]) {
            const camera = initialDiscoveryCamera(user, event, width, height);
            assert.ok(Number.isFinite(camera.zoom) && camera.zoom >= 0 && camera.zoom <= 12);
            const center = project(camera.center);
            const scale = 256 * 2 ** camera.zoom;
            for (const point of [user, event]) {
                const world = project(point);
                assert.ok(Math.abs(wrap(world[0] - center[0])) * scale <= (width - 96) / 2 + 0.001);
                assert.ok(Math.abs(world[1] - center[1]) * scale <= (height - 96) / 2 + 0.001);
            }
        }
        const near = initialDiscoveryCamera([30, 60], [30.00001, 60.00001], width, height);
        assert.ok(Math.abs(near.center[0] - 30) < 1e-8 && Math.abs(near.center[1] - 60) < 1e-8);
        assert.equal(near.zoom, 12);
        const distant = initialDiscoveryCamera([30, 60], [50, 40], width, height);
        assert.ok(distant.zoom < near.zoom);
        assert.ok(Math.abs(distant.center[0] - 30) > 1);
    }
    const empty = initialDiscoveryCamera([30, 60], null, 390, 330);
    assert.equal(empty.zoom, 12);
    assert.ok(Math.abs(empty.center[0] - 30) < 1e-8);
});

test("bootstrap sends filters and origin without changing the feed sort or viewport", async (t) => {
    const calls = recordFetch(t, () => Response.json({ nearest: null }));
    const filters = { q: "#поход", free_only: true };
    const origin = { latitude: 60, longitude: 30 };
    const controller = new AbortController();
    const discovery = require(join(output, "api/discovery.js"));
    assert.deepEqual(await discovery.bootstrapDiscovery(filters, origin, controller.signal), { nearest: null });
    assert.equal(calls[0].url.pathname, "/api/events/discovery/bootstrap");
    assert.deepEqual(JSON.parse(calls[0].body), { filters, origin });
    assert.equal(calls[0].options.signal, controller.signal);
});

const { mapMarkerPresentation } = require(join(output, "utils/mapMarkers.js"));
test("map marker colors and two-line tooltips follow the server personal state", () => {
    const item = { type: "event", count: 1, title: "Поход <script>" };
    for (const [state, color, label] of [
        ["default", "bg-bordermain", "Открыто"], ["going", "bg-pink-600", "Иду"],
        ["organizer", "bg-red-600", "Организую"], ["favorite", "bg-yellow-300", "В избранном"],
    ]) {
        const result = mapMarkerPresentation({ ...item, state });
        assert.ok(result.classes.includes(color));
        assert.equal(result.tooltip, `Поход <script>\n${label}`);
    }
    for (const [count, text] of [[2, "2 движа рядом"], [5, "5 движей рядом"], [21, "21 движ рядом"]]) {
        const result = mapMarkerPresentation({ type: "cluster", count, state: "favorite" });
        assert.equal(result.tooltip, text);
        assert.ok(result.classes.includes("bg-yellow-300"));
    }
    assert.ok(mapMarkerPresentation(item).classes.includes("bg-bordermain"));
});
test("friend picker requests bounded searchable pages without loading the whole friends list", async (t) => {
    const calls = recordFetch(t, () => Response.json([]));
    const controller = new AbortController();
    const { searchFriends } = require(join(output, "api/users.js"));
    await searchFriends("me", "Имя & ник", 20, controller.signal);
    assert.equal(calls[0].url.pathname, "/api/users/me/friends/search");
    assert.equal(calls[0].url.searchParams.get("q"), "Имя & ник");
    assert.equal(calls[0].url.searchParams.get("offset"), "20");
    assert.equal(calls[0].url.searchParams.get("limit"), "20");
    assert.equal(calls[0].options.signal, controller.signal);
});
