"""Render a silent, PPT-ready task decomposition illustration (no robot execution)."""
from pathlib import Path
import subprocess
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
W, H, FPS = 1920, 1080, 24
BG = '#0f1e30'
PANEL = '#1c3246'
WHITE = '#f8fafa'
MUTED = '#adbf c9'.replace(' ', '')
TEAL = '#3fd7c0'
BLUE = '#78aaff'
FONT = subprocess.check_output(['fc-match', '-f', '%{file}', 'Noto Sans CJK SC'], text=True)

def text(draw, xy, content, size=32, color=WHITE):
    draw.text(xy, content, fill=color, font=ImageFont.truetype(FONT, size))

def box(draw, rect, title, subtitle, accent=TEAL):
    x, y, r, b = rect
    draw.rounded_rectangle(rect, 20, fill=PANEL)
    draw.rounded_rectangle((x+24, y+28, x+30, y+70), 3, fill=accent)
    text(draw, (x+48, y+23), title, 36)
    text(draw, (x+26, y+94), subtitle, 27, MUTED)

def arrow(draw, x1, y, x2, color=TEAL):
    draw.line((x1, y, x2-5, y), fill=color, width=4)
    draw.polygon([(x2,y),(x2-12,y-8),(x2-12,y+8)], fill=color)

def frame(stage):
    im = Image.new('RGB', (W,H), BG)
    d = ImageDraw.Draw(im)
    d.rectangle((0,0,12,H), fill=TEAL)
    text(d, (70,38), 'ROBOT AGENT  /  任务分解', 24, TEAL)
    text(d, (70,91), '一句指令，如何变成机器人任务？', 56)
    text(d, (70,186), '去实验室 A 找到笔记本电脑，拿回会议室。', 43)
    d.line((70,267,1850,267), fill='#3a4f60', width=2)
    labels = ['理解指令', '明确目标', '拆分子任务', '绑定依赖', '定义完成条件']
    for i, label in enumerate(labels):
        x = 70+i*362
        d.rounded_rectangle((x,299,x+332,353), 10, fill=TEAL if i==stage else PANEL)
        text(d, (x+18,306), f'0{i+1}  {label}', 26, BG if i==stage else MUTED)
    if stage == 0:
        text(d, (70,422), '从指令中提取三个关键要素', 36)
        box(d, (70,512,634,724), '去哪里', '实验室 A')
        box(d, (678,512,1242,724), '找什么', '笔记本电脑')
        box(d, (1286,512,1850,724), '送到哪里', '会议室')
        text(d, (70,802), '目标：把指定物品从来源地点转移到交付地点。', 34, MUTED)
    elif stage == 1:
        text(d, (70,418), '把自然语言整理成可规划的目标', 36)
        box(d, (70,496,928,680), '目标对象', '实验室 A 内的目标笔记本电脑')
        box(d, (972,496,1850,680), '交付结果', '电脑放到会议桌上，机器人释放物品')
        text(d, (70,733), '场景假设', 29, TEAL)
        text(d, (70,786), '从会议室出发  ·  房间位置已知  ·  目标电脑唯一且可抓取', 33)
        text(d, (70,851), '规划所需能力：导航、目标搜索、抓取、放置、结果验证', 30, MUTED)
    else:
        text(d, (70,402), '取到电脑', 35, TEAL)
        text(d, (977,402), '送回会议室', 35, TEAL)
        tasks = [('前往实验室 A','导航到目标房间'), ('寻找电脑','识别并定位目标'),
                 ('抓取电脑','确认已稳定持有'), ('返回会议室','携带电脑导航'),
                 ('放置电脑','放到指定桌面'), ('验证交付','检查物品与位置')]
        for i,(title,sub) in enumerate(tasks):
            x = 70+i*302
            d.rounded_rectangle((x,486,x+270,688), 18, fill=PANEL)
            text(d, (x+22,502), f'{i+1:02d}', 27, TEAL)
            text(d, (x+22,551), title, 33)
            text(d, (x+22,613), sub, 24, MUTED)
            if i<5:
                arrow(d,x+273,581,x+298)
        if stage == 2:
            text(d, (70,756), '按任务依赖排列：先找到目标，再抓取；确认持有后，再携物返回。', 33)
            text(d, (70,824), '每个节点对应一项技能，箭头表示执行先后依赖。', 30, MUTED)
        elif stage == 3:
            box(d, (70,744,928,934), '搜索 → 抓取', '传递目标 ID 与位姿，执行时绑定实际输出', BLUE)
            box(d, (972,744,1850,934), '抓取 → 携物返回', '确认持有目标后，才能进入返程步骤', BLUE)
        else:
            d.rounded_rectangle((70,744,1850,932), 18, fill='#173d3d', outline=TEAL, width=2)
            text(d, (100,768), '预期完成条件', 35, TEAL)
            text(d, (100,830), '物品正确  +  位于会议桌上  +  已释放且放置稳定', 40)
    text(d, (70,1005), '任务分解示意  ·  机器人技能为场景假设  ·  非实际执行记录', 23, MUTED)
    text(d, (1650,1005), f'{stage+1:02d} / 05', 23, TEAL)
    return im

slides = [frame(i) for i in range(5)]
for i, slide in enumerate(slides):
    slide.save(HERE/f'stage-{i+1:02d}.png')
slides[-1].save(HERE/'poster.png')
cmd = ['ffmpeg','-y','-loglevel','error','-f','rawvideo','-vcodec','rawvideo',
       '-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-',
       '-an','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p',
       '-movflags','+faststart',str(HERE/'laptop-task-decomposition.mp4')]
proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
for i, slide in enumerate(slides):
    for f in range(FPS*5):
        current = Image.blend(slides[i-1], slide, (f+1)/12) if i and f<12 else slide
        proc.stdin.write(current.tobytes())
proc.stdin.close()
if proc.wait():
    raise RuntimeError('ffmpeg failed')
sheet = Image.new('RGB',(960,540*3),BG)
for i,s in enumerate(slides):
    sheet.paste(s.resize((960,540)), (0,540*i)) if i<3 else None
sheet.save(HERE/'preview-first-three.png')
print(HERE/'laptop-task-decomposition.mp4')
