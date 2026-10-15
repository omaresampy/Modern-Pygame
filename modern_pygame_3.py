"""
modern_pygame.py v4.2 - نسخة مُحسَّنة للأداء.

    pip install pygame-ce numpy
    pip install Pillow   # optional: shadow blur
    pip install moderngl # optional: GPU particles

التحسينات في v4.2:
    1. Profiler null-object (صفر overhead لو disabled)
    2. BatchGroup LOD حقيقي (يستخدم _draw_scale فعليًا)
    3. LOD cache للنسخ المصغّرة
    4. ParticleSystem.draw بمسار واحد أسرع
    5. GPU draw_points يبعت ألوان صحيحة
    6. TextCache يرجّع نفس الكائن بدون allocation
    7. Scene.update بدون copy للـ tweens
"""
import pygame as pg
import numpy as np
import time as _time
import math
from itertools import repeat
from dataclasses import dataclass
from typing import Optional, Tuple


try:
    import pygame.surfarray as surfarray
    _HAS_SURFARRAY = True
except ImportError:
    _HAS_SURFARRAY = False

try:
    from PIL import Image, ImageFilter
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


# ============================================================================
# ▓▓▓ PYGAME FACADE ▓▓▓
# ============================================================================
init              = pg.init
quit              = pg.quit
get_init          = pg.get_init
error             = pg.error
register_quit     = pg.register_quit
get_error         = pg.get_error

Rect     = pg.Rect
FRect    = getattr(pg, 'FRect', pg.Rect)
Color    = pg.Color
Vector2  = pg.Vector2
Vector3  = pg.Vector3
FVector2 = getattr(pg, 'FVector2', pg.Vector2)
FVector3 = getattr(pg, 'FVector3', pg.Vector3)
Clock    = pg.time.Clock
Mask     = pg.mask.Mask

event      = pg.event
key        = pg.key
mouse      = pg.mouse
joystick   = pg.joystick
controller = getattr(pg, 'controller', None)
font       = pg.font
display    = pg.display
draw       = pg.draw
transform  = pg.transform
image      = pg.image
mixer      = pg.mixer
time       = pg.time
sprite     = pg.sprite
sndarray   = pg.sndarray
mask_mod   = pg.mask
cursors    = pg.cursors
pgmath     = pg.math
scrap      = getattr(pg, 'scrap', None)
pixelcopy  = getattr(pg, 'pixelcopy', None)
version    = getattr(pg, 'version', None)
sysfont    = getattr(pg, 'sysfont', None)

SysFont   = pg.font.SysFont
Font      = pg.font.Font
get_ticks = pg.time.get_ticks
delay     = pg.time.delay
wait      = pg.time.wait
set_timer = pg.time.set_timer

for _name in dir(pg):
    if _name.startswith('_'):
        continue
    if _name in globals():
        continue
    if (_name.isupper()
            or _name.startswith(('K_', 'KMOD_', 'BUTTON_', 'WINDOWEVENT_'))):
        try:
            globals()[_name] = getattr(pg, _name)
        except AttributeError:
            pass
try:
    del _name
except NameError:
    pass


# ============================================================================
# ⚡ TextCache v4.2 - بدون allocation لو النص مش اتغير
# ============================================================================
class TextCache:
    """يرندر النص فقط عند التغير + بعد فترة زمنية."""
    __slots__ = ('font', 'color', 'shadow_color', 'update_interval',
                 '_last', '_surf', '_shadow', '_accum', '_result')

    def __init__(self, font, color=(255, 255, 255), shadow_color=None,
                 update_interval=0.1):
        self.font = font
        self.color = color
        self.shadow_color = shadow_color
        self.update_interval = update_interval
        self._last = None
        self._surf = None
        self._shadow = None
        self._accum = 99.0
        self._result = (None, None)   # ⚡ كاش للـ tuple

    def render(self, text, dt=0.0):
        self._accum += dt
        needs = (text != self._last or
                 (self.update_interval > 0 and self._accum >= self.update_interval))
        if needs:
            self._surf = self.font.render(text, True, self.color)
            if self.shadow_color is not None:
                self._shadow = self.font.render(text, True, self.shadow_color)
            self._last = text
            self._accum = 0.0
            # ⚡ نبني الـ tuple مرة واحدة
            self._result = (self._surf, self._shadow)
        return self._result

    def force(self):
        self._accum = 999.0


# ============================================================================
# ⚡ Profiler v4.2 - Null Object لما يكون معطل
# ============================================================================
class _NullMeasureCtx:
    """Context manager فارغ - صفر overhead."""
    __slots__ = ()
    def __enter__(self): return self
    def __exit__(self, *args): pass


class Profiler:
    """يقيس وقت كل قسم - بتكلفة صفرية لما يكون disabled."""
    __slots__ = ('_times', '_counts', '_accum', 'enabled', '_current',
                 '_null_ctx')
    _NULL = None

    def __init__(self, enabled=True):
        self._times = {}
        self._counts = {}
        self._accum = {}
        self.enabled = enabled
        self._current = None
        if Profiler._NULL is None:
            Profiler._NULL = _NullMeasureCtx()
        self._null_ctx = Profiler._NULL

    def start(self, name):
        self._current = (name, _time.perf_counter())

    def stop(self, name):
        if self._current is None:
            return
        _, t0 = self._current
        elapsed_ms = (_time.perf_counter() - t0) * 1000.0
        self._accum[name] = self._accum.get(name, 0.0) + elapsed_ms
        self._counts[name] = self._counts.get(name, 0) + 1
        self._current = None

    def measure(self, name):
        # ⚡ المسار السريع لما يكون disabled
        if not self.enabled:
            return self._null_ctx
        return _MeasureCtx(self, name)

    def tick(self, dt=0.0):
        if not self.enabled:
            return
        for name, total in self._accum.items():
            count = self._counts.get(name, 1)
            self._times[name] = total / max(1, count)
        self._accum.clear()
        self._counts.clear()

    def get_stats(self):
        return dict(self._times)

    def format_stats(self, top=5):
        if not self._times:
            return ""
        items = sorted(self._times.items(), key=lambda x: -x[1])[:top]
        return " | ".join(f"{k}:{v:.1f}ms" for k, v in items)


class _MeasureCtx:
    __slots__ = ('prof', 'name')
    def __init__(self, prof, name):
        self.prof = prof
        self.name = name
    def __enter__(self):
        self.prof.start(self.name)
        return self
    def __exit__(self, *args):
        self.prof.stop(self.name)


# ============================================================================
# Free drawing functions
# ============================================================================
_FONT_CACHE: dict = {}


def _get_font(font_, size):
    if font_ is not None:
        return font_
    key = ('default', size)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = pg.font.SysFont("Arial", size)
    return _FONT_CACHE[key]


def draw_text(surface, text, pos, font=None, color=(255, 255, 255),
              size=20, center=False, shadow=None, shadow_offset=(2, 2)):
    f = _get_font(font, size)
    if shadow is not None:
        sh = f.render(text, True, shadow)
        r = (sh.get_rect(center=(pos[0] + shadow_offset[0], pos[1] + shadow_offset[1]))
             if center else (pos[0] + shadow_offset[0], pos[1] + shadow_offset[1]))
        surface.blit(sh, r)
    txt = f.render(text, True, color)
    r = txt.get_rect(center=pos) if center else txt.get_rect(topleft=pos)
    surface.blit(txt, r)
    return r


