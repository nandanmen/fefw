#!/usr/bin/env node
// Zero-dependency static dev server with live reload.
// Usage: node scripts/dev-server.mjs [port]   (or: pnpm dev)
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const port = Number(process.argv[2] || process.env.PORT || 8000);

const types = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
};

const reloadSnippet = `<script>(()=>{const es=new EventSource("/__livereload");es.onmessage=()=>location.reload();})();</script>`;
const clients = new Set();

const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");

  if (url.pathname === "/__livereload") {
    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    });
    res.write(": connected\n\n");
    clients.add(res);
    req.on("close", () => clients.delete(res));
    return;
  }

  let filePath = path.join(root, decodeURIComponent(url.pathname));
  if (!filePath.startsWith(root)) {
    res.writeHead(403).end("Forbidden");
    return;
  }
  if (fs.existsSync(filePath) && fs.statSync(filePath).isDirectory()) {
    filePath = path.join(filePath, "index.html");
  }

  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, { "Content-Type": "text/plain" }).end("Not found");
      return;
    }
    const ext = path.extname(filePath).toLowerCase();
    const headers = { "Content-Type": types[ext] || "application/octet-stream", "Cache-Control": "no-store" };
    if (ext === ".html") {
      const html = data.toString();
      const out = html.includes("</body>")
        ? html.replace(/<\/body>(?![\s\S]*<\/body>)/, reloadSnippet + "</body>")
        : html + reloadSnippet;
      res.writeHead(200, headers).end(out);
    } else {
      res.writeHead(200, headers).end(data);
    }
  });
});

let timer;
fs.watch(root, { recursive: true }, (_event, file) => {
  if (!file || file.startsWith(".git") || file.includes("node_modules")) return;
  clearTimeout(timer);
  timer = setTimeout(() => {
    console.log(`[reload] ${file}`);
    for (const c of clients) c.write("data: reload\n\n");
  }, 50);
});

server.listen(port, () => console.log(`Dev server running at http://localhost:${port}`));
