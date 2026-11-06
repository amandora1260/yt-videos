"""GitHub Actions用：scripts/ の原稿JSONから動画を作り、videos/ と status/ に書き出す"""
import json, os, sys, time, traceback
sys.path.insert(0, os.path.dirname(__file__))
import tts, anim, short, thumb

REPO = os.environ.get("GITHUB_REPOSITORY", "amandora1260/yt-videos")

def run(path):
    b = json.load(open(path, encoding="utf-8"))
    kind = b.get("kind", "main"); name = os.path.splitext(os.path.basename(path))[0]
    os.makedirs("videos", exist_ok=True); os.makedirs("status", exist_ok=True)
    out = f"videos/{name}.mp4"; st = {"script": path, "kind": kind, "ok": False, "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        if kind == "short":
            sec, _ = short.build(b, out, f"/tmp/w_{name}")
        else:
            audios, calls = tts.synth_slides(b["slides"]); st["tts_calls"] = calls
            sec = anim.build(b, audios, f"/tmp/w_{name}", out)
            try:                                               # サムネ（失敗しても動画は出す）
                tp = thumb.make(b, f"videos/{name}_thumb.png")
                st["thumb_url"] = f"https://raw.githubusercontent.com/{REPO}/main/{tp}"
            except Exception as e:
                traceback.print_exc(); st["thumb_error"] = str(e)[:300]
        st.update(ok=True, seconds=round(sec, 1), mb=round(os.path.getsize(out)/1e6, 1),
                  url=f"https://raw.githubusercontent.com/{REPO}/main/{out}")
    except Exception as e:
        traceback.print_exc(); st["error"] = str(e)[:800]
    json.dump(st, open(f"status/{name}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(st, ensure_ascii=False))

if __name__ == "__main__":
    for p in sys.argv[1:]:
        name = os.path.splitext(os.path.basename(p))[0]
        if os.path.exists(f"status/{name}.json") and json.load(open(f"status/{name}.json")).get("ok"):
            print("作成済みのためスキップ:", p); continue
        run(p)
