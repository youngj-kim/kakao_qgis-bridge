const fs = require("fs");
const path = require("path");

const viewer = path.join(__dirname, "..", "kakao_qgis_bridge", "web", "kakao_viewer.html");
const html = fs.readFileSync(viewer, "utf8");
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)]
  .map((match) => match[1])
  .filter((source) => source.trim());

if (scripts.length === 0) {
  throw new Error("No inline viewer JavaScript found");
}

for (const source of scripts) {
  new Function(source);
}

console.log(`Validated ${scripts.length} inline viewer script block(s).`);
