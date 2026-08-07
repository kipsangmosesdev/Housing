import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

# ========== CONFIG ==========

cdn_urls = [
    "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css",
    "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css",
    "https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&family=Karla:wght@400;500;700&display=swap",
    "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",
    "https://unpkg.com/leaflet-control-geocoder@1.13.0/dist/Control.Geocoder.css",
    "https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css",
    "https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css",
    "https://unpkg.com/leaflet-routing-machine@3.2.12/dist/leaflet-routing-machine.css",
    "https://cdn.jsdelivr.net/npm/leaflet.locatecontrol/dist/L.Control.Locate.min.css",
    "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"
]

sender_email = "kimtaim75@gmail.com"      # Replace with your Gmail
receiver_email = "kipsangmoses@outlook.com"    # Replace with your destination email
app_password = "zpzksnbfgodgihhd"         # Use Gmail App Password, NOT normal password

# ========== CDN Check ==========

def check_cdn_links():
    results = []
    for url in cdn_urls:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                results.append((url, "✅ OK"))
            else:
                results.append((url, f"⚠️ Status {response.status_code}"))
        except requests.exceptions.RequestException as e:
            results.append((url, f"❌ Error: {str(e)}"))
    return results

# ========== Email Sender ==========

def send_email(report):
    subject = f"CDN Check Report – {datetime.now().strftime('%Y-%m-%d')}"
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject

    # Format email body
    body = "📊 Daily CDN Health Report:\n\n"
    for url, status in report:
        body += f"{status} - {url}\n"

    msg.attach(MIMEText(body, 'plain'))

    # Send email
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, app_password)
            server.send_message(msg)
        print("✅ Report sent to email successfully.")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

# ========== Run Script ==========

if __name__ == "__main__":
    report = check_cdn_links()
    send_email(report)