def draw_gradient(surface, color1, color2, rect=None, direction='vertical'):
    if rect is None:
        x, y, w, h = 0, 0, surface.get_width(), surface.get_height()
    else:
        x, y, w, h = int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3])
    if w <= 0 or h <= 0:
        return
    c1, c2 = pg.Color(color1), pg.Color(color2)
    if not _HAS_SURFARRAY:
        n = h if direction in ('vertical', 'v') else w
        for i in range(n):
            t = i / max(1, n - 1)
            c = (int(c1.r * (1 - t) + c2.r * t),
                 int(c1.g * (1 - t) + c2.g * t),
                 int(c1.b * (1 - t) + c2.b * t))
            if direction in ('vertical', 'v'):
                pg.draw.line(surface, c, (x, y + i), (x + w, y + i))
            else:
                pg.draw.line(surface, c, (x + i, y), (x + i, y + h))
        return
    a1 = np.array(c1[:3], dtype=np.float32)
    a2 = np.array(c2[:3], dtype=np.float32)
    if direction in ('vertical', 'v'):
        t = np.broadcast_to(np.linspace(0, 1, h, dtype=np.float32).reshape(1, h, 1), (w, h, 1))
    elif direction in ('horizontal', 'h'):
        t = np.broadcast_to(np.linspace(0, 1, w, dtype=np.float32).reshape(w, 1, 1), (w, h, 1))
    else:
        tx = np.linspace(0, 1, w, dtype=np.float32).reshape(w, 1)
        ty = np.linspace(0, 1, h, dtype=np.float32).reshape(1, h)
        t = np.broadcast_to(((tx + ty) / 2).reshape(w, h, 1), (w, h, 1))
    rgb = (a1 * (1 - t) + a2 * t).astype(np.uint8)
    grad = pg.Surface((w, h))
    surfarray.blit_array(grad, rgb)
    surface.blit(grad, (x, y))


def draw_shadow(surface, rect, offset=(4, 4), color=(0, 0, 0, 120),
                blur_radius=6, border_radius=4):
    r = pg.Rect(rect)
    pad = blur_radius * 2
    shadow = pg.Surface((r.width + pad * 2, r.height + pad * 2), pg.SRCALPHA)
    pg.draw.rect(shadow, color, (pad, pad, r.width, r.height),
                 border_radius=border_radius)
    if _HAS_PIL and blur_radius > 0:
        data = pg.image.tobytes(shadow, 'RGBA')
        pil = Image.frombytes('RGBA', shadow.get_size(), data)
        pil = pil.filter(ImageFilter.GaussianBlur(blur_radius))
        shadow = pg.image.frombytes(pil.tobytes(), pil.size, 'RGBA').convert_alpha()
    surface.blit(shadow, (r.x + offset[0] - pad, r.y + offset[1] - pad))


def draw_image_tiled(surface, image_, rect=None, offset=(0, 0)):
    if rect is None:
        rect = (0, 0, surface.get_width(), surface.get_height())
    rx, ry, rw, rh = rect
    iw, ih = image_.get_size()
    if iw <= 0 or ih <= 0:
        return
    ox, oy = offset
    y = ry - ((ry - oy) % ih)
    while y < ry + rh:
        x = rx - ((rx - ox) % iw)
        while x < rx + rw:
            surface.blit(image_, (x, y))
            x += iw
        y += ih


def to_grayscale(s): return pg.transform.grayscale(s)
def invert(s): return pg.transform.invert(s)


def apply_tint(surface, color):
    c = pg.Color(color)
    tint = pg.Surface(surface.get_size(), pg.SRCALPHA)
    tint.fill((c.r, c.g, c.b, 255))
    result = pg.Surface(surface.get_size(), pg.SRCALPHA)
    result.blit(surface, (0, 0))
    result.blit(tint, (0, 0), special_flags=pg.BLEND_RGB_MULT)
    return result


def blend(a, b, alpha=0.5):
    result = pg.Surface(a.get_size(), pg.SRCALPHA)
    result.blit(a, (0, 0))
    tmp = b.copy()
    tmp.set_alpha(int(255 * alpha))
    result.blit(tmp, (0, 0))
    return result


def scale_by_factor(s, f):
    w = max(1, int(s.get_width() * f))
    h = max(1, int(s.get_height() * f))
    return pg.transform.smoothscale(s, (w, h))


def mirror(s, h=True, v=False): return pg.transform.flip(s, h, v)


def crop(surface, rect):
    r = pg.Rect(rect)
    s = pg.Surface((r.width, r.height), pg.SRCALPHA)
    s.blit(surface, (0, 0), r)
    return s


# ============================================================================
# Surface
# ============================================================================
class Surface(pg.Surface):
    SRCALPHA = pg.SRCALPHA

    def __init__(self, size, flags=0, depth=32):
        if isinstance(size, pg.Surface):
            super().__init__(size.get_size(), pg.SRCALPHA, 32)
            self.blit(size, (0, 0))
        elif isinstance(size, pg.Rect):
            super().__init__((size.width, size.height), flags, depth)
        elif hasattr(size, '__iter__'):
            super().__init__((int(size[0]), int(size[1])), flags, depth)
        else:
            super().__init__((int(size), int(size)), flags, depth)

    def draw_text(self, *a, **kw):        return draw_text(self, *a, **kw)
    def draw_gradient(self, *a, **kw):    return draw_gradient(self, *a, **kw)
    def draw_shadow(self, *a, **kw):      return draw_shadow(self, *a, **kw)
    def draw_image_tiled(self, *a, **kw): return draw_image_tiled(self, *a, **kw)
    def to_grayscale(self):               return Surface(to_grayscale(self))
    def invert(self):                     return Surface(invert(self))
    def apply_tint(self, *a, **kw):       return Surface(apply_tint(self, *a, **kw))
    def blend(self, *a, **kw):            return Surface(blend(self, *a, **kw))
    def scale_by_factor(self, *a, **kw):  return Surface(scale_by_factor(self, *a, **kw))
    def mirror(self, *a, **kw):           return Surface(mirror(self, *a, **kw))
    def crop(self, *a, **kw):             return Surface(crop(self, *a, **kw))

    def copy(self):
        s = Surface(self.get_size(), self.get_flags(), 32)
        s.blit(self, (0, 0))
        return s

    @classmethod
    def load(cls, path): return cls(pg.image.load(str(path)))
    def save(self, path, **kw): pg.image.save(self, str(path), **kw)


