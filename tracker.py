import asyncio
import random
import time
import httpx  # Use httpx for async requests
from playwright.async_api import async_playwright

# --- CONFIGURATION ---
PRODUCT_URL = "https://www.amazon.eg/-/en/WD_BLACK-SN850X-Internal-Gaming-Solid/dp/B0B7CKVCCV"
TARGET_PRICE = 6000
TELEGRAM_TOKEN = "8578286728:AAGKOzgLBH_Q5yJamvHfi_XMQ2lyy5HT62E"
CHAT_ID = "929550853"
CHECK_INTERVAL = 5

async def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    async with httpx.AsyncClient() as client:
        await client.post(url, data=payload)
async def get_price(page):
    try:
        print(f"[{time.strftime('%H:%M:%S')}] Checking price for SN850X...")
        await page.goto(PRODUCT_URL, wait_until="domcontentloaded")
        # 1. Check if the "See All Buying Options" button exists
        # If this button is there, Amazon isn't selling it directly right now.
        buying_options_btn = await page.query_selector("#buybox-see-all-buying-choices")
        if buying_options_btn:
            print("Status: Only available from third-party sellers (Buying Options).")
            return None
        # 2. Check if it's explicitly Out of Stock
        out_of_stock_text = await page.query_selector("#outOfStock")
        if out_of_stock_text:
            print("Status: Currently out of stock.")
            return None
        # 3. Targeted Search: Look ONLY in the main product section
        # We use #apex_desktop which is the container for the main price and title
        main_container = await page.query_selector("#apex_desktop")
        if main_container:
            # We look for the 'offscreen' price inside ONLY the main container
            price_element = await main_container.query_selector(".a-price .a-offscreen")
            if price_element:
                price_text = await price_element.inner_text()
                clean_price = "".join(c for c in price_text if c.isdigit() or c == '.')
                return float(clean_price)
            
        print("Status: Main price not found (likely unavailable).")
        return None

    except Exception as e:
        print(f"Error during check: {e}")
        return None

async def get_price(page):
    try:
        print(f"[{time.strftime('%H:%M:%S')}] Checking price...")
        await page.goto(PRODUCT_URL, wait_until="domcontentloaded")
        # Selector for the whole price and the fraction
        # We use a more robust approach to grab the visible price text
        price_element = await page.wait_for_selector(".a-price .a-offscreen", timeout=5000)

        if price_element:
            price_text = await price_element.inner_text()
            # Regex or simple cleaning to get only numbers and dots
            # Example: 'EGP 3,003.00' -> '3003.00'
            clean_price = "".join(c for c in price_text if c.isdigit() or c == '.')
            return float(clean_price)

    except Exception as e:
        print(f"Error scraping price: {e}")
    return None

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        while True:
            page = await context.new_page()
            current_price = await get_price(page)
            if current_price:
                print(f"Current Price: {current_price} EGP")
                if current_price <= TARGET_PRICE:
                    await send_telegram(f"🚨 PRICE DROP! {current_price} EGP\nBuy now: {PRODUCT_URL}")
                    print("Alert sent!")

            await page.close() # Close page but keep browser open
            wait_time = random.uniform(CHECK_INTERVAL * 0.8, CHECK_INTERVAL * 1.2)
            print(f"Waiting {int(wait_time)}s for next check...")
            await asyncio.sleep(wait_time)
if __name__ == "__main__":
    asyncio.run(main())