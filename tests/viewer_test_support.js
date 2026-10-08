const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class Element {
  constructor(tag = "div") {
    this.tagName = tag;
    this.children = [];
    this.listeners = {};
    this.dataset = {};
    this.attributes = {};
    this.hidden = false;
    this.disabled = false;
    this.value = "";
    this._text = "";
    const classes = new Set();
    this.classList = {
      add: (name) => classes.add(name),
      remove: (...names) => names.forEach((name) => classes.delete(name)),
      contains: (name) => classes.has(name) || this.className?.split(" ").includes(name),
      toggle: (name, on) => on ? classes.add(name) : classes.delete(name)
    };
  }
  set textContent(text) { this._text = text; this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(""); }
  get childElementCount() { return this.children.length; }
  append(...children) {
    children.forEach((child) => { child.parentElement = this; });
    this.children.push(...children);
  }
  remove() {
    if (this.parentElement) {
      this.parentElement.children = this.parentElement.children.filter((child) => child !== this);
    }
  }
  replaceChildren(...children) { this.children = []; this.append(...children); }
  appendChild(child) { this.append(child); return child; }
  insertBefore(child, before) {
    const index = this.children.indexOf(before);
    if (index < 0) this.append(child); else this.children.splice(index, 0, child);
  }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  fire(name, fields = {}) {
    this.listeners[name]?.({ preventDefault() {}, stopPropagation() {}, ...fields });
  }
  focus() { this.focused = true; }
  querySelectorAll(selector) {
    const matches = [];
    for (const child of this.children) {
      if (selector.startsWith(".") && child.classList.contains(selector.slice(1))) matches.push(child);
      matches.push(...child.querySelectorAll(selector));
    }
    return matches;
  }
}

function loadController(name) {
  const context = vm.createContext({ window: {} });
  const source = fs.readFileSync(path.join(__dirname, "..", "kakao_qgis_bridge", "web", "viewer_" + name + ".js"), "utf8");
  vm.runInContext(source, context);
  return context.window;
}

function createDocument() {
  return { createElement: (tag) => new Element(tag) };
}

module.exports = { Element, loadController, createDocument };
