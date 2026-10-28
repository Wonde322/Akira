"""Offline sprite renderer. Qt only plays the resulting atlas, never this geometry."""
from pathlib import Path
import math
from PIL import Image, ImageDraw

FRAMES, LEVELS = 32, 4
WIDTH, HEIGHT = 360, 210
SCALE = 2


def render(phase, level):
    image = Image.new('RGBA', (WIDTH * SCALE, HEIGHT * SCALE))
    draw = ImageDraw.Draw(image)
    facets = []
    for ring, radius in enumerate((130, 101)):
        nodes = []
        for i in range(97):
            a = math.tau * i / 96
            # Counter-propagating periodic waves, identical at the loop boundary.
            wave = (math.sin(4*a-phase+ring*.6)*.48 + math.sin(7*a+phase+ring*.9)*.32
                    + math.sin(11*a-2*phase)*.2)
            h = 2.5 + level * (9 + 68 * max(0, wave + .15)**1.5)
            base = (WIDTH/2 + radius*math.cos(a), 147 + radius*.32*math.sin(a))
            top = (base[0] + math.cos(a)*h*.11, base[1]-h)
            nodes.append((base, top))
        for i in range(96):
            base, top = nodes[i]; other, next_top = nodes[i+1]
            # Both rings share the same scene-depth sort: correct mutual occlusion.
            depth = (base[1]+other[1])/2
            shade = (math.sin(i*.42+ring) + 1)/2
            fill = (255, int(156+60*shade), int(74+70*shade), 255)
            if ring: fill = (255, int(196+38*shade), int(108+64*shade), 255)
            facets.append((depth, [base,top,next_top,other], fill))
    for depth, points, fill in sorted(facets,key=lambda f:f[0]):
        points = [(round(x*SCALE),round(y*SCALE)) for x,y in points]
        draw.polygon(points, fill=fill)
        # Straight top edges define continuous angular sheets, without particles/bloom.
        draw.line(points[1:3], fill=(255,246,196,255), width=2)
        draw.line([points[0],points[1]], fill=(215,76,57,190), width=1)
    return image.resize((WIDTH,HEIGHT),Image.Resampling.LANCZOS)


def main():
    atlas = Image.new('RGBA',(WIDTH*8,HEIGHT*16))
    preview=[]
    for row, level in enumerate((.025,.3,.65,1.0)):
        for frame in range(FRAMES):
            im=render(math.tau*frame/FRAMES,level)
            index=row*FRAMES+frame
            atlas.paste(im,((index%8)*WIDTH,(index//8)*HEIGHT))
            if row==2:
                bg=Image.new('RGBA',im.size,'#101013');bg.alpha_composite(im);preview.append(bg.convert('RGB'))
    target=Path(__file__).resolve().parents[1]/'assets/core_atlas.png'
    temporary = target.with_suffix(".tmp")
    atlas.quantize(colors=128, method=Image.Quantize.FASTOCTREE).save(temporary, format="PNG", optimize=True)
    temporary.replace(target)
    preview[0].save('/tmp/akira-core-motion.gif',save_all=True,append_images=preview[1:],duration=60,loop=0)
    print(target, target.stat().st_size)

if __name__=='__main__': main()
