// Polyv signing belongs to the server; the registered page only consumes signed payloads.

var fs = require("fs");
var path = require("path");
var vm = require("vm");

var pass = 0;
var fail = 0;
var errors = [];

function assert(condition, message) {
  if (condition) {
    pass++;
    return;
  }
  fail++;
  errors.push("FAIL: " + message);
}

var appConfig = JSON.parse(
  fs.readFileSync(path.join(__dirname, "../app.json"), "utf8"),
);
var canonicalRoute = "pages/freeCourseDetails/freeCourseDetails";
var registeredRoutes = (appConfig.pages || []).concat(
  (appConfig.subpackages || []).reduce(function (routes, subpackage) {
    return routes.concat(
      (subpackage.pages || []).map(function (page) {
        return subpackage.root + "/" + page;
      }),
    );
  }, []),
);

assert(
  registeredRoutes.filter(function (route) {
    return route.indexOf("freeCourseDetails/freeCourseDetails") !== -1;
  }).length === 1,
  "app.json should register exactly one freeCourseDetails authority",
);
assert(
  registeredRoutes.indexOf(canonicalRoute) !== -1,
  "app.json should register the canonical freeCourseDetails page",
);

var pagePath = path.join(__dirname, "../pages/freeCourseDetails/freeCourseDetails.js");
var source = fs.readFileSync(pagePath, "utf8");
assert(
  !/\b(?:secretKey|privateKey|signingKey)\b/i.test(source),
  "canonical page should not declare a signing secret",
);
assert(
  !/\b(?:md5|sha1|sha256|hmac)\s*\(/i.test(source),
  "canonical page should not calculate a signature hash",
);
assert(
  !/(?:secret|privateKey|signingKey)[^\n;]*(?:vid|videoId|ts)|(?:vid|videoId|ts)[^\n;]*(?:secret|privateKey|signingKey)/i.test(source),
  "canonical page should not combine secret material with video request fields",
);

var capturedDefinition = null;
var videoRequests = [];
var sandbox = {
  Component: function (definition) {
    capturedDefinition = definition;
  },
  console: { error: function () {} },
  require: function (request) {
    if (request === "../../utils/behavior") {
      return {};
    }
    if (request === "../../utils/polyv.js") {
      return {
        default: {
          getVideo: function (requestOptions) {
            videoRequests.push(requestOptions);
          },
        },
      };
    }
    throw new Error("unexpected require: " + request);
  },
};
vm.runInNewContext(source, sandbox, { filename: pagePath });
assert(capturedDefinition && capturedDefinition.methods, "page should register Component methods");

function buildPage(data) {
  var instance = { data: data || {} };
  Object.keys(capturedDefinition.methods).forEach(function (name) {
    instance[name] = capturedDefinition.methods[name];
  });
  instance.setData = function (patch) {
    Object.keys(patch).forEach(function (key) {
      instance.data[key] = patch[key];
    });
  };
  instance.clearBeishuTimer = function () {};
  instance.scheduleBeishuHide = function () {};
  instance.getProgressState = function () {
    return { currentChapterNumber: 1, chapterCount: 1, progressPercent: 100 };
  };
  return instance;
}

var signedChapter = {
  id: "chapter-1",
  title: "chapter",
  displayIndex: 1,
  polyv_ts: 123456,
  polyv_sign: "server-issued-signature",
};
var page = buildPage({
  gratisDetail: { chapter: [signedChapter] },
  videoSrc: {},
});
page.choicePlays({
  currentTarget: { dataset: { video_id: "video-1", index: 0, flag: true } },
});
assert(videoRequests.length === 1, "chapter click should request a signed video once");
assert(videoRequests[0].vid === "video-1", "chapter click should preserve video id");
assert(videoRequests[0].ts === 123456, "chapter click should forward server timestamp");
assert(
  videoRequests[0].sign === "server-issued-signature",
  "chapter click should forward server signature",
);

var requestsBeforeUnsigned = videoRequests.length;
page.requestVideoSrc("video-unsigned", true, { id: "unsigned-chapter" });
assert(
  videoRequests.length === requestsBeforeUnsigned,
  "missing server signature should fail closed before Polyv request",
);
assert(page.pendingAutoPlaySeq === 0, "missing signature should cancel pending autoplay");

var publicPayload = {
  polyv_signatures: {
    "video-public": { ts: 789, sign: "server-public-signature" },
  },
};
var publicPage = buildPage({ gratisDetail: publicPayload, videoSrc: {} });
publicPage.publicVideo("video-public");
assert(videoRequests.length === requestsBeforeUnsigned + 1, "public video should request once");
assert(videoRequests[videoRequests.length - 1].ts === 789, "public video should forward mapped timestamp");
assert(
  videoRequests[videoRequests.length - 1].sign === "server-public-signature",
  "public video should forward mapped signature",
);

if (fail > 0) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_freeCourseDetails_polyv_secret_boundary.js (" + pass + " assertions)");
