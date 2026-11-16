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

Performance profiling and a long memory soak are deferred while the development
machine is busy with video encoding. No speedup or whole-process memory result
is inferred from correctness-test timings. Before release, compare this Qt path
against its former 16-megapixel baseline using identical engine dependencies,
and include sustained editing, scrolling, zooming and document switching.

Speculative neighbors use the current viewport's density and horizontal scroll
position, retaining a viewport-sized strip at the approaching page boundary.
They do not allocate an entire page at high zoom or introduce a coarse rendering
mode. A later visible demand supersedes incompatible speculative geometry.
