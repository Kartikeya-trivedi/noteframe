# Bootstrap maintenance

`setup.bat` and `start.bat` quote their own directory and disable CMD delayed expansion, then call `bootstrap.ps1`. The helper stays compatible with Windows PowerShell 5.1. Use literal file APIs for paths: a checkout may contain spaces, ampersands, brackets or exclamation marks.

`downloads.json` pins x64 archives. Their sources are:

- CPython's [official NuGet distribution](https://docs.python.org/3.13/using/windows.html#the-nuget-org-packages), package `python` on api.nuget.org. Unlike the embeddable ZIP, this contains `venv` and `ensurepip`. The SHA-256 recorded here was computed from the downloaded HTTPS package.
- [Node.js release archives and published SHASUMS256.txt](https://nodejs.org/dist/v22.23.2/SHASUMS256.txt).
- [Gyan's FFmpeg release packages and SHA-256 sidecars](https://www.gyan.dev/ffmpeg/builds/), linked by [FFmpeg's Windows download page](https://ffmpeg.org/download.html#build-windows).

Never fetch an unversioned “latest” binary and skip integrity checking. When updating a pin, download and verify the new archive, inspect its layout, adjust `executable` if necessary, run the bootstrap in a fresh folder with `-LocalTools`, and run the tests. This is archive integrity checking against the repository's manifest, not signature verification of every archive member.

Downloads are streamed into `.partial` files, checked, and moved into the cache only on success. Archives expand into a unique staging folder and are validated before replacing the tool directory. Backups and cleanup paths are checked against their intended parent. No code path removes `.data/`.

Bootstrap checks use only the standard PowerShell/.NET runtime; no Pester install is needed. Full fresh-install CI also exercises the real pinned downloads and Python installation. Network outages or upstream artifact withdrawal cause visible failures, never fallback to unverified binaries.
