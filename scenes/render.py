"""Render a scene as a video in the look of the original stimuli: white table,
black walls, red gate, green ball A, blue ball B, gray others, 50 frames per
second, ending 30 frames after B goes in.

Usage: python scenes/render.py scenes.json out_dir [--frames]
"""
import json
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import imageio.v2 as imageio  # noqa: E402
import numpy as np  # noqa: E402
import pygame  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sim.physics import HEIGHT, RADIUS, WIDTH, simulate  # noqa: E402

COLORS = {"A": (96, 196, 96), "B": (66, 133, 206)}
GRAY = (90, 90, 90)


def frames(scene):
    run = simulate(scene, record=True, full_length=True)
    end = min(run.exit_step + 30, len(next(iter(run.paths.values()))))
    pygame.font.init()
    font = pygame.font.SysFont(None, 44, bold=True)
    surf = pygame.Surface((WIDTH, HEIGHT))
    for t in range(end):
        surf.fill((250, 250, 250))
        pygame.draw.rect(surf, (0, 0, 0), (0, 0, WIDTH, 25))
        pygame.draw.rect(surf, (0, 0, 0), (0, HEIGHT - 25, WIDTH, 25))
        pygame.draw.rect(surf, (0, 0, 0), (0, 25, 25, 233))
        pygame.draw.rect(surf, (0, 0, 0), (0, 492, 25, 233))
        pygame.draw.rect(surf, (232, 112, 112), (0, 258, 25, 234))
        for name, path in run.paths.items():
            x, y = path[t]
            pos = (int(round(x)), int(round(HEIGHT - y)))
            color = COLORS.get(name, GRAY)
            pygame.draw.circle(surf, color, pos, RADIUS)
            pygame.draw.circle(surf, (30, 30, 30), pos, RADIUS, 2)
            if name in COLORS:
                label = font.render(name, True, (20, 20, 20))
                surf.blit(label, label.get_rect(center=pos))
        yield t, np.transpose(pygame.surfarray.array3d(surf), (1, 0, 2))


def render(scene, path, frame_dir=None, every=25):
    with imageio.get_writer(path, fps=50, codec="libx264", quality=8, macro_block_size=None) as w:
        for t, img in frames(scene):
            w.append_data(img)
            if frame_dir and t % every == 0:
                imageio.imwrite(os.path.join(frame_dir, f"{t:03d}.png"), img)


def main():
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    for trial in json.load(open(src)):
        fdir = None
        if "--frames" in sys.argv:
            fdir = os.path.join(out, "frames", trial["trial"])
            os.makedirs(fdir, exist_ok=True)
        render(trial["balls"], os.path.join(out, trial["trial"] + ".mp4"), fdir)
        print("rendered", trial["trial"], flush=True)


if __name__ == "__main__":
    main()
