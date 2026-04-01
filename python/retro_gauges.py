#!/usr/bin/env python3

from __future__ import annotations

import math

import pygame

from python.shared_data import LatestValuesTable
from python.new_gauges import Gauge, render_text

RETRO_BLACK = (6, 5, 5)
RETRO_PANEL = (14, 10, 10)
RETRO_INSET = (9, 8, 8)
RETRO_ORANGE = (245, 126, 58)
RETRO_ORANGE_DIM = (190, 96, 46)
RETRO_AMBER = (247, 193, 76)
RETRO_YELLOW = (240, 202, 73)
RETRO_GOLD = (180, 155, 48)
RETRO_GREEN = (95, 156, 95)
RETRO_GRID = (112, 201, 108)
RETRO_BLUE = (19, 36, 188)
RETRO_CYAN = (97, 221, 235)
RETRO_WHITE = (235, 229, 221)
RETRO_GRAY = (88, 100, 118)
RETRO_DARK_GRAY = (65, 70, 82)
RETRO_WARNING = (246, 213, 84)


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * _clamp01(t)


def _lerp_color(c1, c2, t):
    return tuple(int(_lerp(c1[i], c2[i], t)) for i in range(3))


class RetroHeroDash(Gauge):
    """Full-page retro dashboard inspired by late-90s Japanese UI clusters."""

    def __init__(self, box_xywh, shared_data: LatestValuesTable):
        x, y, w, h = box_xywh
        super().__init__("", "", 0, 1, shared_data)
        self.x, self.y, self.w, self.h = x, y, w, h

    def update(self, surf: pygame.Surface):
        x, y, w, h = self.x, self.y, self.w, self.h

        self._draw_background(surf, x, y, w, h)
        self._draw_outer_frame(surf, x, y, w, h)
        self._draw_main_panel(surf, x + 118, y + 70, 600, 286)
        self._draw_left_stack(surf, x + 18, y + 24, 142, 360)
        self._draw_bottom_banner(surf, x, y + h - 62, w, 62)

    def _sig(self, name: str, default: float = 0.0) -> float:
        value = self.shared_data.get_signal(name)
        if value is None:
            return default
        return float(value)

    def _draw_background(self, surf, x, y, w, h):
        left_col = (236, 107, 53)
        mid_col = (221, 178, 73)
        right_col = (83, 100, 123)
        for ix in range(w):
            t = ix / max(1, w - 1)
            if t < 0.58:
                col = _lerp_color(left_col, mid_col, t / 0.58)
            else:
                col = _lerp_color(mid_col, right_col, (t - 0.58) / 0.42)
            pygame.draw.line(surf, col, (x + ix, y), (x + ix, y + h))

        lower_poly = [
            (x, y + h - 92),
            (x + 165, y + h - 92),
            (x + 215, y + 136),
            (x + 440, y + 136),
            (x + 468, y + h - 92),
            (x + w, y + h - 92),
            (x + w, y + h),
            (x, y + h),
        ]
        pygame.draw.polygon(surf, (84, 142, 84), lower_poly)

        for gy in range(y + 8, y + h - 8, 42):
            pygame.draw.line(surf, RETRO_GRID, (x, gy), (x + 8, gy), 2)
        for gx in range(x + 58, x + w - 24, 96):
            pygame.draw.line(surf, RETRO_GRID, (gx, y + 8), (gx, y + 16), 2)
            pygame.draw.line(surf, RETRO_GRID, (gx + 12, y + 8), (gx + 12, y + 16), 2)

    def _draw_outer_frame(self, surf, x, y, w, h):
        pygame.draw.rect(surf, RETRO_BLACK, (x + 8, y + 8, w - 16, h - 16), 3)
        pygame.draw.rect(surf, RETRO_WHITE, (x + 11, y + 11, w - 22, h - 22), 1)

    def _draw_left_stack(self, surf, x, y, w, h):
        pygame.draw.polygon(surf, RETRO_BLACK, [
            (x + 58, y + 34),
            (x + w - 8, y + 34),
            (x + w - 8, y + 88),
            (x + w - 42, y + 88),
            (x + w - 42, y + 154),
            (x + w - 16, y + 154),
            (x + w - 16, y + 300),
            (x + 84, y + h),
            (x + 34, y + h - 20),
            (x + 72, y + 212),
            (x + 54, y + 206),
            (x + 54, y + 112),
            (x + 72, y + 102),
            (x + 72, y + 34),
        ])

        pygame.draw.rect(surf, RETRO_CYAN, (x + 10, y + 10, 96, 76), 3, border_radius=4)

        light_box = pygame.Rect(x + 96, y + 138, 54, 166)
        surf.fill(RETRO_INSET, light_box)
        pygame.draw.rect(surf, RETRO_GREEN, light_box, 1)

        statuses = [
            ("READY", (90, 240, 70), True),
            ("INV", (30, 45, 255), True),
            ("BSPD", (90, 240, 70), self._sig("BSPDFault", 0) < 1),
            ("IMD", (40, 40, 40), self._sig("IMDFault", 0) < 1),
            ("ABS", (40, 40, 40), True),
            ("WARN", (240, 238, 80), self._sig("PackTemp", 0) < 48),
        ]
        yy = light_box.y + 18
        for label, color, bright in statuses:
            glow = color if bright else tuple(int(c * 0.3) for c in color)
            self._draw_hex_light(surf, light_box.x + 16, yy, 14, glow, label)
            yy += 28

        pygame.draw.line(surf, RETRO_BLACK, (x + 48, y + 318), (x + 88, y + 332), 6)
        pygame.draw.line(surf, RETRO_WHITE, (x + 46, y + 317), (x + 86, y + 331), 1)

    def _draw_hex_light(self, surf, cx, cy, r, color, label):
        pts = []
        for i in range(6):
            a = math.radians(60 * i + 30)
            pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
        pygame.draw.polygon(surf, tuple(max(10, int(c * 0.2)) for c in color), pts)
        pygame.draw.polygon(surf, color, pts, 2)
        pygame.draw.polygon(surf, tuple(min(255, int(c * 0.55 + 80)) for c in color), pts, 1)
        render_text(surf, label, 6, RETRO_BLACK if sum(color) > 300 else RETRO_WHITE, cx, cy)

    def _draw_main_panel(self, surf, x, y, w, h):
        pygame.draw.polygon(surf, RETRO_BLACK, [
            (x, y),
            (x + 82, y),
            (x + 92, y + 24),
            (x + w, y + 24),
            (x + w, y + h),
            (x, y + h),
        ])
        pygame.draw.polygon(surf, RETRO_ORANGE_DIM, [
            (x + 2, y + 2),
            (x + 80, y + 2),
            (x + 88, y + 20),
            (x + w - 2, y + 20),
        ], 2)
        pygame.draw.line(surf, RETRO_ORANGE_DIM, (x + w - 2, y + 20), (x + w - 2, y + h - 2), 2)
        pygame.draw.line(surf, RETRO_ORANGE_DIM, (x + w - 2, y + h - 2), (x + 2, y + h - 2), 2)
        pygame.draw.line(surf, RETRO_ORANGE_DIM, (x + 2, y + h - 2), (x + 2, y + 2), 2)

        self._draw_speed_scale(surf, x + 26, y + 38, 348, 86)
        self._draw_speed_block(surf, x + 30, y + 154, 320, 88)
        self._draw_center_readout(surf, x + 336, y + 148, 140, 100)
        self._draw_right_panels(surf, x + 404, y + 36, 176, 202)
        self._draw_mode_row(surf, x + 42, y + 246, 394, 44)
        self._draw_pressure_box(surf, x + 452, y + 246, 128, 60)

    def _draw_speed_scale(self, surf, x, y, w, h):
        speed = self._sig("Speed", 0)
        max_speed = 75.0
        segs = 45
        active = int(_clamp01(speed / max_speed) * segs)
        seg_w = max(3, (w - 14) // segs)
        for i in range(segs):
            sx = x + i * seg_w
            col = RETRO_BLUE if i < active else (12, 14, 18)
            pygame.draw.rect(surf, col, (sx, y, seg_w - 2, h))
        for marker, label in [(0.0, "0"), (0.2, "15"), (0.4, "30"), (0.6, "45"), (0.8, "60"), (1.0, "75")]:
            mx = int(x + marker * w)
            pygame.draw.line(surf, RETRO_ORANGE, (mx, y + h + 8), (mx, y + h + 24), 3)
            render_text(surf, label, 11, RETRO_ORANGE, mx, y + h + 38)
        for t in [0.72, 0.92]:
            mx = int(x + t * w)
            pygame.draw.line(surf, RETRO_GREEN, (mx, y + h + 42), (mx, y + h + 48), 2)
        for ix in range(0, 11):
            px = x + int(ix * w / 10)
            pygame.draw.line(surf, RETRO_WHITE, (px, y - 14), (px, y - 2), 2)
        render_text(surf, "SPEED SCALE", 12, RETRO_ORANGE, x - 4, y - 42, anchor="midleft", bold=True)
        render_text(surf, "CAUTION", 10, RETRO_ORANGE, x + int(w * 0.76), y + h + 16)
        render_text(surf, "LIMIT", 10, RETRO_ORANGE, x + int(w * 0.93), y + h + 16)

    def _draw_speed_block(self, surf, x, y, w, h):
        render_text(surf, "SPEED", 40, RETRO_ORANGE, x + 10, y + 24, anchor="midleft", bold=True)
        render_text(surf, "(MPH)", 18, RETRO_ORANGE, x + 12, y + 62, anchor="midleft")
        render_text(surf, "TERPS EV", 11, RETRO_ORANGE_DIM, x + 12, y - 8, anchor="midleft")

        caution_box = pygame.Rect(x + 190, y + 10, 104, 68)
        glow = pygame.Surface((caution_box.w, caution_box.h), pygame.SRCALPHA)
        pygame.draw.rect(glow, (255, 145, 74, 50), (0, 0, caution_box.w, caution_box.h), border_radius=8)
        surf.blit(glow, caution_box.topleft)
        pygame.draw.rect(surf, RETRO_ORANGE, caution_box, 2, border_radius=8)
        brake_on = self._sig("BrakePressure", 0) > 5
        caution_text = "CAUTION" if self._sig("PackTemp", 0) < 45 else "HOT BATTERY"
        sub_text = "HAND BRAKE\nENGAGED" if brake_on else "SYSTEM READY"
        render_text(surf, caution_text, 12, RETRO_ORANGE, caution_box.centerx, caution_box.y + 16, bold=True)
        for idx, line in enumerate(sub_text.split("\n")):
            render_text(surf, line, 10, RETRO_ORANGE, caution_box.centerx, caution_box.y + 36 + idx * 16, bold=True)

    def _draw_center_readout(self, surf, x, y, w, h):
        speed = self._sig("Speed", 0)
        shell = pygame.Rect(x, y, w, h)
        glow = pygame.Surface((w + 24, h + 24), pygame.SRCALPHA)
        pygame.draw.rect(glow, (255, 135, 55, 28), (12, 12, w, h), border_radius=18)
        surf.blit(glow, (x - 12, y - 12))
        pygame.draw.rect(surf, (53, 27, 15), shell, border_radius=18)
        pygame.draw.rect(surf, RETRO_ORANGE, shell, 3, border_radius=18)
        render_text(surf, f"{min(75, int(speed)):02d}", 74, RETRO_ORANGE, x + w // 2 + 10, y + h // 2 + 4, bold=True)

    def _draw_right_panels(self, surf, x, y, w, h):
        title = pygame.Rect(x, y, w, 94)
        pygame.draw.rect(surf, RETRO_INSET, title)
        pygame.draw.rect(surf, RETRO_ORANGE, title, 2)
        stripe = pygame.Rect(x + w - 34, y + 8, 22, 78)
        for i in range(4):
            stripe_y = stripe.y + i * 20
            pygame.draw.polygon(surf, (255, 201, 188), [
                (stripe.x, stripe_y),
                (stripe.x + stripe.w, stripe_y),
                (stripe.x + stripe.w, stripe_y + 10),
                (stripe.x, stripe_y + 20),
            ])
        render_text(surf, "TREV-EV", 22, RETRO_ORANGE, x + 10, y + 22, anchor="midleft", bold=True)
        render_text(surf, "ELECTRIC", 19, RETRO_ORANGE, x + 10, y + 48, anchor="midleft", bold=True)
        render_text(surf, "TELEMETRY", 15, RETRO_ORANGE, x + 10, y + 72, anchor="midleft")

        sub = pygame.Rect(x, y + 100, w, 42)
        pygame.draw.rect(surf, RETRO_INSET, sub)
        pygame.draw.rect(surf, RETRO_ORANGE, sub, 2)
        render_text(surf, "BATTERY EV SYSTEM", 11, RETRO_ORANGE, sub.centerx, sub.centery)

        stats = pygame.Rect(x, y + 148, w, 76)
        pygame.draw.rect(surf, RETRO_INSET, stats)
        pygame.draw.rect(surf, RETRO_ORANGE, stats, 2)

        pack_temp = self._sig("PackTemp", 0)
        inverter_temp = self._sig("InverterTemp", 0)
        render_text(surf, "PACK TEMP", 13, RETRO_ORANGE, stats.x + 10, stats.y + 18, anchor="midleft", bold=True)
        render_text(surf, f"{pack_temp:02.0f}", 24, RETRO_ORANGE, stats.right - 10, stats.y + 18, anchor="midright")
        render_text(surf, "INV TEMP", 13, RETRO_ORANGE, stats.x + 10, stats.y + 48, anchor="midleft", bold=True)
        render_text(surf, f"{inverter_temp:02.0f}", 24, RETRO_ORANGE, stats.right - 10, stats.y + 48, anchor="midright")

    def _draw_mode_row(self, surf, x, y, w, h):
        labels = ["STOP", "SLOW", "NORMAL", "ATTACK"]
        speed = self._sig("Speed", 0)
        active = 0 if speed < 1 else 1 if speed < 20 else 2 if speed < 55 else 3
        bw = 70
        gap = 12
        for idx, label in enumerate(labels):
            bx = x + idx * (bw + gap)
            outer = pygame.Rect(bx, y, bw, h)
            inner = pygame.Rect(bx + 4, y + 24, bw - 8, h - 28)
            pygame.draw.rect(surf, RETRO_BLACK, outer)
            pygame.draw.rect(surf, RETRO_ORANGE, outer, 2)
            pygame.draw.rect(surf, RETRO_DARK_GRAY if idx != active else RETRO_ORANGE_DIM, inner)
            render_text(surf, label, 14, RETRO_ORANGE, outer.centerx, y + 12)

    def _draw_pressure_box(self, surf, x, y, w, h):
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(surf, RETRO_INSET, rect)
        pygame.draw.rect(surf, RETRO_ORANGE, rect, 2)
        brake = self._sig("BrakePressure", 0)
        render_text(surf, "BRAKE PRESSURE", 11, RETRO_ORANGE, x + 8, y + 12, anchor="midleft", bold=True)
        render_text(surf, "kg/cm^2", 10, RETRO_ORANGE, x + 8, y + h - 14, anchor="midleft")
        render_text(surf, f"{max(0.0, brake / 25.0):.0f}", 36, RETRO_ORANGE, x + w - 8, y + h - 16, anchor="midright")

    def _draw_bottom_banner(self, surf, x, y, w, h):
        pygame.draw.rect(surf, (180, 159, 51), (x, y, w, h))
        speed = self._sig("Speed", 0)
        pack_temp = self._sig("PackTemp", 0)
        motor_temp = self._sig("MotorTemp", 0)
        apps = self._sig("APPS", 0)
        if pack_temp > 45:
            banner = "WARNING BATTERY TEMP!"
        elif motor_temp > 80:
            banner = "WARNING MOTOR TEMP!"
        elif apps > 50 and speed < 5:
            banner = "CHECK TRACTION RESPONSE!"
        else:
            banner = "SYSTEM NOMINAL"
        render_text(surf, banner, 28, (68, 59, 16), x + w // 2 - 18, y + h // 2 + 4, bold=True)

        for i in range(8):
            sx = x + 352 + i * 26
            pygame.draw.line(surf, RETRO_WARNING, (sx, y + 6), (sx + 18, y + h - 6), 8)

        mileage = int(self._sig("StateOfCharge", 80) * 56 + speed * 24)
        odobox = pygame.Rect(x + w - 176, y + 10, 146, h - 20)
        pygame.draw.rect(surf, (190, 158, 61), odobox, border_radius=4)
        pygame.draw.rect(surf, RETRO_WARNING, odobox, 2, border_radius=4)
        render_text(surf, "MILEAGE", 12, RETRO_WARNING, odobox.centerx, odobox.y + odobox.h - 12)
        render_text(surf, f"{mileage:06d}", 28, RETRO_WARNING, odobox.centerx, odobox.y + 20)
