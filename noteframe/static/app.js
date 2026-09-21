"use strict";
const $ = (id) => document.getElementById(id);
const terminal = new Set(["complete", "failed", "cancelled"]);
let jobs = [],
  current = null,
  pages = [],
  filtered = [],
  shown = 48,
  layout = "grid",
  readerIndex = 0;
let pendingDelete = null,
  toastTimer,
  pollTimer,
  routeVersion = 0,
  librarySignature = "";
const presets = {
  board:
    "Best for a central board with browser controls or a speaker in the top corner. Exports keep the full picture.",
  slides:
    "Compare the full picture. Best for slides, diagrams, code and layouts where notes reach the edges.",
  detailed:
    "Capture every 3 seconds and keep smaller changes. Better for fast writing, with more pages and longer processing.",
};
function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}
function link(text, href, className, external = false) {
  const element = node("a", className, text);
  element.href = href;
  if (external) {
    element.target = "_blank";
    element.rel = "noopener noreferrer";
  }
  return element;
}
function button(text, className, action) {
  const element = node("button", className, text);
  element.type = "button";
  element.addEventListener("click", action);
  return element;
}
function file(job, path) {
  return `/files/${job.id}/${path.split("/").map(encodeURIComponent).join("/")}`;
}
function duration(seconds) {
  if (seconds < 60) return `${Math.floor(seconds)} sec`;
  const hours = Math.floor(seconds / 3600),
    mins = Math.floor((seconds % 3600) / 60);
  return hours ? `${hours}h ${mins}m` : `${mins} min`;
}
function size(bytes) {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${Math.round(bytes / 1024 / 1024)} MB`;
}
function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    $("toast").hidden = true;
  }, 5500);
}
async function api(path, options = {}) {
  const response = await fetch("/api" + path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) {
    let message = "Something went wrong. Please try again.";
    try {
      const body = await response.json();
      message = Array.isArray(body.detail)
        ? body.detail
            .map((item) => item.msg.replace(/^Value error, /, ""))
            .join(" ")
        : body.detail || message;
    } catch {
      /* A proxy or disconnected server may return non-JSON. */
    }
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}
function renderLibrary() {
  const signature = JSON.stringify(jobs);
  if (signature === librarySignature) return;
  librarySignature = signature;
  const grid = $("library-grid");
  grid.replaceChildren();
  $("library-count").textContent =
    `${jobs.length} notebook${jobs.length === 1 ? "" : "s"}`;
  if (!jobs.length) {
    const empty = node("div", "empty-library");
    empty.append(
      node("h3", "", "Your first notebook starts above."),
      node(
        "p",
        "",
        "Paste a lecture, tutorial or class recording. We’ll keep the visible notes together.",
      ),
    );
    grid.append(empty);
    return;
  }
  for (const job of jobs) {
    const card = node("article", "notebook-card");
    const cover = link("", `#notebook/${job.id}`, "cover-link");
    cover.setAttribute("aria-label", `Open ${job.title}`);
    if (job.cover && job.status === "complete") {
      const image = node("img");
      image.src = file(job, "thumbnails/" + job.cover);
      image.alt = "";
      image.loading = "lazy";
      cover.append(image);
    } else {
      const placeholder = node("div", "cover-placeholder");
      placeholder.append(
        node("span", "", job.status === "failed" ? "↻" : "▤"),
        node(
          "small",
          "",
          terminal.has(job.status)
            ? "Ready when you are"
            : "Making room for your notes…",
        ),
      );
      cover.append(placeholder);
    }
    const body = node("div", "card-body"),
      title = node("h3", "card-title");
    title.append(link(job.title, `#notebook/${job.id}`));
    const meta = node("div", "card-meta");
    meta.append(
      node("span", "", job.channel),
      node("span", "", job.duration ? duration(job.duration) : "YouTube video"),
    );
    if (job.page_count)
      meta.append(node("span", "", `${job.page_count.toLocaleString()} pages`));
    const bottom = node("div", "card-bottom");
    const label =
      job.status === "complete"
        ? "● Ready to read"
        : job.status === "failed"
          ? "Needs a retry"
          : job.status === "cancelled"
            ? "Cancelled"
            : `${Math.round(job.progress)}% · ${job.status}`;
    bottom.append(node("span", `status ${job.status}`, label));
    if (terminal.has(job.status)) {
      const remove = button("Remove", "text-button remove-button", () =>
        requestDelete(job),
      );
      remove.setAttribute("aria-label", `Remove ${job.title}`);
      bottom.append(remove);
    } else
      bottom.append(
        link("View progress →", `#notebook/${job.id}`, "text-button"),
      );
    body.append(title, meta, bottom);
    card.append(cover, body);
    grid.append(card);
  }
}
function renderHeading(job) {
  const root = $("notebook-heading");
  root.replaceChildren();
  const header = node("div", "notebook-header"),
    text = node("div");
  text.append(
    node("p", "eyebrow", "YOUR VISUAL NOTEBOOK"),
    node("h1", "", job.title),
  );
  const meta = node("div", "notebook-meta");
  meta.append(node("span", "", job.channel));
  if (job.duration) meta.append(node("span", "", duration(job.duration)));
  if (job.page_count)
    meta.append(
      node("span", "", `${job.page_count.toLocaleString()} original views`),
    );
  text.append(meta);
  header.append(text);
  root.append(header);
  if (job.status === "complete") {
    const actions = node("div", "export-actions");
    actions.append(
      link(
        `Open complete PDF · ${size(job.pdf_bytes)}`,
        file(job, "notes.pdf"),
        "primary",
        true,
      ),
    );
    if (job.exports.length) {
      const details = node("details", "hourly-exports");
      details.append(node("summary", "", "Smaller PDFs by hour"));
      const options = node("div");
      for (const item of job.exports)
        options.append(
          link(
            `Hour ${item.hour} · ${item.pages} pages ↗`,
            file(job, item.filename),
            "",
            true,
          ),
        );
      details.append(options);
      actions.append(details);
    }
    actions.append(link("Watch source video ↗", job.url, "", true));
    root.append(actions);
  }
}
function renderProgress(job) {
  const root = $("job-progress");
  root.replaceChildren();
  if (job.status === "complete") return;
  const panel = node("section", "progress-panel");
  const top = node("div", "progress-top");
  const active = !terminal.has(job.status);
  top.append(
    node(
      "h2",
      "",
      active
        ? "Your notebook is taking shape."
        : job.status === "failed"
          ? "This video needs another try."
          : "We stopped here.",
    ),
  );
  if (active)
    top.append(
      node("span", "progress-percent", `${Math.round(job.progress)}%`),
    );
  panel.append(top, node("p", "", job.message));
  if (active) {
    const progress = node("progress");
    progress.max = 100;
    progress.value = job.progress;
    progress.setAttribute("aria-label", "Overall extraction progress");
    panel.append(progress);
    const stages = node("div", "stages");
    for (const [label, values] of [
      ["Download", ["checking", "downloading"]],
      ["Capture", ["extracting"]],
      ["Select views", ["selecting"]],
      ["Export", ["exporting"]],
    ]) {
      stages.append(
        node("span", values.includes(job.status) ? "current" : "", label),
      );
    }
    panel.append(
      stages,
      node(
        "p",
        "small",
        "Long lectures can take a while. You can browse other notebooks while this runs. Keep the local server running.",
      ),
    );
  }
  const actions = node("div", "progress-actions");
  if (active) {
    const cancel = button(
      job.status === "cancelling" ? "Stopping…" : "Cancel extraction",
      "secondary",
      async () => {
        cancel.disabled = true;
        try {
          await api(`/jobs/${job.id}/cancel`, { method: "POST" });
          await refresh();
        } catch (error) {
          toast(error.message);
          cancel.disabled = false;
        }
      },
    );
    cancel.id = "cancel-extraction";
    cancel.disabled = job.status === "cancelling";
    actions.append(cancel);
  } else {
    actions.append(
      button("Retry extraction", "primary", async () => {
        try {
          const result = await api("/jobs", {
            method: "POST",
            body: JSON.stringify({
              url: job.url,
              preset: job.preset,
              quality: job.quality,
            }),
          });
          location.hash = `notebook/${result.id}`;
          await refresh();
        } catch (error) {
          toast(error.message);
        }
      }),
    );
    actions.append(link("Try another video", "#new", "secondary"));
  }
  panel.append(actions);
  root.append(panel);
}
function setupPages() {
  $("hour-filter").replaceChildren(new Option("All hours", "all"));
  for (const hour of [
    ...new Set(pages.map((p) => Math.floor(p.timestamp / 3600))),
  ]) {
    $("hour-filter").append(new Option(`Hour ${hour + 1}`, String(hour)));
  }
  $("page-search").value = "";
  shown = 48;
  renderPages();
}
function renderPages() {
  const query = $("page-search").value.trim(),
    hour = $("hour-filter").value;
  filtered = pages.filter(
    (page) =>
      (hour === "all" || Math.floor(page.timestamp / 3600) === Number(hour)) &&
      (!query || String(page.page) === query || page.time.includes(query)),
  );
  const grid = $("notes-grid");
  grid.replaceChildren();
  grid.classList.toggle("reading", layout === "reading");
  const visible = filtered.slice(0, shown);
  $("page-count").textContent =
    `${filtered.length.toLocaleString()} page${filtered.length === 1 ? "" : "s"}`;
  for (const [index, page] of visible.entries()) {
    const card = node("article", "note-card");
    const open = button("", "note-image-button", () => openReader(index));
    open.setAttribute("aria-label", `Open page ${page.page} at ${page.time}`);
    const image = node("img");
    image.src = file(
      current,
      (layout === "reading" ? "pages/" : "thumbnails/") + page.filename,
    );
    image.alt = `On-screen notes at ${page.time}`;
    image.loading = "lazy";
    open.append(image);
    const bottom = node("div", "note-card-bottom"),
      label = node("div");
    label.append(
      node("b", "", `Page ${page.page}`),
      node("time", "", page.time),
    );
    bottom.append(
      label,
      link(
        "Watch this moment ↗",
        `${current.url}&t=${Math.floor(page.timestamp)}s`,
        "",
        true,
      ),
    );
    card.append(open, bottom);
    grid.append(card);
  }
  if (!visible.length) {
    const empty = node("div", "empty-library");
    empty.append(
      node("h3", "", "No pages at that spot."),
      node(
        "p",
        "",
        "Try a page number like 42, a timestamp like 02:15, or another hour.",
      ),
    );
    grid.append(empty);
  }
  $("load-more").hidden = filtered.length <= shown;
  $("load-more").textContent =
    `Show ${Math.min(48, filtered.length - shown)} more notes`;
}
function openReader(index) {
  readerIndex = index;
  const page = filtered[index];
  $("reader-title").textContent = `Page ${page.page} · ${page.time}`;
  $("reader-img").src = file(current, "pages/" + page.filename);
  $("reader-img").alt =
    `Original note page ${page.page} captured at ${page.time}`;
  $("reader-source").href = `${current.url}&t=${Math.floor(page.timestamp)}s`;
  $("reader-original").href = file(current, "pages/" + page.filename);
  $("reader-prev").disabled = index === 0;
  $("reader-next").disabled = index === filtered.length - 1;
  if (!$("reader").open) $("reader").showModal();
}
function requestDelete(job) {
  pendingDelete = job;
  $("delete-dialog").showModal();
  $("delete-no").focus();
}
async function route() {
  const version = ++routeVersion;
  const match = location.hash.match(/^#notebook\/([a-f0-9]{32})$/);
  $("home").hidden = Boolean(match);
  $("notebook").hidden = !match;
  if (!match) {
    current = null;
    document.title = "NoteFrame — Your video, in notes.";
    if (location.hash === "#new") {
      $("new").scrollIntoView();
      $("video-url").focus({ preventScroll: true });
    } else if (location.hash === "#library") $("library").scrollIntoView();
    else window.scrollTo(0, 0);
    return;
  }
  try {
    const job = await api(`/jobs/${match[1]}`);
    if (version !== routeVersion) return;
    current = job;
    pages = [];
    $("notes-content").hidden = true;
    renderHeading(current);
    renderProgress(current);
    window.scrollTo(0, 0);
    document.title = `${current.title} — NoteFrame`;
    if (current.status === "complete") {
      const result = await api(`/jobs/${current.id}/pages`);
      if (version !== routeVersion) return;
      pages = result;
      $("notes-content").hidden = false;
      setupPages();
    }
  } catch (error) {
    toast(error.message);
    location.hash = "library";
  }
}
async function refresh() {
  clearTimeout(pollTimer);
  try {
    jobs = await api("/jobs");
    renderLibrary();
    if (current && !terminal.has(current.status)) {
      const updated = jobs.find((job) => job.id === current.id);
      if (updated) {
        if (updated.status === "complete") await route();
        else {
          const focused = document.activeElement?.id;
          current = updated;
          renderHeading(current);
          renderProgress(current);
          if (focused) $(focused)?.focus({ preventScroll: true });
        }
      }
    }
  } catch (error) {
    toast(`Cannot reach the local server. ${error.message}`);
  } finally {
    pollTimer = setTimeout(
      refresh,
      jobs.some((job) => !terminal.has(job.status)) ? 2000 : 10000,
    );
  }
}
$("extract-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("form-error").hidden = true;
  $("extract-button").disabled = true;
  try {
    const job = await api("/jobs", {
      method: "POST",
      body: JSON.stringify({
        url: $("video-url").value,
        preset: document.querySelector('input[name="preset"]:checked').value,
        quality: Number($("quality").value),
      }),
    });
    location.hash = `notebook/${job.id}`;
    await refresh();
  } catch (error) {
    $("form-error").textContent = error.message;
    $("form-error").hidden = false;
  } finally {
    $("extract-button").disabled = false;
  }
});
document.querySelectorAll('input[name="preset"]').forEach((input) =>
  input.addEventListener("change", () => {
    $("preset-description").textContent = presets[input.value];
  }),
);
for (const id of ["hour-filter", "page-search"])
  $(id).addEventListener(id === "page-search" ? "input" : "change", () => {
    shown = 48;
    renderPages();
  });
