"""
pong.py - Pong احترافية بالمكتبة.

المميزات:
    - 3 مستويات صعوبة (Easy/Normal/Hard) مع AI ذكي
    - Ball spin + trail + particles + screen shake
    - Power-ups (Big Paddle / Slow Ball)
    - أصوات مولّدة (paddle/wall/score/powerup)
    - Menu + Game + Pause + MatchEnd scenes
    - Match to 7 points + Match Point indicator
    - Neon glow visuals

    python pong.py

التحكم:
    Menu:  UP/DOWN للتنقل، LEFT/RIGHT للصعوبة، ENTER للاختيار
    Game:  W/S أو الماوس للحركة، M للتبديل، ESC للـ pause
    Pause: ESC أو SPACE للاستئناف، Q للـ menu
"""
from modern_pygame_3 import (
    init, quit, Clock, Rect,
    Surface, Scene, SceneManager, FadeTransition,
    ParticleSystem, ParticleConfig, TextCache,
    display, event, key, mouse, draw, font, transform, mixer, sndarray,
    QUIT, KEYDOWN, MOUSEMOTION,
    K_ESCAPE, K_SPACE, K_RETURN, K_q,
    K_w, K_s, K_a, K_d, K_p, K_m,
    K_UP, K_DOWN, K_LEFT, K_RIGHT,
    SRCALPHA,
)

import math
import random
import numpy as np


# ============================================================================
# Init
# ============================================================================
try:
    mixer.pre_init(44100, -16, 2, 512)
except Exception:
    pass

init()
display.set_caption("PONG PRO")
CLOCK = Clock()


# ============================================================================
# Config
# ============================================================================
VIEW_W, VIEW_H = 1100, 700
FPS = 60

WALL = 14
PADDLE_W, PADDLE_H = 18, 105
PLAYER_X = 50
AI_X = VIEW_W - 50 - PADDLE_W

BALL_R = 10
BALL_SPEED_START = 480
BALL_SPEED_MAX = 850
BALL_SPEEDUP = 1.045
MAX_ANGLE = math.radians(58)
WIN_SCORE = 7

# Colors
BG = (10, 14, 26)
GRID = (22, 30, 48)
FG = (230, 240, 255)
PC = (80, 220, 255)
AC = (255, 80, 140)
BC = (255, 255, 255)
ACCENT = (255, 220, 100)

# Fonts
F_TITLE = font.SysFont("Consolas", 96, bold=True)
F_HUGE = font.SysFont("Consolas", 110, bold=True)
F_BIG = font.SysFont("Consolas", 68, bold=True)
F_MID = font.SysFont("Consolas", 26, bold=True)
F_SMALL = font.SysFont("Consolas", 16, bold=True)


# ============================================================================
# Sounds
# ============================================================================
_SOUNDS = {}
_SOUND_ON = False


def _tone(freq, dur, vol=0.3, decay=4.0):
    try:
        sr = 44100
        n = int(sr * dur)
        t = np.linspace(0, dur, n, False)
        wave = np.sin(2 * np.pi * freq * t)
        env = np.exp(-decay * t / dur)
        wave = (wave * env * vol * 32767).astype(np.int16)
        buf = np.zeros((n, 2), dtype=np.int16)
        buf[:, 0] = wave
        buf[:, 1] = wave
        return sndarray.make_sound(buf)
    except Exception:
        return None


def _init_sounds():
    global _SOUND_ON
    try:
        mixer.init()
        _SOUND_ON = True
    except Exception:
        _SOUND_ON = False
        return
    specs = {
        'paddle': (520, 0.06, 0.35, 5.0),
        'wall':   (330, 0.05, 0.25, 5.0),
        'score':  (220, 0.30, 0.40, 3.0),
        'power':  (880, 0.18, 0.40, 3.0),
        'select': (600, 0.04, 0.25, 5.0),
        'match':  (523, 0.40, 0.40, 2.0),
    }
    for name, (f, d, v, dec) in specs.items():
        _SOUNDS[name] = _tone(f, d, v, dec)


