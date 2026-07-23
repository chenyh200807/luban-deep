(function (global) {
  "use strict";

  var ENDPOINT = "/api/v1/luban-preview/playback-event";
  var SAMPLE_INTERVAL_MS = 1000;
  var CHECKPOINT_INTERVAL_MS = 15000;
  var MAX_PENDING_ACTIONS = 32;
  var MAX_DELIVERY_QUEUE = 32;
  var MAX_DELIVERY_ATTEMPTS = 3;
  var RETRY_BACKOFF_MS = [200, 600];
  var states = typeof WeakMap === "function" ? new WeakMap() : null;
  var deliveryQueue = [];

  function finiteNumber(value, fallback) {
    var number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  }

  function clampMs(value, maximum) {
    var bounded = Math.max(0, Math.round(finiteNumber(value, 0)));
    return maximum > 0 ? Math.min(bounded, maximum) : bounded;
  }

  function randomId() {
    try {
      if (global.crypto && typeof global.crypto.randomUUID === "function") {
        return global.crypto.randomUUID();
      }
      if (global.crypto && typeof global.crypto.getRandomValues === "function") {
        var bytes = new Uint8Array(16);
        global.crypto.getRandomValues(bytes);
        return Array.prototype.map.call(bytes, function (byte) {
          return byte.toString(16).padStart(2, "0");
        }).join("");
      }
    } catch (_) {}
    return (
      Date.now().toString(36) +
      "-" +
      Math.floor(Math.random() * 0x100000000).toString(36)
    );
  }

  function pageName() {
    try {
      var parts = String(global.location && global.location.pathname || "").split("/");
      return parts[parts.length - 1] || "lesson.html";
    } catch (_) {
      return "lesson.html";
    }
  }

  function sectionAt(state, positionMs) {
    var sections = state.episode && state.episode.sections;
    if (!Array.isArray(sections)) return "";
    for (var index = sections.length - 1; index >= 0; index -= 1) {
      if (positionMs >= sections[index].start_ms) return String(sections[index].id || "");
    }
    return sections.length ? String(sections[0].id || "") : "";
  }

  function safeTicket() {
    return String(global.__lubanCardEntryTicket || "").trim();
  }

  function canonicalReason(value) {
    var reason = String(value || "");
    var aliases = {
      state_transition: "auto",
      section_transition: "auto",
      timeline: "auto",
      interval: "auto",
      complete: "ended",
      timeline_end: "ended",
      play_button: "user",
      pause_button: "user",
      replay_button: "user",
      section_jump: "chip",
      before_seek: "scrub",
      ask_open: "ask",
      background: "visibility",
      component_unmount: "unmount",
    };
    reason = aliases[reason] || reason;
    return [
      "",
      "auto",
      "chip",
      "scrub",
      "user",
      "visibility",
      "pagehide",
      "unmount",
      "ask",
      "ended",
    ].indexOf(reason) >= 0 ? reason : "";
  }

  function removeDelivery(item) {
    var index = deliveryQueue.indexOf(item);
    if (index >= 0) deliveryQueue.splice(index, 1);
    if (item.timer != null && typeof global.clearTimeout === "function") {
      global.clearTimeout(item.timer);
    }
    item.cancelled = true;
  }

  function retryDelivery(item) {
    if (item.cancelled) return;
    if (item.attempts >= MAX_DELIVERY_ATTEMPTS) {
      removeDelivery(item);
      return;
    }
    var delay = RETRY_BACKOFF_MS[Math.max(0, item.attempts - 1)] || 600;
    if (typeof global.setTimeout !== "function") {
      removeDelivery(item);
      return;
    }
    item.timer = global.setTimeout(function () {
      item.timer = null;
      deliver(item);
    }, delay);
  }

  function deliver(item) {
    if (item.cancelled) return;
    item.attempts += 1;
    var request;
    try {
      if (typeof global.fetch !== "function") {
        retryDelivery(item);
        return;
      }
      request = global.fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // body is created once when enqueued. Retries therefore preserve the
        // exact event id, session sequence, client clock, and scoped ticket.
        body: item.body,
        keepalive: true,
        credentials: "same-origin",
      });
    } catch (_) {
      retryDelivery(item);
      return;
    }
    Promise.resolve(request)
      .then(function (response) {
        if (!response || !response.ok) throw new Error("playback delivery rejected");
        removeDelivery(item);
      })
      .catch(function () {
        retryDelivery(item);
      });
  }

  function enqueueDelivery(payload) {
    if (deliveryQueue.length >= MAX_DELIVERY_QUEUE) {
      removeDelivery(deliveryQueue[0]);
    }
    var item = {
      body: JSON.stringify(payload),
      attempts: 0,
      timer: null,
      cancelled: false,
    };
    deliveryQueue.push(item);
    deliver(item);
  }

  function post(state, action, fields) {
    if (!state.ready) {
      if (state.pending.length < MAX_PENDING_ACTIONS) {
        state.pending.push({ action: action, fields: fields || {} });
      }
      return;
    }
    var ticket = safeTicket();
    if (!ticket || state.detached) return;
    state.sequence += 1;
    var source = fields || {};
    var positionMs = clampMs(source.positionMs, state.durationMs);
    var payload = {
      contextId: String(state.options.packId || ""),
      entryTicket: ticket,
      eventId: state.sessionId + ":" + state.sequence,
      action: String(action),
      objectId: String(state.episode.object_id),
      section: String(source.section || sectionAt(state, positionMs)),
      occurredAt: Date.now(),
      playbackSessionId: state.sessionId,
      sequence: state.sequence,
      contentRevision: String(state.episode.content_revision),
      positionMs: positionMs,
      fromPositionMs: clampMs(source.fromPositionMs, state.durationMs),
      toPositionMs: clampMs(
        source.toPositionMs == null ? positionMs : source.toPositionMs,
        state.durationMs
      ),
      watchedDeltaMs: Math.max(0, Math.round(finiteNumber(source.watchedDeltaMs, 0))),
      reason: canonicalReason(source.reason),
    };
    if (action !== "exit") state.sessionHasEvents = true;
    enqueueDelivery(payload);
  }

  function flushCheckpoint(state, reason, positionMs, section) {
    var watched = Math.max(0, Math.round(state.pendingWatchedMs));
    if (!watched) return;
    var checkpointSection = section || state.pendingSection || sectionAt(state, positionMs);
    state.pendingWatchedMs = 0;
    state.pendingSection = "";
    state.lastCheckpointAt = Date.now();
    post(state, "checkpoint", {
      positionMs: positionMs,
      fromPositionMs: Math.max(0, positionMs - watched),
      toPositionMs: positionMs,
      watchedDeltaMs: watched,
      section: checkpointSection,
      reason: reason || "interval",
    });
  }

  function addWatchedIntervals(state, fromMs, toMs) {
    var sections = state.episode && state.episode.sections;
    if (!Array.isArray(sections) || toMs <= fromMs) return;
    sections.forEach(function (section) {
      var overlapStart = Math.max(fromMs, finiteNumber(section.start_ms, 0));
      var overlapEnd = Math.min(toMs, finiteNumber(section.end_ms, 0));
      if (overlapEnd <= overlapStart) return;
      var sectionId = String(section.id || "");
      if (state.pendingSection && state.pendingSection !== sectionId) {
        flushCheckpoint(state, "section_transition", overlapStart, state.pendingSection);
      }
      state.pendingSection = sectionId;
      state.pendingWatchedMs += overlapEnd - overlapStart;
    });
  }

  function sample(state) {
    if (state.detached || !state.ready) return;
    var now = Date.now();
    var positionMs = clampMs(finiteNumber(state.component.state.t, 0) * 1000, state.durationMs);
    var playing = state.component.state.playing === true;
    var elapsedMs = Math.max(0, now - state.lastSampleAt);
    var positionDeltaMs = positionMs - state.lastPositionMs;

    if (playing && state.lastPlaying) {
      // Count only forward progress compatible with elapsed wall time. Explicit
      // seeks reset the baseline, so timeline jumps never become watch time.
      var maximumCredibleDelta = Math.max(2000, elapsedMs * 1.75 + 500);
      if (positionDeltaMs >= 0 && positionDeltaMs <= maximumCredibleDelta) {
        addWatchedIntervals(state, state.lastPositionMs, positionMs);
      }
    }

    if (playing && !state.lastPlaying) {
      post(state, "play", { positionMs: positionMs, reason: "state_transition" });
    } else if (!playing && state.lastPlaying && !state.completed) {
      flushCheckpoint(state, "pause", positionMs);
      post(state, "pause", { positionMs: positionMs, reason: "state_transition" });
    }

    var section = sectionAt(state, positionMs);
    if (playing && section && section !== state.lastSection) {
      post(state, "section_enter", {
        positionMs: positionMs,
        section: section,
        reason: "timeline",
      });
      state.lastSection = section;
    }

    if (
      playing &&
      state.pendingWatchedMs > 0 &&
      now - state.lastCheckpointAt >= CHECKPOINT_INTERVAL_MS
    ) {
      flushCheckpoint(state, "interval", positionMs);
    }

    if (!state.completed && state.durationMs > 0 && positionMs >= state.durationMs - 100) {
      flushCheckpoint(state, "complete", state.durationMs);
      state.completed = true;
      state.lastPlaying = false;
      post(state, "complete", {
        positionMs: state.durationMs,
        fromPositionMs: state.durationMs,
        toPositionMs: state.durationMs,
        reason: "timeline_end",
      });
    } else {
      state.lastPlaying = playing;
    }
    state.lastPositionMs = positionMs;
    state.lastSampleAt = now;
  }

  function stateFor(component) {
    return states && component ? states.get(component) : null;
  }

  function exitSession(state, reason) {
    if (!state.ready) return;
    sample(state);
    var positionMs = clampMs(
      finiteNumber(state.component.state && state.component.state.t, 0) * 1000,
      state.durationMs
    );
    if (state.sessionHasEvents || state.pendingWatchedMs > 0) {
      flushCheckpoint(state, reason || "exit", positionMs);
      post(state, "exit", { positionMs: positionMs, reason: reason || "exit" });
    }
    state.sessionId = randomId();
    state.sequence = 0;
    state.sessionHasEvents = false;
    state.pendingWatchedMs = 0;
    state.pendingSection = "";
    state.lastCheckpointAt = Date.now();
    state.lastSampleAt = Date.now();
    state.lastPositionMs = positionMs;
    state.lastPlaying = false;
    state.lastSection = sectionAt(state, positionMs);
    state.completed = false;
  }

  function attach(component, options) {
    if (!states || !component || states.has(component)) return;
    var state = {
      component: component,
      options: options || {},
      sessionId: randomId(),
      sequence: 0,
      sessionHasEvents: false,
      ready: false,
      detached: false,
      pending: [],
      episode: null,
      durationMs: 0,
      pendingWatchedMs: 0,
      pendingSection: "",
      lastCheckpointAt: Date.now(),
      lastSampleAt: Date.now(),
      lastPositionMs: clampMs(finiteNumber(component.state && component.state.t, 0) * 1000, 0),
      lastPlaying: false,
      lastSection: "",
      completed: false,
      interval: null,
      visibilityHandler: null,
      pagehideHandler: null,
    };
    states.set(component, state);
    var manifestUrl = String(state.options.manifestUrl || "playback-manifest.json");
    var manifestRequest;
    try {
      if (typeof global.fetch !== "function") return;
      manifestRequest = global.fetch(manifestUrl, {
        credentials: "same-origin",
        cache: "no-store",
      });
    } catch (_) {
      return;
    }
    Promise.resolve(manifestRequest)
      .then(function (response) {
        if (!response.ok) throw new Error("playback manifest unavailable");
        return response.json();
      })
      .then(function (manifest) {
        var episodes = Array.isArray(manifest && manifest.episodes) ? manifest.episodes : [];
        var currentPage = pageName();
        var episode = episodes.find(function (item) {
          return String(item && item.lesson_file || "") === currentPage;
        });
        if (
          !episode ||
          !String(episode.object_id || "") ||
          !String(episode.content_revision || "") ||
          !Array.isArray(episode.sections)
        ) {
          throw new Error("playback manifest episode mismatch");
        }
        state.episode = episode;
        state.durationMs = Math.max(0, Math.round(finiteNumber(episode.duration_ms, 0)));
        state.ready = true;
        state.lastPositionMs = clampMs(
          finiteNumber(component.state && component.state.t, 0) * 1000,
          state.durationMs
        );
        state.lastSection = sectionAt(state, state.lastPositionMs);
        var pending = state.pending.splice(0);
        pending.forEach(function (item) {
          post(state, item.action, item.fields);
        });
        state.interval = global.setInterval(function () {
          sample(state);
        }, SAMPLE_INTERVAL_MS);
      })
      .catch(function () {
        state.pending.length = 0;
      });

    state.visibilityHandler = function () {
      if (global.document && global.document.visibilityState === "hidden") {
        exitSession(state, "background");
        try {
          if (typeof component.setSpeechPaused === "function") {
            component.setSpeechPaused(true);
          }
          if (
            component.state &&
            component.state.playing === true &&
            typeof component.setState === "function"
          ) {
            component.setState({ playing: false });
          }
        } catch (_) {}
      }
    };
    state.pagehideHandler = function () {
      detach(component, "pagehide");
    };
    if (global.document && typeof global.document.addEventListener === "function") {
      global.document.addEventListener("visibilitychange", state.visibilityHandler);
    }
    if (typeof global.addEventListener === "function") {
      global.addEventListener("pagehide", state.pagehideHandler);
    }
  }

  function toggle(component) {
    var state = stateFor(component);
    if (!state || state.detached) return;
    var positionMs = clampMs(finiteNumber(component.state.t, 0) * 1000, state.durationMs);
    if (component.state.playing === true) {
      flushCheckpoint(state, "pause_button", positionMs);
      post(state, "pause", { positionMs: positionMs, reason: "pause_button" });
      state.lastPlaying = false;
      return;
    }
    if (state.durationMs > 0 && positionMs >= state.durationMs - 100) {
      post(state, "replay", {
        positionMs: 0,
        fromPositionMs: positionMs,
        toPositionMs: 0,
        reason: "play_button",
      });
      state.lastPositionMs = 0;
      state.lastSection = "";
      state.lastPlaying = true;
      state.lastSampleAt = Date.now();
      return;
    }
    post(state, "play", { positionMs: positionMs, reason: "play_button" });
    state.lastPlaying = true;
    state.lastSampleAt = Date.now();
    state.lastPositionMs = positionMs;
  }

  function seek(component, targetSeconds, reason) {
    var state = stateFor(component);
    if (!state || state.detached) return;
    var fromMs = clampMs(finiteNumber(component.state.t, 0) * 1000, state.durationMs);
    var toMs = clampMs(finiteNumber(targetSeconds, 0) * 1000, state.durationMs);
    flushCheckpoint(state, "before_seek", fromMs);
    post(state, "seek", {
      positionMs: toMs,
      fromPositionMs: fromMs,
      toPositionMs: toMs,
      reason: reason || "seek",
    });
    state.lastPositionMs = toMs;
    state.lastSampleAt = Date.now();
    state.lastPlaying = false;
    state.lastSection = sectionAt(state, toMs);
  }

  function replay(component) {
    var state = stateFor(component);
    if (!state || state.detached) return;
    var fromMs = clampMs(finiteNumber(component.state.t, 0) * 1000, state.durationMs);
    flushCheckpoint(state, "replay", fromMs);
    post(state, "replay", {
      positionMs: 0,
      fromPositionMs: fromMs,
      toPositionMs: 0,
      reason: "replay_button",
    });
    state.lastPositionMs = 0;
    state.lastSampleAt = Date.now();
    state.lastPlaying = true;
    state.lastSection = "";
  }

  function pause(component, reason) {
    var state = stateFor(component);
    if (!state || state.detached) return;
    var positionMs = clampMs(finiteNumber(component.state.t, 0) * 1000, state.durationMs);
    flushCheckpoint(state, reason || "pause", positionMs);
    if (state.lastPlaying || component.state.playing === true) {
      post(state, "pause", { positionMs: positionMs, reason: reason || "pause" });
    }
    state.lastPlaying = false;
  }

  function complete(component) {
    var state = stateFor(component);
    if (!state || state.detached || state.completed) return;
    flushCheckpoint(state, "complete", state.durationMs);
    state.completed = true;
    state.lastPlaying = false;
    post(state, "complete", {
      positionMs: state.durationMs,
      fromPositionMs: state.durationMs,
      toPositionMs: state.durationMs,
      reason: "timeline_end",
    });
  }

  function detach(component, reason) {
    var state = stateFor(component);
    if (!state || state.detached) return;
    exitSession(state, reason || "exit");
    state.detached = true;
    if (state.interval != null) global.clearInterval(state.interval);
    if (global.document && typeof global.document.removeEventListener === "function") {
      global.document.removeEventListener("visibilitychange", state.visibilityHandler);
    }
    if (typeof global.removeEventListener === "function") {
      global.removeEventListener("pagehide", state.pagehideHandler);
    }
    states.delete(component);
  }

  global.LubanPlaybackTelemetry = {
    attach: attach,
    toggle: toggle,
    seek: seek,
    replay: replay,
    pause: pause,
    complete: complete,
    detach: detach,
  };
})(window);
