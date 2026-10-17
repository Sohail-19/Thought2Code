import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const source = await readFile(new URL("../src/previewBootstrap.js", import.meta.url), "utf8");
const bootstrap = source.match(/`([\s\S]*)`;\s*$/)?.[1];

test("preview bootstrap provides isolated temporary storage when opaque-origin storage throws", () => {
  assert.ok(bootstrap, "Preview bootstrap source should be defined");

  const windowListeners = {};
  const documentListeners = {};
  const notices = new Map();
  const body = { prepend: (element) => notices.set(element.id, element) };
  const window = {
    addEventListener: (name, callback) => { windowListeners[name] = callback; },
  };
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    get() { throw new Error("SecurityError: opaque origin"); },
  });
  const document = {
    body,
    addEventListener: (name, callback) => { documentListeners[name] = callback; },
    createElement: () => ({ style: {}, setAttribute() {} }),
    getElementById: (id) => notices.get(id) || null,
  };

  vm.runInNewContext(bootstrap, { window, document });

  assert.equal(window.localStorage.getItem("tasks"), null);
  window.localStorage.setItem("tasks", JSON.stringify(["task"]));
  assert.equal(window.localStorage.getItem("tasks"), '["task"]');
  assert.equal(window.localStorage.length, 1);

  windowListeners.error();
  assert.match(
    notices.get("thought2code-preview-error").textContent,
    /script error in the preview/,
  );
  assert.equal(typeof windowListeners.unhandledrejection, "function");
  assert.equal(typeof documentListeners.DOMContentLoaded, "function");
});
