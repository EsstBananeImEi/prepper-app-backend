import smtplib, ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

sender = "webmaster@meinedevpath.de"
recipient = "psychoorc@gmx.net"
smtp_server = "smtp.strato.de"
smtp_port = 465
username = "webmaster@meinedevpath.de"
password = "KzERNZu#cQ_pSw2"

msg = MIMEMultipart("alternative")
msg["Subject"] = "Test E-Mail"
msg["From"] = sender
msg["To"] = recipient
part = MIMEText("<h1>Test</h1><p>Dies ist eine Testnachricht.</p>", "html", "utf-8")
msg.attach(part)

context = ssl.create_default_context()
try:
    with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
        server.login(username, password)
        server.sendmail(sender, recipient, msg.as_string())
    print("Test-E-Mail wurde erfolgreich gesendet!")
except Exception as e:
    print("Fehler beim Senden der Test-E-Mail:", e)
