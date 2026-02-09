"""
EV Racing Dashboard with Real-time Data Input
Supports serial port and CAN bus data integration
"""

import pygame
import time
import json
from datetime import datetime
from collections import deque

# Initialize Pygame
pygame.init()

# Screen dimensions - set to match your display
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)  # Change to FULLSCREEN for race use
pygame.display.set_caption("EV Racing Dashboard")

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREEN = (0, 255, 0)
RED = (255, 0, 0)
YELLOW = (255, 255, 0)
DARK_GRAY = (30, 30, 30)
LIGHT_GRAY = (100, 100, 100)
ORANGE = (255, 165, 0)

# Fonts
font_large = pygame.font.Font(None, 180)
font_medium = pygame.font.Font(None, 100)
font_small = pygame.font.Font(None, 60)
font_tiny = pygame.font.Font(None, 40)

class DataLogger:
    """Log telemetry data to file"""
    def __init__(self, filename='telemetry_log.csv'):
        self.filename = filename
        self.file = open(filename, 'w')
        self.file.write("timestamp,elapsed_time,speed,rpm,gear,soc,lap,lap_time,delta,bbal,ers,mix\n")
    
    def log(self, data):
        timestamp = datetime.now().isoformat()
        line = f"{timestamp},{data['elapsed_time']},{data['speed']},{data['rpm']},"
        line += f"{data['gear']},{data['soc']},{data['lap']},{data['lap_time']},"
        line += f"{data['delta']},{data['bbal']},{data['ers']},{data['mix']}\n"
        self.file.write(line)
        self.file.flush()
    
    def close(self):
        self.file.close()

