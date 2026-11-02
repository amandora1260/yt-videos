"""毎朝の処理：原稿メールを読む → 2人の音声 → スライド動画 → Gmailに送る"""
import datetime as dt, os, sys, time, traceback
sys.path.insert(0, os.path.dirname(__file__))
import mailer, render, tts

JST = dt.timezone(dt.timedelta(hours=9))
MAX_MB = 23                                               # Gmailの添付上限（25MB）に余裕を持たせる

def main():
    today = dt.datetime.now(JST).strftime("%Y-%m-%d")
    os.makedirs("out", exist_ok=True)
    b = None
    for i in range(7):                                    # 原稿メールが遅れても最大30分は5分おきに待つ
        b = mailer.fetch_brief(today)
        if b is not None or os.environ.get("MOCK_BRIEF"): break
        if i < 6: time.sleep(300)
    if b is None:
        mailer.send(f"【動画失敗】{today} 原稿メールが見つかりません",
                    "5:30の米国株ブリーフのタスクから、件名「[YT-BRIEF] " + today + "」の原稿メールが届いていません。\n"
                    "タスクが動いたか、Gmailの送信設定をご確認ください。")
        return
    audios, calls = tts.synth_slides(b["slides"])           # 数枚ずつまとめて作り、呼び出し回数を節約（1日10回まで）
    print(f"音声の呼び出し回数：{calls}回")
    mp4 = f"out/{b.get('date', today)}_米国株ブリーフ.mp4"
    sec, thumb = render.build_video(b, audios, "out/frames", mp4)
    mb = os.path.getsize(mp4) / 1e6
    if mb > MAX_MB:
        raise RuntimeError(f"動画が{mb:.1f}MBあり、メールに添付できません")
    body = (f"今日の動画ができました（{int(sec)//60}分{int(sec)%60}秒）。\n\n"
            "【投稿手順】\n1. 添付の動画を開いて保存\n2. YouTubeアプリの「＋」→「動画」で選択\n"
            "3. 下のタイトル・説明をコピーして貼り付け、公開設定を「公開」にして投稿\n\n"
            "■タイトル\n" + b["yt_title"] + "\n\n■説明\n" + b["yt_description"] + "\n")
    mailer.send(f"【動画完成】{b['date_label']} 米国株モーニングブリーフ", body, [(mp4, "video", "mp4")])
    print(f"完了：{sec:.1f}秒 / {mb:.1f}MB")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        try:
            mailer.send("【動画失敗】米国株ブリーフの動画を作れませんでした",
                        "今日の動画は作成できませんでした（途中までの動画は送っていません）。\n\n原因：" + str(e)[:1500])
        finally:
            sys.exit(1)
