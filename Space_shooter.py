"""
space_shooter_optimized.py
نسخة محسّنة بـ:
- HUD Text Cache (تحديث النص فقط عند التغير)
- Grid-based Collision (O(1) بدل O(n×m))
- Camera transforms vectorized
- Spawn & particles متوازنة

المتطلبات: نفس مكتبة modern_pygame
"""
import pygame as pg
import numpy as np
import random
import time

from modern_pygame_3 import (
    Surface, Clock, ParticleSystem, ParticleConfig,
    Sprite, BatchGroup, Camera,
    draw_text, init, quit,
    QUIT, KEYDOWN, K_ESCAPE,
    K_w, K_a, K_s, K_d, K_h, K_p,
)


# ============================================================================
# Text Cache - يرندر النص فقط عند التغير
# ============================================================================
class TextCache:
    """يخزّن آخر نص مرندر - يمنع إعادة الرسم 60 مرة/ثانية."""
    __slots__ = ('font', 'color', 'shadow_color', '_last', '_surf', '_shadow')

    def __init__(self, font, color=(255, 255, 255), shadow_color=None):
        self.font = font
        self.color = color
        self.shadow_color = shadow_color
        self._last = None
        self._surf = None
        self._shadow = None

    def render(self, text):
        if text != self._last:
            self._surf = self.font.render(text, True, self.color)
            if self.shadow_color:
                self._shadow = self.font.render(text, True, self.shadow_color)
            self._last = text
        return self._surf, self._shadow


# ============================================================================
# الإعدادات
# ============================================================================
WORLD_W, WORLD_H = 1800, 1200
VIEW_W, VIEW_H = 1000, 650

# ✅ أعداد مخفّضة
MAX_ENEMIES = 400
MAX_BULLETS = 200
MAX_PARTICLES = 15_000
SPAWN_INTERVAL = 0.5
ENEMIES_PER_SPAWN = 3
PARTICLES_PER_KILL = 8
PARALLAX_STARS = 120

pg.init()
screen = pg.display.set_mode((VIEW_W, VIEW_H))
pg.display.set_caption("Space Shooter OPTIMIZED")
clock = Clock()


# ============================================================================
# الأصول
# ============================================================================
def make_player():
    s = Surface((48, 48), pg.SRCALPHA)
    pg.draw.polygon(s, (255, 150, 50), [(18, 40), (24, 48), (30, 40)])
    pg.draw.polygon(s, (255, 220, 100), [(20, 42), (24, 48), (28, 42)])
    pg.draw.polygon(s, (100, 200, 255), [(24, 4), (8, 40), (40, 40)])
    pg.draw.polygon(s, (180, 240, 255), [(24, 8), (14, 36), (34, 36)])
    pg.draw.circle(s, (30, 60, 120), (24, 24), 6)
    return s.convert_alpha()


def make_enemy(color):
    s = Surface((32, 32), pg.SRCALPHA)
    pg.draw.polygon(s, color, [(16, 2), (30, 16), (16, 30), (2, 16)])
    pg.draw.polygon(s, (255, 255, 255),
                    [(16, 6), (26, 16), (16, 26), (6, 16)], 1)
    pg.draw.circle(s, (255, 255, 200), (16, 16), 3)
    return s.convert_alpha()


def make_bullet():
    s = Surface((6, 14), pg.SRCALPHA)
    pg.draw.rect(s, (255, 255, 100), (0, 0, 6, 14), border_radius=3)
    pg.draw.rect(s, (255, 255, 255), (2, 2, 2, 10))
    return s.convert_alpha()


player_img = make_player()
enemy_imgs = [
    make_enemy((255, 80, 80)),
    make_enemy((255, 150, 50)),
    make_enemy((200, 80, 255)),
]
bullet_img = make_bullet()


# ============================================================================
# الخلفية
# ============================================================================
world_bg = Surface((WORLD_W, WORLD_H))
world_bg.draw_gradient((8, 8, 25), (25, 8, 45), direction='diagonal')
for _ in range(300):
    x, y = random.randint(0, WORLD_W), random.randint(0, WORLD_H)
    pg.draw.circle(world_bg, (200, 200, 255), (x, y), random.randint(1, 2))
world_bg = world_bg.convert()


