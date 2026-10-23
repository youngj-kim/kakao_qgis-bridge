const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('kakao_qgis_bridge/web/viewer_language.js', 'utf8');
function harness(saved, blocked = false) {
  const store = new Map(saved ? [['kakao_qgis_bridge/ui_language', saved]] : []);
  function button(text) { return {childNodes: [{nodeType: 3, nodeValue: text}], attrs: {}, setAttribute(k,v) {this.attrs[k]=v;}, getAttribute(k) {return this.attrs[k];}, addEventListener(k,v) {this[k]=v;}}; }
  const toggle = button('English'), search = button('Search'), roads = button('Show Roadview roads');
  const buttons = [toggle, search, roads];
  let notify;
  vm.runInNewContext(source, {document: {getElementById: id => id === 'viewer-language-toggle' ? toggle : {}, querySelectorAll: () => buttons}, localStorage: {getItem: k => {if(blocked) throw Error(); return store.get(k);},setItem: (k,v) => {if(blocked) throw Error(); store.set(k,v);}}, MutationObserver: class {constructor(cb) {notify=cb;} observe() {} disconnect() {}}});
  return {toggle, search, roads, buttons, button, store, notify: () => notify()};
}
test('buttons switch both ways and persist selection without altering state', () => {
  const h=harness();
  assert.equal(h.search.childNodes[0].nodeValue,'검색');
  assert.equal(h.toggle.textContent, 'EN');
  h.search.disabled=true;
  h.toggle.click();
  assert.equal(h.search.childNodes[0].nodeValue,'Search');
  assert.equal(h.store.get('kakao_qgis_bridge/ui_language'),'en');
  assert.equal(h.toggle.textContent, 'KR');
  assert.equal(h.search.disabled,true);
  h.toggle.click();
  assert.equal(h.search.childNodes[0].nodeValue,'검색');
});
test('dynamic labels and newly created history buttons follow current language', () => {
  const h=harness();
  h.roads.childNodes[0].nodeValue='Hide Roadview roads';
  const history=h.button('Delete'), count=h.button('Hide results (12)');
  h.buttons.push(history,count);
  h.notify();
  assert.equal(h.roads.childNodes[0].nodeValue,'로드뷰 도로 숨기기');
  assert.equal(history.childNodes[0].nodeValue,'삭제');
  assert.equal(count.childNodes[0].nodeValue,'검색 결과 12개 접기');
  h.toggle.click();
  assert.equal(count.childNodes[0].nodeValue,'Hide results (12)');
});
test('saved language restores and unavailable storage still allows switching', () => {
  assert.equal(harness('en').search.childNodes[0].nodeValue,'Search');
  const h=harness(null,true);h.toggle.click();
  assert.equal(h.search.childNodes[0].nodeValue,'Search');
});

test('map and route options translate both ways, retaining selection and compact center labels', () => {
  const h=harness();
  const options=['일반지도','항공영상','항공영상+지명','추천 경로','최단 시간','최단 거리','지도','경로','Here'].map(h.button);
  options[0].value='ROADMAP';options[0].selected=true;
  h.buttons.push(...options);h.notify();
  assert.equal(options[8].childNodes[0].nodeValue,'현위치');
  h.toggle.click();
  assert.deepEqual(options.map(o=>o.childNodes[0].nodeValue),['Roadmap','Aerial','Aerial + labels','Recommended','Fastest','Shortest','Map','Route','Here']);
  assert.equal(options[0].value,'ROADMAP');assert.equal(options[0].selected,true);
  h.toggle.click();
  assert.equal(options[0].childNodes[0].nodeValue,'일반지도');
  assert.equal(options[8].childNodes[0].nodeValue,'현위치');
});
