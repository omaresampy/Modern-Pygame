"""
snake.py - لعبة الثعبان الكلاسيكية.
بتستخدم modern_pygame فقط - مفيش `import pygame`.

    python snake.py

التحكم:
    Menu:  ENTER / SPACE للبدء
    Game:  WASD أو Arrows للحركة، P للـ pause، ESC للمنيو
    Pause: SPACE للاستئناف، ESC للمنيو
    Over:  SPACE للـ retry، ESC للمنيو
"""
# ─── كل الاستيرادات من modern_pygame (اللي بدوره بيصدّر pygame) ───
from modern_pygame_3 import (
    # Core
    init, quit, Clock,
    Surface, Scene, SceneManager, FadeTransition,
    ParticleSystem, ParticleConfig, TextCache,
    # Submodules
    display, event, key, draw, font, transform,
    # Constants
    QUIT, KEYDOWN, K_ESCAPE, K_SPACE, K_RETURN,
    K_w, K_a, K_s, K_d, K_p,
    K_UP, K_DOWN, K_LEFT, K_RIGHT,
    SRCALPHA,
)

import math
import random


# ============================================================================
# Config
# ============================================================================
CELL = 32
GRID_W = 30
GRID_H = 20
VIEW_W = GRID_W * CELL   # 960
VIEW_H = GRID_H * CELL   # 640
FPS = 60

STEP_START = 0.15
STEP_MIN = 0.055
STEP_ACCEL = 0.0022
SCORE_PER_FOOD = 10

BEST = 0


# ============================================================================
# Init + Screen (قبل أي convert_alpha)
# ============================================================================
init()
SCREEN = display.set_mode((VIEW_W, VIEW_H))
display.set_caption("Snake - Modern Pygame")
_CLOCK = Clock()

F_TITLE = font.SysFont("Consolas", 80, bold=True)
F_HUGE = font.SysFont("Consolas", 96, bold=True)
F_MENU = font.SysFont("Consolas", 28, bold=True)
F_MID = font.SysFont("Consolas", 22, bold=True)
F_SMALL = font.SysFont("Consolas", 16, bold=True)


# ============================================================================
# Snake (منطق اللعبة)
# ============================================================================
class Snake:
    __slots__ = ('body', 'direction', 'grow_pending', 'input_queue', 'alive')

    def __init__(self, gx, gy):
        self.body = [(gx, gy), (gx - 1, gy), (gx - 2, gy)]
        self.direction = (1, 0)
        self.grow_pending = 0
        self.input_queue = []
        self.alive = True

    def queue_dir(self, d):
        last = self.input_queue[-1] if self.input_queue else self.direction
        if d == last:
            return
        if (d[0] + last[0], d[1] + last[1]) == (0, 0):
            return
        if len(self.input_queue) < 2:
            self.input_queue.append(d)

    def step(self):
        if not self.alive:
            return None
        if self.input_queue:
            self.direction = self.input_queue.pop(0)

        hx, hy = self.body[0]
        nx = hx + self.direction[0]
        ny = hy + self.direction[1]

        if nx < 0 or nx >= GRID_W or ny < 0 or ny >= GRID_H:
            self.alive = False
            return 'wall'

        check = self.body if self.grow_pending > 0 else self.body[:-1]
        if (nx, ny) in check:
            self.alive = False
            return 'self'

        self.body.insert(0, (nx, ny))
        if self.grow_pending > 0:
            self.grow_pending -= 1
        else:
            self.body.pop()
        return None

    def eat(self):
        self.grow_pending += 1


