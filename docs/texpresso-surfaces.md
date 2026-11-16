# Display-density live preview

TeXstudio Espresso uses the engine's `surfaces: 1` PNG API for foreground
pages, visible/background prefetch and the magnifier. The runtime and packaging
checks require this capability. There is no alternate legacy renderer in the
Qt client. The shared engine still supports older commands for other clients.

Each image carries the complete page bounds, a device-pixel page grid, an integer
clip within that grid and a raster ID. SyncTeX, links, TikZ bounds and text-width
fitting retain their full-page coordinates. The canvas places cropped pixels at
their clip offset, without stretching them across the whole page. Current-density
images map one raster pixel to one device pixel; retained images can be scaled
while a replacement is pending. Page origins snap to the device grid, including
viewport/toolbar/scroll offsets. Changing display density requests new surfaces.

The viewport requests a rectangle with 256 pixels of overscan rounded outward
to 512-pixel boundaries. Scrolling inside a retained rectangle does not request
another image. The native canonical 512-pixel lattice makes overlapping exports
agree; the client does not retain a separate image for every lattice cell.

Allocation stays bounded at 16 million pixels and 8192 pixels per surface side.
Page grid width can reach 65536 without allocating a full page at that density.
There is one cached surface per page, a 32–64 MiB decoded-image cache, at most
16 page widgets, one decode worker and one latest pending frame. Main/stale
images, color conversion, lens images and temporary patch copies are additional
bounded allocations; the cache budget is not a process-memory ceiling. Hidden
canvases release converted pixmaps as well as their decoded images.

Patch bases require matching page, page bounds, grid and clip. A missing or
mismatched base requests a keyframe. Request ID, source sequence and engine
revision fence stale replies; obsolete viewport density/coverage cancels the
old request. Page discovery uses the same API with a tiny background surface.

## Verification

Build the client with low concurrency, then run tests offscreen:

```sh
cmake --build build-texpresso --parallel 1
QT_QPA_PLATFORM=offscreen SDL_VIDEODRIVER=dummy \
TEXPRESSO_TEST_ENGINE="$PWD/native/texpresso/build/texpresso" \
ctest --test-dir build-texpresso --output-on-failure -j1
```

The rendering suite checks crop placement, overscan reuse, stale-density replies,
patch recovery, magnifier ownership, Retina page revisits and native 12000-pixel
page grids with cropped allocations. Re-run crop placement with
`QT_SCALE_FACTOR=1.25`, `1.5` and `2` for fractional/Retina geometry.
The native `make test-preview-png` suite checks canonical pixel equivalence.

## Local validation, 16 November 2026

All 20 offscreen Qt suites passed against engine `87e1cbb`, including real TeX,
bibliography, source routing, links, TikZ, scrolling and pagination. Canonical
raster tests passed, as did pixel-stripe placement at DPR 1.25, 1.5 and 2.
The native tooling/packaging suite passed all 81 tests.

The serial comparison used freshly built Release clients before/after this
migration, the same Qt and engine/dependencies, and a precompiled public synthetic
PDF. Both paths allowed 16 megapixels. A 2000 × 1400 device-pixel viewport was
requested on the new path, then expanded by its normal overscan and alignment. Each value below pools
14 samples across two runs; the order was baseline/surfaces/surfaces/baseline.
Timings include native export, IPC and asynchronous Qt decoding, excluding TeX
compilation and widget painting.

At a 3200-pixel page grid:

| Content | Previous whole-page path | Cropped surfaces |
| --- | ---: | ---: |
| Text and math | 43.2 ms | 21.6 ms |
| Vectors | 72.0 ms | 30.6 ms |
| Noisy RGB image | 558.8 ms | 273.4 ms |

Each decoded image fell from 55.25 MiB to 20 MiB at that density. These are image
allocations, not whole-process memory. At 1200 pixels, both paths rendered the
whole page and had essentially unchanged medians (text 12.0 ms, vectors 15.7–15.9
ms, image 82.5–82.9 ms). At 4096 pixels the previous path reduced density to fit
16 MP, whereas surfaces retained the requested density; that comparison also
changes visual quality. See [the measurement data](texpresso-surfaces-validation-2026-11-16.json)
for all widths, hashes, versions, sampling and scope.

Speculative neighbors use the current viewport's density and horizontal scroll
position, retaining a viewport-sized strip at the approaching page boundary.
They do not allocate an entire page at high zoom or introduce a coarse rendering
mode. A later visible demand supersedes incompatible speculative geometry.

Two offscreen full-editor memory soaks used disposable 100-page projects with
background file changes and simulated external-build refreshes, alongside typing,
scrolling, zooming, project switching, undo/redo, pause/resume and restart:

| Minimum workload | Scaling | Inputs | Peak editor footprint | Final editor footprint |
| --- | ---: | ---: | ---: | ---: |
| 5 minutes | 1× | 2432 | 147.7 MiB | 130.2 MiB |
| 2 minutes | 2× Retina | 1024 | 171.4 MiB | 155.8 MiB |

Both passed independent clean-PDF/SyncTeX ownership checks and left no owned
compiler processes. The macOS physical footprint includes compressed/swapped
memory. Worker memory is separate and shared/COW checkpoints make summed RSS an
unreliable unique-memory estimate. These finite workloads do not establish
hours-long leak freedom. Some edit phases missed the strict cadence threshold;
no typing-latency claim is derived from those phases. The render/decode comparison
above was measured separately on the quiet machine.
