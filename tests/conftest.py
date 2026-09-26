import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "config", "waybar", "scripts")
THEMES = os.path.join(ROOT, "config", "hypr", "themes")
sys.path.insert(0, SCRIPTS)
