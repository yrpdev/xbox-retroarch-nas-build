# Xbox Series RetroArch SMB repair review

This isolated repository contains the approved Windows build for the Xbox NAS repair. Builds run only by manual dispatch. No Xbox package is installed by this repository; the built package requires separate backup and native verification.

The installed August 19, 2026 RetroArch UWP release can list SMB directories, but its UWP file backend returns zero for the size of an opened SMB file and does not dispatch SMB stat calls. The small source patch initializes SMB file size using the existing seek/tell helpers and dispatches stat to the existing SMB helper. These paths affect ROM, archive and thumbnail reads. The first repair, version 1.22.2.1, has passed native Xbox NES ZIP launch, Mario movement, and NAS PNG artwork tests.

This revision also repairs the UWP fallback for older arcade cores that require native file paths. For `smb://` sources it streams through frontend VFS into the existing local cache using a fixed 64 KiB buffer, verifies the expected byte count and read/write/flush/close results, and removes failed partial copies. Local-path `CopyFileFromAppW` behavior is preserved. Bundled MAME 2003 (0.78) is narrowly routed through that cache because it initializes VFS v1 file streams but still validates content using native stat. Existing temporary-file cleanup remains in control of cached game lifetime. This new arcade behavior still requires Windows-build and native Xbox tests.

The cache copies only the selected file. It does not copy whole NAS folders or infer parent/BIOS dependencies. FBA searches its local ROM directory, then `system/fba`, then `system`; FBA2012 searches only the ROM directory, so required BIOS/parent ZIPs must already be beside its cached content. Initial standalone tests are FBA2012 1942 and MAME2003 Pac-Man; Metal Slug additionally requires the verified NeoGeo BIOS at an FBA-supported local system path.

## Reviewed repository layout

Only these six files are included in this public review/build repository:

```
.github/workflows/xbox-smb-fix.yml  # from xbox-smb-fix.artifact-only.yml
patches/retroarch-uwp-smb-size-stat.patch
tools/appx_delta.py
tools/test_appx_delta.py
tools/requirements-bsdiff.txt
README.md
```

Do not copy the entire workspace, NAS files, ROMs, Xbox backups, account details or signing keys into that repository. The workflow obtains the existing public upstream source and its public test signing certificate itself. It has only `workflow_dispatch` and `contents: read`, uses standard `windows-2022`, and does not publish releases, deploy, install, alter an Xbox, use an Actions cache, or request paid runners.

## Build inputs and checks

- Upstream: <https://github.com/XboxEmulationHub/RetroArch/tree/fac75f5d667f2a501c33b52c70e135d6395266dc>
- Original package: <https://github.com/XboxEmulationHub/RetroArch/releases/download/08-19-2026/RetroArch-SeriesConsoles-AllCores.appx>
- Original package size: `611442346` bytes.
- Original SHA256: `0b327bf6cc4d0b18caa0a0fc2337c96b53920f46bbfd136920e1ed9e5656b00a`.
- Package Name: `1e4cf179-f3c2-404f-b9f3-cb2070a5aad8`; Publisher: `CN=libretro`; x64; version changes from `1.22.2.0` to `1.22.2.2`.
- Public signing certificate SHA256: `881ef621c708e52248b21bc9fa1c4c1c0be603f3f13f0419b6aa6bf5295d1bb2`, matching the installed original package. Its public source certificate expires March 12, 2126.

The workflow follows the pinned official UWP workflow's asset initialization preparation and Release/x64 MSBuild path. It preserves the original package's core/dependency DLL payloads instead of downloading current cores. SDK MakeAppx unpacks the original package, respecting escaped Appx part names. MESA dependencies are copied to their separate project item group to avoid duplicate output names. Each baseline DLL is compared against the final package by SHA256. Original Appx contains no `.lck` members; the recipe also preserves any that are present.

The source project has no explicit PlatformToolset override and targets Windows SDK `10.0` (minimum `10.0.15063.0`). The current Windows 2022 runner inventory supplies VS 2022, Windows SDKs, UWP VC support and MSBuild. The tracked source contains C++/WinRT `3.0.260520.1`; no NuGet restore is inferred. The workflow checks these prerequisites and retains upstream's default toolset. The first repair compiled and signed successfully using these prerequisites. This revised cache code still requires its own successful Windows build and native tests. It must fail without uploading a package if any required step fails.

## Small, exact download