# ============================================================================
# SpatialGrid
# ============================================================================
class SpatialGrid:
    __slots__ = ('cell_size', 'cols', 'rows', 'cells', 'world_w', 'world_h')

    def __init__(self, world_w, world_h, cell_size=64):
        self.cell_size = cell_size
        self.cols = max(1, (world_w + cell_size - 1) // cell_size)
        self.rows = max(1, (world_h + cell_size - 1) // cell_size)
        self.world_w = world_w
        self.world_h = world_h
        self.cells = [[] for _ in range(self.cols * self.rows)]

    def clear(self):
        for c in self.cells:
            c.clear()

    def _idx(self, x, y):
        cx = min(max(0, int(x / self.cell_size)), self.cols - 1)
        cy = min(max(0, int(y / self.cell_size)), self.rows - 1)
        return cy * self.cols + cx

    def insert(self, obj, x, y):
        self.cells[self._idx(x, y)].append(obj)

    def insert_index(self, idx, x, y):
        self.cells[self._idx(x, y)].append(idx)

    def rebuild_arrays(self, xs, ys, count):
        self.clear()
        if count == 0:
            return
        cs = self.cell_size
        cols = self.cols
        cells = self.cells
        cxs = np.minimum((xs[:count] / cs).astype(np.int32), cols - 1)
        cys = np.minimum((ys[:count] / cs).astype(np.int32), self.rows - 1)
        indices = np.arange(count, dtype=np.int32)
        keys = cys * cols + cxs
        order = np.argsort(keys)
        sorted_keys = keys[order]
        sorted_idx = indices[order]
        unique, starts = np.unique(sorted_keys, return_index=True)
        starts = list(starts) + [count]
        for i, k in enumerate(unique):
            cells[int(k)] = sorted_idx[starts[i]:starts[i + 1]].tolist()

    def query_radius(self, x, y, r):
        cs = self.cell_size
        cx1 = max(0, int((x - r) / cs))
        cx2 = min(self.cols - 1, int((x + r) / cs))
        cy1 = max(0, int((y - r) / cs))
        cy2 = min(self.rows - 1, int((y + r) / cs))
        result = []
        for cy in range(cy1, cy2 + 1):
            base = cy * self.cols
            for cx in range(cx1, cx2 + 1):
                result.extend(self.cells[base + cx])
        return result

    def query_rect(self, rect):
        r = max(rect.width, rect.height) // 2 + 1
        return self.query_radius(rect.centerx, rect.centery, r)

    def stats(self):
        used = sum(1 for c in self.cells if c)
        total = sum(len(c) for c in self.cells)
        return {'used': used, 'total': len(self.cells),
                'items': total, 'avg_per_cell': total / max(used, 1)}


# ============================================================================
# LOD
# ============================================================================
class LOD:
    """Adaptive Level of Detail."""
    __slots__ = ('tiers', '_pool')

    def __init__(self):
        self.tiers = [
            (10000, 0.45, 3),
            (6000,  0.55, 2),
            (3500,  0.70, 2),
            (1500,  0.85, 1),
            (0,     1.00, 1),
        ]
        self._pool = {}

    def get_scale(self, count):
        for threshold, scale, _ in self.tiers:
            if count >= threshold:
                return scale
        return 1.0

    def get_skip(self, count):
        for threshold, _, skip in self.tiers:
            if count >= threshold:
                return skip
        return 1

    def get_sprite(self, original_surf, count):
        scale = self.get_scale(count)
        if scale >= 0.99:
            return original_surf
        key = (id(original_surf), scale)
        if key not in self._pool:
            w = max(2, int(original_surf.get_width() * scale))
            h = max(2, int(original_surf.get_height() * scale))
            self._pool[key] = pg.transform.smoothscale(original_surf, (w, h))
        return self._pool[key]

    def clear(self):
        self._pool.clear()


# ============================================================================
# ParticleConfig + Presets
# ============================================================================
@dataclass
class ParticleConfig:
    max_count: int = 100_000
    sprite_radius: int = 6
    n_colors: int = 16
    n_alpha: int = 8
    gravity: float = 0.0
    wind: Tuple[float, float] = (0.0, 0.0)
    drag: float = 0.0
    bounce: bool = True
    recycle_offscreen: bool = False
    attract_point: Optional[Tuple[float, float]] = None
    attract_strength: float = 0.0
    repel_strength: float = 0.0
    lifespan_range: Optional[Tuple[float, float]] = None
    fade_out: bool = False
    trail_alpha: int = 0
    use_grid: bool = False
    cell_size: int = 64
    use_gpu: bool = True
    use_lod: bool = True


class Presets:
    @staticmethod
    def fireworks():
        return ParticleConfig(max_count=200_000, sprite_radius=4,
            gravity=250.0, drag=0.8, bounce=False,
            lifespan_range=(1.5, 3.0), fade_out=True)
    @staticmethod
    def snow():
        return ParticleConfig(max_count=50_000, sprite_radius=3,
            gravity=20.0, wind=(30.0, 0.0), drag=0.1,
            bounce=False, lifespan_range=(6.0, 12.0), recycle_offscreen=True)
    @staticmethod
    def galaxy():
        return ParticleConfig(max_count=300_000, sprite_radius=3,
            gravity=0.0, drag=0.02, bounce=False,
            lifespan_range=(3.0, 8.0), fade_out=True, trail_alpha=8)
    @staticmethod
    def explosion():
        return ParticleConfig(max_count=100_000, sprite_radius=5,
            gravity=400.0, drag=1.5, bounce=True,
            lifespan_range=(0.8, 1.5), fade_out=True)
    @staticmethod
    def classic():
        return ParticleConfig(max_count=500_000, sprite_radius=6,
            gravity=0.0, drag=0.0, bounce=True)


# ============================================================================
# ⚡ ParticleSystem v4.2
# ============================================================================
class ParticleSystem:
    __slots__ = ('cfg', 'max', 'count', 'x', 'y', 'vx', 'vy',
                 'si', 'age', 'life', 'color_idx',
                 'world_w', 'world_h', 'pool',
                 'n_colors', 'n_alpha', 'n_sprites',
                 'grid', 'use_grid', 'lod',
                 'attract_point', 'attract_strength', 'repel_strength',
                 '_gpu', '_cached_draw_skip', '_cached_draw_scale',
                 '_gpu_colors')

    def __init__(self, config: ParticleConfig, world_size=(800, 600)):
        self.cfg = config
        self.max = config.max_count
        self.count = 0
        self.world_w, self.world_h = world_size
        self.n_colors = config.n_colors
        self.n_alpha = config.n_alpha

        self.x = np.zeros(self.max, dtype=np.float32)
        self.y = np.zeros(self.max, dtype=np.float32)
        self.vx = np.zeros(self.max, dtype=np.float32)
        self.vy = np.zeros(self.max, dtype=np.float32)
        self.si = np.zeros(self.max, dtype=np.int32)
        self.age = np.zeros(self.max, dtype=np.float32)
        self.life = np.full(self.max, 1e9, dtype=np.float32)
        self.color_idx = np.zeros(self.max, dtype=np.int32)

        self.attract_point = config.attract_point
        self.attract_strength = config.attract_strength
        self.repel_strength = config.repel_strength

        self.use_grid = config.use_grid
        self.grid = (SpatialGrid(world_size[0], world_size[1], config.cell_size)
                     if self.use_grid else None)

        self.lod = LOD() if config.use_lod else None
        self._cached_draw_skip = 1
        self._cached_draw_scale = 1.0

        self._gpu = None
        if config.use_gpu and OpenGLRenderer.is_available():
            try:
                self._gpu = OpenGLRenderer(world_size)
            except Exception:
                self._gpu = None

        self.pool = self._make_pool(config.n_colors, config.n_alpha,
                                    config.sprite_radius)
        self.n_sprites = len(self.pool)

        # ⚡ Pre-compute RGB colors for GPU (يُستخدم في _draw_gpu)
        self._gpu_colors = None

    def _make_pool(self, n_colors, n_alpha, radius):
        pool = []
        rng = np.random.default_rng(42)
        for _ in range(n_colors):
            c = (int(rng.integers(120, 255)),
                 int(rng.integers(120, 255)),
                 int(rng.integers(180, 255)))
            for a in range(n_alpha):
                alpha = int(255 * (a + 1) / n_alpha)
                s = pg.Surface((radius * 2, radius * 2), pg.SRCALPHA)
                pg.draw.circle(s, (*c, alpha), (radius, radius), radius)
                pool.append(s.convert_alpha())
        return pool

    def spawn(self, n, x_range=None, y_range=None, v_range=350,
              center=None, speed_range=None):
        n = min(n, self.max - self.count)
        if n <= 0:
            return
        s, e = self.count, self.count + n
        W, H = self.world_w, self.world_h
        if center is not None:
            cx, cy = center
            angles = np.random.uniform(0, 2 * np.pi, n).astype(np.float32)
            speeds = (np.random.uniform(speed_range[0], speed_range[1], n).astype(np.float32)
                      if speed_range else
                      np.random.uniform(v_range * 0.3, v_range, n).astype(np.float32))
            self.x[s:e] = cx + np.cos(angles) * 2
            self.y[s:e] = cy + np.sin(angles) * 2
            self.vx[s:e] = np.cos(angles) * speeds
            self.vy[s:e] = np.sin(angles) * speeds
        else:
            self.x[s:e] = (np.random.uniform(*x_range, n) if x_range
                           else np.random.uniform(0, W, n))
            self.y[s:e] = (np.random.uniform(*y_range, n) if y_range
                           else np.random.uniform(0, H, n))
            self.vx[s:e] = np.random.uniform(-v_range, v_range, n)
            self.vy[s:e] = np.random.uniform(-v_range, v_range, n)
        cidx = np.random.randint(0, self.n_colors, n).astype(np.int32)
        self.color_idx[s:e] = cidx
        self.si[s:e] = cidx * self.n_alpha + (self.n_alpha - 1)
        self.age[s:e] = 0.0
        if self.cfg.lifespan_range:
            lo, hi = self.cfg.lifespan_range
            self.life[s:e] = np.random.uniform(lo, hi, n)
        else:
            self.life[s:e] = 1e9
        self.count = e

    def clear(self):
        self.count = 0

    def update(self, dt):
        c = self.count
        if c == 0:
            return
        W, H = self.world_w, self.world_h
        r = self.cfg.sprite_radius
        x = self.x[:c]; y = self.y[:c]
        vx = self.vx[:c]; vy = self.vy[:c]

        if self.cfg.gravity != 0.0:
            vy += self.cfg.gravity * dt
        if self.cfg.wind != (0.0, 0.0):
            vx += self.cfg.wind[0] * dt
            vy += self.cfg.wind[1] * dt

        if self.attract_point is not None:
            ax, ay = self.attract_point
            dx = ax - x; dy = ay - y
            d2 = dx * dx + dy * dy + 100.0
            inv_d = 1.0 / np.sqrt(d2)
            if self.attract_strength != 0.0:
                k = self.attract_strength * dt
                vx += k * dx * inv_d
                vy += k * dy * inv_d
            if self.repel_strength != 0.0:
                k = self.repel_strength * dt
                vx -= k * dx * inv_d / (d2 * 0.0001 + 1.0)
                vy -= k * dy * inv_d / (d2 * 0.0001 + 1.0)

        if self.cfg.drag != 0.0:
            factor = max(0.0, 1.0 - self.cfg.drag * dt)
            vx *= factor; vy *= factor

        x += vx * dt; y += vy * dt

        if self.cfg.bounce:
            left = x < r; right = x > W - r
            top = y < r; bottom = y > H - r
            vx[left] = np.abs(vx[left]); vx[right] = -np.abs(vx[right])
            vy[top] = np.abs(vy[top]); vy[bottom] = -np.abs(vy[bottom])
            np.clip(x, r, W - r, out=x)
            np.clip(y, r, H - r, out=y)

        if self.cfg.lifespan_range is not None:
            self.age[:c] += dt
            dead = self.age[:c] >= self.life[:c]
            if dead.any():
                keep = ~dead
                n_keep = int(keep.sum())
                for arr in (self.x, self.y, self.vx, self.vy, self.si,
                            self.age, self.life, self.color_idx):
                    arr[:n_keep] = arr[:c][keep]
                self.count = n_keep
                c = n_keep

        if self.cfg.fade_out and c > 0:
            ratio = np.clip(self.age[:c] / self.life[:c], 0.0, 1.0)
            ab = ((1.0 - ratio) * (self.n_alpha - 1)).astype(np.int32)
            np.clip(ab, 0, self.n_alpha - 1, out=ab)
            self.si[:c] = self.color_idx[:c] * self.n_alpha + ab

        if self.cfg.recycle_offscreen and c > 0:
            oob = (y > H + 50) | (y < -50) | (x > W + 50) | (x < -50)
            n_oob = int(oob.sum())
            if n_oob > 0:
                idx = np.where(oob)[0]
                self.x[idx] = np.random.uniform(0, W, n_oob)
                self.y[idx] = np.random.uniform(-50, 0, n_oob)
                self.vx[idx] = np.random.uniform(-200, 200, n_oob)
                self.vy[idx] = np.random.uniform(0, 200, n_oob)

        if self.use_grid:
            self.grid.rebuild_arrays(self.x, self.y, c)

        # ⚡ كاش LOD
        if self.lod:
            self._cached_draw_skip = self.lod.get_skip(c)
            self._cached_draw_scale = self.lod.get_scale(c)

    def draw(self, screen):
        c = self.count
        if c == 0:
            return
        if self._gpu is not None:
            self._draw_gpu()
            return

        # ⚡ مسار واحد: نجهز القائمة كاملة ثم fblits
        skip = self._cached_draw_skip
        if skip > 1:
            xs = self.x[:c:skip].astype(np.int32).tolist()
            ys = self.y[:c:skip].astype(np.int32).tolist()
            sis = self.si[:c:skip].tolist()
        else:
            xs = self.x[:c].astype(np.int32).tolist()
            ys = self.y[:c].astype(np.int32).tolist()
            sis = self.si[:c].tolist()
        pool = self.pool
        # ⚡ بناء القائمة مباشرة بدون generators متداخلة
        batch = [(pool[s], (x, y)) for s, x, y in zip(sis, xs, ys)]
        screen.fblits(batch)

    def _draw_gpu(self):
        c = self.count
        if c == 0:
            return
        # ⚡ نجيب الألوان الحقيقية من pool
        if self._gpu_colors is None:
            # نبني جدول: لكل sprite في الـ pool → RGB
            colors = np.zeros((self.n_sprites, 3), dtype=np.float32)
            for i, s in enumerate(self.pool):
                c_rgb = s.get_at((2, 2))
                colors[i, 0] = c_rgb[0] / 255.0
                colors[i, 1] = c_rgb[1] / 255.0
                colors[i, 2] = c_rgb[2] / 255.0
            self._gpu_colors = colors

        r = self.cfg.sprite_radius * 2
        sizes = np.full(c, r, dtype=np.float32)
        colors = self._gpu_colors[self.si[:c]]
        self._gpu.begin()
        self._gpu.draw_points(self.x[:c], self.y[:c], colors, sizes)
        self._gpu.end()

    def set_gpu_renderer(self, renderer):
        self._gpu = renderer

    def apply_trail(self, screen, background_color=(0, 0, 0)):
        alpha = self.cfg.trail_alpha
        if alpha <= 0:
            screen.fill(background_color)
            return
        overlay = pg.Surface(screen.get_size(), pg.SRCALPHA)
        overlay.fill((*background_color, alpha))
        screen.blit(overlay, (0, 0))


# ============================================================================
# Animation
# ============================================================================
class Animation:
    __slots__ = ('frames', 'fps', 'loop', 'frame_duration')

    def __init__(self, frames, fps=12, loop=True):
        self.frames = frames
        self.fps = fps
        self.loop = loop
        self.frame_duration = 1.0 / fps

    @classmethod
    def from_sheet(cls, sheet, fw, fh, row, count, fps=12, loop=True):
        frames = []
        for i in range(count):
            surf = pg.Surface((fw, fh), pg.SRCALPHA)
            surf.blit(sheet, (0, 0), (i * fw, row * fh, fw, fh))
            frames.append(surf.convert_alpha())
        return cls(frames, fps, loop)

    @classmethod
    def from_frames(cls, frames, fps=12, loop=True):
        return cls([f.convert_alpha() for f in frames], fps, loop)


# ============================================================================
# ObjectPool
# ============================================================================
class ObjectPool:
    __slots__ = ('factory', '_free', '_in_use', 'max_size', 'created')

    def __init__(self, factory, initial=0, max_size=100_000):
        self.factory = factory
        self._free = []
        self._in_use = 0
        self.max_size = max_size
        self.created = 0
        for _ in range(min(initial, max_size)):
            self._free.append(factory())
            self.created += 1

    def acquire(self):
        self._in_use += 1
        if self._free:
            return self._free.pop()
        self.created += 1
        return self.factory()

    def release(self, obj):
        if self._in_use > 0:
            self._in_use -= 1
        if len(self._free) < self.max_size:
            self._free.append(obj)

    def release_many(self, objs):
        for o in objs:
            self.release(o)

    @property
    def in_use(self): return self._in_use
    @property
    def available(self): return len(self._free)

    def clear(self):
        self._free.clear()
        self._in_use = 0


# ============================================================================
# Sprite
# ============================================================================
class Sprite(pg.sprite.Sprite):
    def __init__(self, image=None, x=0, y=0, groups=None):
        super().__init__(*(groups or []))
        self.image = image if image is not None else pg.Surface((1, 1), pg.SRCALPHA)
        self.rect = self.image.get_rect(topleft=(x, y))
        self.vx = 0.0
        self.vy = 0.0
        self.alive = True
        self.animations = {}
        self._current_anim = None
        self._current_frame = 0
        self._anim_time = 0.0
        self._anim_finished = False
        self.data = {}

    def add_animation(self, name, animation):
        self.animations[name] = animation
        return self

    def play(self, name, restart=False):
        if name not in self.animations:
            return
        if self._current_anim == name and not restart:
            return
        self._current_anim = name
        self._current_frame = 0
        self._anim_time = 0.0
        self._anim_finished = False
        self.image = self.animations[name].frames[0]

    def update_animation(self, dt):
        if self._current_anim is None:
            return
        anim = self.animations[self._current_anim]
        self._anim_time += dt
        while self._anim_time >= anim.frame_duration:
            self._anim_time -= anim.frame_duration
            if self._current_frame < len(anim.frames) - 1:
                self._current_frame += 1
                self.image = anim.frames[self._current_frame]
            elif anim.loop:
                self._current_frame = 0
                self.image = anim.frames[0]
            else:
                self._anim_finished = True
                break

    def update(self, dt):
        self.rect.x += self.vx * dt
        self.rect.y += self.vy * dt
        self.update_animation(dt)

    def kill(self):
        self.alive = False
        super().kill()


# ============================================================================
# Group
# ============================================================================
class Group(pg.sprite.Group):
    def __init__(self, *sprites, world_size=None, cell_size=64):
        super().__init__(*sprites)
        self.grid = (SpatialGrid(world_size[0], world_size[1], cell_size)
                     if world_size else None)

    def update(self, dt):
        for s in self.sprites():
            s.update(dt)
            if not getattr(s, 'alive', True):
                s.kill()

    def rebuild_grid(self):
        if self.grid is None:
            return
        self.grid.clear()
        for s in self.sprites():
            self.grid.insert(s, s.rect.centerx, s.rect.centery)

    def query_rect(self, rect):
        if self.grid is None:
            return [s for s in self.sprites() if s.rect.colliderect(rect)]
        return [s for s in self.grid.query_rect(rect) if s.rect.colliderect(rect)]

    def draw(self, surface, camera=None):
        if camera is None:
            super().draw(surface)
            return
        cx, cy = camera.rect.x, camera.rect.y
        for s in self.sprites():
            surface.blit(s.image, (s.rect.x - cx, s.rect.y - cy))


# ============================================================================
# PooledGroup
# ============================================================================
class PooledGroup(Group):
    def __init__(self, factory, initial=0, max_pool=100_000,
                 world_size=None, cell_size=64):
        super().__init__(world_size=world_size, cell_size=cell_size)
        self._pool = ObjectPool(factory, initial=initial, max_size=max_pool)

    def acquire(self):
        return self._pool.acquire()

    def spawn(self, *args, **kwargs):
        obj = self._pool.acquire()
        if hasattr(obj, 'spawn'):
            obj.spawn(*args, **kwargs)
        obj.alive = True
        self.add(obj)
        return obj

    def release(self, obj):
        if obj in self.sprites():
            self.remove(obj)
        self._pool.release(obj)

    def release_all(self):
        for s in list(self.sprites()):
            self.remove(s)
            self._pool.release(s)

    @property
    def pool_stats(self):
        return {'in_use': self._pool.in_use,
                'available': self._pool.available,
                'created': self._pool.created}


# ============================================================================
# ⚡ BatchGroup v4.2 - LOD حقيقي مع cache
# ============================================================================
class BatchGroup:
    __slots__ = ('capacity', 'count', 'world_size',
                 'x', 'y', 'vx', 'vy', 'img_idx', 'age', 'life', 'data',
                 'images', '_img_to_idx',
                 '_grid', '_grid_cell', '_grid_dirty',
                 '_lod', '_draw_skip', '_draw_scale',
                 '_lod_cache_scale', '_lod_cache_imgs',
                 '_gpu_ready', '_needs_grid', 'name')

    def __init__(self, capacity=10000, world_size=None, cell_size=64,
                 use_lod=True, use_gpu=False, needs_grid=True, name='batch'):
        self.capacity = capacity
        self.count = 0
        self.world_size = world_size
        self.name = name

        self.x = np.zeros(capacity, dtype=np.float32)
        self.y = np.zeros(capacity, dtype=np.float32)
        self.vx = np.zeros(capacity, dtype=np.float32)
        self.vy = np.zeros(capacity, dtype=np.float32)
        self.img_idx = np.zeros(capacity, dtype=np.int32)
        self.age = np.zeros(capacity, dtype=np.float32)
        self.life = np.full(capacity, 1e9, dtype=np.float32)
        self.data = np.zeros(capacity, dtype=np.float32)

        self.images = []
        self._img_to_idx = {}

        self._grid_cell = cell_size
        self._needs_grid = needs_grid
        self._grid = (SpatialGrid(world_size[0], world_size[1], cell_size)
                      if (world_size and needs_grid) else None)
        self._grid_dirty = True

        self._lod = LOD() if use_lod else None
        self._draw_skip = 1
        self._draw_scale = 1.0

        # ⚡ كاش للنسخ المصغّرة
        self._lod_cache_scale = None
        self._lod_cache_imgs = None

        self._gpu_ready = use_gpu

    def register_image(self, image):
        key = id(image)
        if key not in self._img_to_idx:
            img = image.convert_alpha() if pg.display.get_surface() else image
            self.images.append(img)
            self._img_to_idx[key] = len(self.images) - 1
            # ⚡ أي صورة جديدة تُلغي الـ LOD cache
            self._lod_cache_scale = None
        return self._img_to_idx[key]

    def add(self, x, y, vx=0.0, vy=0.0, image=None, life=None, data=0.0):
        if self.count >= self.capacity:
            return -1
        i = self.count
        self.x[i] = x; self.y[i] = y
        self.vx[i] = vx; self.vy[i] = vy
        self.img_idx[i] = self.register_image(image) if image is not None else 0
        self.age[i] = 0.0
        self.life[i] = life if life is not None else 1e9
        self.data[i] = data
        self.count += 1
        self._grid_dirty = True
        return i

    def add_many(self, xs, ys, vxs, vys, image, life=None, data=0.0):
        n = len(xs)
        if self.count + n > self.capacity:
            n = self.capacity - self.count
        if n <= 0:
            return 0
        s, e = self.count, self.count + n
        img_idx = self.register_image(image) if image is not None else 0
        self.x[s:e] = xs[:n]
        self.y[s:e] = ys[:n]
        self.vx[s:e] = vxs[:n]
        self.vy[s:e] = vys[:n]
        self.img_idx[s:e] = img_idx
        self.age[s:e] = 0.0
        self.life[s:e] = life if life is not None else 1e9
        self.data[s:e] = data
        self.count = e
        self._grid_dirty = True
        return n

    def clear(self):
        self.count = 0
        self._grid_dirty = True

    def _compact(self, mask):
        c = self.count
        keep = ~mask[:c]
        n_keep = int(keep.sum())
        if n_keep == c:
            return
        for arr in (self.x, self.y, self.vx, self.vy,
                    self.img_idx, self.age, self.life, self.data):
            arr[:n_keep] = arr[:c][keep]
        self.count = n_keep
        self._grid_dirty = True

    def _rebuild_grid(self):
        if self._grid is not None and self._grid_dirty:
            self._grid.rebuild_arrays(self.x, self.y, self.count)
            self._grid_dirty = False

    def _get_lod_images(self, scale):
        """⚡ يبني/يرجع نسخ LOD مصغّرة - cached."""
        if scale >= 0.99:
            return self.images
        if self._lod_cache_scale == scale and self._lod_cache_imgs is not None:
            return self._lod_cache_imgs
        # نبني النسخ المصغّرة
        scaled = []
        for img in self.images:
            w = max(2, int(img.get_width() * scale))
            h = max(2, int(img.get_height() * scale))
            scaled.append(pg.transform.smoothscale(img, (w, h)))
        self._lod_cache_scale = scale
        self._lod_cache_imgs = scaled
        return scaled

    def update(self, dt, gravity=0.0, drag=0.0, bounds=None, wrap=False):
        c = self.count
        if c == 0:
            return
        x = self.x[:c]; y = self.y[:c]
        vx = self.vx[:c]; vy = self.vy[:c]
        if gravity != 0.0:
            vy += gravity * dt
        if drag != 0.0:
            f = max(0.0, 1.0 - drag * dt)
            vx *= f; vy *= f
        x += vx * dt
        y += vy * dt
        if bounds is not None:
            xmin, ymin, xmax, ymax = bounds
            if wrap:
                w = xmax - xmin; h = ymax - ymin
                x[:] = ((x - xmin) % w) + xmin
                y[:] = ((y - ymin) % h) + ymin
            else:
                oob = (x < xmin) | (x > xmax) | (y < ymin) | (y > ymax)
                if oob.any():
                    self._compact(oob)
                    c = self.count
                    if c == 0:
                        return
        self.age[:c] += dt
        dead = self.age[:c] >= self.life[:c]
        if dead.any():
            self._compact(dead)
        self._grid_dirty = True

        if self._lod:
            self._draw_skip = self._lod.get_skip(self.count)
            self._draw_scale = self._lod.get_scale(self.count)

    def draw(self, screen, camera=None):
        c = self.count
        if c == 0:
            return
        ox = camera.rect.x if camera else 0
        oy = camera.rect.y if camera else 0
        skip = self._draw_skip

        if skip > 1:
            xs = (self.x[:c:skip] - ox).astype(np.int32).tolist()
            ys = (self.y[:c:skip] - oy).astype(np.int32).tolist()
            idx = self.img_idx[:c:skip].tolist()
        else:
            xs = (self.x[:c] - ox).astype(np.int32).tolist()
            ys = (self.y[:c] - oy).astype(np.int32).tolist()
            idx = self.img_idx[:c].tolist()

        # ⚡ نستخدم النسخ المصغّرة لو LOD شغال
        if self._lod is not None and self._draw_scale < 0.99:
            imgs = self._get_lod_images(self._draw_scale)
        else:
            imgs = self.images

        batch = [(imgs[i], (x, y)) for i, x, y in zip(idx, xs, ys)]
        screen.fblits(batch)

    def collide_with(self, other, my_radius, other_radius,
                     max_pairs=2_000_000, use_grid=True):
        if self.count == 0 or other.count == 0:
            empty = np.empty(0, dtype=np.int32)
            return empty, empty

        n, m = self.count, other.count
        r = my_radius + other_radius

        if use_grid and other._grid is not None:
            other._rebuild_grid()
            xs = self.x[:n]
            ys = self.y[:n]
            my_list, ot_list = [], []
            r2 = r * r
            cell_size = other._grid.cell_size
            cols = other._grid.cols
            rows = other._grid.rows
            cell_lists = other._grid.cells
            other_x = other.x
            other_y = other.y
            for i in range(n):
                xi = float(xs[i]); yi = float(ys[i])
                cx1 = max(0, int((xi - r) / cell_size))
                cx2 = min(cols - 1, int((xi + r) / cell_size))
                cy1 = max(0, int((yi - r) / cell_size))
                cy2 = min(rows - 1, int((yi + r) / cell_size))
                for cy in range(cy1, cy2 + 1):
                    base = cy * cols
                    for cx in range(cx1, cx2 + 1):
                        for j in cell_lists[base + cx]:
                            dx = xi - other_x[j]
                            dy = yi - other_y[j]
                            if dx * dx + dy * dy <= r2:
                                my_list.append(i)
                                ot_list.append(j)
            return (np.array(my_list, dtype=np.int32) if my_list
                    else np.empty(0, dtype=np.int32),
                    np.array(ot_list, dtype=np.int32) if ot_list
                    else np.empty(0, dtype=np.int32))

        if n * m <= max_pairs:
            a = np.column_stack([self.x[:n], self.y[:n]])
            b = np.column_stack([other.x[:m], other.y[:m]])
            d2 = ((a[:, None, :] - b[None, :, :]) ** 2).sum(axis=2)
            mask = d2 <= r * r
            my_i, ot_i = np.where(mask)
            return my_i.astype(np.int32), ot_i.astype(np.int32)

        return self._collide_fallback(other, r)

    def _collide_fallback(self, other, r):
        world_w = self.world_size[0] if self.world_size else 4000
        world_h = self.world_size[1] if self.world_size else 4000
        cell = r * 2 + 4
        grid = SpatialGrid(world_w, world_h, cell)
        for j in range(other.count):
            grid.insert_index(j, other.x[j], other.y[j])
        r2 = r * r
        my_list, ot_list = [], []
        for i in range(self.count):
            for j in grid.query_radius(self.x[i], self.y[i], r):
                dx = self.x[i] - other.x[j]
                dy = self.y[i] - other.y[j]
                if dx * dx + dy * dy <= r2:
                    my_list.append(i); ot_list.append(j)
        return (np.array(my_list, dtype=np.int32) if my_list
                else np.empty(0, dtype=np.int32),
                np.array(ot_list, dtype=np.int32) if ot_list
                else np.empty(0, dtype=np.int32))

    def remove_indices(self, indices):
        if len(indices) == 0:
            return
        mask = np.zeros(self.count, dtype=bool)
        mask[np.asarray(indices, dtype=np.int64)] = True
        self._compact(mask)


# ============================================================================
# Camera
# ============================================================================
class Camera:
    __slots__ = ('rect', 'world_w', 'world_h', 'smooth')

    def __init__(self, width, height, world_w=None, world_h=None, smooth=0.15):
        self.rect = pg.Rect(0, 0, width, height)
        self.world_w = world_w if world_w else width
        self.world_h = world_h if world_h else height
        self.smooth = smooth

    def follow(self, target_rect, snap=False):
        tx = target_rect.centerx - self.rect.width // 2
        ty = target_rect.centery - self.rect.height // 2
        if snap:
            self.rect.x = int(tx); self.rect.y = int(ty)
        else:
            self.rect.x += (tx - self.rect.x) * self.smooth
            self.rect.y += (ty - self.rect.y) * self.smooth
        self.rect.x = max(0, min(self.world_w - self.rect.width, int(self.rect.x)))
        self.rect.y = max(0, min(self.world_h - self.rect.height, int(self.rect.y)))

    def world_to_screen(self, wx, wy):
        return wx - self.rect.x, wy - self.rect.y

    def screen_to_world(self, sx, sy):
        return sx + self.rect.x, sy + self.rect.y


# ============================================================================
# OpenGLRenderer
# ============================================================================
class OpenGLRenderer:
    _available = None

    @classmethod
    def is_available(cls):
        if cls._available is None:
            try:
                import moderngl  # noqa
                cls._available = True
            except ImportError:
                cls._available = False
        return cls._available

    def __init__(self, size):
        if not self.is_available():
            raise ImportError("pip install moderngl")
        import moderngl
        self._mgl = moderngl
        self.ctx = moderngl.create_context(require=330)
        self.size = size
        self.max_points = 1_000_000
        self.prog = self.ctx.program(
            vertex_shader='''
                #version 330
                in vec2 in_pos;
                in vec3 in_color;
                in float in_size;
                uniform vec2 screen;
                out vec3 v_color;
                void main() {
                    vec2 p = (in_pos / screen) * 2.0 - 1.0;
                    p.y = -p.y;
                    gl_Position = vec4(p, 0.0, 1.0);
                    gl_PointSize = in_size;
                    v_color = in_color;
                }
            ''',
            fragment_shader='''
                #version 330
                in vec3 v_color;
                out vec4 f_color;
                void main() {
                    vec2 c = gl_PointCoord - 0.5;
                    if (dot(c, c) > 0.25) discard;
                    f_color = vec4(v_color, 1.0);
                }
            ''')
        self.vbo_pos = self.ctx.buffer(np.zeros((self.max_points, 2), np.float32).tobytes())
        self.vbo_col = self.ctx.buffer(np.zeros((self.max_points, 3), np.float32).tobytes())
        self.vbo_size = self.ctx.buffer(np.ones(self.max_points, np.float32).tobytes())
        self.vao = self.ctx.vertex_array(self.prog, [
            (self.vbo_pos, '2f', 'in_pos'),
            (self.vbo_col, '3f', 'in_color'),
            (self.vbo_size, '1f', 'in_size')])
        self.prog['screen'].value = size
        self._pos = np.zeros((self.max_points, 2), np.float32)
        self._col = np.zeros((self.max_points, 3), np.float32)
        self._siz = np.ones(self.max_points, np.float32)
        self._count = 0

    def begin(self): self._count = 0

    def draw_points(self, xs, ys, colors, sizes):
        n = min(len(xs), self.max_points - self._count)
        if n <= 0: return
        s = self._count; e = s + n
        self._pos[s:e, 0] = xs[:n]; self._pos[s:e, 1] = ys[:n]
        self._col[s:e] = colors[:n]; self._siz[s:e] = sizes[:n]
        self._count = e

    def end(self):
        if self._count == 0: return
        mgl = self._mgl
        self.vbo_pos.write(self._pos[:self._count].tobytes())
        self.vbo_col.write(self._col[:self._count].tobytes())
        self.vbo_size.write(self._siz[:self._count].tobytes())
        self.ctx.clear(0.04, 0.04, 0.12, 1.0)
        self.ctx.enable(mgl.PROGRAM_POINT_SIZE)
        self.vao.render(mode=mgl.POINTS, vertices=self._count)


# ============================================================================
# SCENE SYSTEM
# ============================================================================

class Easing:
    __slots__ = ()

    @staticmethod
    def linear(t): return t
    @staticmethod
    def ease_in_quad(t): return t * t
    @staticmethod
    def ease_out_quad(t): return 1 - (1 - t) * (1 - t)
    @staticmethod
    def ease_in_out_quad(t):
        return 2 * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 2) / 2
    @staticmethod
    def ease_in_cubic(t): return t ** 3
    @staticmethod
    def ease_out_cubic(t): return 1 - pow(1 - t, 3)
    @staticmethod
    def ease_in_out_cubic(t):
        return 4 * t ** 3 if t < 0.5 else 1 - pow(-2 * t + 2, 3) / 2
    @staticmethod
    def ease_out_quart(t): return 1 - pow(1 - t, 4)
    @staticmethod
    def ease_out_quint(t): return 1 - pow(1 - t, 5)
    @staticmethod
    def ease_in_sine(t): return 1 - math.cos((t * math.pi) / 2)
    @staticmethod
    def ease_out_sine(t): return math.sin((t * math.pi) / 2)
    @staticmethod
    def ease_in_out_sine(t):
        return -(math.cos(math.pi * t) - 1) / 2
    @staticmethod
    def ease_in_expo(t):
        return 0 if t == 0 else pow(2, 10 * t - 10)
    @staticmethod
    def ease_out_expo(t):
        return 1 if t == 1 else 1 - pow(2, -10 * t)
    @staticmethod
    def ease_in_out_expo(t):
        if t == 0: return 0
        if t == 1: return 1
        return pow(2, 20 * t - 10) / 2 if t < 0.5 else (2 - pow(2, -20 * t + 10)) / 2
    @staticmethod
    def ease_in_back(t):
        c1 = 1.70158; c3 = c1 + 1
        return c3 * t ** 3 - c1 * t * t
    @staticmethod
    def ease_out_back(t):
        c1 = 1.70158; c3 = c1 + 1
        return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)
    @staticmethod
    def ease_in_out_back(t):
        c1 = 1.70158; c2 = c1 * 1.525
        if t < 0.5:
            return (pow(2 * t, 2) * ((c2 + 1) * 2 * t - c2)) / 2
        return (pow(2 * t - 2, 2) * ((c2 + 1) * (t * 2 - 2) + c2) + 2) / 2
    @staticmethod
    def ease_out_elastic(t):
        if t == 0 or t == 1: return t
        c4 = (2 * math.pi) / 3
        return pow(2, -10 * t) * math.sin((t * 10 - 0.75) * c4) + 1
    @staticmethod
    def ease_in_elastic(t):
        if t == 0 or t == 1: return t
        c4 = (2 * math.pi) / 3
        return -pow(2, 10 * t - 10) * math.sin((t * 10 - 10.75) * c4)
    @staticmethod
    def ease_out_bounce(t):
        n1, d1 = 7.5625, 2.75
        if t < 1 / d1:
            return n1 * t * t
        elif t < 2 / d1:
            t -= 1.5 / d1
            return n1 * t * t + 0.75
        elif t < 2.5 / d1:
            t -= 2.25 / d1
            return n1 * t * t + 0.9375
        else:
            t -= 2.625 / d1
            return n1 * t * t + 0.984375

    @classmethod
    def get(cls, name):
        return getattr(cls, name, cls.linear)


