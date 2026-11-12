"""Gemini APIで2人の掛け合い音声を作る（無料枠で使える設定）"""
import base64, json, os, re, time
import numpy as np, requests

STYLE = ("朝の投資情報番組で、2人が自然に会話しています。"
         "Yakiは大阪弁で話す、少し色っぽくて落ち着いた大人の女性の進行役、Toumoは明るく分かりやすい解説役の男性です。"
         "テンポよく、聞き取りやすい速さで、日本語で自然に話してください。")
NAME_MAP = {"焼きもろこし": "Yaki", "とうもろこし": "Toumo"}
READING = {"焼きもろこし": "やきもろこし"}   # 読み間違い防止（字幕は漢字のまま）
def _read(t):
    for k, v in READING.items(): t = t.replace(k, v)
    return t   # 音声合成には英字名で渡す（字幕は日本語名）

def _models():
    m = os.environ.get("GEMINI_TTS_MODELS", "gemini-3.8-flash-tts,gemini-3.1-flash-tts-preview,gemini-2.5-flash-preview-tts")
    return [x.strip() for x in m.split(",") if x.strip()]

def parse_audio(resp_json):
    """APIの返答から音声（16bit PCM）とサンプリングレートを取り出す"""
    part = resp_json["candidates"][0]["content"]["parts"][0]["inlineData"]
    m = re.search(r"rate=(\d+)", part.get("mimeType", ""))
    rate = int(m.group(1)) if m else 24000
    pcm = np.frombuffer(base64.b64decode(part["data"]), dtype=np.int16)
    return pcm, rate

def synth_dialogue(dialogue):
    """1枚のスライド分の掛け合いを、1回の呼び出しでまとめて音声にする"""
    if os.environ.get("MOCK_TTS") == "1":          # 動作確認用（無音・文字数に比例した長さ）
        sec = sum(len(t["text"]) for t in dialogue) / 8.0 + 0.5 * len(dialogue)
        return np.zeros(int(24000 * sec), np.int16), 24000
    key = os.environ["GEMINI_API_KEY"]
    script = "\n".join(f'{NAME_MAP.get(t["speaker"], t["speaker"])}: {_read(t["text"])}' for t in dialogue)
    voices = {"Yaki": os.environ.get("VOICE_YAKI", "Sulafat"), "Toumo": os.environ.get("VOICE_TOUMO", "Puck")}
    gen = {"responseModalities": ["AUDIO"],
           "speechConfig": {"multiSpeakerVoiceConfig": {"speakerVoiceConfigs": [
               {"speaker": s, "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": v}}} for s, v in voices.items()]}}}
    def make_body(model):
        if "3.8" in model:   # 新しいモデル：発言ごとに話者を指定する形式（話し方の指示文は受け付けない）
            parts = [{"text": _read(t["text"]), "speechMetadata": {"speaker": NAME_MAP.get(t["speaker"], t["speaker"])}} for t in dialogue]
            return {"contents": [{"role": "user", "parts": parts}], "generationConfig": gen}
        return {"contents": [{"parts": [{"text": STYLE + "\n\n" + script}]}], "generationConfig": gen}
    last = None
    for model in _models():
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(4):
            try:
                r = requests.post(url, headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                                  data=json.dumps(make_body(model)), timeout=180)
                if r.status_code == 200:
                    pcm, rate = parse_audio(r.json())
                    return clean(pcm, rate), rate
                last = f"{model}: HTTP {r.status_code} {r.text[:300]}"
                if r.status_code == 429 and "per day" in r.text:
                    break                                             # 1日の上限に達したモデルはすぐ次のモデルへ
                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(30 * (attempt + 1)); continue     # 回数制限・混雑は待って再試行
                break                                             # それ以外は次のモデルへ
            except (requests.RequestException, KeyError, IndexError) as e:
                last = f"{model}: {e}"; time.sleep(15)
    raise RuntimeError("音声の生成に失敗しました：" + str(last))