for (const mode of ["grid", "reading"])
  $(mode + "-view").addEventListener("click", () => {
    layout = mode;
    $("grid-view").setAttribute("aria-pressed", String(mode === "grid"));
    $("reading-view").setAttribute("aria-pressed", String(mode === "reading"));
    renderPages();
  });
$("load-more").addEventListener("click", () => {
  shown += 48;
  renderPages();
});
$("reader-close").addEventListener("click", () => $("reader").close());
$("reader-prev").addEventListener("click", () => openReader(readerIndex - 1));
$("reader-next").addEventListener("click", () => openReader(readerIndex + 1));
$("reader").addEventListener("keydown", (event) => {
  if (event.key === "ArrowLeft" && readerIndex > 0) {
    event.preventDefault();
    openReader(readerIndex - 1);
  }
  if (event.key === "ArrowRight" && readerIndex < filtered.length - 1) {
    event.preventDefault();
    openReader(readerIndex + 1);
  }
});
$("delete-no").addEventListener("click", () => $("delete-dialog").close());
$("delete-yes").addEventListener("click", async () => {
  if (!pendingDelete) return;
  $("delete-yes").disabled = true;
  try {
    await api(`/jobs/${pendingDelete.id}`, { method: "DELETE" });
    $("delete-dialog").close();
    toast("Notebook removed from this computer.");
    await refresh();
  } catch (error) {
    toast(error.message);
  } finally {
    $("delete-yes").disabled = false;
  }
});
window.addEventListener("hashchange", route);
async function start() {
  try {
    const health = await api("/health");
    if (!health.ready) {
      $("setup-warning").hidden = false;
      $("setup-warning").textContent =
        "One-time setup: install FFmpeg and Node.js (or Deno), then restart NoteFrame. Your existing notes are still available.";
    }
  } catch (error) {
    toast(error.message);
  }
  await refresh();
  await route();
}
start();