class RacingDashboard:
    def __init__(self):
        # Telemetry data
        self.elapsed_time = 0
        self.rpm = 0
        self.delta = 0.0
        self.speed = 0
        self.gear = 1
        self.lap = 1
        self.soc = 100
        self.mix = 2
        self.lap_time = 0.0
        self.best_lap = 999.999
        self.ers = 0
        self.bbal = 50.0
        self.pit_limit = False
        self.vsc = False
        
        # Motor temperatures
        self.motor_temp = 40
        self.battery_temp = 40
        self.inverter_temp = 40
        self.controller_temp = 40
        
        # Thresholds
        self.temp_warning = 80
        self.temp_critical = 100
        self.rpm_max = 15000
        self.speed_max = 300
        
        # History for graphs
        self.speed_history = deque(maxlen=100)
        self.rpm_history = deque(maxlen=100)
        
        # Data logger
        self.logger = None
        
    def set_data(self, data_dict):
        """Update dashboard with data from external source (CAN bus, serial, etc.)"""
        for key, value in data_dict.items():
            if hasattr(self, key):
                setattr(self, key, value)
    
    def format_time(self, seconds):
        """Format time as MM:SS:mmm"""
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{minutes:02d}:{secs:02d}:{millis:03d}"
    
    def get_temp_color(self, temp):
        """Get color based on temperature"""
        if temp >= self.temp_critical:
            return RED
        elif temp >= self.temp_warning:
            return ORANGE
        else:
            return WHITE
    
    def draw_box(self, x, y, width, height, color=DARK_GRAY, border_color=WHITE, border_width=3):
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
        else:
            text_rect.left = x
            text_rect.centery = y
            
        screen.blit(text_surface, text_rect)
    
    def draw_label_value_box(self, x, y, width, height, label, value, value_color=WHITE, 
                            temp=None, label_size='small'):
        """Draw a box with label, value, and optional temperature"""
        self.draw_box(x, y, width, height)
        
        label_font = font_tiny if label_size == 'small' else font_small
        label_y = y + 25 if label_size == 'small' else y + 30
        
        self.draw_text(label, label_font, LIGHT_GRAY, x + width // 2, label_y, 'center')
        
        value_y = y + height - 55 if label_size == 'small' else y + height - 65
        value_font = font_medium if width > 200 else font_small
        self.draw_text(value, value_font, value_color, x + width // 2, value_y, 'center')
        
        # Draw temperature if provided
        if temp is not None:
            temp_color = self.get_temp_color(temp)
            self.draw_text(f"{int(temp)}°", font_tiny, temp_color, x + width - 15, y + height // 2, 'right')
    
    def draw_progress_bar(self, x, y, width, height, value, max_value, color=GREEN, 
                         label="", show_value=True):
        """Draw a progress bar"""
        # Background
        self.draw_box(x, y, width, height, BLACK)
        
        # Fill
        fill_width = int((value / max_value) * width)
        if fill_width > 0:
            pygame.draw.rect(screen, color, (x + 2, y + 2, fill_width - 4, height - 4))
        
        # Label and value
        if label:
            self.draw_text(label, font_tiny, WHITE, x + 5, y + height // 2, 'left')
        if show_value:
            self.draw_text(f"{int(value)}", font_tiny, WHITE, x + width - 5, y + height // 2, 'right')
    
    def draw(self):
        """Draw the entire dashboard"""
        screen.fill(BLACK)
        
        # ========== TOP ROW ==========
        # Elapsed Time
        self.draw_box(10, 10, 290, 100, DARK_GRAY, GREEN)
        self.draw_text(self.format_time(self.elapsed_time), font_small, GREEN, 155, 60, 'center')
        
        # RPM with color based on limit
        rpm_color = RED if self.rpm > self.rpm_max * 0.95 else WHITE
        self.draw_box(310, 10, 290, 100, DARK_GRAY, rpm_color)
        self.draw_text(str(int(self.rpm)), font_medium, rpm_color, 455, 60, 'center')
        
        # Delta (positive = gaining time, negative = losing time)
        delta_color = GREEN if self.delta > 0 else RED if self.delta < 0 else WHITE
        delta_text = f"+{self.delta:.3f}" if self.delta > 0 else f"{self.delta:.3f}"
        self.draw_box(610, 10, 290, 100, DARK_GRAY, delta_color)
        self.draw_text(delta_text, font_small, delta_color, 755, 60, 'center')
        
        # Best lap time
        self.draw_box(910, 10, 360, 100, DARK_GRAY, YELLOW)
        self.draw_text("BEST", font_tiny, LIGHT_GRAY, 1090, 35, 'center')
        self.draw_text(self.format_time(self.best_lap) if self.best_lap < 999 else "--:--:---", 
                      font_small, YELLOW, 1090, 75, 'center')
        
        # ========== SECOND ROW ==========
        box_height = 180
        
        # Speed with temperature
        self.draw_label_value_box(10, 120, 200, box_height, "SPEED", int(self.speed), 
                                 WHITE, self.motor_temp)
        
        # Gear (large center display)
        gear_box_width = 250
        self.draw_box(220, 120, gear_box_width, box_height, DARK_GRAY, WHITE, 4)
        self.draw_text(str(self.gear) if self.gear > 0 else "N", font_large, WHITE, 
                      345, 210, 'center')
        
        # Brake Balance with temperature
        self.draw_label_value_box(480, 120, 200, box_height, "BBAL", 
                                 f"{self.bbal:.1f}", WHITE, self.inverter_temp)
        
        # Status indicators
        if self.pit_limit:
            self.draw_box(690, 120, 280, 85, RED, WHITE, 3)
            self.draw_text("PIT LIMIT", font_small, WHITE, 830, 162, 'center')
        else:
            self.draw_box(690, 120, 280, 85, DARK_GRAY, LIGHT_GRAY, 2)
        
        if self.vsc:
            self.draw_box(690, 215, 280, 85, YELLOW, BLACK, 3)
            self.draw_text("VSC", font_medium, BLACK, 830, 257, 'center')
        else:
            self.draw_box(690, 215, 280, 85, DARK_GRAY, LIGHT_GRAY, 2)
        
        # RPM bar
        self.draw_progress_bar(980, 120, 290, 40, self.rpm, self.rpm_max, 
                              RED if self.rpm > self.rpm_max * 0.9 else GREEN, 
                              "RPM", False)
        
        # Speed bar
        self.draw_progress_bar(980, 170, 290, 40, self.speed, self.speed_max, 
                              YELLOW, "SPEED", False)
        
        # Battery SOC bar
        soc_color = RED if self.soc < 20 else ORANGE if self.soc < 40 else GREEN
        self.draw_progress_bar(980, 220, 290, 40, self.soc, 100, soc_color, "SOC %", True)
        
        # Battery temp bar
        temp_color = self.get_temp_color(self.battery_temp)
        self.draw_progress_bar(980, 270, 290, 40, self.battery_temp, 120, temp_color, 
                              "BATT °C", True)
        
        # ========== THIRD ROW ==========
        # Lap
        self.draw_label_value_box(10, 310, 200, box_height, "LAP", int(self.lap), 
                                 WHITE, self.battery_temp)
        
        # SOC (Battery %)
        soc_color = RED if self.soc < 20 else ORANGE if self.soc < 40 else GREEN
        self.draw_label_value_box(220, 310, 120, box_height, "SOC", int(self.soc), 
                                 soc_color, None, 'small')
        
        # Mix (Power mode)
        self.draw_label_value_box(350, 310, 120, box_height, "MIX", int(self.mix), 
                                 WHITE, None, 'small')
        
        # Current Lap Time
        self.draw_box(480, 310, 200, box_height)
        self.draw_text("LAP TIME", font_tiny, LIGHT_GRAY, 580, 335, 'center')
        self.draw_text(self.format_time(self.lap_time), font_small, YELLOW, 580, 410, 'center')
        
        # ERS
        self.draw_label_value_box(690, 310, 120, box_height, "ERS", int(self.ers), 
                                 WHITE, self.controller_temp, 'small')
        
        # Additional info box
        self.draw_box(820, 310, 450, box_height, DARK_GRAY, LIGHT_GRAY, 2)
        info_x = 840
        info_y = 330
        line_height = 35
        
        self.draw_text(f"Motor: {int(self.motor_temp)}°C", font_tiny, 
                      self.get_temp_color(self.motor_temp), info_x, info_y)
        self.draw_text(f"Inverter: {int(self.inverter_temp)}°C", font_tiny, 
                      self.get_temp_color(self.inverter_temp), info_x, info_y + line_height)
        self.draw_text(f"Battery: {int(self.battery_temp)}°C", font_tiny, 
                      self.get_temp_color(self.battery_temp), info_x, info_y + line_height * 2)
        self.draw_text(f"Controller: {int(self.controller_temp)}°C", font_tiny, 
                      self.get_temp_color(self.controller_temp), info_x, info_y + line_height * 3)
        
        # ========== BOTTOM ROW - Battery Cells Visualization ==========
        bar_y = 510
        bar_width = 75
        bar_height = 100
        bar_spacing = 5
        num_cells = 16
        
        for i in range(num_cells):
            x = 10 + i * (bar_width + bar_spacing)
            
            # Calculate cell voltage/health (this should come from BMS)
            # For now, simulate based on SOC
            if self.soc > 80:
                color = GREEN
            elif self.soc > 50:
                if i % 3 == 0:
                    color = GREEN
                else:
                    color = BLACK
            elif self.soc > 20:
                if i % 2 == 0:
                    color = GREEN
                else:
                    color = BLACK
            else:
                if i < 3:
                    color = GREEN
                elif i < 6:
                    color = BLACK
                else:
                    color = RED
            
            self.draw_box(x, bar_y, bar_width, bar_height, color, LIGHT_GRAY, 2)
            
            # Cell number
            self.draw_text(str(i + 1), font_tiny, WHITE if color == BLACK else BLACK, 
                          x + bar_width // 2, bar_y + bar_height // 2, 'center')
        
        # Status text
        status_text = f"FPS: {int(clock.get_fps())}"
        self.draw_text(status_text, font_tiny, LIGHT_GRAY, SCREEN_WIDTH - 10, 
                      SCREEN_HEIGHT - 20, 'right')
    
    def update(self, dt):
        """Update dashboard state"""
        self.elapsed_time += dt
        self.lap_time += dt
        
        # Update history
        self.speed_history.append(self.speed)
        self.rpm_history.append(self.rpm)
        
        # Log data if logger is enabled
        if self.logger:
            data = {
                'elapsed_time': self.elapsed_time,
                'speed': self.speed,
                'rpm': self.rpm,
                'gear': self.gear,
                'soc': self.soc,
                'lap': self.lap,
                'lap_time': self.lap_time,
                'delta': self.delta,
                'bbal': self.bbal,
                'ers': self.ers,
                'mix': self.mix
            }
            self.logger.log(data)
    
    def new_lap(self):
        """Start a new lap"""
        if self.lap_time > 0 and self.lap_time < self.best_lap:
            self.best_lap = self.lap_time
        self.lap += 1
        self.lap_time = 0.0

def main():
    global clock
    clock = pygame.time.Clock()
    dashboard = RacingDashboard()
    running = True
    
    # Enable data logging
    # dashboard.logger = DataLogger()
    
    print("=" * 50)
    print("EV Racing Dashboard - Advanced Version")
    print("=" * 50)
    print("\nKeyboard Controls (for testing):")
    print("  UP/DOWN: Speed ±5")
    print("  LEFT/RIGHT: Change gear")
    print("  +/-: RPM ±500")
    print("  SPACE: Toggle pit limit")
    print("  V: Toggle VSC")
    print("  N: New lap")
    print("  L: Toggle logging")
    print("  ESC or Q: Exit")
    print("\n" + "=" * 50)
    
    # Simulation mode for testing
    simulation_mode = True
    sim_speed_target = 0
    sim_rpm_target = 0
    
    while running:
        dt = clock.tick(60) / 1000.0
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                    running = False
                elif event.key == pygame.K_UP:
                    sim_speed_target = min(300, sim_speed_target + 10)
                elif event.key == pygame.K_DOWN:
                    sim_speed_target = max(0, sim_speed_target - 10)
                elif event.key == pygame.K_RIGHT:
                    dashboard.gear = min(6, dashboard.gear + 1)
                    sim_rpm_target = dashboard.gear * 2500
                elif event.key == pygame.K_LEFT:
                    dashboard.gear = max(1, dashboard.gear - 1)
                    sim_rpm_target = dashboard.gear * 2500
                elif event.key == pygame.K_EQUALS or event.key == pygame.K_PLUS:
                    sim_rpm_target = min(15000, sim_rpm_target + 500)
                elif event.key == pygame.K_MINUS:
                    sim_rpm_target = max(0, sim_rpm_target - 500)
                elif event.key == pygame.K_SPACE:
                    dashboard.pit_limit = not dashboard.pit_limit
                elif event.key == pygame.K_v:
                    dashboard.vsc = not dashboard.vsc
                elif event.key == pygame.K_n:
                    dashboard.new_lap()
                elif event.key == pygame.K_l:
                    if dashboard.logger:
                        dashboard.logger.close()
                        dashboard.logger = None
                        print("Logging disabled")
                    else:
                        dashboard.logger = DataLogger()
                        print("Logging enabled")
        
        # Simulation: smooth transitions
        if simulation_mode:
            dashboard.speed += (sim_speed_target - dashboard.speed) * 0.1
            dashboard.rpm += (sim_rpm_target - dashboard.rpm) * 0.1
            
            # Simulate battery drain
            if dashboard.speed > 0:
                dashboard.soc -= 0.01 * dt
                dashboard.soc = max(0, dashboard.soc)
            
            # Simulate temperature increase with speed
            temp_increase = dashboard.speed / 100 * dt
            dashboard.motor_temp = min(120, dashboard.motor_temp + temp_increase)
            dashboard.battery_temp = min(100, 35 + dashboard.soc / 10 + dashboard.speed / 50)
            dashboard.inverter_temp = min(110, 30 + dashboard.rpm / 200)
            dashboard.controller_temp = min(100, 35 + dashboard.speed / 30)
        
        dashboard.update(dt)
        dashboard.draw()
        pygame.display.flip()
    
    if dashboard.logger:
        dashboard.logger.close()
    
    pygame.quit()

if __name__ == "__main__":
    main()
    