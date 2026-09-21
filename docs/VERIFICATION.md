# Verification of v0.1.0

Checked locally on Windows, Python 3.12, with FFmpeg and Node.js installed.

- 17 automated tests passed. These include a generated three-board video processed by real FFmpeg, screenshot selection, PDF rendering inputs, page count, timestamp text and clickable source links.
- URL validation rejected arbitrary hosts, localhost targets, deceptive domains, non-video YouTube URLs and unusual ports.
- Queue tests exercised active-job deduplication, queued/running cancellation, deletion of stopped jobs, persistence, and restart recovery. A real sleeping child process was terminated by cancellation.
- API checks covered Host/Origin restrictions, hidden metadata files, valid artifact access and unknown jobs.
- Ruff and JavaScript syntax checks passed.
- A fresh public, short YouTube video was submitted through the browser UI and completed through download, capture, gallery and PDF export. Both exported pages had the expected source URI annotations. This checked the network pipeline; it was not an extraction-quality benchmark.
- The previous 1,011-page lecture extraction was imported and browsed in the new app. Browser checks covered rejected links, page 500 search, full-resolution preview, clearing search, reading mode, next-page navigation and source timestamps. No browser error/warning logs were observed during these checks.

The imported lecture was not downloaded or fully re-extracted during this app build. The earlier extraction was visually spot-checked; neither run has a ground-truth coverage score. Responsive CSS is included, but this validation does not claim a full mobile device/browser matrix.

Two upstream deprecation warnings were emitted by Starlette's HTTPX/AnyIO test-client integration. They did not fail the tests.

`requirements-dev.lock.txt` records the versions installed for this verification, excluding the local editable project path. It is a Windows development environment snapshot, not a cross-platform hash-locked distribution.
