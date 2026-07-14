var ROOT = "/packageDeeptutor";
var KNOWN_PACKAGE_PATHS = {
  "pages/assessment/assessment": true,
  "pages/billing/billing": true,
  "pages/chat/chat": true,
  "pages/history/history": true,
  "pages/legal/terms": true,
  "pages/login/login": true,
  "pages/login/manual": true,
  "pages/login/reset-password": true,
  "pages/learn/learn": true,
  "pages/luban/concept-cards/concept-cards": true,
  "pages/luban/errorbank/errorbank": true,
  "pages/luban/review/review": true,
  "pages/luban/station/station": true,
  "pages/luban/stations/stations": true,
  "pages/mistake-book/mistake-book": true,
  "pages/onboarding/onboarding": true,
  "pages/practice/practice": true,
  "pages/feedback/feedback": true,
  "pages/first-run/first-run": true,
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
  passwordReset: function (query) {
    return withQuery("pages/login/reset-password", query);
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
  report: function (query) {
    return withQuery("pages/report/report", query);
  },
  mistakeBook: function () {
    return resolve("pages/mistake-book/mistake-book");
  },
  learn: function (query) {
    return withQuery("pages/learn/learn", query);
  },
  lubanStations: function (query) {
    return withQuery("pages/luban/stations/stations", query);
  },
  lubanStation: function (packId) {
    return withQuery("pages/luban/station/station", { pack_id: packId });
  },
  lubanReview: function (query) {
    return withQuery("pages/luban/review/review", query);
  },
  lubanConceptCards: function (query) {
    return withQuery("pages/luban/concept-cards/concept-cards", query);
  },
  lubanErrorbank: function (query) {
    return withQuery("pages/luban/errorbank/errorbank", query);
  },
  lubanGauntlet: function (query) {
    return withQuery("pages/luban/gauntlet/gauntlet", query);
  },
  profile: function () {
    return resolve("pages/profile/profile");
  },
  onboarding: function (query) {
    return withQuery("pages/onboarding/onboarding", query);
  },
  billing: function () {
    return resolve("pages/billing/billing");
  },
  assessment: function (query) {
    return withQuery("pages/assessment/assessment", query);
  },
  practice: function () {
    return resolve("pages/practice/practice");
  },
  feedback: function (query) {
    return withQuery("pages/feedback/feedback", query);
  },
  terms: function () {
    return resolve("pages/legal/terms");
  },
};
