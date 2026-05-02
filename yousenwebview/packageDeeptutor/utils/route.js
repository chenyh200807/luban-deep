var ROOT = "/packageDeeptutor";
var KNOWN_PACKAGE_PATHS = {
  "pages/assessment/assessment": true,
  "pages/billing/billing": true,
  "pages/chat/chat": true,
  "pages/history/history": true,
  "pages/legal/terms": true,
  "pages/login/login": true,
  "pages/login/manual": true,
  "pages/practice/practice": true,
  "pages/profile/profile": true,
  "pages/register/register": true,
  "pages/report/report": true,
};

function _trimPath(path) {
  return String(path || "")
    .trim()
    .replace(/^\/+/, "")
    .replace(/^packageDeeptutor\/+/, "");
}

function _safeDecode(value) {
  var raw = String(value || "").trim();
  if (!raw) return "";
  try {
    return decodeURIComponent(raw);
  } catch (_) {
    return raw;
  }
}

function resolve(path) {
  var clean = _trimPath(path);
  if (!clean) return ROOT;
  return ROOT + "/" + clean;
}

function withQuery(path, query) {
  var url = resolve(path);
  if (!query || typeof query !== "object") return url;
  var parts = [];
  Object.keys(query).forEach(function (key) {
    var value = query[key];
    if (value === undefined || value === null || value === "") return;
    parts.push(
      encodeURIComponent(key) + "=" + encodeURIComponent(String(value)),
    );
  });
  return parts.length ? url + "?" + parts.join("&") : url;
}

function resolveInternalUrl(target, fallback) {
  var raw = _safeDecode(target);
  if (!raw) return fallback || resolve("pages/chat/chat");
  if (/^https?:\/\//i.test(raw)) {
    return fallback || resolve("pages/chat/chat");
  }
  var queryIndex = raw.indexOf("?");
  var pathOnly = queryIndex >= 0 ? raw.slice(0, queryIndex) : raw;
  var query = queryIndex >= 0 ? raw.slice(queryIndex) : "";
  var clean = _trimPath(pathOnly);
  if (!KNOWN_PACKAGE_PATHS[clean]) {
    return fallback || resolve("pages/chat/chat");
  }
  return resolve(clean) + query;
}

module.exports = {
  ROOT: ROOT,
  resolve: resolve,
  withQuery: withQuery,
  resolveInternalUrl: resolveInternalUrl,
  login: function (query) {
    return withQuery("pages/login/login", query);
  },
  manualLogin: function (query) {
    return withQuery("pages/login/manual", query);
  },
  register: function (query) {
    return withQuery("pages/register/register", query);
  },
  chat: function (query) {
    return withQuery("pages/chat/chat", query);
  },
  history: function () {
    return resolve("pages/history/history");
  },
  report: function () {
    return resolve("pages/report/report");
  },
  profile: function () {
    return resolve("pages/profile/profile");
  },
  billing: function () {
    return resolve("pages/billing/billing");
  },
  assessment: function () {
    return resolve("pages/assessment/assessment");
  },
  practice: function () {
    return resolve("pages/practice/practice");
  },
  terms: function () {
    return resolve("pages/legal/terms");
  },
};