class Tween:
    __slots__ = ('from_', 'to', 'duration', 'ease_fn', 'on_complete',
                 '_elapsed', '_value', '_done', 'delay', '_delay_left')

    def __init__(self, from_, to, duration, ease='ease_out_quad',
                 on_complete=None, delay=0.0):
        self.from_ = float(from_)
        self.to = float(to)
        self.duration = max(0.0001, float(duration))
        self.ease_fn = Easing.get(ease)
        self.on_complete = on_complete
        self.delay = float(delay)
        self._delay_left = self.delay
        self._elapsed = 0.0
        self._value = self.from_
        self._done = False

    def update(self, dt):
        if self._done:
            return self._value
        if self._delay_left > 0:
            self._delay_left -= dt
            if self._delay_left > 0:
                return self._value
            dt = -self._delay_left
            self._delay_left = 0
        self._elapsed += dt
        if self._elapsed >= self.duration:
            self._elapsed = self.duration
            self._done = True
            self._value = self.to
            if self.on_complete:
                self.on_complete()
            return self._value
        t = self._elapsed / self.duration
        e = self.ease_fn(t)
        self._value = self.from_ + (self.to - self.from_) * e
        return self._value

    @property
    def value(self): return self._value
    @property
    def done(self): return self._done
    @property
    def progress(self):
        return min(1.0, self._elapsed / self.duration)

    def reset(self):
        self._elapsed = 0.0
        self._delay_left = self.delay
        self._value = self.from_
        self._done = False
        return self

    def cancel(self):
        self._done = True
        return self


