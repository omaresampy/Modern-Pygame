"""
game_demo.py - لعبة Survivors كاملة بـ Scene System.
3 مشاهد: Menu → Game → GameOver + Pause Overlay.

    python game_demo.py

التحكم:
    Menu:     UP/DOWN + ENTER
    Game:     WASD/arrows + auto-fire + ESC pause + H hud
    Pause:    ESC أو P
    GameOver: UP/DOWN + ENTER
"""
import pygame as pg
import numpy as np
import random
import math

from modern_pygame_3 import (
    Surface, Clock, Rect,
    Scene, SceneManager, FadeTransition, SlideTransition,
    Tween, Easing,
    Sprite, Group, BatchGroup, ObjectPool, Animation,
    ParticleSystem, ParticleConfig, Presets,
    Camera,
    TextCache, Profiler, LOD,
    draw_text, init, quit,
    QUIT, KEYDOWN, K_ESCAPE,
    K_w, K_a, K_s, K_d, K_h, K_p, K_SPACE, K_RETURN,
)


# ============================================================================
# Config
# ============================================================================
VIEW_W, VIEW_H = 1100, 700
WORLD_W, WORLD_H = 2600, 1800
FPS = 60

MAX_ENEMIES = 1500
MAX_BULLETS = 800
MAX_PARTICLES = 15_000
MAX_XP_ORBS = 1200

PLAYER_SPEED = 320
PLAYER_RADIUS = 16
PLAYER_BASE_HP = 100
PLAYER_FIRE_RATE = 0.22
BULLET_DAMAGE = 12
BULLET_SPEED = 720
ENEMY_RADIUS = 14
ENEMY_CONTACT_DAMAGE = 8
ENEMY_BASE_HP = 20
ENEMY_BASE_SPEED = 95
XP_PICKUP_RADIUS = 32


# ============================================================================
# ⚠️ init + set_mode قبل أي convert_alpha
# ============================================================================
init()
SCREEN = pg.display.set_mode((VIEW_W, VIEW_H))
pg.display.set_caption("Survivors - Modern Pygame v4.0")

# Fonts
F_TITLE = pg.font.SysFont("Consolas", 64, bold=True)
F_HUGE = pg.font.SysFont("Consolas", 90, bold=True)
F_MENU = pg.font.SysFont("Consolas", 28, bold=True)
F_MID = pg.font.SysFont("Consolas", 22, bold=True)
F_SMALL = pg.font.SysFont("Consolas", 16, bold=True)
F_TINY = pg.font.SysFont("Consolas", 12, bold=True)


# ============================================================================
# Assets
# ============================================================================
def make_player_sprite():
    s = Surface((40, 40), pg.SRCALPHA)
    pg.draw.circle(s, (50, 80, 150), (20, 20), 18)
    pg.draw.circle(s, (100, 200, 255), (20, 20), 14)
    pg.draw.circle(s, (200, 240, 255), (20, 20), 8)
    pg.draw.circle(s, (255, 255, 255), (16, 16), 4)
    return s.convert_alpha()


def make_enemy_sprite(color, radius=14):
    size = radius * 2 + 4
    s = Surface((size, size), pg.SRCALPHA)
    c = size // 2
    pg.draw.circle(s, (0, 0, 0, 80), (c, c + 2), radius)
    pg.draw.circle(s, color, (c, c), radius)
    pg.draw.circle(s, (0, 0, 0), (c, c), radius, 2)
    pg.draw.circle(s, (255, 255, 255), (c - 3, c - 2), 3)
    pg.draw.circle(s, (255, 255, 255), (c + 3, c - 2), 3)
    pg.draw.circle(s, (0, 0, 0), (c - 3, c - 2), 1)
    pg.draw.circle(s, (0, 0, 0), (c + 3, c - 2), 1)
    return s.convert_alpha()


def make_bullet_sprite():
    s = Surface((8, 8), pg.SRCALPHA)
    pg.draw.circle(s, (255, 255, 100), (4, 4), 3)
    pg.draw.circle(s, (255, 255, 255), (4, 4), 2)
    return s.convert_alpha()


def make_xp_orb():
    s = Surface((12, 12), pg.SRCALPHA)
    pg.draw.circle(s, (100, 255, 100), (6, 6), 5)
    pg.draw.circle(s, (200, 255, 200), (6, 6), 3)
    return s.convert_alpha()


