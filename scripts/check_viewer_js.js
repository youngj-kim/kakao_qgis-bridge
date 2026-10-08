const fs = require("fs");
const path = require("path");

const viewer = path.join(__dirname, "..", "kakao_qgis_bridge", "web", "kakao_viewer.html");
const html = fs.readFileSync(viewer, "utf8").replace(
  /__VIEWER_([A-Z_]+)_SCRIPT__/g,
  (_, name) => fs.readFileSync(path.join(path.dirname(viewer), "viewer_" + name.toLowerCase() + ".js"), "utf8")
);
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)]
  .map((match) => match[1])
  .filter((source) => source.trim());

if (scripts.length === 0) {
  throw new Error("No inline viewer JavaScript found");
}

for (const source of scripts) {
  new Function(source);
}

const bridge = fs.readFileSync(path.join(__dirname, "..", "kakao_qgis_bridge", "external_bridge.py"), "utf8");
const externalScript = bridge.match(/EXTERNAL_BRIDGE_SCRIPT = r"""([\s\S]*?)"""/)[1]
  .replace(/<\/?script>/g, "").replace("__KAKAO_BRIDGE_TOKEN_JSON__", '"test-token"');
new Function(externalScript);

console.log(`Validated ${scripts.length} inline viewer script block(s).`);
console.log("Validated external bridge script.");
