#crawl từ vinpearl giai đoạn 2

# ...existing code...
import time
import json
import uuid
import argparse
import os
import csv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from readability import Document
from bs4 import BeautifulSoup
import markdownify
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

def scrape_page(url, save_html_path=None, headless=True, wait=2, driver_path=None):
    options = Options()
    if headless:
        # Use new headless mode where available
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    service = Service(executable_path=driver_path) if driver_path else Service()
    driver = webdriver.Chrome(service=service, options=options)
    try:
        driver.get(url)
        time.sleep(wait)
        
        # Scroll down multiple times to trigger lazy-load content
        scroll_pause = 0.8
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 0
        max_scrolls = 10
        
        while scroll_attempts < max_scrolls:
            # Scroll down to bottom
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(scroll_pause)
            
            # Try to click "Xem thêm" / "Read more" / expand buttons
            try:
                expand_buttons = driver.execute_script("""
                    var buttons = [];
                    // Common expand button selectors
                    var selectors = [
                        'button:contains("Xem thêm")',
                        'button:contains("Đọc thêm")', 
                        'a:contains("Xem thêm")',
                        '[class*="expand"]',
                        '[class*="show-more"]',
                        '[class*="read-more"]'
                    ];
                    // Find buttons with text content
                    var allButtons = document.querySelectorAll('button, a, span[role="button"]');
                    for (var i = 0; i < allButtons.length; i++) {
                        var text = allButtons[i].innerText.toLowerCase();
                        if (text.includes('xem thêm') || text.includes('đọc thêm') || 
                            text.includes('read more') || text.includes('show more')) {
                            allButtons[i].click();
                            buttons.push(allButtons[i]);
                        }
                    }
                    return buttons.length;
                """);
                if expand_buttons > 0:
                    time.sleep(1)  # Wait for content to expand
            except:
                pass
            
            # Calculate new scroll height and compare
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                scroll_attempts += 1
            else:
                scroll_attempts = 0
            last_height = new_height
        
        # Scroll back to top to ensure all content is in view
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.5)
        
        # Wait for any remaining XHR/fetch requests
        driver.execute_script("""
            return new Promise(resolve => {
                if (document.readyState === 'complete') {
                    setTimeout(resolve, 1000);
                } else {
                    window.addEventListener('load', () => setTimeout(resolve, 1000));
                }
            });
        """)
        
        html = driver.page_source
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    if save_html_path:
        with open(save_html_path, "w", encoding="utf-8") as f:
            f.write(html)
    return html