class Scene:
    __slots__ = ('manager', 'transparent', 'bg_color', '_tweens',
                 '_entered_once')

    def __init__(self):
        self.manager = None
        self.transparent = False
        self.bg_color = (0, 0, 0)
        self._tweens = []
        self._entered_once = False

    def on_enter(self): pass
    def on_exit(self): pass
    def on_pause(self): pass
    def on_resume(self): pass
    def handle_event(self, event_): pass

    def update(self, dt):
        # ⚡ iteration بدون copy للـ list كل frame
        if not self._tweens:
            return
        i = 0
        while i < len(self._tweens):
            t = self._tweens[i]
            t.update(dt)
            if t.done:
                self._tweens.pop(i)
            else:
                i += 1

    def draw(self, screen):
        if not self.transparent:
            screen.fill(self.bg_color)

    def tween(self, from_, to, duration, ease='ease_out_quad',
              on_complete=None, delay=0.0):
        t = Tween(from_, to, duration, ease, on_complete, delay)
        self._tweens.append(t)
        return t

    def clear_tweens(self):
        self._tweens.clear()

    def switch_to(self, scene, transition=None):
        if self.manager:
            self.manager.switch(scene, transition)

    def push(self, scene, transition=None):
        if self.manager:
            self.manager.push(scene, transition)

    def pop(self, transition=None):
        if self.manager:
            self.manager.pop(transition)


