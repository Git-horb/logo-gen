import gradio as gr
import time
import random
import re
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

HEADLESS = True
MIN_DELAY = 2
MAX_DELAY = 5

def human_delay():
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

def detect_cloudflare(html: str):
    return (
        "Just a moment" in html
        or "cf-browser-verification" in html
        or "cloudflare" in html.lower()
    )

def find_logo_style_browser(page, style_name):
    search_url = f"https://en.ephoto360.com/index/search?q={style_name}"
    page.goto(search_url, timeout=60000)
    human_delay()

    html = page.content()

    if detect_cloudflare(html):
        return None, "Cloudflare blocked search page"

    match = re.search(r'https://en\.ephoto360\.com/[^"]+\.html', html)
    if not match:
        return None, "Style not found"

    return match.group(0), None

def generate_logo(text, style):
    if not text or not style:
        return None, "Fill all fields"

    logs = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=HEADLESS,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage"
                ]
            )

            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
            )

            page = context.new_page()

            logs.append("Searching style...")

            style_url, err = find_logo_style_browser(page, style)
            if err:
                browser.close()
                return None, err

            logs.append("Opening style page...")

            page.goto(style_url, timeout=60000)
            human_delay()

            html = page.content()

            if detect_cloudflare(html):
                browser.close()
                return None, "Blocked by Cloudflare on style page"

            soup = BeautifulSoup(html, "html.parser")

            token = soup.find("input", {"name": "token"})
            build_server = soup.find("input", {"name": "build_server"})
            build_server_id = soup.find("input", {"name": "build_server_id"})

            if not token or not build_server or not build_server_id:
                browser.close()
                return None, "Failed to extract tokens"

            logs.append("Tokens extracted")

            payload = {
                "text[]": text,
                "submit": "Go",
                "token": token["value"],
                "build_server": build_server["value"],
                "build_server_id": build_server_id["value"]
            }

            create_url = "https://en.ephoto360.com/effect/create-image"

            logs.append("Generating image...")

            response = page.request.post(create_url, form=payload, timeout=60000)

            if response.status != 200:
                browser.close()
                return None, f"Server returned {response.status}"

            result = response.json()

            if not result.get("success"):
                browser.close()
                return None, f"Ephoto error: {result}"

            final_image = payload["build_server"] + result["full_image"]

            logs.append("Done.")

            browser.close()

            return final_image, "\n".join(logs)

    except Exception as e:
        return None, f"Runtime error: {str(e)}"

with gr.Blocks() as demo:
    gr.Markdown("## 🚀 Ephoto360 Browser Generator (Fly.io Edition)")

    with gr.Row():
        txt = gr.Textbox(label="Text")
        stl = gr.Textbox(label="Style (example: neon)")

    btn = gr.Button("Generate")
    img = gr.Image()
    status = gr.Textbox(label="Logs", lines=8)

    btn.click(generate_logo, [txt, stl], [img, status])

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
