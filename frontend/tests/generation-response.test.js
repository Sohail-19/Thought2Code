import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { parseGenerateResponse } from "../src/generationResponse.js";

const rateLimitDetail = "The AI provider's usage limit has been reached. Please wait and try again later.";

test("generation keeps the API's safe HTTP 429 detail for the UI", async () => {
  const appSource = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");
  const response = {
    ok: false,
    status: 429,
    json: async () => ({ detail: rateLimitDetail }),
  };

  await assert.rejects(parseGenerateResponse(response), { message: rateLimitDetail });
  assert.match(appSource, /parseGenerateResponse\(response\)/);
  assert.match(appSource, /setError\(requestError\.message/);
});

test("generation response parsing retains a safe fallback for malformed responses", async () => {
  await assert.rejects(
    parseGenerateResponse({ ok: false, json: async () => { throw new Error("invalid json"); } }),
    { message: "The API returned an unreadable response. Please try again." },
  );
});

test("generation shows a safe local API message for network failures", async () => {
  const appSource = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");

  assert.match(appSource, /requestError instanceof TypeError/);
  assert.match(appSource, /Could not reach the local API/);
});
