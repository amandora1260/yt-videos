"""音声を文字起こし（Whisper）して台本と照らし合わせ、各発言が始まる位置で音声を切る。
「間」と文字数で推測するより正確で、字幕と声がずれにくい。
文字起こしが使えないとき（ライブラリなし・失敗）は None を返し、呼び出し側が従来の方法に戻す。"""
import difflib, os, re
import numpy as np

MODEL = os.environ.get("WHISPER_MODEL", "small")
_M = None

def _model():
    global _M
    if _M is None:
        from faster_whisper import WhisperModel
        _M = WhisperModel(MODEL, device="cpu", compute_type="int8")
    return _M

def _norm(t):
    return re.sub(r"[\s、。，．・「」『』（）()！？!?…ー〜~,:：%％+\-]", "", t)

def _words(pcm, rate):
    a = pcm.astype(np.float32) / 32768
    if rate != 16000:                                       # Whisperは16kHz
        idx = np.linspace(0, len(a) - 1, int(len(a) * 16000 / rate)); a = np.interp(idx, np.arange(len(a)), a).astype(np.float32)
    segs, _ = _model().transcribe(a, language="ja", word_timestamps=True, condition_on_previous_text=False)
    return [(w.start, w.end, w.word) for s in segs for w in s.words]

def line_starts(lines, words):
    """台本の発言ごとに、声が始まる時刻（秒）を返す。見つからない発言は None"""
    st, owner, head = "", [], []
    for i, t in enumerate(lines):
        n = _norm(t); head.append(len(st)); st += n; owner += [i] * len(n)
    hy, ht = "", []
    for s, e, w in words:
        n = _norm(w)
        for k, ch in enumerate(n): hy += ch; ht.append(s + (e - s) * k / max(1, len(n)))
    first = {}
    for a, b, size in difflib.SequenceMatcher(None, st, hy, autojunk=False).get_matching_blocks():
        for k in range(size):
            if a + k >= len(owner): break
            i = owner[a + k]; pos = a + k - head[i]       # 発言の何文字目で一致したか
            if i not in first and pos <= 6: first[i] = ht[b + k] - pos * 0.12
    return [first.get(i) for i in range(len(lines))]

def cut(pcm, rate, lines):
    """発言ごとに切り分けた音声のリストを返す（失敗したら None）"""
    if len(lines) <= 1: return [pcm]
    if os.environ.get("MOCK_TTS") == "1" or os.environ.get("NO_ALIGN") == "1": return None
    starts = None
    for attempt in range(2):                                # 一時的な失敗（モデルの取得など）に備えて1回やり直す
        try:
            starts = line_starts(lines, _words(pcm, rate)); break
        except Exception as e:                              # ライブラリがない・モデルを取れない等
            print("文字起こしでの切り分けに失敗：", e)
    if starts is None: return None
    dur = len(pcm) / rate
    found = sum(s is not None for s in starts[1:])
    if found < (len(lines) - 1) * 0.6:                      # 照合できた発言が少なすぎるときは信用しない
        print(f"文字起こしの照合が少ないため従来の方法で切ります（{found}/{len(lines)-1}）"); return None
    # 見つからなかった発言は、前後の見つかった発言のあいだを文字数で按分する
    w = [len(_norm(t)) + 3 for t in lines]; starts[0] = 0.0
    known = [i for i, s in enumerate(starts) if s is not None] + [len(lines)]
    ends = {len(lines): dur}
    for a, b in zip(known[:-1], known[1:]):
        ta, tb = starts[a], ends.get(b, starts[b] if b < len(lines) else dur)
        for i in range(a + 1, b):
            starts[i] = ta + (tb - ta) * sum(w[a:i]) / sum(w[a:b])
    # 各開始位置を、すぐ手前の一番静かな所（声の切れ目）に合わせる
    fw = rate // 100; n = len(pcm) // fw
    rms = np.sqrt((pcm[:n * fw].astype(np.float32).reshape(n, fw) ** 2).mean(axis=1))
    cuts, prev = [], 0
    for s in starts[1:]:
        c = int(s * 100); lo = max(prev + 20, c - 50); hi = min(n - 1, c + 15)
        if hi > lo:
            win = rms[lo:hi]; q = win <= win.min() * 1.5 + 1  # 静かな所が続く区間の真ん中
            idx = np.where(q)[0]; c = lo + int(idx[np.argmin(np.abs(idx - (c - lo - 5)))])
        thr = 0.05 * np.percentile(rms, 90)               # 無音が長いときは、声の出だしの0.12秒前まで寄せる
        lim = min(n - 1, c + 300); k = c                 # 続く無音の中だけを進む（最大3秒）
        while k + 1 < lim and rms[k + 1] < thr: k += 1
        c = max(c, k - 12)
        c = max(c, prev + 20); cuts.append(c); prev = c
    edges = [0] + [c * fw for c in cuts] + [len(pcm)]
    return [pcm[a:b] for a, b in zip(edges[:-1], edges[1:])]