# ============================================================================
# الكائنات
# ============================================================================
player = Sprite(player_img, x=WORLD_W // 2 - 24, y=WORLD_H // 2 - 24)
player.speed = 380.0
player.hp = 100
player.fire_cd = 0.0
player.fire_rate = 0.10

enemies = BatchGroup(capacity=MAX_ENEMIES, world_size=(WORLD_W, WORLD_H))
bullets = BatchGroup(capacity=MAX_BULLETS, world_size=(WORLD_W, WORLD_H))

particles = ParticleSystem(
    ParticleConfig(
        max_count=MAX_PARTICLES,
        sprite_radius=4,
        gravity=200.0,
        drag=1.2,
        bounce=False,
        lifespan_range=(0.4, 0.9),
        fade_out=True,
    ),
    (VIEW_W, VIEW_H),
)

camera = Camera(VIEW_W, VIEW_H, world_w=WORLD_W, world_h=WORLD_H, smooth=0.15)
camera.follow(player.rect, snap=True)


# ============================================================================
# Parallax - نجوم مع depth محسوب مسبقاً
# ============================================================================
parallax_x = np.array([random.uniform(0, VIEW_W * 2) for _ in range(PARALLAX_STARS)],
                      dtype=np.float32)
parallax_y = np.array([random.uniform(0, VIEW_H * 2) for _ in range(PARALLAX_STARS)],
                      dtype=np.float32)
parallax_depth = np.array([random.uniform(0.1, 0.5) for _ in range(PARALLAX_STARS)],
                          dtype=np.float32)
parallax_size = np.array([random.randint(1, 2) for _ in range(PARALLAX_STARS)],
                         dtype=np.int32)
# ✅ سطح واحد بنرسمه بسرعة
parallax_layer = pg.Surface((VIEW_W, VIEW_H), pg.SRCALPHA)
parallax_layer.fill((0, 0, 0, 0))
for i in range(PARALLAX_STARS):
    pg.draw.circle(parallax_layer, (120, 120, 160),
                   (int(parallax_x[i]), int(parallax_y[i])), int(parallax_size[i]))
parallax_layer = parallax_layer.convert_alpha()


# ============================================================================
# HUD Text Caches
# ============================================================================
fonts = {
    'lg': pg.font.SysFont("Consolas", 22, bold=True),
    'sm': pg.font.SysFont("Consolas", 14, bold=True),
}

hud_fps = TextCache(fonts['lg'], (150, 255, 150))
hud_score = TextCache(fonts['lg'], (255, 255, 100), (0, 0, 0))
hud_hp = TextCache(fonts['sm'], (255, 100, 100))
hud_stats = TextCache(fonts['sm'], (180, 220, 255))
hud_help = TextCache(fonts['sm'], (150, 150, 180))


# ============================================================================
# الحالة
# ============================================================================
state = {
    'score': 0,
    'kills': 0,
    'show_hud': True,
    'running': True,
    'damage_flash': 0.0,
}
enemy_wave_timer = 0.0


# ============================================================================
# الحلقة الرئيسية
# ============================================================================
report_t = time.perf_counter()
hud_update_t = 0.0

while state['running']:
    dt = clock.tick(0) / 1000.0
    if dt > 0.05:
        dt = 0.05

    # ═══════ Events ═══════
    for e in pg.event.get():
        if e.type == QUIT:
            state['running'] = False
        elif e.type == KEYDOWN:
            k = e.key
            if k == K_ESCAPE:
                state['running'] = False
            elif k == K_h:
                state['show_hud'] = not state['show_hud']
            elif k == K_p:
                # debug toggle
                pass

    # ═══════ Input ═══════
    keys = pg.key.get_pressed()
    mx = (1 if (keys[K_d] or keys[pg.K_RIGHT]) else 0) - \
         (1 if (keys[K_a] or keys[pg.K_LEFT]) else 0)
    my = (1 if (keys[K_s] or keys[pg.K_DOWN]) else 0) - \
         (1 if (keys[K_w] or keys[pg.K_UP]) else 0)
    if mx and my:
        inv = 0.70710678118
        mx *= inv
        my *= inv

    player.vx = mx * player.speed
    player.vy = my * player.speed
    player.update(dt)
    player.rect.x = max(0, min(WORLD_W - player.rect.width, player.rect.x))
    player.rect.y = max(0, min(WORLD_H - player.rect.height, player.rect.y))

    camera.follow(player.rect)

    # ═══════ Auto-fire ═══════
    player.fire_cd -= dt
    if player.fire_cd <= 0 and enemies.count > 0:
        # ✅ استخدم numpy للبحث عن أقرب عدو
        dx = enemies.x[:enemies.count] - player.rect.centerx
        dy = enemies.y[:enemies.count] - player.rect.centery
        d2 = dx * dx + dy * dy
        j = int(np.argmin(d2))
        if d2[j] < 700 * 700:
            d = d2[j] ** 0.5
            bullets.add(player.rect.centerx - 3, player.rect.centery - 7,
                        dx[j] / d * 700, dy[j] / d * 700,
                        bullet_img, life=1.8)
            player.fire_cd = player.fire_rate

    # ═══════ Spawn ═══════
    enemy_wave_timer -= dt
    if enemy_wave_timer <= 0:
        enemy_wave_timer = SPAWN_INTERVAL
        for _ in range(ENEMIES_PER_SPAWN):
            angle = random.uniform(0, 6.2832)
            dist = random.uniform(500, 700)
            ex = player.rect.centerx + np.cos(angle) * dist
            ey = player.rect.centery + np.sin(angle) * dist
            ex = max(20, min(WORLD_W - 20, ex))
            ey = max(20, min(WORLD_H - 20, ey))
            dx = player.rect.centerx - ex
            dy = player.rect.centery - ey
            d = max(1, (dx * dx + dy * dy) ** 0.5)
            spd = random.uniform(60, 120)
            idx = random.randint(0, len(enemy_imgs) - 1)
            enemies.add(ex, ey,
                        dx / d * spd, dy / d * spd,
                        enemy_imgs[idx], life=30.0, data=idx)

    # ═══════ Update ═══════
    bullets.update(dt, bounds=(0, 0, WORLD_W, WORLD_H))
    enemies.update(dt, bounds=(0, 0, WORLD_W, WORLD_H))

    # ═══════ Collisions: bullets vs enemies (grid) ═══════
    if bullets.count > 0 and enemies.count > 0:
        b_hit, e_hit = bullets.collide_with(enemies, 5, 16)
        if len(b_hit) > 0:
            bullets.remove_indices(b_hit)
            unique_e = np.unique(e_hit)
            # ✅ انفجارات أخف
            for j in unique_e:
                sx = enemies.x[j] - camera.rect.x
                sy = enemies.y[j] - camera.rect.y
                if -50 < sx < VIEW_W + 50 and -50 < sy < VIEW_H + 50:
                    particles.spawn(PARTICLES_PER_KILL, center=(sx, sy),
                                    speed_range=(80, 250))
                state['score'] += 10
                state['kills'] += 1
            enemies.remove_indices(unique_e)

    # ═══════ Collisions: enemies vs player ═══════
    if enemies.count > 0:
        dx = enemies.x[:enemies.count] - player.rect.centerx
        dy = enemies.y[:enemies.count] - player.rect.centery
        d2 = dx * dx + dy * dy
        hit = np.where(d2 <= 30 * 30)[0]
        if len(hit) > 0:
            player.hp -= 10 * len(hit)
            state['damage_flash'] = 0.3
            if player.hp <= 0:
                state['running'] = False
            enemies.remove_indices(hit)

    particles.update(dt)

    # ═══════ Render ═══════
    screen.blit(world_bg, (-camera.rect.x, -camera.rect.y))

    # Parallax - سطح واحد فقط
    px = int(camera.rect.x * 0.3) % VIEW_W
    py = int(camera.rect.y * 0.3) % VIEW_H
    screen.blit(parallax_layer, (-px, -py))
    screen.blit(parallax_layer, (VIEW_W - px, -py))
    screen.blit(parallax_layer, (-px, VIEW_H - py))

    # ✅ Enemies + bullets بتحويل numpy للكاميرا مرة واحدة
    enemies.draw(screen, camera=camera)
    bullets.draw(screen, camera=camera)

    # Player
    screen.blit(player.image,
                (player.rect.x - camera.rect.x,
                 player.rect.y - camera.rect.y))

    # Particles (screen-space)
    particles.draw(screen)

    # Damage flash
    if state['damage_flash'] > 0:
        state['damage_flash'] -= dt
        a = int(80 * max(0, state['damage_flash']) / 0.3)
        flash = pg.Surface((VIEW_W, VIEW_H), pg.SRCALPHA)
        flash.fill((255, 30, 30, a))
        screen.blit(flash, (0, 0))

    # ═══════ HUD - فقط كل 0.1 ثانية ═══════
    hud_update_t += dt
    if state['show_hud'] and hud_update_t >= 0.1:
        hud_update_t = 0.0
        fps = clock.get_fps()
        surf, _ = hud_fps.render(f"FPS: {fps:.0f}")
        screen.blit(surf, (VIEW_W - 130, 12))

        surf, sh = hud_score.render(f"Score: {state['score']}")
        if sh:
            screen.blit(sh, (14, 14))
        screen.blit(surf, (12, 12))

        surf, _ = hud_hp.render(f"HP: {max(0, player.hp)}")
        screen.blit(surf, (12, 40))

        surf, _ = hud_stats.render(
            f"E:{enemies.count}  B:{bullets.count}  P:{particles.count}"
        )
        screen.blit(surf, (12, 60))

    if state['show_hud']:
        surf, _ = hud_help.render(
            "[WASD/Arrows] move   [auto-fire]   [H] hud   [ESC] quit"
        )
        screen.blit(surf, (12, VIEW_H - 26))

    pg.display.flip()

    # ═══════ Report ═══════
    now = time.perf_counter()
    if now - report_t > 1.5:
        print(f"FPS: {clock.get_fps():5.1f} | "
              f"E:{enemies.count:4d}  B:{bullets.count:4d}  "
              f"P:{particles.count:5d} | Score: {state['score']}")
        report_t = now

pg.quit()