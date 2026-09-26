(function (global, factory) {
  typeof exports === 'object' && typeof module !== 'undefined' ? factory(exports) :
  typeof define === 'function' && define.amd ? define(['exports'], factory) :
  (global = typeof globalThis !== 'undefined' ? globalThis : global || self, factory(global["flatpickr-zh-TW"] = {}));
})(this, (function (exports) { 'use strict';

  var fp = typeof window !== "undefined" && window.flatpickr !== undefined
      ? window.flatpickr
      : {
          l10ns: {},
      };
  var MandarinTraditional = {
      weekdays: {
          shorthand: ["週日", "週一", "週二", "週三", "週四", "週五", "週六"],
          longhand: [
              "星期日",
              "星期一",
              "星期二",
              "星期三",
              "星期四",
              "星期五",
              "星期六",
          ],
      },
      months: {
          shorthand: [
              "一月",
              "二月",
              "三月",
              "四月",
              "五月",
              "六月",
              "七月",
              "八月",
              "九月",
              "十月",
              "十一月",
              "十二月",
          ],
          longhand: [
              "一月",
              "二月",
              "三月",
              "四月",
              "五月",
              "六月",
              "七月",
              "八月",
              "九月",
              "十月",
              "十一月",
              "十二月",
          ],
      },
      rangeSeparator: " 至 ",
      weekAbbreviation: "週",
      scrollTitle: "滾動切換",
      toggleTitle: "點擊切換 12/24 小時時制",
  };
  fp.l10ns.zh_tw = MandarinTraditional;
  // BeakPlatform 補：form.io 以 language "zh-TW" 請求 flatpickr-zh-TW.js 並把同名字串當 flatpickr locale，
  // 上游只註冊 zh_tw，這裡加同名別名（本檔是 flatpickr-zh-tw.js 的副本，僅改全域名稱與此別名）。
  fp.l10ns['zh-TW'] = MandarinTraditional;
  var flatpickrZhTw = fp.l10ns;

  exports.MandarinTraditional = MandarinTraditional;
  exports["default"] = flatpickrZhTw;

  Object.defineProperty(exports, '__esModule', { value: true });

}));
