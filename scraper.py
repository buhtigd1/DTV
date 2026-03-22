import requests
import time
import json
import logging
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime
from typing import List, Dict, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("distrotv_scraper")

class DistroTVScraper:
    def __init__(self):
        # Official API Endpoints
        self.feed_url = "https://tv.jsrdn.com/tv_v5/getfeed.php"
        self.epg_url = "https://tv.jsrdn.com/epg/query.php"
        
        # Official App User-Agent for better stream stability
        self.headers = {
            'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 9; AFTT Build/STT9.221129.002) GTV/AFTT DistroTV/2.0.9'
        }

    def fetch_channels(self) -> List[Dict[str, Any]]:
        try:
            logger.info("Fetching DistroTV V5 feed...")
            response = requests.get(f"{self.feed_url}?t={int(time.time())}", headers=self.headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            shows = data.get("shows", {})
            channels = []
            
            for ch_id, ch_data in shows.items():
                if ch_data.get("type") != "live":
                    continue
                
                try:
                    # Navigate nested seasons/episodes structure
                    seasons = ch_data.get("seasons", [])
                    if not seasons: continue
                    
                    episodes = seasons[0].get("episodes", [])
                    if not episodes: continue
                    
                    content = episodes[0].get("content", {})
                    stream_url = content.get("url", "")
                    if not stream_url: continue

                    # Clean URL and extract metadata
                    stream_url = stream_url.split('?', 1)[0]
                    raw_id = ch_data.get("name", "")
                    title = ch_data.get("title", "").strip()
                    
                    # Logic: Split the group string by comma and take only the first category
                    raw_group = ch_data.get("genre", "DistroTV")
                    clean_group = raw_group.split(',')[0].strip()
                    
                    if not raw_id or not title: continue

                    channels.append({
                        'id': f"distrotv-{raw_id}",
                        'raw_id': raw_id,
                        'name': title,
                        'stream_url': stream_url,
                        'logo': ch_data.get("img_logo", ""),
                        'group': clean_group,
                        'description': ch_data.get("description", "").strip()
                    })
                except Exception:
                    continue
            
            logger.info(f"Successfully parsed {len(channels)} live channels.")
            return channels
        except Exception as e:
            logger.error(f"Feed error: {e}")
            return []
    
    def generate_m3u(self, channels: List[Dict[str, Any]]):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
        url_tvg = "https://raw.githubusercontent.com/buhtigd1/DTV/main/epg.xml"
    
        m3u = [
            f'#EXTM3U url-tvg="{url_tvg}"',
            f"# Last Updated: {now} UTC"
        ]

        referrer = "https://www.distro.tv/"
        
        for ch in sorted(channels, key=lambda x: x['name'].lower()):
            # Inject headers for cross-platform playback compatibility
            inf_line = (f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-logo="{ch["logo"]}" '
                        f'group-title="{ch["group"]}" '
                        f'http-referrer="{referrer}" '
                        f'http-origin="{referrer}" '
                        f'http-user-agent="{self.headers["User-Agent"]}",{ch["name"]}')
            m3u.append(inf_line)
            m3u.append(f'#EXTVLCOPT:http-referrer={referrer}')
            m3u.append(f'#EXTVLCOPT:http-origin={referrer}')
            m3u.append(f'#EXTVLCOPT:http-user-agent={self.headers["User-Agent"]}')
            m3u.append(ch["stream_url"])
            
        return "\n".join(m3u)

    def generate_epg_xml(self, channels: List[Dict[str, Any]]):
        root = ET.Element("tv", {"generator-info-name": "DistroTV-Scraper-V5"})
        for ch in channels:
            c_node = ET.SubElement(root, "channel", id=ch['id'])
            ET.SubElement(c_node, "display-name").text = ch['name']
            ET.SubElement(c_node, "icon", src=ch['logo'])

        for ch in channels:
            try:
                resp = requests.get(self.epg_url, params={'ch': ch['raw_id']}, headers=self.headers, timeout=5)
                if resp.status_code == 200:
                    for prog in resp.json().get('listings', []):
                        start = datetime.fromtimestamp(int(prog['start'])).strftime("%Y%m%d%H%M%S +0000")
                        stop = datetime.fromtimestamp(int(prog['end'])).strftime("%Y%m%d%H%M%S +0000")
                        p_node = ET.SubElement(root, "programme", {"start": start, "stop": stop, "channel": ch['id']})
                        ET.SubElement(p_node, "title", lang="en").text = prog.get('title', 'No Title')
                        ET.SubElement(p_node, "desc", lang="en").text = prog.get('description', 'No description available.')
                time.sleep(0.05)
            except Exception:
                continue
        return minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")

if __name__ == "__main__":
    scraper = DistroTVScraper()
    ch_list = scraper.fetch_channels()
    
    if ch_list:
        # STEP 1: Save M3U and JSON first to ensure data is written if EPG hangs
        logger.info(f"Writing {len(ch_list)} channels to dtv.m3u...")
        with open("dtv.m3u", "w", encoding="utf-8") as f:
            f.write(scraper.generate_m3u(ch_list))
        
        with open("channels.json", "w", encoding="utf-8") as f:
            json.dump(ch_list, f, indent=4)
            
        # STEP 2: Attempt EPG
        logger.info("Starting EPG generation...")
        try:
            epg_content = scraper.generate_epg_xml(ch_list)
            with open("epg.xml", "w", encoding="utf-8") as f:
                f.write(epg_content)
            logger.info("EPG file written successfully.")
        except Exception as e:
            logger.error(f"EPG generation failed: {e}")
            
        logger.info("Scraper task finished.")