def html_to_markdown_chunks(raw_html, chunk_size=800, chunk_overlap=80):
    """Extract content preserving tables, images, and layout structure"""
    soup = BeautifulSoup(raw_html, "html.parser")
    
    # Extract title from multiple possible locations
    title = ""
    title_tags = soup.find_all(['title', 'h1'])
    for tag in title_tags:
        if tag.name == 'title':
            title = tag.get_text(strip=True)
            break
        elif tag.name == 'h1' and not title:
            title = tag.get_text(strip=True)
    
    # Try to find main content area (common patterns in Vietnamese travel sites)
    main_content = None
    content_selectors = [
        'article', 'main', '.article-content', '.post-content', 
        '.entry-content', '.content-detail', '#content', '.main-content',
        '[class*="article"]', '[class*="post-content"]',
        '[class*="detail-content"]', '[itemprop="articleBody"]'
    ]
    
    for selector in content_selectors:
        if selector.startswith('.'):
            main_content = soup.find(class_=selector[1:])
        elif selector.startswith('#'):
            main_content = soup.find(id=selector[1:])
        elif selector.startswith('['):
            # Handle attribute selectors
            if 'itemprop' in selector:
                main_content = soup.find(attrs={'itemprop': 'articleBody'})
            elif 'class*=' in selector:
                class_pattern = selector.split('"')[1]
                main_content = soup.find(class_=lambda x: x and class_pattern in x)
        else:
            main_content = soup.find(selector)
        
        if main_content:
            break
    
    # If no main content found, use body
    if not main_content:
        main_content = soup.find('body') or soup
    
    # Remove unwanted elements but keep structure
    for tag in main_content.find_all(['script', 'style', 'noscript', 'nav', 'header', 'footer', 'aside']):
        tag.decompose()
    
    # Remove ads and social sharing (common patterns)
    for tag in main_content.find_all(class_=lambda x: x and any(word in str(x).lower() for word in 
                                     ['ad', 'advertisement', 'social', 'share', 'comment', 'sidebar'])):
        tag.decompose()
    
    # Preserve image captions and alt text
    for img in main_content.find_all('img'):
        alt_text = img.get('alt', '')
        # Look for caption in parent figure or nearby elements
        caption = ''
        parent = img.find_parent('figure')
        if parent:
            figcaption = parent.find('figcaption')
            if figcaption:
                caption = figcaption.get_text(strip=True)
        
        # If we have caption or alt, add as text after image
        if caption or alt_text:
            caption_text = f"[Hình ảnh: {caption or alt_text}]"
            new_tag = soup.new_tag('p')
            new_tag.string = caption_text
            img.insert_after(new_tag)
    
    # Convert to markdown with better table support
    markdown_text = markdownify.markdownify(
        str(main_content), 
        heading_style="ATX",
        bullets="-",
        strip=['a'],  # Keep links but strip a tags for cleaner text
    )

    headers = [("#", "title"), ("##", "section"), ("###", "subsection")]
    md_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers)
    md_docs = md_splitter.split_text(markdown_text)

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = []
    for d in md_docs:
        small_chunks = text_splitter.split_text(d.page_content)
        for c in small_chunks:
            meta = d.metadata.copy()
            meta["page_title"] = title
            chunks.append({"content": c, "metadata": meta})
    return chunks, markdown_text, title

def detect_type(section):
    s = (section or "").lower()
    if any(k in s for k in ["địa điểm", "bãi biển", "chơi gì", "check in"]):
        return "destination"
    if any(k in s for k in ["khách sạn", "resort", "lưu trú"]):
        return "accommodation"
    if any(k in s for k in ["ăn gì", "ẩm thực", "món ăn", "nhà hàng"]):
        return "food"
    if any(k in s for k in ["di chuyển", "phương tiện", "xe", "máy bay"]):
        return "transportation"
    if any(k in s for k in ["chi phí", "giá", "vé"]):
        return "pricing"
    if any(k in s for k in ["thời điểm", "thời gian", "mùa"]):
        return "schedule"
    return "general"

def build_final_chunks(markdown_text, province, source, chunk_size=900, chunk_overlap=100):
    headers = [("#", "title"), ("##", "section"), ("###", "subsection")]
    md_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers)
    md_docs = md_splitter.split_text(markdown_text)

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    final_chunks = []
    sections_found = set()
    
    for doc in md_docs:
        small_chunks = text_splitter.split_text(doc.page_content)
        section_name = doc.metadata.get("section") or doc.metadata.get("subsection") or doc.metadata.get("title") or "Nội dung"
        section_type = detect_type(section_name)
        sections_found.add(section_name)
        
        for chunk in small_chunks:
            final_chunks.append({
                "id": uuid.uuid4().hex[:12],
                "province": province,
                "source": source,
                "section": section_name,
                "type": section_type,
                "name": section_name,
                "content": chunk,
                "tokens": int(len(chunk.split()) * 1.3)
            })
    
    return final_chunks, sections_found

def process_target(url, province, source, out_prefix=None, save_html=False, headless=True, driver_path=None):
    out_prefix = out_prefix or province
    try:
        raw_html = scrape_page(url, save_html_path=(f"output_{out_prefix}.html" if save_html else None),
                               headless=headless, wait=2, driver_path=driver_path)
    except Exception as e:
        print(f"  Error scraping: {e}")
        return [], set()

    chunks_md, markdown_text, title = html_to_markdown_chunks(raw_html)
    final_chunks, sections = build_final_chunks(markdown_text, province, source)
    
    # Log sections found for completeness tracking
    if sections:
        print(f"  Sections: {', '.join(list(sections)[:5])}{'...' if len(sections) > 5 else ''}")
    
    return final_chunks, sections