class Transition:
    __slots__ = ('duration', 'elapsed', '_done')

    def __init__(self, duration=0.4):
        self.duration = float(duration)
        self.elapsed = 0.0
        self._done = False

    def begin(self):
        self.elapsed = 0.0
        self._done = False

    def update(self, dt):
        self.elapsed += dt
        if self.elapsed >= self.duration:
            self._done = True
        return self._done

    def draw(self, screen, snapshot, new_draw_fn):
        new_draw_fn(screen)

    @property
    def progress(self):
        return min(1.0, self.elapsed / self.duration) if self.duration > 0 else 1


class FadeTransition(Transition):
    __slots__ = ('color', '_ov')

    def __init__(self, duration=0.4, color=(0, 0, 0)):
        super().__init__(duration)
        self.color = color
        self._ov = None

    def draw(self, screen, snapshot, new_draw_fn):
        w, h = screen.get_size()
        if self._ov is None or self._ov.get_size() != (w, h):
            self._ov = pg.Surface((w, h), pg.SRCALPHA)
        t = self.progress
        if t < 0.5:
            screen.blit(snapshot, (0, 0))
            a = int(255 * (t / 0.5))
            self._ov.fill((*self.color, a))
            screen.blit(self._ov, (0, 0))
        else:
            new_draw_fn(screen)
            a = int(255 * (1 - (t - 0.5) / 0.5))
            self._ov.fill((*self.color, a))
            screen.blit(self._ov, (0, 0))


