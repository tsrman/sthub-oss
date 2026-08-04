# Third-party notices

STHub itself remains licensed under [Apache-2.0](LICENSE). The components below
do not change that license. They carry separate notice and redistribution
obligations when their relevant artifacts are distributed.

## `sharp` platform libvips binaries

- License: LGPL-3.0-or-later. See
  [the bundled license text](third_party/licenses/LGPL-3.0.txt). LGPL-3.0
  incorporates the terms of GPL-3.0 by reference, so
  [the GPL-3.0 text](third_party/licenses/GPL-3.0.txt) is bundled alongside it.
- Attribution and package source: [lovell/sharp-libvips v1.3.2](https://github.com/lovell/sharp-libvips/tree/v1.3.2).
  The actual `node:20-alpine` Linux x64 Docker build installs
  `@img/sharp-libvips-linuxmusl-x64` 1.3.2, whose metadata declares libvips
  8.18.3. Corresponding libvips source is available from
  [libvips/libvips](https://github.com/libvips/libvips/tree/v8.18.3).
- Role: `sharp` selects an optional `@img/sharp-libvips-*` package matching the
  target operating system, architecture, and C library. Thus a multi-architecture
  image may contain a different matching platform binary. Next.js may load that
  prebuilt shared `libvips` binary at runtime for image optimization; it is not an
  intentional browser-bundle dependency.
- Redistribution: this notice, the LGPL text, and the corresponding-source/
  relinking obligations apply to whichever platform binary is included in the
  distributed Docker image, standalone runtime, or other artifact. Distributors
  must retain the notice and LGPL text, provide corresponding source (or a durable
  written offer/access path) for LGPL-covered components and modifications, and
  preserve recipients' rights to replace/relink the LGPL library as applicable.

## `caniuse-lite` 1.0.30001799

- License: CC-BY-4.0. See
  [the bundled license text](third_party/licenses/CC-BY-4.0.txt).
- Creator attribution (installed package metadata): Ben Briggs
  &lt;beneb.info@gmail.com&gt; (http://beneb.info). Source:
  [Browserslist/caniuse-lite](https://github.com/browserslist/caniuse-lite).
- Role: browser-support data consumed by Browserslist/PostCSS tooling during
  frontend builds; it is not intentionally shipped in STHub's browser code.
- Redistribution: if this data is included in a source archive, build image, or
  other distributed artifact, retain attribution, the CC-BY-4.0 license and a
  link to the source, and indicate modifications where applicable.

## `psycopg2-binary` 2.9.10

- License: LGPL-3.0-or-later with the OpenSSL exception. See
  [the bundled LGPL-3.0 text](third_party/licenses/LGPL-3.0.txt) and
  [the GPL-3.0 text](third_party/licenses/GPL-3.0.txt) it incorporates.
- Attribution and package source:
  [psycopg/psycopg2](https://github.com/psycopg/psycopg2).
- Role: installed into the distributed `streamlit-base` image
  (`streamlit-base/Dockerfile`) so user applications can reach PostgreSQL. The
  `-binary` distribution also bundles prebuilt `libpq` and its TLS dependencies.
  This is the only copyleft component on the Python side.
- Redistribution: distributors of the `streamlit-base` image must retain this
  notice and the LGPL/GPL texts, provide corresponding source (or a durable
  written offer) for the LGPL-covered components, and preserve recipients'
  rights to replace or relink the LGPL library.

## MPL-2.0 build-time components

- License: MPL-2.0. See
  [the bundled license text](third_party/licenses/MPL-2.0.txt).
- Components (installed package metadata): `lightningcss` 1.32.0 with its
  platform binaries, and `axe-core` 4.12.1. Sources:
  [parcel-bundler/lightningcss](https://github.com/parcel-bundler/lightningcss)
  and [dequelabs/axe-core](https://github.com/dequelabs/axe-core).
- Role: both are `devDependencies` reached through the Next.js/PostCSS toolchain
  and the testing stack. They run during builds and tests and are not copied
  into the frontend runtime image, so they are not part of STHub's shipped
  browser code.
- Redistribution: MPL-2.0 obligations attach per file when the covered source or
  its binaries are distributed. If a source archive, image, or other artifact
  includes these packages, retain this notice and the MPL-2.0 text and make the
  corresponding source form available.

## Bundled Monaco Editor notices

`monaco-editor` 0.49.0 is bundled under MIT. Its Microsoft copyright license is
at `frontend/public/monaco-editor/LICENSE`; its complete upstream third-party
notice file is preserved verbatim at
`frontend/public/monaco-editor/ThirdPartyNotices.txt`.
