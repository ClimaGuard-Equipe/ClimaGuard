"""Render the existing ClimaGuard C mark as a Windows application icon."""
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parent
image = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((8, 8, 504, 504), radius=112, fill='#123c35')
draw.arc((106, 98, 406, 414), start=44, end=316, fill='#b8eacb', width=56)
draw.ellipse((348, 86, 412, 150), fill='#e3b766')
image.save(root / 'climaguard.ico', sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
image.save(root / 'climaguard.png')