class SlideTransition(Transition):
    __slots__ = ('direction', '_new_surf', '_ease')

    def __init__(self, duration=0.5, direction='left'):
        super().__init__(duration)
        self.direction = direction
        self._new_surf = None
        self._ease = 'ease_out_cubic'

    def draw(self, screen, snapshot, new_draw_fn):
        w, h = screen.get_size()
        if self._new_surf is None or self._new_surf.get_size() != (w, h):
            self._new_surf = pg.Surface((w, h))
        self._new_surf.fill((0, 0, 0))
        new_draw_fn(self._new_surf)
        t = self.progress
        e = Easing.get(self._ease)(t)
        if self.direction == 'left':
            off = int(w * e)
            screen.blit(self._new_surf, (w - off, 0))
            screen.blit(snapshot, (-off, 0))
        elif self.direction == 'right':
            off = int(w * e)
            screen.blit(self._new_surf, (off - w, 0))
            screen.blit(snapshot, (off, 0))
        elif self.direction == 'up':
            off = int(h * e)
            screen.blit(self._new_surf, (0, h - off))
            screen.blit(snapshot, (0, -off))
        elif self.direction == 'down':
            off = int(h * e)
            screen.blit(self._new_surf, (0, off - h))
            screen.blit(snapshot, (0, off))