# ============================================================================
# MenuScene
# ============================================================================
class MenuScene(Scene):
    def __init__(self):
        super().__init__()
        self.bg_color = (10, 14, 20)
        self.stars = [
            [random.uniform(0, VIEW_W), random.uniform(0, VIEW_H),
             random.randint(1, 2), random.uniform(15, 50)]
            for _ in range(120)
        ]
        self.deco_snake = [[VIEW_W // 2 - i * CELL, VIEW_H // 2 + 180]
                           for i in range(14)]
        self.title_y_t = None
        self.title_scale_t = None

    def on_enter(self):
        self.title_y_t = self.tween(-120, 180, 0.9, 'ease_out_back')
        self.title_scale_t = self.tween(0.5, 1.0, 0.7, 'ease_out_elastic',
                                         delay=0.2)

    def handle_event(self, e):
        if e.type != KEYDOWN:
            return
        if e.key in (K_RETURN, K_SPACE):
            self.switch_to(GameScene(), FadeTransition(0.45, (0, 0, 0)))
        elif e.key == K_ESCAPE:
            event.post(event.Event(QUIT))

    def update(self, dt):
        super().update(dt)
        for s in self.stars:
            s[1] += s[3] * dt
            if s[1] > VIEW_H:
                s[1] = -5
                s[0] = random.uniform(0, VIEW_W)
        for seg in self.deco_snake:
            seg[0] += 60 * dt
            if seg[0] > VIEW_W + CELL:
                seg[0] = -CELL

    def draw(self, screen):
        screen.fill(self.bg_color)
        for s in self.stars:
            draw.circle(screen, (70, 90, 120), (int(s[0]), int(s[1])), s[2])

        for i, seg in enumerate(self.deco_snake):
            t = i / max(1, len(self.deco_snake) - 1)
            r = int(50 + 60 * (1 - t))
            g = int(200 - 60 * t)
            b = int(80 + 60 * (1 - t))
            x, y = int(seg[0]), int(seg[1])
            draw.rect(screen, (r, g, b),
                      (x + 3, y + 3, CELL - 6, CELL - 6),
                      border_radius=8)

        y = int(self.title_y_t.value) if self.title_y_t else 180
        s = max(0.1, self.title_scale_t.value) if self.title_scale_t else 1.0
        title = F_HUGE.render("SNAKE", True, (120, 240, 150))
        w = max(1, int(title.get_width() * s))
        h = max(1, int(title.get_height() * s))
        scaled = transform.smoothscale(title, (w, h))
        screen.blit(scaled, scaled.get_rect(center=(VIEW_W // 2, y)))

        sub = F_MID.render("Modern Pygame · Scene System", True, (150, 170, 200))
        screen.blit(sub, sub.get_rect(center=(VIEW_W // 2, y + 80)))

        if BEST > 0:
            best_txt = F_MID.render(f"Best: {BEST}", True, (255, 220, 100))
            screen.blit(best_txt, best_txt.get_rect(
                center=(VIEW_W // 2, y + 130)))

        pulse = 0.7 + 0.3 * math.sin(_CLOCK.get_time() / 300)
        c = int(255 * pulse)
        start = F_MENU.render("Press ENTER to Start", True, (c, 255, c))
        screen.blit(start, start.get_rect(center=(VIEW_W // 2, VIEW_H - 130)))

        tip = F_SMALL.render("[WASD/Arrows] move  ·  [P] pause  ·  [ESC] menu",
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

    def handle_event(self, e):
        if e.type != KEYDOWN:
            return
        if e.key in (K_SPACE, K_p):
            self.pop()
        elif e.key == K_ESCAPE:
            self.manager.switch(MenuScene(), FadeTransition(0.4))

    def draw(self, screen):
        a = int(self.alpha_t.value) if self.alpha_t else 0
        ov = Surface((VIEW_W, VIEW_H), SRCALPHA)
        ov.fill((0, 0, 0, a))
        screen.blit(ov, (0, 0))
        if a > 100:
            title = F_TITLE.render("PAUSED", True, (255, 220, 100))
            screen.blit(title, title.get_rect(
                center=(VIEW_W // 2, VIEW_H // 2 - 30)))
            sub = F_MID.render("SPACE to resume  ·  ESC for menu",
                               True, (220, 220, 220))
            screen.blit(sub, sub.get_rect(
                center=(VIEW_W // 2, VIEW_H // 2 + 50)))


# ============================================================================
# GameOverScene
# ============================================================================
class GameOverScene(Scene):
    def __init__(self, score, length, is_best):
        super().__init__()
        self.bg_color = (28, 8, 12)
        self.score = score
        self.length = length
        self.is_best = is_best
        self.scale_t = None
        self.selected = 0
        self.items = ['RETRY', 'MENU']

    def on_enter(self):
        self.scale_t = self.tween(0.3, 1.0, 0.55, 'ease_out_back')

    def handle_event(self, e):
        if e.type != KEYDOWN:
            return
        if e.key in (K_UP, K_w):
            self.selected = (self.selected - 1) % len(self.items)
        elif e.key in (K_DOWN, K_s):
            self.selected = (self.selected + 1) % len(self.items)
        elif e.key in (K_RETURN, K_SPACE):
            if self.items[self.selected] == 'RETRY':
                self.switch_to(GameScene(), FadeTransition(0.4, (150, 0, 0)))
            else:
                self.switch_to(MenuScene(), FadeTransition(0.4))
        elif e.key == K_ESCAPE:
            self.switch_to(MenuScene(), FadeTransition(0.4))

    def draw(self, screen):
        screen.fill(self.bg_color)
        s = max(0.1, self.scale_t.value) if self.scale_t else 1.0
        title = F_HUGE.render("GAME OVER", True, (255, 80, 80))
        w = max(1, int(title.get_width() * s))
        h = max(1, int(title.get_height() * s))
        scaled = transform.smoothscale(title, (w, h))
        screen.blit(scaled, scaled.get_rect(center=(VIEW_W // 2, 170)))
        if self.is_best:
            badge = F_MENU.render("★ NEW BEST ★", True, (255, 220, 100))
            screen.blit(badge, badge.get_rect(center=(VIEW_W // 2, 270)))
        y = 350
        for text, color in [
            (f"Score: {self.score}", (255, 255, 100)),
            (f"Length: {self.length}", (150, 220, 255)),
            (f"Best: {BEST}", (200, 200, 220)),
        ]:
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
# GameScene
# ============================================================================
class GameScene(Scene):
    def __init__(self):
        super().__init__()
        self.bg_color = (10, 14, 20)
        self.snake = Snake(GRID_W // 2, GRID_H // 2)
        self.food = self._spawn_food()
        self.score = 0
        self.length = 3
        self.speed = STEP_START
        self.step_timer = 0.0
        self.time_played = 0.0
        self.death_flash = 0.0
        self.popups = []

        self.particles = ParticleSystem(
            ParticleConfig(
                max_count=6000, sprite_radius=4,
                gravity=250.0, drag=2.0, bounce=False,
                lifespan_range=(0.35, 0.75), fade_out=True,
                use_gpu=False, use_lod=False,
            ),
            (VIEW_W, VIEW_H),
        )

        self._last_dt = 0.0
        self.hud_score = TextCache(F_MID, (255, 255, 100),
                                    shadow_color=(0, 0, 0),
                                    update_interval=0.1)
        self.hud_best = TextCache(F_MID, (200, 220, 255),
                                   shadow_color=(0, 0, 0),
                                   update_interval=0.3)
        self.hud_speed = TextCache(F_SMALL, (180, 200, 220),
                                    update_interval=0.2)
        self.hud_help = TextCache(F_SMALL, (110, 110, 130),
                                   update_interval=10.0)
        self.grid_surf = self._make_grid()

    def _make_grid(self):
        gs = Surface((VIEW_W, VIEW_H))
        gs.fill(self.bg_color)
        for x in range(0, VIEW_W, CELL):
            draw.line(gs, (16, 22, 32), (x, 0), (x, VIEW_H))
        for y in range(0, VIEW_H, CELL):
            draw.line(gs, (16, 22, 32), (0, y), (VIEW_W, y))
        for x in range(0, VIEW_W, CELL * 2):
            for y in range(0, VIEW_H, CELL * 2):
                draw.circle(gs, (22, 30, 42), (x, y), 1)
        draw.rect(gs, (60, 80, 100), (0, 0, VIEW_W, VIEW_H), 3)
        return gs.convert()

    def _spawn_food(self):
        occupied = set(self.snake.body)
        free = [(x, y) for y in range(GRID_H) for x in range(GRID_W)
                if (x, y) not in occupied]
        return random.choice(free) if free else None

    def handle_event(self, e):
        if e.type != KEYDOWN:
            return
        if e.key in (K_ESCAPE, K_p):
            self.push(PauseOverlay())
            return
        d = None
        if e.key in (K_UP, K_w):
            d = (0, -1)
        elif e.key in (K_DOWN, K_s):
            d = (0, 1)
        elif e.key in (K_LEFT, K_a):
            d = (-1, 0)
        elif e.key in (K_RIGHT, K_d):
            d = (1, 0)
        if d:
            self.snake.queue_dir(d)

    def update(self, dt):
        super().update(dt)
        self._last_dt = dt
        self.time_played += dt

        self.step_timer += dt
        if self.step_timer >= self.speed:
            self.step_timer -= self.speed
            self._step()

        for p in self.popups[:]:
            p[3] -= dt
            if p[3] <= 0:
                self.popups.remove(p)

        self.particles.update(dt)
        if self.death_flash > 0:
            self.death_flash -= dt

    def _step(self):
        result = self.snake.step()
        if result in ('wall', 'self'):
            self._on_death()
            return
        if self.snake.body[0] == self.food:
            self._on_eat()

    def _on_eat(self):
        global BEST
        self.score += SCORE_PER_FOOD
        self.snake.eat()
        self.length = len(self.snake.body)
        self.speed = max(STEP_MIN, self.speed - STEP_ACCEL)
        self.food = self._spawn_food()

        hx, hy = self.snake.body[0]
        cx = hx * CELL + CELL // 2
        cy = hy * CELL + CELL // 2
        self.particles.spawn(18, center=(cx, cy), speed_range=(120, 300))
        self.popups.append([hx, hy, f"+{SCORE_PER_FOOD}", 0.9, 0.9])

        if self.score > BEST:
            BEST = self.score

    def _on_death(self):
        self.death_flash = 0.6
        for gx, gy in self.snake.body[:30]:
            self.particles.spawn(3,
                                 center=(gx * CELL + CELL // 2,
                                         gy * CELL + CELL // 2),
                                 speed_range=(60, 200))
        is_best = self.score >= BEST and self.score > 0
        self.switch_to(
            GameOverScene(self.score, self.length, is_best),
            FadeTransition(0.5, (100, 0, 0)))

    def draw(self, screen):
        screen.blit(self.grid_surf, (0, 0))

        if self.food is not None:
            fx, fy = self.food
            cx = fx * CELL + CELL // 2
            cy = fy * CELL + CELL // 2
            pulse = 1.0 + 0.15 * math.sin(self.time_played * 7)
            r = int((CELL // 2 - 4) * pulse)
            glow = Surface((CELL * 2, CELL * 2), SRCALPHA)
            draw.circle(glow, (255, 80, 80, 60), (CELL, CELL), r + 8)
            screen.blit(glow, (cx - CELL, cy - CELL))
            draw.circle(screen, (200, 40, 40), (cx, cy), r)
            draw.circle(screen, (255, 80, 80), (cx - 3, cy - 3), max(1, r - 4))
            draw.circle(screen, (255, 180, 180), (cx - 5, cy - 5), max(1, r - 8))
            draw.rect(screen, (90, 60, 30), (cx - 2, cy - r - 4, 4, 6))

        self._draw_snake(screen)
        self.particles.draw(screen)

        for gx, gy, text, life, max_life in self.popups:
            t = 1.0 - life / max_life
            cx = gx * CELL + CELL // 2
            cy = gy * CELL + CELL // 2 - int(40 * t)
            alpha = int(255 * (1 - t))
            surf = F_MID.render(text, True, (255, 255, 120))
            surf.set_alpha(alpha)
            screen.blit(surf, surf.get_rect(center=(cx, cy)))

        dt = self._last_dt
        surf, sh = self.hud_score.render(f"SCORE: {self.score}", dt)
        if sh:
            screen.blit(sh, (20, 18))
        screen.blit(surf, (18, 16))

        surf, _ = self.hud_best.render(f"BEST: {BEST}", dt)
        screen.blit(surf, (VIEW_W - surf.get_width() - 18, 16))

        sp = STEP_START / self.speed
        surf, _ = self.hud_speed.render(f"SPEED: x{sp:.2f}", dt)
        screen.blit(surf, (VIEW_W - surf.get_width() - 18, 44))

        surf, _ = self.hud_help.render(
            f"[WASD] move   [P] pause   [ESC] menu   Length: {self.length}",
            dt)
        screen.blit(surf, (18, VIEW_H - 26))

        if self.death_flash > 0:
            a = int(180 * self.death_flash / 0.6)
            flash = Surface((VIEW_W, VIEW_H), SRCALPHA)
            flash.fill((255, 40, 40, a))
            screen.blit(flash, (0, 0))

    def _draw_snake(self, screen):
        body = self.snake.body
        n = len(body)
        for i in range(n - 1, -1, -1):
            gx, gy = body[i]
            t = i / max(1, n - 1)
            r = int(90 + 120 * (1 - t))
            g = int(230 - 80 * t)
            b = int(120 + 80 * (1 - t))
            x = gx * CELL
            y = gy * CELL
            margin = 2 if i == 0 else 3
            draw.rect(screen, (r, g, b),
                      (x + margin, y + margin,
                       CELL - margin * 2, CELL - margin * 2),
                      border_radius=9)
            if i != 0:
                draw.rect(screen,
                          (min(255, r + 50), min(255, g + 10), min(255, b + 50)),
                          (x + margin + 3, y + margin + 3,
                           CELL - margin * 2 - 6, 4),
                          border_radius=2)

        if n > 0:
            hx, hy = body[0]
            dx, dy = self.snake.direction
            cx = hx * CELL + CELL // 2
            cy = hy * CELL + CELL // 2
            if dx != 0:
                e1 = (cx + dx * 6, cy - 6)
                e2 = (cx + dx * 6, cy + 6)
            else:
                e1 = (cx - 6, cy + dy * 6)
                e2 = (cx + 6, cy + dy * 6)
            draw.circle(screen, (255, 255, 255), e1, 4)
            draw.circle(screen, (255, 255, 255), e2, 4)
            draw.circle(screen, (20, 20, 40), e1, 2)
            draw.circle(screen, (20, 20, 40), e2, 2)


# ============================================================================
# Main
# ============================================================================
def main():
    sm = SceneManager(SCREEN)
    sm.switch(MenuScene(), FadeTransition(0.5, (0, 0, 0)))

    running = True
    while running:
        dt = _CLOCK.tick(FPS) / 1000.0
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