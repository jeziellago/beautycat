// BeautyCat frontend — vanilla JS, virtual scrolling, WebSocket client.
(() => {
  const LEVELS = ["V", "D", "I", "W", "E", "A", "F"];
  const LEVEL_RANK = Object.fromEntries(LEVELS.map((l, i) => [l, i]));
  const ROW_H = 22;
  const OVERSCAN = 12;

  // ---------- State ----------
  const state = {
    serial: null,
    ws: null,
    wsBackoff: 1000,
    records: [],          // all records (post-server, full buffer)
    visibleIdx: [],       // indices into `records` matching the current filter
    paused: false,
    pendingBatch: [],     // records arrived while paused
    autoscroll: true,
    filter: {
      level: "",
      tag: "",
      package: "",
      search: "",
      regex: false,
    },
    devices: [],
    presets: [],
  };

  // ---------- DOM refs ----------
  const $ = (id) => document.getElementById(id);
  const els = {
    device: $("deviceSelect"),
    refreshDevices: $("refreshDevices"),
    connStatus: $("connStatus"),
    level: $("levelFilter"),
    tag: $("tagFilter"),
    pkg: $("packageFilter"),
    search: $("searchInput"),
    regex: $("regexToggle"),
    pause: $("pauseBtn"),
    clear: $("clearBtn"),
    preset: $("presetSelect"),
    savePreset: $("savePresetBtn"),
    deletePreset: $("deletePresetBtn"),
    exportTxt: $("exportTxtBtn"),
    exportJson: $("exportJsonBtn"),
    scroller: $("logScroller"),
    sizer: $("logSizer"),
    viewport: $("logViewport"),
    empty: $("emptyState"),
    statTotal: $("statTotal"),
    statVisible: $("statVisible"),
    statAutoscroll: $("statAutoscroll"),
    statPaused: $("statPaused"),
    modal: $("logModal"),
    modalLevel: $("modalLevel"),
    modalTime: $("modalTime"),
    modalTag: $("modalTag"),
    modalPkg: $("modalPkg"),
    modalIds: $("modalIds"),
    modalBody: $("modalBody"),
    modalCopy: $("modalCopyBtn"),
  };

  // ---------- Utilities ----------
  const debounce = (fn, ms) => {
    let t;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), ms);
    };
  };

  const escapeHtml = (s) =>
    s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");

  const compileSearch = (term, useRegex) => {
    if (!term) return null;
    if (useRegex) {
      try {
        return new RegExp(term, "i");
      } catch {
        return null;
      }
    }
    return new RegExp(term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i");
  };

  // ---------- Filter ----------
  function matches(record) {
    const f = state.filter;
    if (f.level) {
      if ((LEVEL_RANK[record.level] ?? -1) < LEVEL_RANK[f.level]) return false;
    }
    if (f.tag && !record.tag.toLowerCase().includes(f.tag.toLowerCase())) return false;
    if (f.package) {
      const pkg = (record.package || "").toLowerCase();
      if (!pkg.includes(f.package.toLowerCase())) return false;
    }
    if (f.search) {
      const re = compileSearch(f.search, f.regex);
      if (re && !re.test(record.message)) return false;
      if (!re && !record.message.toLowerCase().includes(f.search.toLowerCase())) return false;
    }
    return true;
  }

  function rebuildVisible() {
    const out = [];
    for (let i = 0; i < state.records.length; i++) {
      if (matches(state.records[i])) out.push(i);
    }
    state.visibleIdx = out;
  }

  function appendVisible(startIndex) {
    for (let i = startIndex; i < state.records.length; i++) {
      if (matches(state.records[i])) state.visibleIdx.push(i);
    }
  }

  // ---------- Rendering (virtual scroll) ----------
  function updateSizer() {
    els.sizer.style.height = `${state.visibleIdx.length * ROW_H}px`;
  }

  function highlight(message) {
    const f = state.filter;
    if (!f.search) return escapeHtml(message);
    const re = compileSearch(f.search, f.regex);
    if (!re) return escapeHtml(message);
    const reG = new RegExp(re.source, re.flags.includes("g") ? re.flags : re.flags + "g");
    let html = "";
    let last = 0;
    let m;
    while ((m = reG.exec(message)) !== null) {
      if (m.index === reG.lastIndex) { reG.lastIndex++; continue; }
      html += escapeHtml(message.slice(last, m.index));
      html += `<mark class="hl">${escapeHtml(m[0])}</mark>`;
      last = m.index + m[0].length;
    }
    html += escapeHtml(message.slice(last));
    return html;
  }

  function rowHtml(record, topPx) {
    const pkg = record.package ? `<span class="pkg">${escapeHtml(record.package)}</span>` : "";
    const firstLine = record.message.split("\n", 1)[0];
    const multiline = record.message.includes("\n");
    const more = multiline ? `<span class="more" title="Click to view full message">⋯</span>` : "";
    return (
      `<div class="row lvl-${record.level}" style="top:${topPx}px" data-seq="${record.seq}">` +
      `<span class="col-time">${escapeHtml(record.time || record.date)}</span>` +
      `<span class="col-pid">${record.pid}</span>` +
      `<span class="col-tid">${record.tid}</span>` +
      `<span class="col-lvl">${record.level}</span>` +
      `<span class="col-pkg-tag">${pkg}<span class="tag">${escapeHtml(record.tag)}</span></span>` +
      `<span class="msg">${highlight(firstLine)}${more}</span>` +
      `</div>`
    );
  }

  function render() {
    const scrollTop = els.scroller.scrollTop;
    const viewportH = els.scroller.clientHeight;
    const total = state.visibleIdx.length;

    if (total === 0) {
      els.viewport.innerHTML = "";
      els.empty.classList.toggle("hidden", state.records.length > 0);
      els.statVisible.textContent = "0 visible";
      return;
    }
    els.empty.classList.add("hidden");

    const first = Math.max(0, Math.floor(scrollTop / ROW_H) - OVERSCAN);
    const last = Math.min(total, Math.ceil((scrollTop + viewportH) / ROW_H) + OVERSCAN);

    const parts = [];
    for (let i = first; i < last; i++) {
      const idx = state.visibleIdx[i];
      const rec = state.records[idx];
      parts.push(rowHtml(rec, i * ROW_H));
    }
    els.viewport.innerHTML = parts.join("");
    els.statVisible.textContent = `${total} visible`;
  }

  function scrollToBottom() {
    els.scroller.scrollTop = els.scroller.scrollHeight;
  }

  function setAutoscroll(on) {
    state.autoscroll = on;
    els.statAutoscroll.textContent = on ? "auto-scroll on" : "auto-scroll off";
    els.statAutoscroll.className = on ? "auto-on" : "auto-off";
  }

  els.scroller.addEventListener("scroll", () => {
    const distFromBottom = els.scroller.scrollHeight - els.scroller.scrollTop - els.scroller.clientHeight;
    setAutoscroll(distFromBottom < 8);
    render();
  });

  window.addEventListener("resize", render);

  // Click row to open the detail modal with the full message.
  els.viewport.addEventListener("click", (e) => {
    const row = e.target.closest(".row");
    if (!row) return;
    const seq = Number(row.dataset.seq);
    const rec = recordBySeq(seq);
    if (rec) openModal(rec);
  });

  // ---------- Detail modal ----------
  function recordBySeq(seq) {
    // Most clicks land on recently-rendered rows; scan from the end for speed.
    for (let i = state.records.length - 1; i >= 0; i--) {
      if (state.records[i].seq === seq) return state.records[i];
    }
    return null;
  }

  function isModalOpen() {
    return !els.modal.classList.contains("hidden");
  }

  function openModal(record) {
    els.modalLevel.textContent = record.level;
    els.modalLevel.className = `modal-level lvl-${record.level}`;
    const ts = [record.date, record.time].filter(Boolean).join(" ");
    els.modalTime.textContent = ts;
    els.modalTag.textContent = record.tag || "";
    els.modalPkg.textContent = record.package || "";
    els.modalPkg.classList.toggle("hidden", !record.package);
    els.modalIds.textContent = `pid ${record.pid} · tid ${record.tid}`;
    els.modalBody.textContent = record.message;
    els.modal.classList.remove("hidden");
    els.modalCopy.textContent = "⧉ Copy";
  }

  function closeModal() {
    els.modal.classList.add("hidden");
  }

  els.modal.addEventListener("click", (e) => {
    if (e.target.closest("[data-modal-close]")) closeModal();
  });

  els.modalCopy.addEventListener("click", async () => {
    const text = els.modalBody.textContent || "";
    try {
      await navigator.clipboard.writeText(text);
      els.modalCopy.textContent = "✓ Copied";
      setTimeout(() => { els.modalCopy.textContent = "⧉ Copy"; }, 1200);
    } catch {
      els.modalCopy.textContent = "✗ Failed";
      setTimeout(() => { els.modalCopy.textContent = "⧉ Copy"; }, 1200);
    }
  });

  // ---------- Status ----------
  function updateStats() {
    els.statTotal.textContent = `${state.records.length} records`;
    els.statVisible.textContent = `${state.visibleIdx.length} visible`;
    els.statPaused.textContent = state.paused ? "paused" : "live";
    els.statPaused.style.color = state.paused ? "#f5c451" : "";
  }

  function setConnStatus(s) {
    els.connStatus.className = `conn-dot ${s}`;
    els.connStatus.title = s;
  }

  // ---------- Filter inputs ----------
  const applyFilterChange = () => {
    rebuildVisible();
    updateSizer();
    render();
    updateStats();
    if (state.autoscroll) scrollToBottom();
  };

  els.level.addEventListener("change", () => {
    state.filter.level = els.level.value;
    applyFilterChange();
  });
  const onFilterText = debounce(() => {
    state.filter.tag = els.tag.value.trim();
    state.filter.package = els.pkg.value.trim();
    state.filter.search = els.search.value;
    state.filter.regex = els.regex.checked;
    applyFilterChange();
  }, 80);
  els.tag.addEventListener("input", onFilterText);
  els.pkg.addEventListener("input", onFilterText);
  els.search.addEventListener("input", onFilterText);
  els.regex.addEventListener("change", onFilterText);

  // ---------- Controls ----------
  function setPaused(p) {
    state.paused = p;
    els.pause.textContent = p ? "▶ Resume" : "⏸ Pause";
    els.pause.classList.toggle("active", p);
    if (!p && state.pendingBatch.length) {
      const start = state.records.length;
      state.records.push(...state.pendingBatch);
      state.pendingBatch = [];
      appendVisible(start);
      updateSizer();
      render();
      if (state.autoscroll) scrollToBottom();
    }
    updateStats();
  }

  els.pause.addEventListener("click", () => setPaused(!state.paused));

  els.clear.addEventListener("click", async () => {
    if (!state.serial) return;
    try {
      await fetch(`/api/devices/${encodeURIComponent(state.serial)}/clear`, { method: "POST" });
    } catch {
      /* server may already be in trouble — clear UI anyway */
    }
    state.records = [];
    state.visibleIdx = [];
    closeModal();
    updateSizer();
    render();
    updateStats();
  });

  els.exportTxt.addEventListener("click", () => doExport("txt"));
  els.exportJson.addEventListener("click", () => doExport("json"));

  function doExport(fmt) {
    if (!state.serial) return;
    const q = new URLSearchParams({
      fmt,
      level: state.filter.level,
      tag: state.filter.tag,
      package: state.filter.package,
      search: state.filter.search,
      regex: state.filter.regex ? "true" : "false",
    });
    window.location.href = `/api/devices/${encodeURIComponent(state.serial)}/export?${q.toString()}`;
  }

  // ---------- Keyboard ----------
  window.addEventListener("keydown", (e) => {
    const inField = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
    if (e.key === "Escape" && isModalOpen()) {
      e.preventDefault();
      closeModal();
      return;
    }
    if (e.key === "/" && !inField) {
      e.preventDefault();
      els.search.focus();
      els.search.select();
    } else if (e.code === "Space" && !inField) {
      e.preventDefault();
      setPaused(!state.paused);
    } else if (e.ctrlKey && e.key.toLowerCase() === "l") {
      e.preventDefault();
      els.clear.click();
    } else if (e.key === "Escape") {
      els.tag.value = "";
      els.pkg.value = "";
      els.search.value = "";
      els.regex.checked = false;
      els.level.value = "";
      state.filter = { level: "", tag: "", package: "", search: "", regex: false };
      applyFilterChange();
      if (inField) document.activeElement.blur();
    }
  });

  // ---------- Devices ----------
  async function loadDevices() {
    try {
      const r = await fetch("/api/devices");
      const data = await r.json();
      state.devices = data.devices || [];
      const prev = state.serial;
      els.device.innerHTML = "";
      if (state.devices.length === 0) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "No devices";
        els.device.appendChild(opt);
        state.serial = null;
        return;
      }
      for (const d of state.devices) {
        const opt = document.createElement("option");
        opt.value = d.serial;
        const label = d.model ? `${d.model} (${d.serial}) — ${d.state}` : `${d.serial} — ${d.state}`;
        opt.textContent = label;
        els.device.appendChild(opt);
      }
      const target = state.devices.find((d) => d.serial === prev) ? prev : state.devices[0].serial;
      els.device.value = target;
      if (target !== state.serial) await connectSerial(target);
    } catch (e) {
      console.error("loadDevices failed", e);
    }
  }
  els.refreshDevices.addEventListener("click", loadDevices);
  els.device.addEventListener("change", () => connectSerial(els.device.value));

  // ---------- WebSocket ----------
  function closeWs() {
    if (state.ws) {
      try { state.ws.close(); } catch {}
      state.ws = null;
    }
  }

  async function connectSerial(serial) {
    if (!serial) return;
    closeWs();
    state.serial = serial;
    state.records = [];
    state.visibleIdx = [];
    state.pendingBatch = [];
    closeModal();
    updateSizer();
    render();
    updateStats();
    setConnStatus("offline");

    const proto = location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${location.host}/ws/${encodeURIComponent(serial)}`;
    openWs(url);
  }

  function openWs(url) {
    const ws = new WebSocket(url);
    state.ws = ws;
    ws.addEventListener("open", () => {
      setConnStatus("online");
      state.wsBackoff = 1000;
    });
    ws.addEventListener("message", (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg.type === "snapshot") {
        state.records = msg.records || [];
        rebuildVisible();
        updateSizer();
        render();
        updateStats();
        if (state.autoscroll) scrollToBottom();
      } else if (msg.type === "append") {
        const records = msg.records || [];
        if (state.paused) {
          state.pendingBatch.push(...records);
          updateStats();
          return;
        }
        const start = state.records.length;
        state.records.push(...records);
        appendVisible(start);
        updateSizer();
        render();
        updateStats();
        if (state.autoscroll) scrollToBottom();
      } else if (msg.type === "error") {
        console.error("server error", msg.message);
        setConnStatus("error");
      }
    });
    ws.addEventListener("close", () => {
      setConnStatus("offline");
      // Reconnect with backoff if the user is still on the same device
      const delay = Math.min(state.wsBackoff, 8000);
      state.wsBackoff = Math.min(state.wsBackoff * 2, 8000);
      setTimeout(() => {
        if (state.serial && (!state.ws || state.ws.readyState !== WebSocket.OPEN)) {
          openWs(url);
        }
      }, delay);
    });
    ws.addEventListener("error", () => {
      setConnStatus("error");
    });
  }

  // ---------- Presets ----------
  async function loadPresets() {
    try {
      const r = await fetch("/api/presets");
      const data = await r.json();
      state.presets = data.presets || [];
      renderPresets();
    } catch (e) {
      console.error(e);
    }
  }

  function renderPresets() {
    els.preset.innerHTML = "";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "— presets —";
    els.preset.appendChild(placeholder);
    for (const p of state.presets) {
      const opt = document.createElement("option");
      opt.value = p.name;
      opt.textContent = p.name;
      els.preset.appendChild(opt);
    }
  }

  els.preset.addEventListener("change", () => {
    const p = state.presets.find((x) => x.name === els.preset.value);
    if (!p) return;
    els.level.value = p.level || "";
    els.tag.value = p.tag || "";
    els.pkg.value = p.package || "";
    els.search.value = p.search || "";
    els.regex.checked = !!p.regex;
    state.filter = {
      level: els.level.value,
      tag: els.tag.value,
      package: els.pkg.value,
      search: els.search.value,
      regex: els.regex.checked,
    };
    applyFilterChange();
  });

  els.savePreset.addEventListener("click", async () => {
    const name = prompt("Save current filter as preset. Name:");
    if (!name || !name.trim()) return;
    const body = { name: name.trim(), ...state.filter };
    const r = await fetch("/api/presets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (r.ok) {
      const data = await r.json();
      state.presets = data.presets || [];
      renderPresets();
      els.preset.value = name.trim();
    }
  });

  els.deletePreset.addEventListener("click", async () => {
    const name = els.preset.value;
    if (!name) return;
    if (!confirm(`Delete preset "${name}"?`)) return;
    const r = await fetch(`/api/presets/${encodeURIComponent(name)}`, { method: "DELETE" });
    if (r.ok) {
      const data = await r.json();
      state.presets = data.presets || [];
      renderPresets();
    }
  });

  // ---------- Boot ----------
  (async function boot() {
    await Promise.all([loadDevices(), loadPresets()]);
    updateStats();
    render();
    // Periodic device list refresh (cheap)
    setInterval(loadDevices, 5000);
  })();
})();