class SceneManager:
    __slots__ = ('screen', 'stack', 'transition', 'snapshot', '_size')

    def __init__(self, screen):
        self.screen = screen
        self.stack = []
        self.transition = None
        self.snapshot = None
        self._size = screen.get_size()

    def switch(self, scene, transition=None):
        snap = self._take_snapshot() if self.stack else None
        while self.stack:
            self.stack.pop().on_exit()
        scene.manager = self
        scene.on_enter()
        self.stack.append(scene)
        if transition is not None and snap is not None:
            self.transition = transition
            self.snapshot = snap
            self.transition.begin()

    def push(self, scene, transition=None):
        if self.stack:
            self.stack[-1].on_pause()
        scene.manager = self
        self.stack.append(scene)
        scene.on_enter()

    def pop(self, transition=None):
        if not self.stack:
            return
        top = self.stack.pop()
        top.on_exit()
        if self.stack:
            self.stack[-1].on_resume()

    def clear(self):
        while self.stack:
            self.stack.pop().on_exit()

    def _take_snapshot(self):
        snap = pg.Surface(self._size, pg.SRCALPHA)
        for scene in self.stack:
            scene.draw(snap)
            if not scene.transparent:
                break
        return snap

    def handle_event(self, event_):
        if self.transition is not None:
            return
        if self.stack:
            self.stack[-1].handle_event(event_)

    def update(self, dt):
        if self.transition is not None:
            if self.transition.update(dt):
                self.transition = None
                self.snapshot = None
        if self.stack:
            self.stack[-1].update(dt)

    def draw(self):
        screen = self.screen
        if self.transition is not None and self.snapshot is not None:
            if self.stack:
                new_scene = self.stack[-1]
                self.transition.draw(screen, self.snapshot, new_scene.draw)
            else:
                screen.blit(self.snapshot, (0, 0))
        else:
            for scene in self.stack:
                scene.draw(screen)

    @property
    def current(self):
        return self.stack[-1] if self.stack else None

    @property
    def is_transitioning(self):
        return self.transition is not None

    def __len__(self):
        return len(self.stack)


# ============================================================================
# Batch helpers
# ============================================================================
def batch_blit(screen, sprites, positions):
    screen.fblits(zip(sprites, positions))


def batch_blit_same(screen, sprite_, positions):
    screen.fblits(zip(repeat(sprite_, len(positions)), positions))


# ============================================================================
# PEP 562
# ============================================================================
__all__ = [
    n for n in globals()
    if not n.startswith('_')
    and n not in ('pg', 'np', 'repeat', 'dataclass',
                  'Optional', 'Tuple', 'Image', 'ImageFilter',
                  'surfarray', 'math', '_time')
]


def __getattr__(name):
    try:
        return getattr(pg, name)
    except AttributeError:
        pass
    for _sub in (pg.event, pg.key, pg.mouse, pg.display, pg.draw,
                 pg.transform, pg.image, pg.font, pg.mixer,
                 pg.time, pg.sprite, pg.mask, pg.math, pg.cursors):
        try:
            return getattr(_sub, name)
        except AttributeError:
            continue
    raise AttributeError(
        f"module 'modern_pygame' has no attribute {name!r} "
        f"(also not found in pygame)"
    )


def __dir__():
    base = set(globals().keys())
    try:
        base.update(dir(pg))
    except Exception:
        pass
    return sorted(base)