Only a delta and review metadata are uploaded, with one-day retention and no artifact cache. The combined artifact must be **less than 450,000,000 bytes**, or the job fails before upload. Actual delta size remains unknown until the Windows build exists.

`appx_delta.py` treats a signed Appx as raw ZIP records. Unchanged records are copied from the exact baseline; changed records use hash-pinned `bsdiff4 1.3.2` or literal bytes. It does not unzip/recompress/re-sign the reconstructed package. The workflow reconstructs the entire package and compares its full SHA256 against the signed build before upload. This preserves the signature bytes exactly. A matching full SHA is the acceptance check; this is transport of a built package, not runtime patching.

Artifact contents include `package-delta.bin`, `package-delta.json`, `build-review.json`, provenance, the exact build workflow, source diff and generated asset-init sources, this README, and reconstruction tools. Neither the original 611 MB Appx nor the newly built full Appx is uploaded. GitHub may retain ordinary workflow logs; the artifact expires after one day or can be deleted after a verified local download. No billing setting is changed.

## Reconstruct locally after an authorized successful build

Use Python **3.12**, an unused destination path, the original package listed above, and the downloaded artifact directory. On this Mac the existing original package is `work/xbox-setup/RetroArch-SeriesConsoles-AllCores.appx`. Keep the original package unchanged for rollback.

```
python3.12 -m venv work/xbox-setup/smb-delta-venv
work/xbox-setup/smb-delta-venv/bin/python -m pip install --disable-pip-version-check --index-url https://pypi.org/simple --only-binary=:all: --require-hashes --no-deps -r ARTIFACT/requirements-bsdiff.txt
work/xbox-setup/smb-delta-venv/bin/python ARTIFACT/appx_delta.py apply work/xbox-setup/RetroArch-SeriesConsoles-AllCores.appx ARTIFACT work/xbox-setup/RetroArch-SeriesConsoles-SMBFix_1.22.2.2.appx
```

Replace `ARTIFACT` with the actual downloaded directory. The helper verifies baseline size/hash, payload size/hash, and complete reconstructed size/hash; it refuses an existing output. Compare its final SHA to both `package-delta.json` and `build-review.json`, independently inspect the reconstructed Appx identity/signature, and preserve the complete downloaded provenance before artifact deletion. No install command is included. Xbox Dev Home reset the first updated package from Game to App; explicitly recheck and restore Game classification after this update as well.

Before an Xbox update, back up the existing LocalState and playlist/config files. Matching package identity is expected to retain app data, but this remains unverified until native update/readback. Versioned installed `D:\DevelopmentFiles\WindowsApps\...` paths will change, so playlists with absolute core paths require adjustment. Keep the original package plus backup for recovery. Do not uninstall the working package as a shortcut.

## Acceptance after reconstruction

Native Xbox tests must show the existing local and NAS NES games and NAS thumbnails still work, then confirm streamed cache launches for FBA2012 1942, MAME2003 Pac-Man and FBA Metal Slug with its verified local BIOS. Confirm exact arcade core paths, saves and cheat lists. MAME2010 remains a local cache where its older core lacks direct SMB support. Do not mark PS1 verified until an actual game boots and plays; the current local SwanStation PBP test only reached the BIOS screen.

## Primary references

- [Pinned upstream UWP workflow](https://github.com/XboxEmulationHub/RetroArch/blob/fac75f5d667f2a501c33b52c70e135d6395266dc/.github/workflows/UWP.yml)
- [Windows 2022 runner inventory](https://github.com/actions/runner-images/blob/main/images/windows/Windows2022-Readme.md)
- [Microsoft MakeAppx](https://learn.microsoft.com/en-us/windows/uwp/packaging/create-app-package-with-makeappx-tool)
- [bsdiff4 project](https://github.com/ilanschnell/bsdiff4), [PyPI version metadata](https://pypi.org/pypi/bsdiff4/1.3.2/json)
- [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions), [artifact deletion](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/remove-workflow-artifacts)


The cache-copy helper compiled separately with `clang -std=c99 -Wall -Wextra -Werror` and passed 11 offline success/error cases, including bounded reads, early EOF, negative reads, short writes, flush and close failures, and partial-output cleanup. Those local test artifacts remain outside this six-file public repository. The patch passed `git apply --check` against the exact pinned source. Arcade native testing remains required; no core DLL has been rebuilt or substituted.