def load_targets_from_csv(csv_path):
    targets = []
    with open(csv_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # CSV columns: url,province,source
            if "url" in row and "province" in row and "source" in row:
                targets.append({"url": row["url"].strip(), "province": row["province"].strip(), "source": row["source"].strip()})
    return targets

def load_urls_from_txt(txt_path):
    """Load URLs from text file, one URL per line, ignoring empty lines and comments"""
    urls = []
    with open(txt_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                urls.append(line)
    return urls

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape pages and produce markdown/simple chunk JSON per target")
    parser.add_argument("--csv", help="CSV file with columns url,province,source", default=None)
    parser.add_argument("--txt", help="Text file with URLs, one per line", default="text.txt")
    parser.add_argument("--province", help="Province name for output", default="ho_chi_minh")
    parser.add_argument("--source", help="Source name", default="vinpearl")
    parser.add_argument("--output", help="Output JSON file path", default="ho_chi_minh_chunks_simple.json")
    parser.add_argument("--headless", action="store_true", help="Run browser headless")
    parser.add_argument("--driver-path", help="Path to chromedriver executable (optional)", default=None)
    args = parser.parse_args()

    # Load URLs from text file (default mode for Can Tho)
    if os.path.exists(args.txt):
        print(f"Loading URLs from {args.txt}...")
        urls = load_urls_from_txt(args.txt)
        print(f"Found {len(urls)} URLs to process\n")
        
        all_chunks = []
        all_sections = set()
        success_count = 0
        error_count = 0
        page_stats = []
        
        for i, url in enumerate(urls, 1):
            print(f"[{i}/{len(urls)}] {url}")
            try:
                chunks, sections = process_target(
                    url,
                    args.province,
                    args.source,
                    out_prefix=f"{args.province}_{i}",
                    save_html=False,
                    headless=args.headless,
                    driver_path=args.driver_path
                )
                if chunks:
                    all_chunks.extend(chunks)
                    all_sections.update(sections)
                    success_count += 1
                    page_stats.append({
                        'url': url,
                        'chunks': len(chunks),
                        'sections': len(sections),
                        'status': 'success'
                    })
                    print(f"  ✓ Success: {len(chunks)} chunks, {len(sections)} sections")
                else:
                    error_count += 1
                    page_stats.append({'url': url, 'status': 'empty'})
                    print(f"  ✗ Failed: no chunks returned")
            except Exception as e:
                error_count += 1
                page_stats.append({'url': url, 'status': 'error', 'error': str(e)})
                print(f"  ✗ Error: {e}")
        
        # Write all chunks to single output file
        print(f"\n" + "="*60)
        print(f"CRAWLING COMPLETED")
        print(f"="*60)
        print(f"Success: {success_count}/{len(urls)} pages")
        print(f"Failed: {error_count}/{len(urls)} pages")
        print(f"Total chunks: {len(all_chunks)}")
        print(f"Total unique sections: {len(all_sections)}")
        
        # Show content types distribution
        type_counts = {}
        for chunk in all_chunks:
            t = chunk.get('type', 'unknown')
            type_counts[t] = type_counts.get(t, 0) + 1
        print(f"\nContent types:")
        for t, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  - {t}: {count} chunks")
        
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(all_chunks, f, ensure_ascii=False, indent=2)
        print(f"\nOutput saved to: {args.output}")
        print("="*60)
    
    elif args.csv and os.path.exists(args.csv):
        # CSV mode (legacy)
        targets = load_targets_from_csv(args.csv)
        for t in targets:
            print("Processing", t["province"], "-", t["url"])
            chunks, sections = process_target(
                t["url"],
                t["province"],
                t.get("source", "unknown"),
                out_prefix=t["province"],
                save_html=True,
                headless=args.headless,
                driver_path=args.driver_path
            )
            print(f" => chunks: {len(chunks)}, sections: {len(sections)}")
    else:
        print(f"Error: No input file found. Please provide --txt or --csv file.")
        print(f"Looking for: {args.txt}")
