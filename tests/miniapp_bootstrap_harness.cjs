"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const app = fs.readFileSync(path.join(__dirname, "..", "miniapp_static", "app.js"), "utf8");
const match = app.match(/  async function bootstrap\(\) \{[\s\S]*?\n  \}\n\n  bootstrap\(\);/);
assert.ok(match);
const bootstrapSource = match[0].replace(/\n\n  bootstrap\(\);$/, "\n  globalThis.runBootstrap = bootstrap;");

async function scenario({ webApp, search = "", apiResult, homeError = false }) {
  const events = [];
  const messages = [];
  const calls = [];
  const sandbox = {
    URLSearchParams,
    window: { Telegram: webApp === undefined ? undefined : { WebApp: webApp },
      location: { search } },
    console: { warn: (...values) => events.push(values) },
    showUnavailable: message => messages.push(message),
    apiRequest: async (_path, options) => {
      calls.push(options.body);
      if (apiResult instanceof Error) throw apiResult;
      return apiResult;
    },
    loadView: async () => { if (homeError) throw new Error("home failure"); },
    sessionToken: null,
    globalThis: null,
  };
  sandbox.globalThis = sandbox;
  vm.runInNewContext(`${bootstrapSource}\n`, sandbox);
  await sandbox.runBootstrap();
  return { events, messages, calls };
}

(async () => {
  const absent = await scenario({});
  assert.equal(absent.events[0][1].reason, "missing_init_data");
  assert.equal(absent.events[0][1].has_web_app, false);
  assert.equal(absent.calls.length, 0);

  const empty = await scenario({ webApp: { initData: "", initDataUnsafe: {
    start_param: "SECRET_UNSAFE_START",
  } } });
  assert.equal(empty.events[0][1].reason, "missing_init_data");
  assert.equal(empty.events[0][1].has_web_app, true);
  assert.equal(empty.events[0][1].has_unsafe_start_param, true);
  assert.equal(empty.calls.length, 0);

  const unsafeOnly = await scenario({ webApp: { initData: "auth_date=123",
    initDataUnsafe: { start_param: "SECRET_UNSAFE_START" }, ready() {}, expand() {},
  } });
  assert.equal(unsafeOnly.events[0][1].reason, "missing_launch_token");
  assert.equal(unsafeOnly.events[0][1].has_unsafe_start_param, true);
  assert.equal(unsafeOnly.calls.length, 0);

  const apiError = Object.assign(new Error("SECRET_SERVER_MESSAGE"), { status: 401 });
  const rejected = await scenario({ webApp: { initData: "auth_date=123",
    ready() {}, expand() {},
  }, search: "?tgWebAppStartParam=SECRET_QUERY_TOKEN", apiResult: apiError });
  assert.equal(rejected.calls[0].launch_token, "SECRET_QUERY_TOKEN");
  assert.equal(rejected.events[0][1].reason, "session_api_error");
  assert.equal(rejected.events[0][1].status, 401);
  assert.equal(rejected.messages.length, 1);
  assert.ok(!JSON.stringify(rejected.events).includes("SECRET_"));

  const home = await scenario({ webApp: { initData: "start_param=SECRET_INIT_TOKEN",
    ready() {}, expand() {},
  }, apiResult: { session_token: "SECRET_SESSION_TOKEN" }, homeError: true });
  assert.equal(home.calls[0].launch_token, "SECRET_INIT_TOKEN");
  assert.equal(home.events[0][1].reason, "post_session_load_error");
  assert.ok(!JSON.stringify(home.events).includes("SECRET_"));
})().catch(error => { console.error(error); process.exitCode = 1; });
