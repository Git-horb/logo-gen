# app.py
import gradio as gr
import time
import random
import re
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# -------------------------------
# Config
# -------------------------------
HEADLESS = True       # False for local debugging
MIN_DELAY = 2
MAX_DELAY = 5

# Optional proxy for Playwright
PROXY = None
# PROXY = "http://user:pass@ip:port"

# -------------------------------
# Utils
# -------------------------------
def human_delay():
    """Random delay to mimic human behavior"""
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

def detect_cloudflare(html: str):
    """Detect if page is blocked by Cloudflare"""
    return "Just a moment" in html or "cf-browser-verification" in html or "cloudflare" in html.lower()

def find_style_jina(style_name: str):
    """Use Jina AI search to find style URL"""
    try:
        search_url = f"https://r.jina.ai/https://en.ephoto360.com/index/search?q={style_name}"
        res = requests.get(search_url, timeout=15)
        match = re.search(r'https://en\.ephoto360\.com/[^"]+\.html', res.text)
        if match:
            return match.group(0), None
        return None, f"Style '{style_name}' not found via Jina"
    except Exception as e:
        return None, f"Jina search failed: {str(e)}"

# -------------------------------
# Generator
# -------------------------------
def generate_logo(text, style):
    """Generate logo via Ephoto360 using Playwright + Jina"""
    if not text or not style:
        return None, "Fill in both text and style fields"

    logs = []
    try:
        # --- 1. Search style via Jina ---
        logs.append(f"Searching for style '{style}' via Jina...")
        style_url, err = find_style_jina(style)
        if err:
            return None, "\n".join(logs + [err])
        logs.append(f"Found style URL: {style_url}")

        # --- 2. Start Playwright ---
        with sync_playwright() as p:
            args = ["--disable-blink-features=AutomationControlled"]
            browser = p.chromium.launch(
                headless=HEADLESS,
                args=args,
                proxy={"server": PROXY} if PROXY else None
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
            )
            page = context.new_page()

            # --- 3. Open style page ---
            logs.append("Opening style page...")
            page.goto(style_url, timeout=60000)
            human_delay()

            html = page.content()
            if detect_cloudflare(html):
                browser.close()
                return None, "\n".join(logs + ["Blocked by Cloudflare on style page"])

            soup = BeautifulSoup(html, "html.parser")
            token = soup.find("input", {"name": "token"})
            build_server = soup.find("input", {"name": "build_server"})
            build_server_id = soup.find("input", {"name": "build_server_id"})

            if not token or not build_server or not build_server_id:
                browser.close()
                return None, "\n".join(logs + ["Failed to extract required tokens"])

            logs.append("Tokens extracted successfully")

            # --- 4. Submit generation request ---
            payload = {
                "text[]": text,
                "submit": "Go",
                "token": token["value"],
                "build_server": build_server["value"],
                "build_server_id": build_server_id["value"]
            }

            create_url = "https://en.ephoto360.com/effect/create-image"
            logs.append("Submitting generation request...")
            response = page.request.post(create_url, form=payload, timeout=60000)

            if response.status != 200:
                browser.close()
                return None, "\n".join(logs + [f"Server returned {response.status}"])

            result = response.json()
            if not result.get("success"):
                browser.close()
                return None, "\n".join(logs + [f"Ephoto error: {result}"])

            final_image = payload["build_server"] + result["full_image"]
            logs.append("Image generated successfully")

            browser.close()
            return final_image, "\n".join(logs)

    except Exception as e:
        return None, f"Runtime error: {str(e)}"

# -------------------------------
# Gradio UI
# -------------------------------
with gr.Blocks() as demo:
    gr.Markdown("## 🧠 Ephoto360 Browser Generator with Jina Search (Cloudflare Safe)")

    with gr.Row():
        txt = gr.Textbox(label="Logo Text")
        stl = gr.Textbox(label="Style (example: neon)")

    btn = gr.Button("Generate")
    img = gr.Image()
    logs = gr.Textbox(label="Logs", lines=10)

    btn.click(generate_logo, [txt, stl], [img, logs])

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
