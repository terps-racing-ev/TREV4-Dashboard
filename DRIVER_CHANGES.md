# Driver Changes

This documents the display-driver changes made while debugging `python main.py`
inside the venv on the Raspberry Pi external display.

## Original Problem

The app forced SDL to use `kmsdrm` at import time:

```python
os.environ["SDL_VIDEODRIVER"] = "kmsdrm"
```

When the venv's pip-installed pygame could not provide `kmsdrm`, pygame raised:

```text
pygame.error: kmsdrm not available
```

The fallback path still failed because `SDL_VIDEODRIVER` was still set to
`kmsdrm`, so SDL retried the same unavailable backend.

Later, after removing the forced import-time driver, SDL selected `offscreen`.
That let the UI thread start, but it rendered nowhere:

```text
Display initialized with SDL default backend: (800, 480)
UI thread started (30 fps)
```

The actual default driver in the venv was:

```text
offscreen
```

## Code Changes

### `graphics_driver.py`

- Removed import-time forcing of `SDL_VIDEODRIVER=kmsdrm`.
- Kept `SDL_AUDIODRIVER=dummy` on Linux to avoid audio-device noise.
- Added Linux driver selection in `init_display()`:
  - If `SDL_VIDEODRIVER` is already set, respect it.
  - If running under a desktop session (`DISPLAY` or `WAYLAND_DISPLAY`), try:
    - SDL default
    - `wayland`
    - `x11`
    - `kmsdrm`
    - `linuxfb`
  - If running from a TTY/console, try:
    - `kmsdrm`
    - `linuxfb`
    - SDL default
- Added a clean retry helper that resets pygame's display subsystem between
  driver attempts:

```python
pygame.display.quit()
pygame.display.init()
```

- Added reporting of the actual SDL driver selected by pygame:

```python
pygame.display.get_driver()
```

- Added detection for invisible display backends:

```python
_INVISIBLE_VIDEO_DRIVERS = {"dummy", "offscreen"}
```

When SDL default selects one of those invisible backends, the app now treats it
as an error instead of pretending the dashboard is visible.

### `dashboard.py`

- Moved display initialization inside the UI thread's `try` block.
- This makes display failures print as a clean `UI thread error` instead of an
  unhandled thread traceback.
- Fixed a Linux path warning by changing:

```python
"assets\fonts\monofonto rg.otf"
```

to:

```python
"assets/fonts/monofonto rg.otf"
```

## Python Environment Changes

The venv was originally importing pygame from the pip wheel:

```text
/opt/TREV4-Dashboard/venv/lib/python3.13/site-packages/pygame
```

That wheel bundled its own SDL:

```text
pygame.libs/libSDL2-2-6e5c51a6.0.so.0.2800.4
```

That bundled SDL selected `offscreen` in the Pi TTY environment and did not
provide a usable visible display backend.

The venv was changed to allow system site packages:

```text
include-system-site-packages = true
```

The pip pygame wheel was removed from the venv:

```bash
venv/bin/pip uninstall -y pygame
```

After that, the venv imports Debian/Raspberry Pi pygame:

```text
/usr/lib/python3/dist-packages/pygame
```

and links against system SDL:

```text
/lib/aarch64-linux-gnu/libSDL2-2.0.so.0
```

## System Packages Installed

Installed the system SDL/pygame stack:

```bash
sudo apt-get install -y libsdl2-2.0-0 python3-pygame
```

Installed Mesa/EGL runtime packages after KMSDRM became available but failed
with `EGL not initialized`:

```bash
sudo apt-get install -y libegl1 libgles2 libgl1-mesa-dri mesa-utils
```

Relevant installed package versions at the time of this note:

```text
libsdl2-2.0-0        2.32.4+dfsg-1
python3-pygame       2.6.1-1+b2
libegl1              1.7.0-1+b2
libgles2             1.7.0-1+b2
libgl1-mesa-dri      25.0.7-2+rpt4
mesa-utils           9.0.0-2+b2
```

## Observed Current State

The venv now reports:

```text
pygame 2.6.1
SDL 2.32.4
default driver KMSDRM
```

The Pi display devices are present and accessible:

```text
/dev/fb0
/dev/dri/card0
/dev/dri/card1
/dev/dri/renderD128
```

The user is in the required groups:

```text
video
render
```

The HDMI connector reports:

```text
/sys/class/drm/card0-HDMI-A-1/status: connected
/sys/class/drm/card0-HDMI-A-1/modes: 800x480
```

After installing system SDL and Mesa/EGL, the app reaches:

```text
Display initialized with kmsdrm backend (actual: KMSDRM): (800, 480)
UI thread started (30 fps)
```

There is still a repeated SDL warning during rendering:

```text
ERROR: Could not queue pageflip: -22
```

That warning likely means KMSDRM is initializing but page flips are being
rejected by the DRM/display stack. The next debugging area is KMSDRM pageflip
configuration, active VT/session ownership, or explicit selection of the
correct DRM card/connector.

## Pageflip Fix

KMSDRM accepted `pygame.display.set_mode()` but still printed this on every
`pygame.display.flip()`:

```text
ERROR: Could not queue pageflip: -22
```

The dashboard now tries a tiny direct framebuffer backend before SDL display
backends on Linux:

```text
pygame Surface -> 16-bit RGB565 conversion surface -> /dev/fb0 mmap
```

On this display, `/dev/fb0` reports:

```text
name: vc4drmfb
virtual_size: 800,480
bits_per_pixel: 16
stride: 1600
```

That exactly matches the dashboard resolution, so writing the final frame
directly to `/dev/fb0` avoids SDL/KMSDRM page flips entirely. The normal app
startup now reaches:

```text
Display initialized with framebuffer backend: (800, 480)
UI thread started (30 fps)
```

with no pageflip spam.

## Useful Debug Commands

Check which pygame and SDL the venv is using:

```bash
venv/bin/python -c "import pygame; print(pygame.__file__); print(pygame.get_sdl_version()); pygame.display.init(); print(pygame.display.get_driver())"
```

Check DRM connector state:

```bash
cat /sys/class/drm/card0-HDMI-A-1/status
cat /sys/class/drm/card0-HDMI-A-1/modes
```

Check EGL:

```bash
eglinfo -B
```

Force KMSDRM for a minimal pygame test:

```bash
env SDL_VIDEODRIVER=kmsdrm venv/bin/python -c "import pygame; pygame.init(); s=pygame.display.set_mode((800,480)); print(pygame.display.get_driver(), s); pygame.display.flip(); pygame.time.wait(1000); pygame.quit()"
```