def sfx(name):
    if not _SOUND_ON:
        return
    s = _SOUNDS.get(name)
    if s is not None:
        s.play()


_init_sounds()


# ============================================================================
# Pre-rendered trail sprites
# ============================================================================
_TRAIL = None


def _trail_sprites():
    global _TRAIL
    if _TRAIL is None:
        sprites = []
        N = 12
        for i in range(N):
            t = i / N
            a = int(170 * t)
            r = max(1, int(BALL_R * (0.3 + 0.7 * t)))
            s = Surface((r * 2, r * 2), SRCALPHA)
            draw.circle(s, (255, 255, 255, a), (r, r), r)
            sprites.append((s, r))
        _TRAIL = sprites
    return _TRAIL


# ============================================================================
# Entities
# ============================================================================
class Paddle:
    def __init__(self, x, y, color):
        self.base_h = PADDLE_H
        self.color = color
        self.rect = Rect(x, y, PADDLE_W, PADDLE_H)
        self.vy = 0.0
        self.size_timer = 0.0
        self.size_factor = 1.0

    def set_size_factor(self, f, duration=0.0):
        cy = self.rect.centery
        self.rect.height = int(self.base_h * f)
        self.rect.centery = cy
        self.size_factor = f
        self.size_timer = duration

    def update_buffs(self, dt):
        if self.size_timer > 0:
            self.size_timer -= dt
            if self.size_timer <= 0:
                self.set_size_factor(1.0)


class AIPaddle(Paddle):
    def __init__(self, x, y, color, speed, error):
        super().__init__(x, y, color)
        self.speed = speed
        self.error = error
        self._target_y = y + PADDLE_H / 2
        self._reroll_timer = 0.0

    def update(self, dt, ball):
        self.update_buffs(dt)

        if ball.vx > 0:
            self._reroll_timer -= dt
            if self._reroll_timer <= 0:
                self._reroll_timer = 0.35
                self._target_y = ball.y + random.uniform(-self.error, self.error)
        else:
            self._target_y = VIEW_H / 2

        cy = self.rect.centery
        diff = self._target_y - cy
        max_move = self.speed * dt
        if abs(diff) <= max_move:
            self.vy = diff / dt if dt > 0 else 0
            self.rect.centery = int(self._target_y)
        else:
            self.vy = math.copysign(self.speed, diff)
            self.rect.centery = int(cy + self.vy * dt)

        if self.rect.top < WALL:
            self.rect.top = WALL
        if self.rect.bottom > VIEW_H - WALL:
            self.rect.bottom = VIEW_H - WALL


class Ball:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.vx = 0.0
        self.vy = 0.0
        self.r = BALL_R
        self.speed = BALL_SPEED_START
        self.trail = []
        self.slow_factor = 1.0
        self.slow_timer = 0.0

    def reset(self):
        self.x = VIEW_W / 2
        self.y = VIEW_H / 2
        self.vx = 0.0
        self.vy = 0.0
        self.speed = BALL_SPEED_START
        self.trail.clear()
        self.slow_factor = 1.0
        self.slow_timer = 0.0

    def serve(self, direction):
        angle = random.uniform(-0.35, 0.35)
        self.vx = math.cos(angle) * self.speed * direction
        self.vy = math.sin(angle) * self.speed

    def update(self, dt):
        f = self.slow_factor
        self.x += self.vx * f * dt
        self.y += self.vy * f * dt
        self.trail.append((self.x, self.y))
        if len(self.trail) > 12:
            self.trail.pop(0)
        if self.slow_timer > 0:
            self.slow_timer -= dt
            if self.slow_timer <= 0:
                self.slow_factor = 1.0

    def set_speed(self, s):
        self.speed = s
        mag = math.hypot(self.vx, self.vy)
        if mag > 0:
            self.vx = self.vx / mag * s
            self.vy = self.vy / mag * s


class PowerUp:
    def __init__(self, x, y, kind):
        self.x = float(x)
        self.y = float(y)
        self.kind = kind
        self.vy = 220
        self.r = 18
        self.t = 0.0

    def update(self, dt):
        self.y += self.vy * dt
        self.t += dt

    @property
    def color(self):
        return (100, 240, 130) if self.kind == 'big' else (100, 180, 255)


