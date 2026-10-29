"""Offline cyclic inbetweening of the approved 4x4 RGBA keyframe sheet.

Usage: python scripts/prepare_core_motion.py keyframes.png assets/core_motion.png
Build-only dependencies: Pillow, numpy, opencv-python-headless.
No image-processing dependencies are needed by the desktop player.
"""
import argparse
import numpy as np
import cv2
from PIL import Image

WIDTH, HEIGHT, PHASES = 320, 210, 256
Y, X = np.mgrid[:HEIGHT, :WIDTH].astype(np.float32)


def inverse_warp(frame, flow, amount):
    mx, my = X.copy(), Y.copy()
    for _ in range(4):
        displacement = cv2.remap(flow, mx, my, cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_REPLICATE)
        mx, my = X - amount * displacement[..., 0], Y - amount * displacement[..., 1]
    return cv2.remap(frame, mx, my, cv2.INTER_LINEAR)


def build(source, destination):
    sheet = Image.open(source).convert('RGBA')
    keys, gray = [], []
    for i in range(16):
        col, row = i % 4, i // 4
        tile = sheet.crop((col*sheet.width//4, row*sheet.height//4,
                           (col+1)*sheet.width//4, (row+1)*sheet.height//4))
        rgba = np.asarray(tile.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)).astype(np.float32)/255
        # Remove extraction fringe once, never threshold interpolated coverage.
        rgba[..., 3] = np.clip((rgba[..., 3]*255-220)/32, 0, 1)
        rgba[..., :3] *= rgba[..., 3:]
        keys.append(rgba)
        gray.append(cv2.cvtColor((rgba[..., :3]*255).astype(np.uint8), cv2.COLOR_RGB2GRAY))
    estimator = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    estimator.setUseSpatialPropagation(True)
    frames = []
    for i, a in enumerate(keys):
        j = (i+1) % len(keys)
        forward = estimator.calc(gray[i], gray[j], None)
        backward = estimator.calc(gray[j], gray[i], None)
        for step in range(PHASES//16):
            t = step/(PHASES//16)
            frames.append(inverse_warp(a, forward, t)*(1-t) +
                          inverse_warp(keys[j], backward, 1-t)*t)
    # Circular filtering also smooths velocity changes at source keyframes and
    # the last/first join. Work in premultiplied RGBA to retain clean edges.
    atlas = Image.new('RGBA', (WIDTH*8, HEIGHT*(PHASES//8)))
    kernel = (1, 4, 6, 4, 1)
    for i in range(PHASES):
        frame = sum(frames[(i+offset-2) % PHASES]*weight
                    for offset, weight in enumerate(kernel))/16
        alpha = frame[..., 3:]
        rgb = frame[..., :3]/np.maximum(alpha, 1/65535)
        rgba = np.clip(np.dstack((rgb, alpha))*255+.5, 0, 255).astype(np.uint8)
        # One-bit RGB rounding reduces storage noise without a shared palette.
        # Keep all 256 alpha levels for subpixel contour coverage.
        rgba[..., :3] = (np.minimum(254, rgba[..., :3].astype(np.uint16)+1)//2*2).astype(np.uint8)
        rgba[rgba[..., 3] == 0, :3] = 0
        atlas.paste(Image.fromarray(rgba), ((i%8)*WIDTH, (i//8)*HEIGHT))
    # Preserve full colour and alpha; palette reduction causes contour flashing.
    atlas.save(destination, optimize=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('destination')
    args = parser.parse_args()
    build(args.source, args.destination)
