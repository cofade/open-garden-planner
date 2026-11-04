# Case study: a site plan that was too big to decode, and a snapshot that re-encoded it (#659, #660)

**Symptom.** A user's 9917 x 7009 cadastral plan is a 2.8 MB PNG. Importing it
through **File -> Import Background Image...** produced no background, and a
plan that already embedded the image reopened with a "[Missing Image: ...]"
placeholder. Separately, on a plan whose background had loaded, the window
stopped responding for about a second at a time — worst when an agent read the
plan, and again roughly every five minutes with nobody touching anything.

**The probe that found it.** Two lines, in the app's own environment, no GUI:

```python
print(QImageReader.allocationLimit())          # 256  (MB, process-wide, a static)
pm = QPixmap(); print(pm.loadFromData(png))    # False for a 294 kB, 9000x8000 PNG
QImageReader.setAllocationLimit(512)
print(pm.loadFromData(png))                    # True, 9000x8000, in 0.20 s
```

and, for the freeze, timing the real item rather than a raw pixmap:

```python
item = BackgroundImageItem("bg.png", _pixmap_data=png)
for _ in range(3):
    t = time.perf_counter(); item.to_dict(); print(time.perf_counter() - t)
# 1.16  1.21  1.18   -- identical 307,004-character payload each time
```

The decode failure also leaves a log line, which is what a support report would
show: `QImageIOHandler: Rejecting image as it exceeds the current allocation
limit of 256 megabytes`.

**Wrong theories.** (1) "The file is corrupt / not really a PNG" — `identify`
and `QImageReader(path).size()` both read it fine; the file is 294 kB and the
header is valid. (2) "The machine is out of memory" — it has 32 GB free, and the
failure is instant (0.01 s), not a slow allocation: nothing was attempted.
(3) "The import dialog rejects big files" — there is no size check in the dialog
or the action; the constructor's `QPixmap(path)` simply returns a null pixmap.
(4) "The freeze is the 3D view or the autosave writing the file" — the file write
is fast; the time goes into `QGraphicsPixmapItem`'s serializer, and autosave just
happens to be the caller that reveals it.

**Root cause.** Two independent consequences of one design: the item stores the
image as a `QPixmap` and also serializes it inline.

1. Qt's image allocation limit is a **process-wide static** on `QImageReader`,
   256 MB by default, applied to the *decoded* size. A site plan is small on disk
   and large in memory (9000 x 8000 RGBA = 275 MiB), so `QPixmap(path)` and
   `loadFromData()` both refuse it. Nothing in the app raised the limit, and the
   existing AUD-043 placeholder path then turned the refusal into "the image is
   missing", which looks like data loss rather than a limit.
2. `to_dict()` re-encoded the pixmap as PNG and base64 on every call. A project
   snapshot is taken on every Agent API plan read and every autosave (on by
   default, five minutes), so the same unchanged bytes were encoded thousands of
   times over a session, on the GUI thread.

**Fix.** `_decode_budget()` raises the limit to 512 MB around one decode and
restores the previous value in `finally` (a leaked raise would enlarge every
later decode in the process, for images nobody asked about); the pixel cap is
checked from the **header** first, so an over-size file is refused with a
translated message instead of a `null` pixmap. `to_dict()` encodes once and
reuses the string, keyed on `QPixmap.cacheKey()` so the cache cannot outlive the
pixels.

**Lessons.**

- **A null pixmap is not evidence about the file.** `QPixmap(path).isNull()`
  conflates "missing", "unsupported format" and "above the allocation limit".
  When a decode fails, print `QImageReader.allocationLimit()` and the reader's
  `errorString()` before blaming the asset.
- **The failure mode of a raised limit is a leak of the limit itself.** It is a
  static: raise it in a `contextmanager` with `finally`, never as a module-level
  `setAllocationLimit()` call at import. And do not "raise" blindly — the
  disabled value is **0** and it is the only sentinel (Qt ignores a negative
  argument and `allocationLimit()` never returns one), so a condition like
  `previous < wanted` that accepts 0 silently narrows a deliberately disabled
  check to your own budget. Raise only when the current value is a positive
  number below yours. `QT_IMAGEIO_MAXALLOC` beats the static outright: a user who
  sets it keeps their limit, and the fix silently does nothing for them.
- **Check the second copy.** The fix that makes a 275 MiB image loadable also
  makes the flipped copy in `__init__` 275 MiB. The real budget is the pair, so
  the accepted pixel count has to be stated for the pair.
- **Time the layer the user waits on.** The freeze was invisible in a raw
  `QPixmap.save` measurement on a small image; it only became obvious when the
  timer wrapped the item's real serializer and the payload turned out to be
  identical on every call. Identical output on repeated calls is the signature
  of a missing cache.
- **A cache needs a key, not a promise.** `QPixmap.cacheKey()` costs an integer
  read and makes "the payload cannot be stale" a property of Qt rather than of a
  comment. The invalidation test could then assign a new pixmap directly — the
  same seam a future "replace image" action will use.