def clean(pcm, rate):
    """音声の最初と最後に混ざる「ザッ」という雑音を取り除き、なめらかにつなぐ"""
    a = pcm.astype(np.float32)
    w = max(1, rate // 100)                                   # 10ms単位で音量を見る
    n = len(a) // w
    if n < 20: return pcm
    rms = np.sqrt((a[:n*w].reshape(n, w) ** 2).mean(axis=1))
    quiet = rms < 0.03 * np.percentile(rms, 90)
    end = n
    tail = 50                                                 # 最後の0.5秒を確認
    for i in range(n - 6, max(n - tail, 0), -1):              # 末尾の雑音の手前にある無音を探す
        if quiet[i:i+5].all() and not quiet[i+5:n].all():
            end = i + 3; break
    start = 0
    for i in range(0, min(10, n - 4)):                        # 先頭0.1秒以内の雑音のあとの無音を探す
        if quiet[i:i+4].all():
            if i > 0: start = i + 2
            break
    out = a[start*w:end*w]
    f = min(len(out)//2, int(rate*0.015))                     # 15msのフェードで「プツッ」も防ぐ
    if f > 0:
        out[:f] *= np.linspace(0, 1, f); out[-f:] *= np.linspace(1, 0, f)
    return out.astype(np.int16)

def _split_by_pauses(pcm, rate, weights):
    """1回でまとめて作った音声を、文字数の比率を目安に、近くの「間（無音）」で切り分ける"""
    w = rate // 100
    n = len(pcm) // w
    rms = np.sqrt((pcm[:n*w].astype(np.float32).reshape(n, w) ** 2).mean(axis=1))
    quiet = rms < 0.05 * np.percentile(rms, 90)
    total = sum(weights); cuts = []; acc = 0
    for wt in weights[:-1]:
        acc += wt
        target = int(n * acc / total)
        lo, hi = max(1, target - 800), min(n - 1, target + 800)     # 前後8秒の範囲で探す
        best, best_len, i = target, 0, lo
        while i < hi:
            if quiet[i]:
                j = i
                while j < hi and quiet[j]: j += 1
                run = j - i
                score = run - abs((i + j) // 2 - target) / 200     # 長い無音（区切りの間）を最優先
                if score > best_len: best, best_len = (i + j) // 2, score
                i = j
            else:
                i += 1
        cuts.append(best * w)
    edges = [0] + cuts + [len(pcm)]
    out = []
    for a, b in zip(edges[:-1], edges[1:]):
        seg = pcm[a:b].astype(np.float32)
        m = len(seg) // w                                   # 前後の長すぎる無音を0.25秒まで詰める
        if m > 10:
            r2 = np.sqrt((seg[:m*w].reshape(m, w) ** 2).mean(axis=1))
            loud = np.where(r2 >= 0.05 * np.percentile(rms, 90))[0]
            if len(loud):
                s0 = max(0, loud[0] - 25) * w; e0 = min(m, loud[-1] + 26) * w
                seg = seg[s0:e0]
        f = min(len(seg) // 2, int(rate * 0.01))
        if f > 0: seg[:f] *= np.linspace(0, 1, f); seg[-f:] *= np.linspace(1, 0, f)
        out.append(seg.astype(np.int16))
    return out

def synth_slides(slides, max_chars=None, with_lines=False):
    """スライドを数枚ずつまとめて音声にし（呼び出し回数を節約）、スライドごとに切り分けて返す。
    with_lines=True なら (音声, レート, 発言ごとの音声のリスト or None) を返す"""
    import time
    max_chars = max_chars or int(os.environ.get("TTS_CHUNK_CHARS", "700"))
    groups, cur, cur_len = [], [], 0
    for s in slides:
        L = sum(len(t["text"]) for t in s["dialogue"])
        if cur and cur_len + L > max_chars:
            groups.append(cur); cur, cur_len = [], 0
        cur.append(s); cur_len += L
    if cur: groups.append(cur)
    result = []
    for gi, g in enumerate(groups):
        dialogue = []
        for si, s in enumerate(g):                       # スライドの区切りに長い間を入れて、切り分けやすくする
            for ti, t in enumerate(s["dialogue"]):
                last = ti == len(s["dialogue"]) - 1 and si < len(g) - 1
                dialogue.append({"speaker": t["speaker"], "text": t["text"] + (" [long pause]" if last else "")})
        pcm, rate = synth_dialogue(dialogue)
        import align                                     # 文字起こしで発言の始まりを見つけて切る（字幕ずれ防止）
        lines = align.cut(pcm, rate, [t["text"] for s in g for t in s["dialogue"]])
        if lines is not None:
            k = 0
            for s in g:
                ls = lines[k:k + len(s["dialogue"])]; k += len(s["dialogue"])
                result.append((np.concatenate(ls), rate, ls) if with_lines else (np.concatenate(ls), rate))
        else:                                            # 使えないときは従来の方法（「間」と文字数で推測）
            weights = [sum(len(t["text"]) + 4 for t in s["dialogue"]) for s in g]
            pieces = _split_by_pauses(pcm, rate, weights) if len(g) > 1 else [pcm]
            result += [(p, rate, None) if with_lines else (p, rate) for p in pieces]
        if os.environ.get("MOCK_TTS") != "1" and gi < len(groups) - 1:
            time.sleep(int(os.environ.get("TTS_WAIT_SEC", "25")))
    return result, len(groups)
