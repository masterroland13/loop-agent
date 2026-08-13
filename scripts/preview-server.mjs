import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(__dirname, '..', 'dist')
const port = Number(process.env.PORT || 5173)
const backend = process.env.BACKEND_URL || 'http://127.0.0.1:8000'

const mime = {
  html: 'text/html; charset=utf-8',
  js: 'application/javascript; charset=utf-8',
  css: 'text/css; charset=utf-8',
  svg: 'image/svg+xml',
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  ico: 'image/x-icon',
  json: 'application/json; charset=utf-8',
}

function proxy(req, res, targetPath) {
  const url = new URL(targetPath, backend)
  const headers = { ...req.headers, host: url.host }
  delete headers['host']

  const proxyReq = http.request(
    url,
    { method: req.method, headers },
    (proxyRes) => {
      res.writeHead(proxyRes.statusCode || 500, proxyRes.headers)
      proxyRes.pipe(res)
    },
  )

  proxyReq.on('error', () => {
    res.writeHead(502, { 'Content-Type': 'text/plain; charset=utf-8' })
    res.end('Backend unavailable. Start backend on port 8000.')
  })

  req.pipe(proxyReq)
}

function serveStatic(req, res) {
  let pathname = decodeURIComponent(new URL(req.url, `http://${req.headers.host}`).pathname)
  if (pathname === '/') pathname = '/index.html'

  let filePath = path.join(root, pathname)
  if (!filePath.startsWith(root)) {
    res.writeHead(403)
    res.end('Forbidden')
    return
  }

  if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
    filePath = path.join(root, 'index.html')
  }

  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' })
      res.end('Not found')
      return
    }
    const ext = path.extname(filePath).slice(1)
    res.writeHead(200, { 'Content-Type': mime[ext] || 'application/octet-stream' })
    res.end(data)
  })
}

const server = http.createServer((req, res) => {
  const pathname = new URL(req.url, `http://${req.headers.host}`).pathname
  if (pathname.startsWith('/api') || pathname === '/health') {
    proxy(req, res, pathname)
    return
  }
  serveStatic(req, res)
})

server.listen(port, '0.0.0.0', () => {
  console.log(`Preview server: http://localhost:${port}/`)
  console.log(`API proxy -> ${backend}`)
})
