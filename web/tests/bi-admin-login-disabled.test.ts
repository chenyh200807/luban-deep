import test from "node:test";
import assert from "node:assert/strict";

import { isAdminLoginSubmitDisabled } from "../app/(workspace)/bi/_v2/admin-login-disabled.ts";

test("initial empty username and password keeps submit disabled", () => {
  assert.equal(
    isAdminLoginSubmitDisabled({ submitting: false, username: "", password: "" }),
    true,
  );
});

test("typing only the username keeps submit disabled (password still empty)", () => {
  assert.equal(
    isAdminLoginSubmitDisabled({ submitting: false, username: "ops-admin", password: "" }),
    true,
  );
});

test("typing only the password keeps submit disabled (username still empty)", () => {
  assert.equal(
    isAdminLoginSubmitDisabled({ submitting: false, username: "", password: "hunter2" }),
    true,
  );
});

test("non-empty username + non-empty password enables submit", () => {
  assert.equal(
    isAdminLoginSubmitDisabled({
      submitting: false,
      username: "ops-admin",
      password: "hunter2",
    }),
    false,
  );
});

test("whitespace-only username keeps submit disabled (trim drops it)", () => {
  assert.equal(
    isAdminLoginSubmitDisabled({ submitting: false, username: "   ", password: "hunter2" }),
    true,
  );
});

test("whitespace-only password keeps submit disabled (trim drops it)", () => {
  assert.equal(
    isAdminLoginSubmitDisabled({ submitting: false, username: "ops-admin", password: "\t \n" }),
    true,
  );
});

test("submitting=true keeps submit disabled even when credentials are filled", () => {
  assert.equal(
    isAdminLoginSubmitDisabled({
      submitting: true,
      username: "ops-admin",
      password: "hunter2",
    }),
    true,
  );
});
