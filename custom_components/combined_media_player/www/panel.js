/**
 * Combined Media Player – Gerätereihenfolge Panel
 * Drag & Drop reordering of source devices (= priority order).
 */
class CombinedMpOrderPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._entries = [];
    this._loaded = false;
    this._saving = {};
    this._dragSrc = null;
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first && !this._loaded) {
      this._loaded = true;
      this._loadEntries();
    }
  }

  // ── Backend calls ─────────────────────────────────────────────────────────

  async _loadEntries() {
    try {
      const result = await this._hass.callWS({
        type: "combined_media_player/get_entries",
      });
      this._entries = result.entries.map((e) => ({
        ...e,
        sources: [...e.sources],
        dirty: false,
      }));
    } catch (err) {
      this._entries = [];
      this._error = `Fehler beim Laden: ${err.message ?? err}`;
    }
    this._render();
  }

  async _save(entryIndex) {
    const entry = this._entries[entryIndex];
    this._saving[entry.entry_id] = true;
    this._render();
    try {
      await this._hass.callWS({
        type: "combined_media_player/reorder_sources",
        entry_id: entry.entry_id,
        sources: entry.sources,
      });
      entry.dirty = false;
    } catch (err) {
      this._error = `Speichern fehlgeschlagen: ${err.message ?? err}`;
    }
    delete this._saving[entry.entry_id];
    this._render();
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  _friendlyName(entityId) {
    const state = this._hass?.states?.[entityId];
    return state?.attributes?.friendly_name ?? entityId;
  }

  _esc(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ── Render ────────────────────────────────────────────────────────────────

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 16px;
          max-width: 720px;
          margin: 0 auto;
          font-family: var(--paper-font-body1_-_font-family, inherit);
          color: var(--primary-text-color);
        }
        h1 {
          font-size: 1.4em;
          font-weight: 500;
          margin: 0 0 4px;
        }
        .subtitle {
          color: var(--secondary-text-color, #888);
          font-size: 0.9em;
          margin: 0 0 20px;
        }
        .card {
          background: var(--card-background-color, #fff);
          border-radius: 12px;
          box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,.12));
          margin-bottom: 20px;
          overflow: hidden;
        }
        .card-header {
          padding: 14px 16px 10px;
          font-size: 1.05em;
          font-weight: 600;
          border-bottom: 1px solid var(--divider-color, #e0e0e0);
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .card-header svg {
          flex-shrink: 0;
          opacity: .6;
        }
        .hint {
          font-size: 0.78em;
          color: var(--secondary-text-color, #888);
          padding: 6px 16px 2px;
        }
        ul.source-list {
          list-style: none;
          margin: 0;
          padding: 4px 0;
        }
        li.source-item {
          display: flex;
          align-items: center;
          padding: 9px 16px;
          gap: 12px;
          cursor: grab;
          user-select: none;
          border-radius: 8px;
          margin: 2px 8px;
          transition: background 0.12s;
        }
        li.source-item:active { cursor: grabbing; }
        li.source-item:hover { background: var(--secondary-background-color, #f5f5f5); }
        li.source-item.drag-over {
          background: var(--primary-color, #03a9f4);
          opacity: 0.45;
        }
        li.source-item.dragging { opacity: 0.25; }
        .handle {
          color: var(--secondary-text-color, #aaa);
          font-size: 1.1em;
          line-height: 1;
        }
        .badge {
          min-width: 22px;
          height: 22px;
          border-radius: 50%;
          background: var(--primary-color, #03a9f4);
          color: #fff;
          font-size: 0.72em;
          font-weight: 700;
          display: flex;
          align-items: center;
          justify-content: center;
          flex-shrink: 0;
        }
        .entity-info { flex: 1; overflow: hidden; }
        .entity-name {
          font-size: 0.93em;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .entity-id {
          font-size: 0.74em;
          color: var(--secondary-text-color, #888);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .card-footer {
          padding: 10px 16px 14px;
          display: flex;
          justify-content: flex-end;
        }
        button.save {
          background: var(--primary-color, #03a9f4);
          color: #fff;
          border: none;
          border-radius: 6px;
          padding: 8px 22px;
          font-size: 0.88em;
          font-weight: 500;
          cursor: pointer;
          transition: opacity .15s;
        }
        button.save:disabled { opacity: .5; cursor: default; }
        .error {
          background: var(--error-color, #db4437);
          color: #fff;
          padding: 10px 16px;
          border-radius: 8px;
          margin-bottom: 16px;
          font-size: 0.88em;
        }
        .empty {
          padding: 40px 16px;
          text-align: center;
          color: var(--secondary-text-color, #888);
        }
      </style>

      <h1>Gerätereihenfolge</h1>
      <p class="subtitle">Ziehe die Geräte in die gewünschte Prioritätsreihenfolge.<br>
        Position 1 = höchste Priorität (wird zuerst angezeigt, wenn aktiv).</p>

      ${this._error ? `<div class="error">${this._esc(this._error)}</div>` : ""}

      ${
        !this._loaded
          ? `<div class="empty">Lade…</div>`
          : this._entries.length === 0
          ? `<div class="empty">Keine Combined Media Player konfiguriert.</div>`
          : this._entries.map((e, i) => this._renderCard(e, i)).join("")
      }
    `;
    this._error = null;
    this._attachEvents();
  }

  _renderCard(entry, idx) {
    const saving = !!this._saving[entry.entry_id];
    return `
      <div class="card">
        <div class="card-header">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 3v9.28A4 4 0 1 0 16 16V7h4V3h-8zm-2 15a2 2 0 1 1 0-4 2 2 0 0 1 0 4z"/>
          </svg>
          ${this._esc(entry.title)}
        </div>
        <p class="hint">⠿ Zeilen ziehen zum Umsortieren</p>
        <ul class="source-list" data-entry="${idx}">
          ${entry.sources
            .map(
              (src, si) => `
            <li class="source-item"
                draggable="true"
                data-entry="${idx}"
                data-index="${si}">
              <span class="handle">⠿</span>
              <span class="badge">${si + 1}</span>
              <span class="entity-info">
                <div class="entity-name">${this._esc(this._friendlyName(src))}</div>
                <div class="entity-id">${this._esc(src)}</div>
              </span>
            </li>`
            )
            .join("")}
        </ul>
        <div class="card-footer">
          <button class="save" data-entry="${idx}" ${saving ? "disabled" : ""}>
            ${saving ? "Wird gespeichert…" : "Reihenfolge speichern"}
          </button>
        </div>
      </div>
    `;
  }

  // ── Events ────────────────────────────────────────────────────────────────

  _attachEvents() {
    // Save buttons
    this.shadowRoot.querySelectorAll("button.save").forEach((btn) => {
      btn.addEventListener("click", () => {
        this._save(parseInt(btn.dataset.entry, 10));
      });
    });

    // Drag & drop
    const items = this.shadowRoot.querySelectorAll("li.source-item");
    items.forEach((item) => {
      item.addEventListener("dragstart", (e) => {
        this._dragSrc = item;
        item.classList.add("dragging");
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", ""); // required in Firefox
      });

      item.addEventListener("dragend", () => {
        item.classList.remove("dragging");
        items.forEach((i) => i.classList.remove("drag-over"));
        this._dragSrc = null;
      });

      item.addEventListener("dragover", (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        if (item !== this._dragSrc) {
          items.forEach((i) => i.classList.remove("drag-over"));
          item.classList.add("drag-over");
        }
      });

      item.addEventListener("dragleave", () => {
        item.classList.remove("drag-over");
      });

      item.addEventListener("drop", (e) => {
        e.preventDefault();
        if (!this._dragSrc || this._dragSrc === item) return;

        const srcEntryIdx = parseInt(this._dragSrc.dataset.entry, 10);
        const dstEntryIdx = parseInt(item.dataset.entry, 10);
        if (srcEntryIdx !== dstEntryIdx) return; // no cross-entry drag

        const srcIdx = parseInt(this._dragSrc.dataset.index, 10);
        const dstIdx = parseInt(item.dataset.index, 10);

        const entry = this._entries[srcEntryIdx];
        const [moved] = entry.sources.splice(srcIdx, 1);
        entry.sources.splice(dstIdx, 0, moved);
        entry.dirty = true;

        this._render();
      });
    });
  }
}

customElements.define("combined-mp-order-panel", CombinedMpOrderPanel);
