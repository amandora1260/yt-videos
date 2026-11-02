"""Gmailで原稿メールを受け取り、完成した動画をメールで送る（アプリパスワードを使用）"""
import email, imaplib, json, os, re, smtplib
from email.header import decode_header
from email.message import EmailMessage

ADDR = lambda: os.environ["GMAIL_ADDRESS"]
PW = lambda: os.environ["GMAIL_APP_PASSWORD"]

def _body_text(msg):
    parts = msg.walk() if msg.is_multipart() else [msg]
    for p in parts:
        if p.get_content_type() == "text/plain":
            return p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", "replace")
    for p in (msg.walk() if msg.is_multipart() else [msg]):   # HTMLしか無い場合
        if p.get_content_type() == "text/html":
            html = p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", "replace")
            html = re.sub(r"<br\s*/?>", "\n", html); return re.sub(r"<[^>]+>", "", html)
    return ""

def extract_json(text):
    """本文の <<<JSON と JSON>>> の間を取り出す"""
    import html as h
    m = re.search(r"<<<JSON(.*?)JSON>>>", h.unescape(text), re.S)
    if not m: raise ValueError("原稿メールに <<<JSON 〜 JSON>>> が見つかりません")
    return json.loads(m.group(1).strip())

def fetch_brief(date_str):
    """件名 [YT-BRIEF] YYYY-MM-DD のメールのうち最新のものを読む"""
    if os.environ.get("MOCK_BRIEF"):
        return json.load(open(os.environ["MOCK_BRIEF"], encoding="utf-8"))
    im = imaplib.IMAP4_SSL("imap.gmail.com"); im.login(ADDR(), PW())
    im.select('"[Gmail]/All Mail"', readonly=True)
    typ, data = im.search(None, "X-GM-RAW", f'"subject:YT-BRIEF subject:{date_str} newer_than:2d"')
    ids = data[0].split()
    if not ids:
        im.logout(); return None
    typ, msgdata = im.fetch(ids[-1], "(RFC822)"); im.logout()
    return extract_json(_body_text(email.message_from_bytes(msgdata[0][1])))

def send(subject, body, attachments=()):
    msg = EmailMessage()
    msg["From"] = ADDR(); msg["To"] = ADDR(); msg["Subject"] = subject
    msg.set_content(body)
    for path, mtype, sub in attachments:
        with open(path, "rb") as f:
            msg.add_attachment(f.read(), maintype=mtype, subtype=sub, filename=os.path.basename(path))
    if os.environ.get("DRY_RUN") == "1":                       # 動作確認用：送らずにファイルに保存
        open("out/mail_preview.eml", "wb").write(bytes(msg)); return
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(ADDR(), PW()); s.send_message(msg)
