import pytest
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

EMAIL    = "miths.124@gmail.com"
PASSWORD = "lqAmrlDA"
BASE_URL = "https://hiring.idenhq.com/"

@pytest.fixture(scope="session")
def browser_context():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        yield ctx
        ctx.close()
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
        # Increase wait time to ensure page loads fully
        page.wait_for_timeout(1000)

    # Wait for the page to stabilize and ensure content is loaded
    page.wait_for_load_state("networkidle")
    
    # 3) Scroll gradually until "ID: 100" appears (or we hit max scrolls)
    max_scrolls = 30  # Increased max scrolls
    for i in range(max_scrolls):
        # Check if we've found ID: 100
        if page.query_selector("text=ID: 100"):
            print(f"Found ID: 100 after {i+1} scrolls")
            break
            
        # Scroll in smaller increments for better content loading
        page.evaluate("() => window.scrollBy(0, 500)")
        page.wait_for_timeout(800)  # Longer wait to ensure content loads
        
        # Every 5 scrolls, perform a complete scroll to bottom and wait longer
        if i % 5 == 4:
            page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)

    # 4) Extract cards with improved individual card extraction with updated fields
    products = page.evaluate(
        """() => {
        // Collect every potential "card" element that might contain products
        const potentialCards = Array.from(document.querySelectorAll('div[class*="card"], div[class*="product"], div[class*="item"], article, section, div[class*="list-item"]'));
        
        // More precise ID pattern matching
        const idPattern = /ID:\\s*(\\d+)/i;
        
        // Filter to keep only those with an ID pattern
        const cards = potentialCards.filter(el => idPattern.test(el.textContent || el.innerText || ''));
        
        const result = cards.map(card => {
          // Get text content for THIS CARD ONLY (not from child elements that might be other cards)
          const allChildNodes = Array.from(card.childNodes);
          let cardText = '';
          allChildNodes.forEach(node => {
            // Only include direct text nodes or non-card element nodes
            if (node.nodeType === Node.TEXT_NODE) {
              cardText += node.textContent + ' ';
            } else if (node.nodeType === Node.ELEMENT_NODE && 
                      !node.matches('div[class*="card"], div[class*="product"], div[class*="item"], article, section, div[class*="list-item"]')) {
              cardText += (node.textContent || node.innerText || '') + ' ';
            }
          });
          
          // Fallback to direct text content if the above method didn't work
          if (!cardText.trim()) {
            cardText = card.textContent || card.innerText || '';
          }
          
          // Extract heading as a primary field
          let heading = '';
          const headingElement = card.querySelector('h1, h2, h3, h4, h5, h6, strong, b, .title, [class*="title"], [class*="name"], [class*="product-name"]');
          if (headingElement) {
            heading = (headingElement.textContent || headingElement.innerText || '').trim();
            // Clean the heading - remove ID and other fields if they accidentally got included
            heading = heading.replace(/ID:\\s*\\d+/i, '').trim();
            heading = heading.replace(/dimensions:.*$/i, '').trim();
            heading = heading.replace(/cost:.*$/i, '').trim();
            heading = heading.replace(/sku:.*$/i, '').trim();
            heading = heading.replace(/guarantee:.*$/i, '').trim();
            heading = heading.replace(/details:.*$/i, '').trim();
            heading = heading.replace(/updated:.*$/i, '').trim();
          }
          
          // Initialize product object with heading as a prominent field and exactly the format needed
          const product = {
            heading: heading || 'Unknown Product',
            id: null,
            dimensions: '',
            Details: '',
            Cost: '',
            SKU: '',
            Guarantee: '',
            Updated: ''
          };
          
          // Extract ID as a primary field from THIS CARD ONLY
          const idMatch = cardText.match(idPattern);
          if (idMatch && idMatch[1]) {
            product.id = Number(idMatch[1]);
          }
          
          // Extract other fields from THIS CARD ONLY with the exact field names requested
          const dimensionsMatch = cardText.match(/dimensions:?\\s*([^\\n\\r,;]+)/i);
          if (dimensionsMatch && dimensionsMatch[1]) {
            product.dimensions = dimensionsMatch[1].trim();
          }
          
          const detailsMatch = cardText.match(/details:?\\s*([^\\n\\r,;]+)/i);
          if (detailsMatch && detailsMatch[1]) {
            product.Details = detailsMatch[1].trim();
          }
          
          const costMatch = cardText.match(/cost:?\\s*([^\\n\\r,;]+)/i);
          if (costMatch && costMatch[1]) {
            product.Cost = costMatch[1].trim();
          }
          
          const skuMatch = cardText.match(/sku:?\\s*([^\\n\\r,;]+)/i);
          if (skuMatch && skuMatch[1]) {
            product.SKU = skuMatch[1].trim();
          }
          
          const guaranteeMatch = cardText.match(/guarantee:?\\s*([^\\n\\r,;]+)/i);
          if (guaranteeMatch && guaranteeMatch[1]) {
            product.Guarantee = guaranteeMatch[1].trim();
          }
          
          const updatedMatch = cardText.match(/updated:?\\s*([^\\n\\r,;]+)/i);
          if (updatedMatch && updatedMatch[1]) {
            product.Updated = updatedMatch[1].trim();
          }
          
          return product;
        });
        
        // Filter for valid products with IDs up to 100
        return result
          .filter(p => typeof p.id === 'number' && !isNaN(p.id) && p.id <= 100)
          // Sort by ID
          .sort((a, b) => a.id - b.id);
      }"""
    )
    
    # Add debug information
    print(f"Found {len(products)} products")
    
    # Take a screenshot for debugging
    page.screenshot(path="debug_screenshot.png")

    # 5) Write to JSON
    out = Path("products.json")
    out.write_text(json.dumps(products, indent=2), encoding="utf-8")
    print(f"\n✅ Scraped {len(products)} products (ID ≤ 100) → {out.resolve()}\n")

    # 6) Sanity check
    assert products, "No products were scraped!"