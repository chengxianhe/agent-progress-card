# Bundled Python runtime

Distributable Weiguang apps include CPython 3.12.16 from
[python-build-standalone](https://github.com/astral-sh/python-build-standalone), release `20261110`.
Download URLs and SHA-256 digests are fixed in `desktop/runtime/python-lock.json`.

The runtime is redistributed with its original license files, including the PSF license at
`Contents/Resources/Python/lib/python3.12/LICENSE.txt` and dependency notices throughout that prefix.
The install-only archive omits the full distribution’s dependency license directory.
We additionally preserve all 20 texts from the same release’s full archive in
`Contents/Resources/Python/licenses/`; their source and digest are in
`desktop/runtime/license-source.json`. Unused developer bin launchers are excluded.
Those components retain their own licenses; the application's MIT license does not replace them.

The runtime provider's [licensing notes](https://gregoryszorc.com/docs/python-build-standalone/main/running.html#licensing)
describe the included libraries. Preserve the runtime libraries and all notices when repackaging.
Original project attribution remains in `LICENSE` and `NOTICE`.
