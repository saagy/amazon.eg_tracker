import flet as ft
import asyncio
import random
import os
from dotenv import load_dotenv, set_key
from playwright.async_api import async_playwright
import httpx

# Load existing config
load_dotenv()

async def send_telegram(message, token, chat_id):
    """Send a message to Telegram"""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    async with httpx.AsyncClient() as client:
        await client.post(url, data=payload)

class TrackerGUI:
    def __init__(self):
        self.is_running = False
        self.browser = None
        self.context = None
        self.price_history = []  # Store last 10 prices for trend analysis
        self.consecutive_failures = 0
        self.max_failures = 3  # Stop after 3 consecutive errors
        
    async def start_tracking(self, e):
        url = self.url_input.value.strip()
        target_price = self.target_price_input.value.strip()
        token = self.telegram_token_input.value.strip()
        chat_id = self.chat_id_input.value.strip()
        interval = self.interval_input.value.strip()
        
        # Validation
        if not url or not target_price or not token or not chat_id or not interval:
            self.status_text.value = "❌ Please fill all fields"
            self.page.update()
            return
            
        try:
            target_price = float(target_price)
            interval = int(interval)
        except ValueError:
            self.status_text.value = "❌ Invalid price or interval"
            self.page.update()
            return
        
        # Save settings to .env
        set_key(".env", "PRODUCT_URL", url)
        set_key(".env", "TARGET_PRICE", str(target_price))
        set_key(".env", "TELEGRAM_TOKEN", token)
        set_key(".env", "CHAT_ID", chat_id)
        set_key(".env", "CHECK_INTERVAL", str(interval))
        
        self.is_running = True
        self.start_button.disabled = True
        self.stop_button.disabled = False
        self.status_text.value = "✅ Tracker started..."
        self.price_history_text.value = "Price History: N/A"
        self.log_text.value = ""
        self.page.update()
        
        # Start tracking loop
        await self.run_tracker(url, target_price, token, chat_id, interval)
    
    async def run_tracker(self, url, target_price, token, chat_id, interval):
        async with async_playwright() as p:
            try:
                self.browser = await p.chromium.launch(headless=True)
                self.context = await self.browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                self.price_history = []
                self.consecutive_failures = 0
                
                while self.is_running:
                    try:
                        page = await self.context.new_page()
                        
                        # Scrape price
                        await page.goto(url, wait_until="domcontentloaded")
                        
                        # Check if only available from third-party sellers
                        buying_options_btn = await page.query_selector("#buybox-see-all-buying-choices")
                        if buying_options_btn:
                            self.status_text.value = "⚠️ Only available from third-party sellers"
                            self.log_text.value += "Only available from third-party sellers\n"
                            await page.close()
                            self.consecutive_failures = 0
                            wait_time = random.uniform(interval * 0.8, interval * 1.2)
                            await self.countdown_sleep(wait_time)
                            continue
                        
                        # Check if out of stock
                        out_of_stock_text = await page.query_selector("#outOfStock")
                        if out_of_stock_text:
                            self.status_text.value = "❌ Out of stock"
                            self.log_text.value += "Out of stock\n"
                            await page.close()
                            self.consecutive_failures = 0
                            wait_time = random.uniform(interval * 0.8, interval * 1.2)
                            await self.countdown_sleep(wait_time)
                            continue
                        
                        main_container = await page.query_selector("#apex_desktop")
                        
                        if main_container:
                            whole = await main_container.query_selector(".a-price-whole")
                            if whole:
                                whole_text = await whole.inner_text()
                                clean_price = "".join(c for c in whole_text if c.isdigit() or c == '.')
                                current_price = float(clean_price)
                                
                                # Track price history and show trend
                                self.price_history.append(current_price)
                                if len(self.price_history) > 10:
                                    self.price_history.pop(0)
                                
                                # Update price history display
                                history_display = " → ".join([f"{p:.0f}" for p in self.price_history])
                                self.price_history_text.value = f"Price History (EGP): {history_display}"
                                
                                trend = self.get_price_trend()
                                self.log_text.value += f"Current Price: {current_price} EGP {trend}\n"
                                self.consecutive_failures = 0
                                
                                if current_price <= target_price:
                                    self.status_text.value = f"🚨 PRICE DROP! {current_price} EGP"
                                    self.log_text.value += f"🚨 ALERT: Price dropped to {current_price} EGP! Tracker stopped.\n"
                                    await send_telegram(f"🚨 PRICE DROP! {current_price} EGP\nBuy now: {url}", token, chat_id)
                                    self.is_running = False
                                    self.start_button.disabled = False
                                    self.stop_button.disabled = True
                                else:
                                    self.status_text.value = f"Price: {current_price} EGP (Target: {target_price}) {trend}"
                            else:
                                self.status_text.value = "⚠️ Item unavailable"
                                self.log_text.value += "Item unavailable or out of stock\n"
                                self.consecutive_failures = 0
                        
                        await page.close()
                        
                    except Exception as ex:
                        self.consecutive_failures += 1
                        self.log_text.value += f"Error: {str(ex)} [Attempt {self.consecutive_failures}/{self.max_failures}]\n"
                        
                        if self.consecutive_failures >= self.max_failures:
                            self.status_text.value = f"🛑 Stopped: Too many errors ({self.max_failures})"
                            self.log_text.value += f"\n⚠️ Tracker stopped due to {self.max_failures} consecutive errors\n"
                            self.is_running = False
                        else:
                            wait_time = random.uniform(interval * 0.8, interval * 1.2)
                            await self.countdown_sleep(wait_time)
                            continue
                    
                    # Keep last 20 lines
                    lines = self.log_text.value.split('\n')
                    if len(lines) > 20:
                        self.log_text.value = '\n'.join(lines[-20:])
                    
                    self.page.update()
                    wait_time = random.uniform(interval * 0.8, interval * 1.2)
                    await self.countdown_sleep(wait_time)
            
            finally:
                # Graceful cleanup - always close browser
                if self.context:
                    await self.context.close()
                if self.browser:
                    await self.browser.close()
                self.context = None
                self.browser = None
    
    def stop_tracking(self, e):
        self.is_running = False
        self.start_button.disabled = False
        self.stop_button.disabled = True
        self.status_text.value = "⏹️ Tracker stopped"
        self.page.update()
    
    def clear_logs(self, e):
        self.log_text.value = ""
        self.page.update()
    
    async def countdown_sleep(self, duration):
        """Sleep while showing countdown in status"""
        for remaining in range(int(duration), 0, -1):
            if not self.is_running:
                break
            self.status_text.value = f"Next check in {remaining}s..."
            self.page.update()
            await asyncio.sleep(1)
    
    def get_price_trend(self):
        """Analyze price history and return trend indicator"""
        if len(self.price_history) < 2:
            return ""
        
        current = self.price_history[-1]
        previous = self.price_history[-2]
        
        if current < previous:
            return "📉"
        elif current > previous:
            return "📈"
        else:
            return "→"
    
    def on_window_close(self, e):
        """Handle graceful shutdown when window closes"""
        self.is_running = False
    
    def build(self, page):
        self.page = page
        page.title = "Amazon Price Tracker"
        page.window.width = 900
        page.window.height = 1000
        
        # Handle window close event for graceful shutdown
        page.on_close = self.on_window_close
        
        # Get existing values
        existing_url = os.getenv("PRODUCT_URL", "")
        existing_target = os.getenv("TARGET_PRICE", "5000")
        existing_token = os.getenv("TELEGRAM_TOKEN", "")
        existing_chat_id = os.getenv("CHAT_ID", "")
        existing_interval = os.getenv("CHECK_INTERVAL", "300")
        
        # Title
        title = ft.Text("Amazon Price Tracker", size=24, weight="bold")
        
        # URL Input
        self.url_input = ft.TextField(
            label="Amazon URL",
            value=existing_url,
            multiline=True,
            min_lines=2,
        )
        
        # Target Price Input
        self.target_price_input = ft.TextField(
            label="Target Price (EGP)",
            value=existing_target,
            keyboard_type="number",
        )
        
        # Telegram Token Input
        self.telegram_token_input = ft.TextField(
            label="Telegram Bot Token",
            value=existing_token,
            password=True,
        )
        
        # Chat ID Input
        self.chat_id_input = ft.TextField(
            label="Telegram Chat ID",
            value=existing_chat_id,
        )
        
        # Interval Input
        self.interval_input = ft.TextField(
            label="Check Interval (seconds)",
            value=existing_interval,
            keyboard_type="number",
        )
        interval_help = ft.Text("Recommended: 300 (5 min), 600 (10 min)", size=11, color="grey")
        
        # Status Text
        self.status_text = ft.Text("Ready", size=14, color="blue")
        
        # Price History Display
        self.price_history_text = ft.Text("Price History: N/A", size=11, color="grey")
        
        # Log Text
        self.log_text = ft.Text("", size=10, selectable=True)
        log_container = ft.Container(
            content=ft.Column([self.log_text], scroll="auto"),
            height=350,
            border=ft.Border.all(1, "grey"),
            padding=10,
        )
        
        # Buttons
        self.start_button = ft.Button(
            "Start Tracking",
            on_click=self.start_tracking,
            bgcolor="green",
            color="white",
        )
        
        self.stop_button = ft.Button(
            "Stop Tracking",
            on_click=self.stop_tracking,
            disabled=True,
            bgcolor="red",
            color="white",
        )
        
        self.clear_button = ft.Button(
            "Clear Logs",
            on_click=self.clear_logs,
            bgcolor="grey",
            color="white",
        )
        
        button_row = ft.Row([self.start_button, self.stop_button], spacing=10)
        
        # Left Column - Input Fields
        left_column = ft.Column([
            title,
            ft.Divider(),
            self.url_input,
            self.target_price_input,
            self.telegram_token_input,
            self.chat_id_input,
            self.interval_input,
            interval_help,
            button_row,
        ], spacing=10, scroll="auto", width=400)
        
        # Right Column - Status and Logs
        logs_header = ft.Row([
            ft.Text("Logs:", weight="bold"),
            self.clear_button,
        ], spacing=10)
        
        right_column = ft.Column([
            ft.Text("Status:", weight="bold"),
            self.status_text,
            self.price_history_text,
            logs_header,
            log_container,
        ], spacing=10, scroll="auto", expand=True)
        
        # Layout - Horizontal
        content = ft.Row([
            left_column,
            ft.VerticalDivider(),
            right_column,
        ], spacing=10, expand=True)
        
        page.add(
            ft.Container(
                content=content,
                padding=20,
                expand=True,
            )
        )

def main(page: ft.Page):
    gui = TrackerGUI()
    gui.build(page)

if __name__ == "__main__":
    ft.run(main)
