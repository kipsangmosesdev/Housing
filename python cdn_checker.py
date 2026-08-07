from datetime import datetime

import requests

# List of CDN URLs to check
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

def check_cdn_links():
    results = []
    print(f"CDN Check Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    for url in cdn_urls:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                results.append((url, "✅ OK"))
            else:
                results.append((url, f"⚠️ Status {response.status_code}"))
        except requests.exceptions.RequestException as e:
            results.append((url, f"❌ Error: {str(e)}"))

    for url, status in results:
        print(f"{status} - {url}")

if __name__ == "__main__":
    check_cdn_links()
