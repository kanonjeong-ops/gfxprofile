# Third-party notices

## @decky/api 1.1.3 — LGPL-2.1

This plugin's `dist/index.js` **contains bundled code** from `@decky/api`,
which is licensed under the GNU Lesser General Public License v2.1.
A full copy of that license is included at `licenses/LGPL-2.1.txt`.

- Upstream: https://github.com/SteamDeckHomebrew/loader-api
- The complete source of the exact bundled version is included in this
  repository at `third_party/decky-api-1.1.3.tgz` (the published npm
  package, which contains its TypeScript source). The version is pinned
  in `pnpm-lock.yaml`.

To modify `@decky/api` and relink it with this plugin: point the
`@decky/api` dependency in `package.json` at your modified copy, then run
`pnpm install && pnpm build` to produce a new `dist/index.js`.
This plugin's own code is released under the Unlicense, so nothing here
restricts that.

## @decky/ui — LGPL-2.1

Used at runtime but **not distributed** with this plugin — Decky Loader
provides it. Listed for completeness.

## tslib — 0BSD

Declared as a dependency, but no tslib code is present in the distributed
`dist/index.js`. 0BSD imposes no conditions.
