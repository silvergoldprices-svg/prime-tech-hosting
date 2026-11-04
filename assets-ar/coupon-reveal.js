/*! Reveal Coupon – lightweight, no dependencies */
(function () {
  "use strict";
  function openAff(url) {
    if (!url) return;
    try { window.open(url, "_blank", "noopener,noreferrer"); }
    catch (e) { window.location.href = url; }
  }
  function copyText(text, btn) {
    function done() {
      var old = btn.textContent;
      btn.textContent = "تم النسخ ✓";
      btn.classList.add("copied");
      setTimeout(function () { btn.textContent = old; btn.classList.remove("copied"); }, 1800);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(function () { fallbackCopy(text, btn); });
    } else { fallbackCopy(text, btn); }
  }
  function fallbackCopy(text, btn) {
    var ta = document.createElement("textarea");
    ta.value = text; ta.style.position = "fixed"; ta.style.left = "-9999px";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } catch (e) {}
    document.body.removeChild(ta);
    var old = btn.textContent;
    btn.textContent = "تم النسخ ✓"; btn.classList.add("copied");
    setTimeout(function () { btn.textContent = old; btn.classList.remove("copied"); }, 1800);
  }
  function reveal(box) {
    var codeEl = box.querySelector(".coupon-code");
    var btn = box.querySelector(".coupon-reveal");
    var aff = box.getAttribute("data-aff") || "";
    if (!codeEl || !btn) return;
    codeEl.hidden = false;
    btn.disabled = true;
    btn.textContent = "تم الإظهار";
    if (aff) openAff(aff);
    var codeText = codeEl.querySelector(".code-text");
    if (codeText) {
      try {
        var range = document.createRange();
        range.selectNodeContents(codeText);
        var sel = window.getSelection();
        sel.removeAllRanges(); sel.addRange(range);
      } catch (e) {}
    }
  }
  document.addEventListener("click", function (e) {
    var t = e.target;
    if (!t) return;
    if (t.classList.contains("coupon-reveal") || t.closest(".coupon-reveal")) {
      var btn = t.classList.contains("coupon-reveal") ? t : t.closest(".coupon-reveal");
      var box = btn.closest(".coupon-box");
      if (box) { e.preventDefault(); reveal(box); }
      return;
    }
    if (t.classList.contains("copy-btn") || t.closest(".copy-btn")) {
      var cbtn = t.classList.contains("copy-btn") ? t : t.closest(".copy-btn");
      var code = cbtn.getAttribute("data-copy") || "";
      if (code) { e.preventDefault(); copyText(code, cbtn); }
    }
  });
})();
