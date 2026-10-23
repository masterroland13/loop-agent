import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    {
      name: 'webkit-gfm-email-regex',
      generateBundle(_opts, bundle) {
        const oldRe = String.raw`/(?<=^|\s|\p{P}|\p{S})([-.\w+]+)@([-\w]+(?:\.[-\w]+)+)/gu`
        const nextRe = String.raw`/([-.\w+]+)@([-\w]+(?:\.[-\w]+)+)/gu`
        for (const chunk of Object.values(bundle)) {
          if (chunk.type !== 'chunk') continue
          chunk.code = chunk.code.replaceAll(oldRe, nextRe)
          if (chunk.code.includes('(?<=')) {
            throw new Error('bundle still has a lookbehind regex; WebKitGTK 2.38 cannot parse it')
          }
        }
      },
    },
    {
      name: 'classic-script-for-webkit',
      transformIndexHtml(html) {
        // WebKitGTK 2.38 may skip type=module. Load the IIFE with fetch+eval.
        return html.replace(
          /<script type="module" crossorigin src="(\/assets\/[^"]+\.js)"><\/script>/,
          `<script>
      if (!Object.hasOwn) {
        Object.hasOwn = function (o, k) { return Object.prototype.hasOwnProperty.call(o, k) }
      }
      if (typeof structuredClone !== 'function') {
        structuredClone = function (v) { return JSON.parse(JSON.stringify(v)) }
      }
      window.__loopPointer = function (x, y) {
        var prev = window.__loopHoverEl
        var el = (x < 0 || y < 0) ? null : document.elementFromPoint(x, y)
        if (el === prev) return
        if (prev) {
          prev.classList.remove('loop-hover')
          prev.removeAttribute('data-loop-hover')
        }
        window.__loopHoverEl = el
        if (!el) {
          return
        }
        el.classList.add('loop-hover')
        el.setAttribute('data-loop-hover', '1')
      }
      function show(msg) {
        var boot = document.getElementById('boot')
        if (boot) boot.textContent = msg
        try { fetch('/api/shell-boot', { method: 'POST', body: String(msg) }) } catch (e) {}
      }
      show('页面脚本已运行，正在加载界面…')
      fetch('$1?boot=1').then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status)
        return res.text()
      }).then(function (code) {
        try { (0, eval)(code) }
        catch (err) { show('脚本错误：' + (err && err.message ? err.message : err)) }
      }).catch(function (err) {
        show('脚本下载失败：' + (err && err.message ? err.message : err))
      })
    </script>`,
        )
      },
    },
  ],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
