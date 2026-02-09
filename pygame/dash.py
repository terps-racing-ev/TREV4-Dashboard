import pygame
import time
import random
from datetime import datetime

# Initialize Pygame
pygame.init()

# Screen dimensions
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("EV Racing Dashboard")

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREEN = (0, 255, 0)
RED = (255, 0, 0)
YELLOW = (255, 255, 0)
DARK_GRAY = (30, 30, 30)
LIGHT_GRAY = (100, 100, 100)

# Fonts
font_large = pygame.font.Font(None, 180)
font_medium = pygame.font.Font(None, 100)
font_small = pygame.font.Font(None, 60)
font_tiny = pygame.font.Font(None, 40)

class RacingDashboard:
    def __init__(self):
        # Telemetry data
        self.elapsed_time = 0  # seconds
        self.rpm = 11500
        self.delta = 10.365
        self.speed = 230  # km/h
        self.gear = 5
        self.lap = 14
        self.soc = 100  # State of Charge (battery %)
        self.mix = 2  # Power mix mode
        self.lap_time = 64.32  # seconds
        self.ers = 3  # Energy Recovery System level
        self.bbal = 55.5  # Brake balance
        self.pit_limit = False
        self.vsc = False
        
        # Warning indicators
        self.temp_40_indicators = [True, True, True, True]
        
    def format_time(self, seconds):
        """Format time as MM:SS:mmm"""
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{minutes:02d}:{secs:02d}:{millis:03d}"
    
    def draw_box(self, x, y, width, height, color=DARK_GRAY, border_color=WHITE, border_width=2):
        """Draw a bordered box"""
        pygame.draw.rect(screen, color, (x, y, width, height))
        pygame.draw.rect(screen, border_color, (x, y, width, height), border_width)
    
    def draw_text(self, text, font, color, x, y, align='left'):
        """Draw text with alignment"""
        text_surface = font.render(str(text), True, color)
        text_rect = text_surface.get_rect()
        
        if align == 'center':
            text_rect.center = (x, y)
        elif align == 'right':
            text_rect.right = x
            text_rect.centery = y
        else:  # left
            text_rect.left = x
            text_rect.centery = y
            
        screen.blit(text_surface, text_rect)
    
    def draw_label_value_box(self, x, y, width, height, label, value, value_color=WHITE, label_size='small'):
        """Draw a box with label and value"""
        self.draw_box(x, y, width, height)
        
        label_font = font_tiny if label_size == 'small' else font_small
        label_y = y + 25 if label_size == 'small' else y + 30
        
        self.draw_text(label, label_font, WHITE, x + width // 2, label_y, 'center')
        
        value_y = y + height - 50 if label_size == 'small' else y + height - 60
        self.draw_text(value, font_medium if width > 200 else font_small, value_color, 
                      x + width // 2, value_y, 'center')
    
    def draw(self):
        """Draw the entire dashboard"""
        screen.fill(BLACK)
        
        # Top row - Time, RPM, Delta
        # Elapsed Time
        self.draw_box(10, 10, 290, 100)
        self.draw_text(self.format_time(self.elapsed_time), font_small, GREEN, 150, 60, 'center')
        
        # RPM
        self.draw_box(310, 10, 290, 100)
        self.draw_text(str(self.rpm), font_medium, RED, 455, 60, 'center')
        
        # Delta
        delta_color = GREEN if self.delta >= 0 else RED
        delta_text = f"+{self.delta:.3f}" if self.delta >= 0 else f"{self.delta:.3f}"
        self.draw_box(610, 10, 290, 100)
        self.draw_text(delta_text, font_small, delta_color, 755, 60, 'center')
        
        # Second row - Speed, Gear, Brake Balance
        # Speed
        box_height = 180
        self.draw_label_value_box(10, 120, 200, box_height, "SPEED", self.speed, WHITE)
        
        # Temperature indicator next to speed
        if self.temp_40_indicators[0]:
            self.draw_text("40", font_tiny, RED, 190, 210, 'center')
        
        # Gear (large center display)
        gear_box_width = 250
        self.draw_box(220, 120, gear_box_width, box_height)
        self.draw_text(str(self.gear), font_large, WHITE, 220 + gear_box_width // 2, 210, 'center')
        
        # Temperature indicator next to gear
        if self.temp_40_indicators[1]:
            self.draw_text("40", font_tiny, RED, 450, 210, 'center')
        
        # Brake Balance
        self.draw_label_value_box(480, 120, 200, box_height, "BBAL", self.bbal, WHITE)
        
        # Pit Limit / VSC indicators
        if self.pit_limit:
            self.draw_box(690, 120, 210, 85, RED)
            self.draw_text("PIT LIMIT", font_tiny, WHITE, 795, 162, 'center')
        
        if self.vsc:
            self.draw_box(690, 215, 210, 85, YELLOW)
            self.draw_text("VSC", font_small, BLACK, 795, 257, 'center')
        
        # Third row - Lap, SOC, Lap Time, ERS
        # Lap
        box_height = 180
        self.draw_label_value_box(10, 310, 200, box_height, "LAP", self.lap, WHITE)
        
        # Temperature indicator next to lap
        if self.temp_40_indicators[2]:
            self.draw_text("40", font_tiny, RED, 190, 400, 'center')
        
        # SOC (Battery)
        self.draw_label_value_box(220, 310, 120, box_height, "SOC", self.soc, GREEN, 'small')
        
        # Mix
        self.draw_label_value_box(350, 310, 120, box_height, "MIX", self.mix, WHITE, 'small')
        
        # Lap Time
        self.draw_box(480, 310, 200, box_height)
        self.draw_text(self.format_time(self.lap_time), font_small, YELLOW, 580, 400, 'center')
        
        # ERS
        self.draw_label_value_box(690, 310, 120, box_height, "ERS", self.ers, WHITE, 'small')
        
        # Temperature indicator next to ERS
        if self.temp_40_indicators[3]:
            self.draw_text("40", font_tiny, RED, 790, 400, 'center')
        
        # Bottom row - Status bars (simplified battery cells visualization)
        bar_y = 500
        bar_width = 50
        bar_height = 80
        bar_spacing = 10
        
        # Draw battery cell representation
        for i in range(16):
            x = 10 + i * (bar_width + bar_spacing)
            
            # Determine color based on battery status (simplified)
            if i < 2:
                color = RED
            elif i < 5:
                color = BLACK
            else:
                color = GREEN
            
            self.draw_box(x, bar_y, bar_width, bar_height, color, LIGHT_GRAY, 1)
    
    def update(self, dt):
        """Update telemetry data (for simulation)"""
        self.elapsed_time += dt
        self.lap_time += dt
        
        # Simulate some variations (you'll replace this with real data)
        # self.rpm = max(0, min(15000, self.rpm + random.randint(-100, 100)))
        # self.speed = max(0, min(300, self.speed + random.randint(-2, 2)))

def main():
    clock = pygame.time.Clock()
    dashboard = RacingDashboard()
    running = True
    
    print("EV Racing Dashboard")
    print("-------------------")
    print("Controls:")
    print("  UP/DOWN: Change speed")
    print("  LEFT/RIGHT: Change gear")
    print("  SPACE: Toggle pit limit")
    print("  V: Toggle VSC")
    print("  ESC: Exit")
    
    while running:
        dt = clock.tick(60) / 1000.0  # Delta time in seconds
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_UP:
                    dashboard.speed = min(300, dashboard.speed + 5)
                elif event.key == pygame.K_DOWN:
                    dashboard.speed = max(0, dashboard.speed - 5)
                elif event.key == pygame.K_RIGHT:
                    dashboard.gear = min(6, dashboard.gear + 1)
                elif event.key == pygame.K_LEFT:
                    dashboard.gear = max(1, dashboard.gear - 1)
                elif event.key == pygame.K_SPACE:
                    dashboard.pit_limit = not dashboard.pit_limit
                elif event.key == pygame.K_v:
                    dashboard.vsc = not dashboard.vsc
                elif event.key == pygame.K_r:
                    # Reset lap time
                    dashboard.lap_time = 0
                    dashboard.lap += 1
        
        # Update and draw
        dashboard.update(dt)
        dashboard.draw()
        
        pygame.display.flip()
    
    pygame.quit()

if __name__ == "__main__":
    main()
    