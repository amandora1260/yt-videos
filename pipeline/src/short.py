"""YouTubeショート（縦型1080×1920・30〜45秒）を作る"""
import os, subprocess, numpy as np
from PIL import Image, ImageDraw
import render, tts
from render import F, wrap, WHITE, GRAY, ACC, UP, DN, SPK_COL
W, H = 1080, 1920
BG = (14, 27, 48); PANEL = (24, 42, 72)

def frame(b, card, speaker, text, idx, total):
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 10], fill=ACC)
    # 上部：見出し（結論＋数字）
    y = 150
    for l in b["headline"].split("\n"):
        for ll in wrap(d, l, F("Black", 92), W - 120):
            d.text((W/2, y), ll, font=F("Black", 92), fill=WHITE, anchor="ma"); y += 118
    d.text((W/2, y + 20), b["date_label"], font=F("Regular", 40), fill=GRAY, anchor="ma")
    # 中央：数字カード
    c = b["cards"][card]
    d.rounded_rectangle([90, 560, W - 90, 960], radius=36, fill=PANEL)
    big = c["big"]; col = DN if big.startswith("-") or c.get("tone") == "bad" else UP if big.startswith("+") or c.get("tone") == "good" else ACC
    fs = 170 if len(big) <= 6 else 130 if len(big) <= 9 else 96
    d.text((W/2, 740), big, font=F("Black", fs), fill=col, anchor="mm")
    d.text((W/2, 890), c["small"], font=F("Bold", 50), fill=WHITE, anchor="mm")
    # 字幕：大きめ・画面中央寄り（下部のボタン類を避ける）
    if render.show_subtitles(b):                            # 字幕（話者名＋せりふ）は設定で切り替え（既定は出さない）
        f = F("Bold", 62); lines = wrap(d, text, f, W - 300)   # 右の「いいね」ボタン列を避けて少し左寄せ
        if len(lines) > 3:                                      # 長いせりふは文字を少し小さくして全部出す
            f = F("Bold", 52); lines = wrap(d, text, f, W - 280)[:5]
        top = 1040
        nf = F("Bold", 44); col = SPK_COL.get(speaker, ACC)
        tw = d.textlength(speaker, font=nf)
        d.rounded_rectangle([W/2 - tw/2 - 30, top, W/2 + tw/2 + 30, top + 70], radius=14, fill=col)
        d.text((W/2, top + 35), speaker, font=nf, fill=(15, 15, 25), anchor="mm")
        y = top + 100
        for l in lines:
            d.text((W/2 - 70, y), l, font=f, fill=WHITE, anchor="ma", stroke_width=3, stroke_fill=(0, 0, 0)); y += int(f.size * 1.4)
    # 下部：チャンネル名と進み具合
    d.text((W/2, 1000), "とうもろこしの米国投資ちゃんねる", font=F("Medium", 38), fill=GRAY, anchor="mm")
    d.rectangle([0, H - 12, int(W * (idx + 1) / total), H], fill=ACC)
    return im

def split_lines(pcm, rate, dialogue):
    """1回で作った音声を、発言ごとの「間」で切り分ける（字幕と声をそろえる）"""
    w = rate // 100; n = len(pcm) // w
    rms = np.sqrt((pcm[:n*w].astype(np.float32).reshape(n, w) ** 2).mean(axis=1))
    quiet = rms < 0.05 * np.percentile(rms, 90)
    runs = []; i = 0                                        # 0.15秒以上の「間」を全部拾う
    while i < n:
        if quiet[i]:
            j = i
            while j < n and quiet[j]: j += 1
            if j - i >= 8 and i > 0 and j < n: runs.append((i, j))
            i = j
        else: i += 1
    weights = [len(t["text"]) + 3 for t in dialogue]
    cuts = []; prev = 0; acc = 0
    for k, wt in enumerate(weights[:-1]):
        acc += wt; target = n * acc / sum(weights)
        cand = [r for r in runs if (r[0] + r[1]) / 2 > prev + 50 and abs((r[0] + r[1]) / 2 - target) < 250]
        if cand:
            best = max(cand, key=lambda r: (r[1] - r[0]) - abs((r[0] + r[1]) / 2 - target) / 15)
            c = (best[0] + best[1]) // 2
        else:                                               # 見つからなければ、目安の近くで一番静かな所
            lo = int(max(prev + 50, target - 150)); hi = int(min(n - 1, target + 150))
            c = lo + int(np.argmin(rms[lo:hi])) if hi > lo else int(target)
        cuts.append(c); prev = c
    edges = [0] + [c * w for c in cuts] + [len(pcm)]
    return [pcm[a:b] for a, b in zip(edges[:-1], edges[1:])]

