/**
 * FeedbackLens Embeddable Widget
 *
 * Usage: paste this into any website:
 *   <script src="http://localhost:8000/static/widget.js"
 *           data-workspace="demo"
 *           data-api="http://localhost:8000"
 *           async></script>
 *
 * The script renders a floating "Feedback" button in the bottom-right corner.
 * Clicking it opens a compact form.  Submitting POSTs to the FeedbackLens API,
 * which scrubs PII and queues AI processing automatically.
 *
 * This file is self-contained — no dependencies, no build step, no framework.
 * It creates its own shadow DOM so it does not clash with the host site's styles.
 */
(function () {
  "use strict";

  // -----------------------------------------------------------------------
  // 1. Read configuration from the script tag's data attributes.
  //    The tag that loaded us has data-workspace and data-api on it.
  // -----------------------------------------------------------------------
  var scriptTag = document.currentScript;
  if (!scriptTag) return; // bail if we cannot find ourselves

  var workspace = scriptTag.getAttribute("data-workspace");
  var apiBase = (scriptTag.getAttribute("data-api") || "").replace(/\/+$/, "");

  if (!workspace || !apiBase) {
    console.error("[FeedbackLens] Missing data-workspace or data-api on script tag.");
    return;
  }

  var submitUrl = apiBase + "/workspaces/" + workspace + "/widget/submit";

  // -----------------------------------------------------------------------
  // 2. Create the widget container and attach a shadow DOM so our styles
  //    do not leak into the host page and theirs do not break ours.
  // -----------------------------------------------------------------------
  var host = document.createElement("div");
  host.id = "feedbacklens-widget";
  document.body.appendChild(host);
  var shadow = host.attachShadow({ mode: "closed" });

  // -----------------------------------------------------------------------
  // 3. Inject all styles into the shadow DOM.
  // -----------------------------------------------------------------------
  var style = document.createElement("style");
  style.textContent = [
    /* -- Floating button -- */
    ".fl-btn {",
    "  position: fixed; bottom: 24px; right: 24px; z-index: 2147483647;",
    "  display: flex; align-items: center; gap: 6px;",
    "  padding: 10px 18px; border: none; border-radius: 999px;",
    "  background: #18181b; color: #fff; font: 500 14px/1 system-ui, sans-serif;",
    "  cursor: pointer; box-shadow: 0 4px 16px rgba(0,0,0,0.18);",
    "  transition: transform 0.15s, box-shadow 0.15s;",
    "}",
    ".fl-btn:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(0,0,0,0.25); }",
    ".fl-btn svg { width: 16px; height: 16px; fill: currentColor; }",

    /* -- Modal overlay -- */
    ".fl-overlay {",
    "  position: fixed; inset: 0; z-index: 2147483646;",
    "  background: rgba(0,0,0,0.3); display: none; align-items: flex-end;",
    "  justify-content: flex-end; padding: 24px;",
    "}",
    ".fl-overlay.open { display: flex; }",

    /* -- Form card -- */
    ".fl-card {",
    "  width: 360px; max-width: calc(100vw - 48px);",
    "  background: #fff; border-radius: 16px;",
    "  box-shadow: 0 8px 32px rgba(0,0,0,0.18);",
    "  font-family: system-ui, -apple-system, sans-serif;",
    "  overflow: hidden;",
    "}",
    "@media (prefers-color-scheme: dark) {",
    "  .fl-card { background: #1c1c1e; color: #f5f5f7; }",
    "  .fl-input, .fl-textarea { background: #2c2c2e !important; color: #f5f5f7 !important; border-color: #3a3a3c !important; }",
    "  .fl-close { color: #a1a1aa !important; }",
    "}",

    /* -- Card header -- */
    ".fl-header {",
    "  display: flex; align-items: center; justify-content: space-between;",
    "  padding: 16px 20px 0;",
    "}",
    ".fl-title { font-size: 16px; font-weight: 600; margin: 0; }",
    ".fl-close {",
    "  background: none; border: none; cursor: pointer; font-size: 20px;",
    "  color: #71717a; padding: 0; line-height: 1;",
    "}",

    /* -- Form fields -- */
    ".fl-body { padding: 12px 20px 20px; display: flex; flex-direction: column; gap: 10px; }",
    ".fl-textarea, .fl-input {",
    "  width: 100%; box-sizing: border-box; padding: 10px 12px;",
    "  border: 1px solid #e4e4e7; border-radius: 10px; font: 14px/1.5 system-ui, sans-serif;",
    "  resize: vertical; outline: none; transition: border-color 0.15s;",
    "}",
    ".fl-textarea:focus, .fl-input:focus { border-color: #18181b; }",
    ".fl-textarea { min-height: 100px; }",
    ".fl-row { display: flex; gap: 8px; }",
    ".fl-row > * { flex: 1; }",

    /* -- Submit button -- */
    ".fl-submit {",
    "  width: 100%; padding: 10px; border: none; border-radius: 10px;",
    "  background: #18181b; color: #fff; font: 500 14px/1 system-ui, sans-serif;",
    "  cursor: pointer; transition: opacity 0.15s;",
    "}",
    ".fl-submit:hover { opacity: 0.85; }",
    ".fl-submit:disabled { opacity: 0.5; cursor: not-allowed; }",

    /* -- Status messages -- */
    ".fl-status { font-size: 13px; text-align: center; padding: 4px 0; }",
    ".fl-status.ok { color: #16a34a; }",
    ".fl-status.err { color: #dc2626; }",
    ".fl-branding { font-size: 11px; text-align: center; color: #a1a1aa; padding: 0 0 12px; }",
  ].join("\n");
  shadow.appendChild(style);

  // -----------------------------------------------------------------------
  // 4. Build the floating button.
  // -----------------------------------------------------------------------
  var btn = document.createElement("button");
  btn.className = "fl-btn";
  btn.setAttribute("aria-label", "Send feedback");
  btn.innerHTML =
    '<svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>' +
    " Feedback";
  shadow.appendChild(btn);

  // -----------------------------------------------------------------------
  // 5. Build the modal overlay and form.
  // -----------------------------------------------------------------------
  var overlay = document.createElement("div");
  overlay.className = "fl-overlay";

  overlay.innerHTML = [
    '<div class="fl-card">',
    '  <div class="fl-header">',
    '    <h3 class="fl-title">Send feedback</h3>',
    '    <button class="fl-close" aria-label="Close">×</button>',
    "  </div>",
    '  <form class="fl-body">',
    '    <textarea class="fl-textarea" placeholder="Tell us what you think…" required minlength="3" maxlength="5000"></textarea>',
    '    <div class="fl-row">',
    '      <input class="fl-input" type="text" placeholder="Name (optional)" maxlength="120" />',
    '      <input class="fl-input" type="email" placeholder="Email (optional)" maxlength="320" />',
    "    </div>",
    '    <button type="submit" class="fl-submit">Submit</button>',
    '    <div class="fl-status"></div>',
    "  </form>",
    '  <div class="fl-branding">Powered by FeedbackLens</div>',
    "</div>",
  ].join("\n");
  shadow.appendChild(overlay);

  // -----------------------------------------------------------------------
  // 6. Wire up the open/close behaviour.
  // -----------------------------------------------------------------------
  var closeBtn = overlay.querySelector(".fl-close");
  var form = overlay.querySelector("form");
  var textarea = overlay.querySelector("textarea");
  var nameInput = overlay.querySelectorAll("input")[0];
  var emailInput = overlay.querySelectorAll("input")[1];
  var submitBtn = overlay.querySelector(".fl-submit");
  var statusEl = overlay.querySelector(".fl-status");

  btn.addEventListener("click", function () {
    overlay.classList.add("open");
    btn.style.display = "none";
    textarea.focus();
  });

  function closeWidget() {
    overlay.classList.remove("open");
    btn.style.display = "";
  }

  closeBtn.addEventListener("click", closeWidget);
  overlay.addEventListener("click", function (e) {
    if (e.target === overlay) closeWidget();
  });

  // -----------------------------------------------------------------------
  // 7. Handle form submission — POST to the API and show the result.
  // -----------------------------------------------------------------------
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var text = textarea.value.trim();
    if (text.length < 3) return;

    submitBtn.disabled = true;
    submitBtn.textContent = "Sending…";
    statusEl.textContent = "";
    statusEl.className = "fl-status";

    var payload = { text: text };
    if (nameInput.value.trim()) payload.name = nameInput.value.trim();
    if (emailInput.value.trim()) payload.email = emailInput.value.trim();

    fetch(submitUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (res) {
        if (!res.ok) throw new Error("Request failed with " + res.status);
        return res.json();
      })
      .then(function (data) {
        statusEl.textContent = data.message || "Thank you for your feedback!";
        statusEl.className = "fl-status ok";
        // Reset the form after a short delay so the user sees the message.
        setTimeout(function () {
          form.reset();
          statusEl.textContent = "";
          closeWidget();
        }, 2000);
      })
      .catch(function (err) {
        statusEl.textContent = "Something went wrong. Please try again.";
        statusEl.className = "fl-status err";
        console.error("[FeedbackLens]", err);
      })
      .finally(function () {
        submitBtn.disabled = false;
        submitBtn.textContent = "Submit";
      });
  });
})();
