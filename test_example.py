import pytest
import json
import time
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

EMAIL    = "miths.124@gmail.com"
PASSWORD = "lqAmrlDA"
BASE_URL = "https://hiring.idenhq.com/"

SESSION_FILE = Path("session.json")

@pytest.fixture(scope="session")
def browser_context():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        if SESSION_FILE.exists():
            context = browser.new_context(storage_state=str(SESSION_FILE))
        else:
            # fresh context, we'll log in below
            context = browser.new_context()
        context.storage_state(path=str(SESSION_FILE))
        yield context
        browser.close()

@pytest.fixture
def page(browser_context):
    page = browser_context.new_page()
    yield page
    page.close()

def test_challenge_navigation(page):
    # 1) Login & launch
    page.goto(BASE_URL)
    page.get_by_role("textbox", name="Email").fill(EMAIL)
    page.get_by_role("textbox", name="Password").fill(PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    page.get_by_role("button", name="Launch Challenge").click()

    # 2) Hidden‑path to listing
    for step in ("Start Journey", "Continue Search", "Inventory Section"):
        page.get_by_role("button", name=step).click()
        page.wait_for_timeout(1000)

    page.wait_for_load_state("networkidle")
    
    max_scrolls = 30  
    found_id_100 = False
    
    for i in range(max_scrolls):
        if page.query_selector("text=ID: 100"):
            print(f"Found ID: 100 after {i+1} scrolls")
            found_id_100 = True
            break
            
        # Scroll in smaller increments for better content loading
        page.evaluate("() => window.scrollBy(0, 500)")
        page.wait_for_timeout(800)  # Longer wait to ensure content loads
        
        # Every 5 scrolls, perform a complete scroll to bottom and wait longer
        if i % 5 == 4:
            page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)
    
    if not found_id_100:
        print("Warning: ID: 100 might not have been found. Continuing with available products.")
    
    page.screenshot(path="debug_screenshot.png")
    
    # 4) Extract product data 
    products = []
    
    product_cards = page.query_selector_all('div[class*="card"], div[class*="product"]')
    print(f"Found {len(product_cards)} potential product cards")
    
    for card in product_cards:
        card_text = card.text_content()
        
        id_match = re.search(r'ID:\s*(\d+)', card_text, re.IGNORECASE)
        if not id_match:
            continue
            
        try:
            product_id = int(id_match.group(1))
            if product_id > 100:
                continue
        except (ValueError, IndexError):
            continue
        
        print(f"Processing card with ID: {product_id}")
        
        heading_match = re.search(r'^(.*?)ID:', card_text, re.DOTALL)
        heading = heading_match.group(1).strip() if heading_match else "Unknown Product"
        
        if not heading or heading == "Unknown Product":
            heading_element = card.query_selector('h1, h2, h3, h4, h5, h6, strong, b, [class*="title"], [class*="name"]')
            if heading_element:
                heading_text = heading_element.text_content().strip()
                # Check if this text doesn't contain field labels
                if not any(label in heading_text.lower() for label in ["id:", "dimensions:", "details:", "cost:", "sku:", "guarantee:", "updated:"]):
                    heading = heading_text
        
        # Define regex patterns for each field
        patterns = {
            "dimensions": r'Dimensions:\s*([^\n\r]*?)(?=ID:|Dimensions:|Details:|Cost:|SKU:|Guarantee:|Updated:|$)',
            "details": r'Details:\s*([^\n\r]*?)(?=ID:|Dimensions:|Details:|Cost:|SKU:|Guarantee:|Updated:|$)',
            "cost": r'Cost:\s*([^\n\r]*?)(?=ID:|Dimensions:|Details:|Cost:|SKU:|Guarantee:|Updated:|$)',
            "sku": r'SKU:\s*([^\n\r]*?)(?=ID:|Dimensions:|Details:|Cost:|SKU:|Guarantee:|Updated:|$)',
            "guarantee": r'Guarantee:\s*([^\n\r]*?)(?=ID:|Dimensions:|Details:|Cost:|SKU:|Guarantee:|Updated:|$)',
            "updated": r'Updated:\s*([^\n\r]*?)(?=ID:|Dimensions:|Details:|Cost:|SKU:|Guarantee:|Updated:|$)'
        }
        
        dimensions = re.search(patterns["dimensions"], card_text, re.IGNORECASE)
        details = re.search(patterns["details"], card_text, re.IGNORECASE)
        cost = re.search(patterns["cost"], card_text, re.IGNORECASE)
        sku = re.search(patterns["sku"], card_text, re.IGNORECASE)
        guarantee = re.search(patterns["guarantee"], card_text, re.IGNORECASE)
        updated = re.search(patterns["updated"], card_text, re.IGNORECASE)
        
        # Create product object
        product = {
            "heading": heading,
            "id": product_id,
            "dimensions": dimensions.group(1).strip() if dimensions else "",
            "Details": details.group(1).strip() if details else "",
            "Cost": cost.group(1).strip() if cost else "",
            "SKU": sku.group(1).strip() if sku else "",
            "Guarantee": guarantee.group(1).strip() if guarantee else "",
            "Updated": updated.group(1).strip() if updated else ""
        }
        
        print(f"  Extracted dimensions: '{product['dimensions']}'")
        print(f"  Extracted details: '{product['Details']}'")
        print(f"  Extracted cost: '{product['Cost']}'")
        print(f"  Extracted SKU: '{product['SKU']}'")
        
        products.append(product)
    
    products.sort(key=lambda p: p["id"])
    
    out = Path("products.json")
    out.write_text(json.dumps(products, indent=2), encoding="utf-8")
    print(f"\n✅ Scraped {len(products)} products (ID ≤ 100) → {out.resolve()}\n")

    assert products, "No products were scraped!"
    
    print(f"Field counts in scraped data:")
    empty_counts = {
        "dimensions": sum(1 for p in products if not p.get("dimensions")),
        "Details": sum(1 for p in products if not p.get("Details")),
        "Cost": sum(1 for p in products if not p.get("Cost")),
        "SKU": sum(1 for p in products if not p.get("SKU")),
        "Guarantee": sum(1 for p in products if not p.get("Guarantee")),
        "Updated": sum(1 for p in products if not p.get("Updated"))
    }
    
    for field, count in empty_counts.items():
        print(f"  {field}: {len(products) - count} populated, {count} empty")
