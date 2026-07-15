// Run: node yousenwebview/tests/test_station_f16_practice_scope.js
var assert = require("assert");
var fs = require("fs");
var path = require("path");
var vm = require("vm");

function flush() {
  return new Promise(function (resolve) { setTimeout(resolve, 0); });
}

function loadStation(detail) {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/luban/station/station.js"),
    "utf8",
  );
  var pageDef;
  var redirects = [];
  var sandbox = {
    console: console,
    Promise: Promise,
    setTimeout: setTimeout,
    encodeURIComponent: encodeURIComponent,
    require: function (request) {
      if (request === "../../../utils/api") {
        return {
          getLubanLessonDetail: function () { return Promise.resolve(detail); },
          issueLubanCardEntry: function () { return Promise.resolve({ entry_ticket: "card-capability" }); },
          unwrapResponse: function (value) { return value; },
          describeRequestError: function (_error, fallback) { return fallback; },
        };
      }
      if (request === "../../../utils/auth") return { isLoggedIn: function () { return true; } };
      if (request === "../../../utils/route") {
        return { lubanStation: function (packId) { return "/station?pack_id=" + packId; } };
      }
      if (request === "../../../utils/runtime") return { redirectToLogin: function () {} };
      if (request === "../../../utils/surface-telemetry") {
        return { trackProductBehavior: function () {} };
      }
      if (request === "../../../utils/helpers") return {};
      throw new Error("unexpected require: " + request);
    },
    wx: {
      redirectTo: function (payload) { redirects.push(payload.url); },
      navigateTo: function () {},
    },
    getCurrentPages: function () { return []; },
    Page: function (definition) { pageDef = definition; },
  };
  vm.runInNewContext(source, sandbox, { filename: "station.js" });
  var page = {
    data: JSON.parse(JSON.stringify(pageDef.data)),
    setData: function (patch) { Object.assign(this.data, patch || {}); },
  };
  Object.keys(pageDef).forEach(function (key) {
    if (key !== "data") page[key] = pageDef[key];
  });
  return { page: page, redirects: redirects };
}

(async function main() {
  var f16 = loadStation({
    title: "F16",
    content_sha256: "pack-sha",
    card_url: "https://cdn/f16/lesson.html?v=bundle",
    practice_url: "https://cdn/f16/practice.html?v=bundle",
  });
  f16.page.onLoad({ pack_id: "F16" });
  await flush();
  assert.strictEqual(f16.page.data.currentUrl, "https://cdn/f16/lesson.html?v=bundle#entry_ticket=card-capability");
  assert.strictEqual(
    f16.page.data.cardUrl,
    "https://cdn/f16/lesson.html?v=bundle#entry_ticket=card-capability",
    "station must pass a narrow card-entry capability in the fragment, not its bearer credential",
  );
  assert.strictEqual(f16.page.data.cardUrl.indexOf("entry_ticket=") < f16.page.data.cardUrl.indexOf("#"), false, "ticket must never enter URL query");
  assert.deepStrictEqual(f16.redirects, [], "opening a finished card must not leave the canonical web-view flow");

  var s05 = loadStation({
    title: "S05",
    content_sha256: "pack-sha",
    card_url: "https://cdn/s05/lesson.html",
    practice_url: "https://cdn/s05/practice.html?v=bundle",
  });
  s05.page.onLoad({ pack_id: "S05" });
  await flush();
  assert.strictEqual(s05.page.data.currentUrl, "https://cdn/s05/lesson.html#entry_ticket=card-capability");
  assert.deepStrictEqual(s05.redirects, [], "all compiled packs must stay inside the finished card flow");

  var stationWxml = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/luban/station/station.wxml"),
    "utf8",
  );
  var stationWxss = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/luban/station/station.wxss"),
    "utf8",
  );
  var stationJs = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/luban/station/station.js"),
    "utf8",
  );
  assert.strictEqual(stationWxml.indexOf("st-footer"), -1, "native controls must not cover the web-view touch surface");
  assert.strictEqual(stationWxss.indexOf("position: fixed"), -1, "station shell must not keep a hidden fixed touch layer");
  assert.strictEqual(stationJs.indexOf("onPrimaryTap"), -1, "practice navigation belongs to the finished card, not a second native controller");
  assert.strictEqual(stationJs.indexOf("postLessonProgress"), -1, "lesson evidence must keep the card bridge as its only client writer");

  console.log("PASS test_station_f16_practice_scope.js");
})().catch(function (error) {
  console.error(error);
  process.exit(1);
});