# ============================================================================
# MenuScene
# ============================================================================
class MenuScene(Scene):
    def __init__(self):
        super().__init__()
        self.bg_color = BG
        self.selected = 1
        self.difficulty = 'normal'
        self.title_y_t = None
        self.bg_surf = self._make_bg()
        self.stars = [
            [random.uniform(0, VIEW_W), random.uniform(0, VIEW_H),
             random.uniform(20, 60), random.randint(1, 2)]
            for _ in range(100)
        ]

    def _make_bg(self):
        s = Surface((VIEW_W, VIEW_H))
        s.fill(BG)
        for x in range(0, VIEW_W, 40):
            draw.line(s, GRID, (x, 0), (x, VIEW_H))
        for y in range(0, VIEW_H, 40):
            draw.line(s, GRID, (0, y), (VIEW_W, y))
        return s.convert()

    def on_enter(self):
        self.title_y_t = self.tween(-100, 140, 0.9, 'ease_out_back')

    def _cycle_diff(self, d):
        order = ['easy', 'normal', 'hard']
        i = order.index(self.difficulty)
        self.difficulty = order[(i + d) % len(order)]
        sfx('select')

    def handle_event(self, e):
        if e.type != KEYDOWN:
            return
        if e.key in (K_UP, K_w):
            self.selected = (self.selected - 1) % 3
            sfx('select')
        elif e.key in (K_DOWN, K_s):
            self.selected = (self.selected + 1) % 3
            sfx('select')
        elif e.key == K_LEFT and self.selected == 0:
            self._cycle_diff(-1)
        elif e.key == K_RIGHT and self.selected == 0:
            self._cycle_diff(1)
        elif e.key in (K_RETURN, K_SPACE):
            if self.selected == 0:
                self._cycle_diff(1)
            elif self.selected == 1:
                sfx('select')
                self.switch_to(GameScene(self.difficulty),
                               FadeTransition(0.5, (0, 0, 0)))
            else:
                event.post(event.Event(QUIT))
        elif e.key == K_ESCAPE:
            event.post(event.Event(QUIT))

    def update(self, dt):
        super().update(dt)
        for s in self.stars:
            s[1] += s[2] * dt
            if s[1] > VIEW_H:
                s[1] = -5
                s[0] = random.uniform(0, VIEW_W)

    def draw(self, screen):
        screen.blit(self.bg_surf, (0, 0))
        for s in self.stars:
            draw.circle(screen, (60, 80, 120), (int(s[0]), int(s[1])), s[3])

        ty = int(self.title_y_t.value) if self.title_y_t else 140
        title = F_TITLE.render("PONG", True, PC)
        screen.blit(title, title.get_rect(center=(VIEW_W // 2, ty)))
        sub = F_MID.render("· PRO EDITION ·", True, AC)
        screen.blit(sub, sub.get_rect(center=(VIEW_W // 2, ty + 70)))

        base_y = 400
        items = [
            f"<  {self.difficulty.upper()}  >",
            "PLAY",
            "QUIT",
        ]
        for i, item in enumerate(items):
            c = ACCENT if i == self.selected else (140, 160, 190)
            prefix = "> " if i == self.selected else "  "
            t = F_MID.render(prefix + item, True, c)
            screen.blit(t, t.get_rect(center=(VIEW_W // 2, base_y + i * 55)))

        h1 = F_SMALL.render(
            "UP/DOWN — Navigate   ·   LEFT/RIGHT — Difficulty",
            True, (100, 120, 150))
        h2 = F_SMALL.render(
            "ENTER — Select   ·   ESC — Quit",
            True, (100, 120, 150))
        screen.blit(h1, h1.get_rect(center=(VIEW_W // 2, VIEW_H - 80)))
        screen.blit(h2, h2.get_rect(center=(VIEW_W // 2, VIEW_H - 55)))


# ============================================================================
# PauseScene
# ============================================================================
class PauseScene(Scene):
    def __init__(self):
        super().__init__()
        self.transparent = True
        self.alpha_t = None

    def on_enter(self):
        self.alpha_t = self.tween(0, 220, 0.25, 'ease_out_quad')

    def handle_event(self, e):
        if e.type == KEYDOWN:
            if e.key in (K_ESCAPE, K_p, K_SPACE):
                self.pop()
            elif e.key == K_q:
                self.manager.switch(MenuScene(), FadeTransition(0.4))

    def draw(self, screen):
        a = int(self.alpha_t.value) if self.alpha_t else 0
        ov = Surface((VIEW_W, VIEW_H), SRCALPHA)
        ov.fill((0, 0, 0, a))
        screen.blit(ov, (0, 0))
        if a > 120:
            title = F_BIG.render("PAUSED", True, FG)
            screen.blit(title, title.get_rect(
                center=(VIEW_W // 2, VIEW_H // 2 - 40)))
            h1 = F_MID.render("ESC / SPACE — Resume", True, (200, 200, 220))
            h2 = F_MID.render("Q — Quit to Menu", True, (200, 200, 220))
            screen.blit(h1, h1.get_rect(center=(VIEW_W // 2, VIEW_H // 2 + 45)))
            screen.blit(h2, h2.get_rect(center=(VIEW_W // 2, VIEW_H // 2 + 85)))


# ============================================================================
# MatchEndScene
# ============================================================================
class MatchEndScene(Scene):
    def __init__(self, player_won, ps, as_, difficulty='normal'):
        super().__init__()
        self.bg_color = BG
        self.player_won = player_won
        self.ps = ps
        self.as_ = as_
        self.difficulty = difficulty
        self.scale_t = None
        self.selected = 0
        self.items = ['PLAY AGAIN', 'MENU']

    def on_enter(self):
        self.scale_t = self.tween(0.3, 1.0, 0.6, 'ease_out_back')
        sfx('match')

    def handle_event(self, e):
        if e.type != KEYDOWN:
            return
        if e.key in (K_UP, K_w):
            self.selected = (self.selected - 1) % 2
            sfx('select')
        elif e.key in (K_DOWN, K_s):
            self.selected = (self.selected + 1) % 2
            sfx('select')
        elif e.key in (K_RETURN, K_SPACE):
            if self.items[self.selected] == 'PLAY AGAIN':
                self.switch_to(GameScene(self.difficulty),
                               FadeTransition(0.5))
            else:
                self.switch_to(MenuScene(), FadeTransition(0.5))
        elif e.key == K_ESCAPE:
            self.switch_to(MenuScene(), FadeTransition(0.5))

    def draw(self, screen):
        screen.fill(self.bg_color)

        s = max(0.1, self.scale_t.value) if self.scale_t else 1.0
        txt = "VICTORY!" if self.player_won else "DEFEAT"
        color = PC if self.player_won else AC
        title = F_HUGE.render(txt, True, color)
        w = max(1, int(title.get_width() * s))
        h = max(1, int(title.get_height() * s))
        scaled = transform.smoothscale(title, (w, h))
        screen.blit(scaled, scaled.get_rect(center=(VIEW_W // 2, 200)))

        score = F_BIG.render(f"{self.ps}   —   {self.as_}", True, FG)
        screen.blit(score, score.get_rect(center=(VIEW_W // 2, 340)))

        base_y = 480
        for i, item in enumerate(self.items):
            c = ACCENT if i == self.selected else (140, 140, 160)
            prefix = "> " if i == self.selected else "  "
            t = F_MID.render(prefix + item, True, c)
            screen.blit(t, t.get_rect(center=(VIEW_W // 2, base_y + i * 55)))


# ============================================================================
# GameScene
# ============================================================================
class GameScene(Scene):
    def __init__(self, difficulty='normal'):
        super().__init__()
        self.bg_color = BG
        self.difficulty = difficulty

        self.player = Paddle(PLAYER_X, VIEW_H // 2 - PADDLE_H // 2, PC)
        speeds = {'easy': 260, 'normal': 400, 'hard': 580}
        errors = {'easy': 80, 'normal': 40, 'hard': 15}
        self.ai = AIPaddle(AI_X, VIEW_H // 2 - PADDLE_H // 2, AC,
                            speeds[difficulty], errors[difficulty])

        self.ball = Ball(VIEW_W / 2, VIEW_H / 2)

        self.player_score = 0
        self.ai_score = 0
        self.player_flash = 0.0
        self.ai_flash = 0.0

        self.shake = 0.0
        self.shake_offset = (0.0, 0.0)

        self.particles = ParticleSystem(
            ParticleConfig(
                max_count=2000, sprite_radius=3,
                gravity=0, drag=2.5, bounce=False,
                lifespan_range=(0.25, 0.6), fade_out=True,
                use_gpu=False, use_lod=False,
            ),
            (VIEW_W, VIEW_H),
        )

        self.powerups = []
        self.powerup_timer = random.uniform(4, 6)

        self.popups = []

        self.serve_timer = 1.0
        self.serve_dir = random.choice([-1, 1])
        self.ball_frozen = True

        self.mouse_control = True
        self._internal = None

        self.hud_score_p = TextCache(F_HUGE, FG, (0, 0, 0), 0.0)
        self.hud_score_a = TextCache(F_HUGE, FG, (0, 0, 0), 0.0)
        self.hud_help = TextCache(F_SMALL, (130, 140, 170), None, 5.0)

        self.bg_surf = self._make_bg()

    def _make_bg(self):
        s = Surface((VIEW_W, VIEW_H))
        s.fill(BG)
        for x in range(0, VIEW_W, 40):
            draw.line(s, GRID, (x, 0), (x, VIEW_H))
        for y in range(0, VIEW_H, 40):
            draw.line(s, GRID, (0, y), (VIEW_W, y))
        draw.rect(s, (40, 55, 85), (0, 0, VIEW_W, WALL))
        draw.rect(s, (40, 55, 85), (0, VIEW_H - WALL, VIEW_W, WALL))
        for y in range(WALL, VIEW_H - WALL, 24):
            draw.rect(s, (45, 60, 95), (VIEW_W // 2 - 2, y, 4, 12))
        return s.convert()

    def on_enter(self):
        self._reset_serve(random.choice([-1, 1]), delay=1.2)

    def handle_event(self, e):
        if e.type == KEYDOWN:
            if e.key == K_ESCAPE:
                self.push(PauseScene())
            elif e.key == K_m:
                self.mouse_control = not self.mouse_control
        elif e.type == MOUSEMOTION and self.mouse_control:
            self.player.rect.centery = e.pos[1]
            if self.player.rect.top < WALL:
                self.player.rect.top = WALL
            if self.player.rect.bottom > VIEW_H - WALL:
                self.player.rect.bottom = VIEW_H - WALL

    def _reset_serve(self, direction, delay=1.0):
        self.ball.reset()
        self.serve_dir = direction
        self.serve_timer = delay
        self.ball_frozen = True

    def _start_serve(self):
        self.ball.serve(self.serve_dir)
        self.ball_frozen = False

    def _trigger_shake(self, amount):
        self.shake = min(1.0, self.shake + amount)

    def _burst(self, x, y, count=10, speed=(120, 320)):
        self.particles.spawn(count, center=(x, y), speed_range=speed)

    def _add_popup(self, text, x, y, color=FG):
        self.popups.append([text, x, y, 1.0, 1.0, color])

    def update(self, dt):
        super().update(dt)

        if self.shake > 0:
            self.shake = max(0.0, self.shake - dt * 4)
            amp = self.shake * 14
            self.shake_offset = (
                random.uniform(-amp, amp),
                random.uniform(-amp, amp),
            )
        else:
            self.shake_offset = (0.0, 0.0)

        # Player keyboard
        keys = key.get_pressed()
        vy = 0
        if keys[K_w] or keys[K_UP]:
            vy -= 1
        if keys[K_s] or keys[K_DOWN]:
            vy += 1
        if vy != 0:
            self.mouse_control = False
            self.player.vy = vy * 700
            self.player.rect.y += int(self.player.vy * dt)
            if self.player.rect.top < WALL:
                self.player.rect.top = WALL
            if self.player.rect.bottom > VIEW_H - WALL:
                self.player.rect.bottom = VIEW_H - WALL
        else:
            self.player.vy = 0

        self.player.update_buffs(dt)
        self.ai.update(dt, self.ball)

        if self.ball_frozen:
            self.serve_timer -= dt
            if self.serve_timer <= 0:
                self._start_serve()
        else:
            self.ball.update(dt)
            self._check_collisions()

        if self.player_flash > 0:
            self.player_flash = max(0.0, self.player_flash - dt * 3)
        if self.ai_flash > 0:
            self.ai_flash = max(0.0, self.ai_flash - dt * 3)

        # Power-ups
        self.powerup_timer -= dt
        if self.powerup_timer <= 0:
            self.powerup_timer = random.uniform(7, 12)
            px = random.uniform(120, VIEW_W - 120)
            kind = random.choice(['big', 'slow'])
            self.powerups.append(PowerUp(px, WALL + 40, kind))

        for pu in list(self.powerups):
            pu.update(dt)

            if (pu.x + pu.r > self.player.rect.left and
                    pu.x - pu.r < self.player.rect.right and
                    pu.y + pu.r > self.player.rect.top and
                    pu.y - pu.r < self.player.rect.bottom):
                self._apply_powerup(pu.kind, is_player=True)
                self.powerups.remove(pu)
                continue

            if (pu.x + pu.r > self.ai.rect.left and
                    pu.x - pu.r < self.ai.rect.right and
                    pu.y + pu.r > self.ai.rect.top and
                    pu.y - pu.r < self.ai.rect.bottom):
                self._apply_powerup(pu.kind, is_player=False)
                self.powerups.remove(pu)
                continue

            if pu.y - pu.r > VIEW_H - WALL:
                self.powerups.remove(pu)

        self.particles.update(dt)

        for p in list(self.popups):
            p[3] -= dt
            if p[3] <= 0:
                self.popups.remove(p)

    def _apply_powerup(self, kind, is_player):
        who = "P1" if is_player else "CPU"
        color = PC if is_player else AC
        if kind == 'big':
            target = self.player if is_player else self.ai
            target.set_size_factor(1.4, duration=6.0)
            self._add_popup(f"{who}: BIG!", VIEW_W // 2, 130, color)
        elif kind == 'slow':
            self.ball.slow_factor = 0.6
            self.ball.slow_timer = 4.0
            self._add_popup(f"{who}: SLOW!", VIEW_W // 2, 130, color)
        sfx('power')

    def _check_collisions(self):
        b = self.ball

        if b.y - b.r <= WALL:
            b.y = WALL + b.r
            b.vy = -b.vy
            sfx('wall')
            self._trigger_shake(0.15)
            self._burst(b.x, WALL, count=5, speed=(60, 180))
        elif b.y + b.r >= VIEW_H - WALL:
            b.y = VIEW_H - WALL - b.r
            b.vy = -b.vy
            sfx('wall')
            self._trigger_shake(0.15)
            self._burst(b.x, VIEW_H - WALL, count=5, speed=(60, 180))

        pr = self.player.rect
        if b.vx < 0 and (b.x - b.r) <= pr.right and (b.x + b.r) >= pr.left:
            if pr.top <= b.y <= pr.bottom:
                self._bounce_off_paddle(pr, is_player=True)

        ar = self.ai.rect
        if b.vx > 0 and (b.x + b.r) >= ar.left and (b.x - b.r) <= ar.right:
            if ar.top <= b.y <= ar.bottom:
                self._bounce_off_paddle(ar, is_player=False)

        if b.x - b.r <= 0:
            self._on_score(by_player=False)
        elif b.x + b.r >= VIEW_W:
            self._on_score(by_player=True)

    def _bounce_off_paddle(self, pr, is_player):
        b = self.ball
        rel = (b.y - pr.centery) / (pr.height / 2)
        rel = max(-1.0, min(1.0, rel))
        angle = rel * MAX_ANGLE

        new_speed = min(b.speed * BALL_SPEEDUP, BALL_SPEED_MAX)
        b.set_speed(new_speed)

        if is_player:
            b.vx = math.cos(angle) * new_speed
            b.vy = math.sin(angle) * new_speed + self.player.vy * 0.15
            b.x = pr.right + b.r + 2
            self._burst(b.x, b.y, count=12, speed=(150, 400))
        else:
            b.vx = -math.cos(angle) * new_speed
            b.vy = math.sin(angle) * new_speed + self.ai.vy * 0.15
            b.x = pr.left - b.r - 2
            self._burst(b.x, b.y, count=12, speed=(150, 400))

        sfx('paddle')
        self._trigger_shake(0.28)

    def _on_score(self, by_player):
        if by_player:
            self.player_score += 1
            self.player_flash = 1.0
            self._add_popup("+1", VIEW_W - 130, 100, PC)
        else:
            self.ai_score += 1
            self.ai_flash = 1.0
            self._add_popup("+1", 130, 100, AC)

        sfx('score')
        self._trigger_shake(0.55)
        self._burst(VIEW_W / 2, VIEW_H / 2, count=45, speed=(200, 500))

        if self.player_score >= WIN_SCORE:
            self.switch_to(
                MatchEndScene(True, self.player_score, self.ai_score,
                              self.difficulty),
                FadeTransition(0.6, (100, 200, 255)))
            return
        if self.ai_score >= WIN_SCORE:
            self.switch_to(
                MatchEndScene(False, self.player_score, self.ai_score,
                              self.difficulty),
                FadeTransition(0.6, (255, 100, 180)))
            return

        dir_ = -1 if by_player else 1
        self._reset_serve(dir_, delay=1.3)

    def draw(self, screen):
        if self._internal is None:
            self._internal = Surface((VIEW_W, VIEW_H))
        surf = self._internal

        surf.blit(self.bg_surf, (0, 0))

        # Power-ups
        for pu in self.powerups:
            pulse = 1.0 + 0.15 * math.sin(pu.t * 10)
            r = int(pu.r * pulse)
            glow = Surface((r * 4, r * 4), SRCALPHA)
            draw.circle(glow, (*pu.color, 70), (r * 2, r * 2), r + 8)
            surf.blit(glow, (int(pu.x) - r * 2, int(pu.y) - r * 2))
            draw.circle(surf, pu.color, (int(pu.x), int(pu.y)), r)
            draw.circle(surf, (255, 255, 255),
                        (int(pu.x) - r // 3, int(pu.y) - r // 3),
                        max(2, r // 3))

        # Trail
        trail = _trail_sprites()
        for i, (tx, ty) in enumerate(self.ball.trail):
            s_, r_ = trail[i] if i < len(trail) else trail[-1]
            surf.blit(s_, (int(tx) - r_, int(ty) - r_))

        # Ball
        bx, by = int(self.ball.x), int(self.ball.y)
        if self.ball_frozen:
            pulse = 1.0 + 0.3 * math.sin(self.serve_timer * 8)
            r = int(self.ball.r * pulse)
        else:
            r = self.ball.r
        glow_r = int(r * 3)
        glow = Surface((glow_r * 2, glow_r * 2), SRCALPHA)
        draw.circle(glow, (100, 200, 255, 70), (glow_r, glow_r), glow_r)
        surf.blit(glow, (bx - glow_r, by - glow_r))
        draw.circle(surf, BC, (bx, by), r)
        draw.circle(surf, (200, 230, 255),
                    (bx - r // 3, by - r // 3), max(2, r - 3))

        # Particles
        self.particles.draw(surf)

        # Paddles
        self._draw_paddle(surf, self.player)
        self._draw_paddle(surf, self.ai)

        # Popups
        for text, x, y, life, max_life, color in self.popups:
            t = 1.0 - life / max_life
            dy = int(50 * t)
            a = int(255 * (1 - t))
            s_ = F_BIG.render(text, True, color)
            s_.set_alpha(a)
            surf.blit(s_, s_.get_rect(center=(x, y - dy)))

        # HUD
        self._draw_hud(surf)

        # Blit with shake
        ox, oy = int(self.shake_offset[0]), int(self.shake_offset[1])
        screen.fill((0, 0, 0))
        screen.blit(surf, (ox, oy))

    def _draw_paddle(self, surf, pad):
        r = pad.rect
        pad_w = 8
        glow = Surface((r.width + pad_w * 2, r.height + pad_w * 2), SRCALPHA)
        draw.rect(glow, (*pad.color, 90),
                  (pad_w, pad_w, r.width, r.height), border_radius=10)
        surf.blit(glow, (r.x - pad_w, r.y - pad_w))
        draw.rect(surf, pad.color, r, border_radius=8)
        draw.rect(surf, (255, 255, 255, 180),
                  (r.x + 3, r.y + 3, r.width - 6, 4), border_radius=2)

    def _draw_hud(self, surf):
        # Player score
        s, _ = self.hud_score_p.render(str(self.player_score))
        if self.player_flash > 0:
            scale = 1.0 + self.player_flash * 0.5
            w = int(s.get_width() * scale)
            h = int(s.get_height() * scale)
            s2 = transform.smoothscale(s, (w, h))
            surf.blit(s2, s2.get_rect(center=(VIEW_W // 4, 90)))
        else:
            surf.blit(s, s.get_rect(center=(VIEW_W // 4, 90)))

        # AI score
        s, _ = self.hud_score_a.render(str(self.ai_score))
        if self.ai_flash > 0:
            scale = 1.0 + self.ai_flash * 0.5
            w = int(s.get_width() * scale)
            h = int(s.get_height() * scale)
            s2 = transform.smoothscale(s, (w, h))
            surf.blit(s2, s2.get_rect(center=(3 * VIEW_W // 4, 90)))
        else:
            surf.blit(s, s.get_rect(center=(3 * VIEW_W // 4, 90)))

        # Labels
        lbl_p = F_SMALL.render("PLAYER", True, PC)
        surf.blit(lbl_p, lbl_p.get_rect(center=(VIEW_W // 4, 155)))
        lbl_a = F_SMALL.render("CPU", True, AC)
        surf.blit(lbl_a, lbl_a.get_rect(center=(3 * VIEW_W // 4, 155)))

        # Match point
        if self.player_score == WIN_SCORE - 1 or self.ai_score == WIN_SCORE - 1:
            mp = F_MID.render("MATCH POINT", True, ACCENT)
            surf.blit(mp, mp.get_rect(center=(VIEW_W // 2, 60)))

        # Difficulty
        d = F_SMALL.render(f"DIFFICULTY: {self.difficulty.upper()}",
                            True, (140, 160, 200))
        surf.blit(d, d.get_rect(center=(VIEW_W // 2, VIEW_H - 32)))

        # Help
        h, _ = self.hud_help.render(
            "[W/S or Mouse] move  ·  [M] toggle mouse  ·  [ESC] pause")
        surf.blit(h, h.get_rect(center=(VIEW_W // 2, VIEW_H - 55)))

        # Active buffs
        y = 195
        if self.player.size_timer > 0:
            t = F_SMALL.render(f"BIG  {self.player.size_timer:.1f}s",
                                True, (100, 240, 130))
            surf.blit(t, t.get_rect(center=(VIEW_W // 4, y)))
            y += 22
        if self.ball.slow_timer > 0:
            t = F_SMALL.render(f"SLOW {self.ball.slow_timer:.1f}s",
                                True, (100, 180, 255))
            surf.blit(t, t.get_rect(center=(VIEW_W // 4, y)))


# ============================================================================
# Main
# ============================================================================
def main():
    screen = display.set_mode((VIEW_W, VIEW_H))
    sm = SceneManager(screen)
    sm.switch(MenuScene(), FadeTransition(0.6, (0, 0, 0)))

    running = True
    while running:
        dt = CLOCK.tick(FPS) / 1000.0
        if dt > 0.05:
            dt = 0.05

        for e in event.get():
            if e.type == QUIT:
                running = False
            else:
                sm.handle_event(e)

        sm.update(dt)
        sm.draw()
        display.flip()

    quit()


if __name__ == "__main__":
    main()