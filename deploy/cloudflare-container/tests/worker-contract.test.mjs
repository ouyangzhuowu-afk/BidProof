import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const root = new URL("..", import.meta.url);

test("container worker exposes the singleton BidProof service", () => {
  const worker = fs.readFileSync(new URL("worker/index.js", root), "utf8");
  const config = fs.readFileSync(new URL("wrangler.jsonc", root), "utf8");

  assert.match(worker, /class BidProofContainer extends Container/);
  assert.match(worker, /defaultPort\s*=\s*8080/);
  assert.match(worker, /getByName\("singleton"\)/);
  assert.match(worker, /BIDPROOF_ENV:\s*"production"/);
  assert.match(worker, /BIDPROOF_ALLOW_TRUSTED_HEADERS:\s*"0"/);
  assert.match(worker, /BIDPROOF_BOOTSTRAP_TOKEN:\s*env\.BIDPROOF_BOOTSTRAP_TOKEN/);
  assert.match(config, /bidproof\.marketcase\.net\/\*/);
  assert.match(config, /"class_name"\s*:\s*"BidProofContainer"/);
});
