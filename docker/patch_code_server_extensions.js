const fs = require("fs");
const path = require("path");

const extensionsRoot = process.argv[2];
if (!extensionsRoot || !fs.existsSync(extensionsRoot) || !fs.statSync(extensionsRoot).isDirectory()) {
    console.error(`[code-server-patch] extension directory not found: ${extensionsRoot || "<missing>"}`);
    process.exit(1);
}

let patched = 0;
for (const entry of fs.readdirSync(extensionsRoot, { withFileTypes: true })) {
    if (!entry.isDirectory()) {
        continue;
    }

    const manifestPath = path.join(extensionsRoot, entry.name, "package.json");
    if (!fs.existsSync(manifestPath)) {
        continue;
    }

    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
    if (typeof manifest.browser !== "string") {
        continue;
    }

    const browserEntry = path.resolve(path.dirname(manifestPath), manifest.browser);
    const candidates = [browserEntry, `${browserEntry}.js`, `${browserEntry}.cjs`, `${browserEntry}.mjs`];
    if (candidates.some((candidate) => fs.existsSync(candidate))) {
        continue;
    }

    console.log(`[code-server-patch] removing missing browser entry from ${entry.name}: ${manifest.browser}`);
    delete manifest.browser;
    fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
    patched += 1;
}

console.log(`[code-server-patch] patched ${patched} extension manifest(s)`);
