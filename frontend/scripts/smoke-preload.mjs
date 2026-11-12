/**
 * 浏览器环境预加载：vite-node 下让 Vue 运行时看到 jsdom 的 window/document。
 * 用法：NODE_OPTIONS="--import ./scripts/smoke-preload.mjs" npx vite-node scripts/smoke-compare.mjs
 */
import { JSDOM } from 'jsdom'

const dom = new JSDOM('<!doctype html><html><body><div id="app"></div></body></html>', {
  url: 'http://127.0.0.1:5173/',
  pretendToBeVisual: true,
})
globalThis.window = dom.window
globalThis.document = dom.window.document
globalThis.history = dom.window.history
globalThis.location = dom.window.location
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true })
for (const key of [
  'HTMLElement', 'SVGElement', 'Element', 'Node', 'Event', 'MouseEvent', 'KeyboardEvent',
  'CustomEvent', 'Text', 'Comment', 'DocumentFragment', 'HTMLSelectElement', 'getComputedStyle',
]) {
  globalThis[key] = dom.window[key]
}
globalThis.requestAnimationFrame = (callback) => setTimeout(() => callback(Date.now()), 0)
globalThis.cancelAnimationFrame = (id) => clearTimeout(id)