def build(b, out_mp4, workdir, pcm=None, rate=None):
    os.makedirs(workdir, exist_ok=True)
    if pcm is None:
        pcm, rate = tts.synth_dialogue(b["dialogue"])
        import scipy.io.wavfile as wv; wv.write(os.path.join(workdir, "raw.wav"), rate, pcm)   # 作り直し用に保存
    pieces = split_lines(pcm, rate, b["dialogue"])
    entries = []; aud = []
    gap = np.zeros(int(rate * 0.12), np.int16)
    for i, (t, p) in enumerate(zip(b["dialogue"], pieces)):
        fp = os.path.join(workdir, f"{i:03d}.png")
        frame(b, t.get("card", 0), t["speaker"], t["text"], i, len(pieces)).save(fp)
        seg = np.concatenate([p, gap]); aud.append(seg); entries.append((fp, len(seg) / rate))
    import scipy.io.wavfile as wv
    a = np.concatenate(aud).astype(np.float32); a = a / max(1, np.abs(a).max()) * 0.85 * 32767
    wav = os.path.join(workdir, "voice.wav"); wv.write(wav, rate, a.astype(np.int16))
    lst = os.path.join(workdir, "list.txt")
    with open(lst, "w") as f:
        for p, dd in entries: f.write(f"file '{os.path.abspath(p)}'\nduration {dd:.3f}\n")
        f.write(f"file '{os.path.abspath(entries[-1][0])}'\n")
    # キャラの口パク（15fps）を下部に重ねる
    import math, anim, chars
    FPS = 15; env = chars.envelope(a.astype(np.int16), rate, FPS); cdir = os.path.join(workdir, "c"); os.makedirs(cdir, exist_ok=True)
    tl = []; t0 = 0.0
    for (fp, dd), x in zip(entries, b["dialogue"]): tl.append((t0, t0 + dd, x["speaker"])); t0 += dd
    CHH = 300
    for i in range(len(env)):
        tt = i / FPS; sp = next((s_ for a_, b_, s_ in tl if a_ <= tt < b_), None)
        cv = Image.new("RGBA", (W, CHH + 30), (0, 0, 0, 0))
        for kind, side, ph in (("とうもろこし", "L", 0.0), ("焼きもろこし", "R", 1.3)):
            talk = sp == kind; e = float(env[i]) if talk else 0.0
            lv = 0 if e < 0.2 else 1 if e < 0.45 else 2 if e < 0.7 else 3
            bo = 12 * abs(math.sin(tt * 6 + ph)) if talk and e > 0.2 else 3 * math.sin(tt * 1.5 + ph)
            spr = anim.sprite(kind, lv, CHH); x0 = 110 if side == "L" else W - spr.width - 210   # 右側の「いいね」ボタン列を避ける
            cv.alpha_composite(spr, (x0, int(16 - bo)))
        cv.save(os.path.join(cdir, f"{i:05d}.png"))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-i", wav,
                    "-framerate", str(FPS), "-i", os.path.join(cdir, "%05d.png"),
                    "-filter_complex", f"[0:v]fps=30[bg];[bg][2:v]overlay=0:1390:eof_action=pass,format=yuv420p[v]", "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-tune", "stillimage", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", out_mp4], check=True)
    return sum(e_[1] for e_ in entries), [len(p) / rate for p in pieces]