PLAYER_IMG = make_player_sprite()
ENEMY_IMGS = [
    make_enemy_sprite((220, 80, 80)),
    make_enemy_sprite((220, 150, 80)),
    make_enemy_sprite((180, 80, 220)),
    make_enemy_sprite((80, 200, 220)),
]
BULLET_IMG = make_bullet_sprite()
XP_IMG = make_xp_orb()

_CLOCK = Clock()


# ============================================================================
# MenuScene
# ============================================================================
class MenuScene(Scene):
    def __init__(self):
        super().__init__()
        self.bg_color = (12, 12, 30)
        self.stars = [
            [random.uniform(0, VIEW_W), random.uniform(0, VIEW_H),
             random.randint(1, 2), random.uniform(20, 60)]
            for _ in range(150)
        ]
        self.selected = 0
        self.items = ['PLAY', 'QUIT']
        self.title_y_t = None
        self.title_alpha_t = None
        self.subtitle_alpha_t = None

    def on_enter(self):
        self.title_y_t = self.tween(-150, 180, 0.9, 'ease_out_back')
        self.title_alpha_t = self.tween(0, 255, 0.6, 'ease_out_cubic')
        self.subtitle_alpha_t = self.tween(0, 255, 0.8, 'ease_out_cubic',
                                            delay=0.4)

    def handle_event(self, event):
        if event.type != KEYDOWN:
            return
        if event.key in (pg.K_UP, K_w):
            self.selected = (self.selected - 1) % len(self.items)
        elif event.key in (pg.K_DOWN, K_s):
            self.selected = (self.selected + 1) % len(self.items)
        elif event.key in (K_RETURN, K_SPACE):
            if self.items[self.selected] == 'PLAY':
                self.switch_to(GameScene(), FadeTransition(0.5, (0, 0, 0)))
            else:
                pg.event.post(pg.event.Event(QUIT))

    def update(self, dt):
        super().update(dt)
        for s in self.stars:
            s[1] += s[3] * dt
            if s[1] > VIEW_H:
                s[1] = -5
                s[0] = random.uniform(0, VIEW_W)

    def draw(self, screen):
        screen.fill(self.bg_color)
        for s in self.stars:
            pg.draw.circle(screen, (90, 100, 140), (int(s[0]), int(s[1])), s[2])

        title_y = int(self.title_y_t.value) if self.title_y_t else 180
        a = int(self.title_alpha_t.value) if self.title_alpha_t else 255
        title = F_HUGE.render("SURVIVORS", True, (150, 220, 255))
        if a < 255:
            title.set_alpha(a)
        screen.blit(title, title.get_rect(center=(VIEW_W // 2, title_y)))

        a2 = int(self.subtitle_alpha_t.value) if self.subtitle_alpha_t else 255
        sub = F_MID.render("a modern_pygame showcase", True, (140, 160, 200))
        if a2 < 255:
            sub.set_alpha(a2)
        screen.blit(sub, sub.get_rect(center=(VIEW_W // 2, title_y + 80)))

        base_y = VIEW_H // 2 + 60
        for i, item in enumerate(self.items):
            color = (255, 255, 100) if i == self.selected else (140, 140, 170)
            prefix = "> " if i == self.selected else "  "
            txt = F_MENU.render(prefix + item, True, color)
            r = txt.get_rect(center=(VIEW_W // 2, base_y + i * 55))
            screen.blit(txt, r)

        tip = F_SMALL.render("[UP/DOWN] select   [ENTER] confirm   [ESC] quit",
                             True, (100, 100, 130))
        screen.blit(tip, tip.get_rect(center=(VIEW_W // 2, VIEW_H - 40)))


# ============================================================================
# PauseOverlay
# ============================================================================
class PauseOverlay(Scene):
    def __init__(self):
        super().__init__()
        self.transparent = True
        self.alpha_t = None

    def on_enter(self):
        self.alpha_t = self.tween(0, 200, 0.25, 'ease_out_quad')

    def handle_event(self, event):
        if event.type == KEYDOWN:
            if event.key in (K_ESCAPE, K_p):
                self.pop()

    def draw(self, screen):
        a = int(self.alpha_t.value) if self.alpha_t else 0
        ov = pg.Surface((VIEW_W, VIEW_H), pg.SRCALPHA)
        ov.fill((0, 0, 0, a))
        screen.blit(ov, (0, 0))
        if a > 100:
            title = F_HUGE.render("PAUSED", True, (255, 255, 100))
            screen.blit(title, title.get_rect(center=(VIEW_W // 2, VIEW_H // 2 - 40)))
            sub = F_MID.render("[ESC] or [P] to resume", True, (220, 220, 220))
            screen.blit(sub, sub.get_rect(center=(VIEW_W // 2, VIEW_H // 2 + 50)))


# ============================================================================
# GameOverScene
# ============================================================================
class GameOverScene(Scene):
    def __init__(self, score, time_played, kills, level):
        super().__init__()
        self.bg_color = (30, 5, 5)
        self.score = score
        self.time_played = time_played
        self.kills = kills
        self.level = level
        self.over_scale_t = None
        self.selected = 0
        self.items = ['RETRY', 'MENU']

    def on_enter(self):
        self.over_scale_t = self.tween(0.3, 1.0, 0.55, 'ease_out_back')

    def handle_event(self, event):
        if event.type != KEYDOWN:
            return
        if event.key in (pg.K_UP, K_w):
            self.selected = (self.selected - 1) % len(self.items)
        elif event.key in (pg.K_DOWN, K_s):
            self.selected = (self.selected + 1) % len(self.items)
        elif event.key in (K_RETURN, K_SPACE):
            if self.items[self.selected] == 'RETRY':
                self.switch_to(GameScene(), FadeTransition(0.5, (150, 0, 0)))
            else:
                self.switch_to(MenuScene(), FadeTransition(0.5))

    def draw(self, screen):
        screen.fill(self.bg_color)

        s = max(0.1, self.over_scale_t.value) if self.over_scale_t else 1.0
        title = F_HUGE.render("GAME OVER", True, (255, 80, 80))
        w = max(1, int(title.get_width() * s))
        h = max(1, int(title.get_height() * s))
        scaled = pg.transform.smoothscale(title, (w, h))
        screen.blit(scaled, scaled.get_rect(center=(VIEW_W // 2, 150)))

        y = 280
        stats = [
            (f"Score: {self.score}", (255, 255, 100)),
            (f"Kills: {self.kills}", (255, 150, 100)),
            (f"Level: {self.level}", (150, 220, 255)),
            (f"Time: {self.time_played:.1f}s", (200, 200, 220)),
        ]
        for text, color in stats:
            txt = F_MID.render(text, True, color)
            screen.blit(txt, txt.get_rect(center=(VIEW_W // 2, y)))
            y += 40

        base_y = 520
        for i, item in enumerate(self.items):
            color = (255, 255, 100) if i == self.selected else (150, 150, 150)
            prefix = "> " if i == self.selected else "  "
            txt = F_MENU.render(prefix + item, True, color)
            r = txt.get_rect(center=(VIEW_W // 2, base_y + i * 50))
            screen.blit(txt, r)


# ============================================================================
# Player
# ============================================================================
class Player:
    __slots__ = ('x', 'y', 'hp', 'max_hp', 'radius', 'rect',
                 'fire_cd', 'fire_rate', 'damage', 'bullet_count', 'spread')

    def __init__(self):
        self.x = WORLD_W // 2
        self.y = WORLD_H // 2
        self.hp = PLAYER_BASE_HP
        self.max_hp = PLAYER_BASE_HP
        self.radius = PLAYER_RADIUS
        self.rect = Rect(self.x - self.radius, self.y - self.radius,
                         self.radius * 2, self.radius * 2)
        self.fire_cd = 0
        self.fire_rate = PLAYER_FIRE_RATE
        self.damage = BULLET_DAMAGE
        self.bullet_count = 1
        self.spread = 0


# ============================================================================
# GameScene
# ============================================================================
class GameScene(Scene):
    def __init__(self):
        super().__init__()
        self.bg_color = (10, 10, 25)
        self.player = Player()

        self.enemies = BatchGroup(capacity=MAX_ENEMIES,
                                  world_size=(WORLD_W, WORLD_H),
                                  cell_size=64, use_lod=True, name='enemies')
        self.bullets = BatchGroup(capacity=MAX_BULLETS,
                                  world_size=(WORLD_W, WORLD_H),
                                  cell_size=64, use_lod=False, name='bullets')
        self.xp_orbs = BatchGroup(capacity=MAX_XP_ORBS,
                                  world_size=(WORLD_W, WORLD_H),
                                  cell_size=64, use_lod=False,
                                  needs_grid=False, name='xp')
        self.enemy_hp = np.zeros(MAX_ENEMIES, dtype=np.float32)

        self.particles = ParticleSystem(
            ParticleConfig(
                max_count=MAX_PARTICLES, sprite_radius=4,
                gravity=150.0, drag=1.5, bounce=False,
                lifespan_range=(0.35, 0.9), fade_out=True,
                use_gpu=False, use_lod=True,
            ),
            (VIEW_W, VIEW_H),
        )

        self.camera = Camera(VIEW_W, VIEW_H, world_w=WORLD_W, world_h=WORLD_H,
                             smooth=0.18)
        self.camera.rect.x = int(self.player.x - VIEW_W // 2)
        self.camera.rect.y = int(self.player.y - VIEW_H // 2)

        self.background = self._make_background()

        self.score = 0
        self.kills = 0
        self.level = 1
        self.xp = 0
        self.xp_needed = 10
        self.time_played = 0.0
        self.spawn_timer = 0.0
        self.damage_flash = 0.0
        self.show_hud = True

        self._last_dt = 0.0
        self.hud_fps = TextCache(F_SMALL, (140, 140, 160), update_interval=0.15)
        self.hud_score = TextCache(F_MID, (255, 255, 100), (0, 0, 0),
                                    update_interval=0.1)
        self.hud_level = TextCache(F_MID, (180, 220, 255), (0, 0, 0),
                                    update_interval=0.3)
        self.hud_hp = TextCache(F_SMALL, (255, 100, 100), update_interval=0.15)
        self.hud_help = TextCache(F_SMALL, (130, 130, 150),
                                   update_interval=10.0)

    def _make_background(self):
        bg = Surface((WORLD_W, WORLD_H))
        bg.draw_gradient((10, 15, 25), (25, 10, 35), direction='diagonal')
        for x in range(0, WORLD_W, 100):
            pg.draw.line(bg, (20, 30, 50), (x, 0), (x, WORLD_H), 1)
        for y in range(0, WORLD_H, 100):
            pg.draw.line(bg, (20, 30, 50), (0, y), (WORLD_W, y), 1)
        for _ in range(500):
            x = random.randint(0, WORLD_W)
            y = random.randint(0, WORLD_H)
            pg.draw.circle(bg, (60, 80, 120), (x, y), random.randint(1, 2))
        return bg.convert()

    def handle_event(self, event):
        if event.type == KEYDOWN:
            if event.key == K_ESCAPE:
                self.push(PauseOverlay())
            elif event.key == K_h:
                self.show_hud = not self.show_hud

    def update(self, dt):
        super().update(dt)
        self._last_dt = dt
        self.time_played += dt

        keys = pg.key.get_pressed()
        mx = (1 if (keys[K_d] or keys[pg.K_RIGHT]) else 0) - \
             (1 if (keys[K_a] or keys[pg.K_LEFT]) else 0)
        my = (1 if (keys[K_s] or keys[pg.K_DOWN]) else 0) - \
             (1 if (keys[K_w] or keys[pg.K_UP]) else 0)
        if mx and my:
            mx *= 0.7071
            my *= 0.7071

        p = self.player
        p.x += mx * PLAYER_SPEED * dt
        p.y += my * PLAYER_SPEED * dt
        p.x = max(p.radius, min(WORLD_W - p.radius, p.x))
        p.y = max(p.radius, min(WORLD_H - p.radius, p.y))
        p.rect.x = int(p.x - p.radius)
        p.rect.y = int(p.y - p.radius)
        p.fire_cd = max(0, p.fire_cd - dt)

        self.camera.follow(p.rect)

        # Spawn
        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            diff = 1.0 + min(4.0, self.time_played / 30.0)
            self.spawn_timer = 0.5 / diff
            count = int(3 * diff)
            for _ in range(count):
                angle = random.uniform(0, 6.2832)
                dist = random.uniform(500, 700)
                ex = p.x + math.cos(angle) * dist
                ey = p.y + math.sin(angle) * dist
                ex = max(20, min(WORLD_W - 20, ex))
                ey = max(20, min(WORLD_H - 20, ey))
                idx = random.randint(0, len(ENEMY_IMGS) - 1)
                j = self.enemies.add(ex, ey, 0, 0, ENEMY_IMGS[idx],
                                     life=60.0, data=float(idx))
                if j >= 0:
                    self.enemy_hp[j] = ENEMY_BASE_HP * (1.0 + self.time_played / 60.0)

        c = self.enemies.count
        if c > 0:
            dx = p.x - self.enemies.x[:c]
            dy = p.y - self.enemies.y[:c]
            d = np.sqrt(dx * dx + dy * dy) + 0.001
            self.enemies.vx[:c] = dx / d * ENEMY_BASE_SPEED
            self.enemies.vy[:c] = dy / d * ENEMY_BASE_SPEED
            self.enemies.update(dt, bounds=(0, 0, WORLD_W, WORLD_H))

        # Auto-fire
        if p.fire_cd <= 0 and c > 0:
            dx = self.enemies.x[:c] - p.x
            dy = self.enemies.y[:c] - p.y
            d2 = dx * dx + dy * dy
            j = int(np.argmin(d2))
            if d2[j] < 700 * 700:
                d = math.sqrt(d2[j]) + 0.001
                bvx = dx[j] / d * BULLET_SPEED
                bvy = dy[j] / d * BULLET_SPEED
                if p.bullet_count == 1:
                    self.bullets.add(p.x - 4, p.y - 4, bvx, bvy,
                                     BULLET_IMG, life=1.6)
                else:
                    base_angle = math.atan2(bvy, bvx)
                    spread = math.radians(p.spread)
                    for k in range(p.bullet_count):
                        a = base_angle + (k - (p.bullet_count - 1) / 2) * spread
                        self.bullets.add(p.x - 4, p.y - 4,
                                         math.cos(a) * BULLET_SPEED,
                                         math.sin(a) * BULLET_SPEED,
                                         BULLET_IMG, life=1.6)
                p.fire_cd = p.fire_rate

        self.bullets.update(dt, bounds=(0, 0, WORLD_W, WORLD_H))

        # Collisions
        if self.bullets.count > 0 and self.enemies.count > 0:
            b_hit, e_hit = self.bullets.collide_with(
                self.enemies, 5, ENEMY_RADIUS, use_grid=True)
            if len(b_hit) > 0:
                for j in e_hit:
                    if self.enemy_hp[j] > 0:
                        self.enemy_hp[j] -= p.damage
                self.bullets.remove_indices(b_hit)
                cc = self.enemies.count
                dead = np.where(self.enemy_hp[:cc] <= 0)[0]
                if len(dead) > 0:
                    for j in dead:
                        sx, sy = self.camera.world_to_screen(
                            self.enemies.x[j], self.enemies.y[j])
                        if -50 < sx < VIEW_W + 50 and -50 < sy < VIEW_H + 50:
                            self.particles.spawn(5, center=(sx, sy),
                                                 speed_range=(80, 260))
                        self.xp_orbs.add(self.enemies.x[j], self.enemies.y[j],
                                         0, 0, XP_IMG, life=15.0)
                    self.kills += len(dead)
                    self.score += len(dead) * 10
                    self.enemies.remove_indices(dead)

        c = self.enemies.count
        if c > 0:
            dx = self.enemies.x[:c] - p.x
            dy = self.enemies.y[:c] - p.y
            d2 = dx * dx + dy * dy
            r = p.radius + ENEMY_RADIUS
            hit = np.where(d2 <= r * r)[0]
            if len(hit) > 0:
                p.hp -= ENEMY_CONTACT_DAMAGE * len(hit)
                self.damage_flash = 0.35
                self.enemies.remove_indices(hit)

        c = self.xp_orbs.count
        if c > 0:
            dx = self.xp_orbs.x[:c] - p.x
            dy = self.xp_orbs.y[:c] - p.y
            d2 = dx * dx + dy * dy
            r2 = XP_PICKUP_RADIUS * XP_PICKUP_RADIUS
            picked = np.where(d2 <= r2)[0]
            if len(picked) > 0:
                self.xp += len(picked)
                self.xp_orbs.remove_indices(picked)
                while self.xp >= self.xp_needed:
                    self.xp -= self.xp_needed
                    self.level += 1
                    self.xp_needed = int(self.xp_needed * 1.35)
                    self._apply_level_up()

        self.particles.update(dt)

        if self.damage_flash > 0:
            self.damage_flash -= dt

        if p.hp <= 0:
            self.switch_to(
                GameOverScene(self.score, self.time_played,
                              self.kills, self.level),
                FadeTransition(0.6, (150, 0, 0)))

    def _apply_level_up(self):
        p = self.player
        pick = random.choice(['damage', 'fire_rate', 'bullet_count', 'hp'])
        if pick == 'damage':
            p.damage += 4
        elif pick == 'fire_rate':
            p.fire_rate = max(0.06, p.fire_rate * 0.9)
        elif pick == 'bullet_count':
            p.bullet_count = min(5, p.bullet_count + 1)
            p.spread = max(8, p.spread + 6)
        elif pick == 'hp':
            p.max_hp += 15
            p.hp = min(p.max_hp, p.hp + 15)

    def draw(self, screen):
        cam = self.camera
        screen.blit(self.background, (-cam.rect.x, -cam.rect.y))

        self.xp_orbs.draw(screen, camera=cam)
        self.enemies.draw(screen, camera=cam)
        self.bullets.draw(screen, camera=cam)

        p = self.player
        px = int(p.x - cam.rect.x - 20)
        py = int(p.y - cam.rect.y - 20)
        screen.blit(PLAYER_IMG, (px, py))

        self.particles.draw(screen)

        if self.damage_flash > 0:
            a = int(100 * max(0, self.damage_flash) / 0.35)
            flash = pg.Surface((VIEW_W, VIEW_H), pg.SRCALPHA)
            flash.fill((255, 30, 30, a))
            screen.blit(flash, (0, 0))

        if self.show_hud:
            dt = self._last_dt
            surf, sh = self.hud_score.render(f"SCORE: {self.score}", dt)
            if sh: screen.blit(sh, (12, 12))
            screen.blit(surf, (10, 10))

            surf, sh = self.hud_level.render(
                f"LVL {self.level}  XP {self.xp}/{self.xp_needed}", dt)
            if sh: screen.blit(sh, (12, 36))
            screen.blit(surf, (10, 34))

            hp_pct = max(0, p.hp / p.max_hp)
            bar_w, bar_h = 260, 22
            bx, by = 10, VIEW_H - 36
            pg.draw.rect(screen, (40, 20, 20), (bx, by, bar_w, bar_h),
                         border_radius=4)
            pg.draw.rect(screen, (220, 50, 50),
                         (bx, by, int(bar_w * hp_pct), bar_h), border_radius=4)
            pg.draw.rect(screen, (255, 255, 255), (bx, by, bar_w, bar_h), 2,
                         border_radius=4)
            surf, _ = self.hud_hp.render(
                f"HP: {max(0, int(p.hp))}/{int(p.max_hp)}", dt)
            screen.blit(surf, (bx + 8, by + 3))

            fps_txt = (f"FPS: {_CLOCK.get_fps():.0f}  |  "
                       f"E: {self.enemies.count}  "
                       f"B: {self.bullets.count}  "
                       f"P: {self.particles.count}")
            surf, _ = self.hud_fps.render(fps_txt, dt)
            tw = surf.get_width()
            screen.blit(surf, (VIEW_W - tw - 10, 10))

            surf, _ = self.hud_help.render(
                "[WASD] move   [H] hud   [ESC] pause", dt)
            tw = surf.get_width()
            screen.blit(surf, (VIEW_W - tw - 10, VIEW_H - 22))


# ============================================================================
# Main
# ============================================================================
def main():
    sm = SceneManager(SCREEN)
    sm.switch(MenuScene(), FadeTransition(0.6, (0, 0, 0)))

    running = True
    while running:
        dt = _CLOCK.tick(FPS) / 1000.0
        if dt > 0.05:
            dt = 0.05

        for e in pg.event.get():
            if e.type == QUIT:
                running = False
            elif e.type == KEYDOWN and e.key == K_ESCAPE:
                cur = sm.current
                if isinstance(cur, (GameScene, PauseOverlay)):
                    sm.handle_event(e)
                else:
                    running = False
            else:
                sm.handle_event(e)

        sm.update(dt)
        sm.draw()
        pg.display.flip()

    quit()


if __name__ == "__main__":
    main()