#!/usr/bin/env python3
"""
Europass CV PDF Generator using Playwright Automation

Automates the Europass CV editor to:
1. Import an XML file
2. Select template cv-3
3. Generate and download the PDF

Works without EU Login authentication using the guest editor.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Installing playwright...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "playwright"])
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])
    from playwright.async_api import async_playwright


async def generate_europass_pdf(
    xml_path: Path,
    output_path: Path,
    headless: bool = True,
    timeout: int = 60000
) -> bool:
    """Generate a Europass PDF from an XML file using browser automation."""
    print(f"Input:  {xml_path}")
    print(f"Output: {output_path}")
    print(f"Mode:   {'headless' if headless else 'visible'}")
    print()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            accept_downloads=True,
            locale='fr-FR'
        )
        page = await context.new_page()
        
        try:
            # Step 1: Navigate to CV editor
            print("1. Navigating to Europass CV editor...")
            await page.goto(
                "https://europa.eu/europass/eportfolio/screen/cv-editor?lang=fr",
                wait_until="networkidle",
                timeout=timeout
            )
            await page.wait_for_timeout(2000)
            
            # Step 2: Open import dialog
            print("2. Opening import dialog...")
            start_button = page.get_by_role("button", name="Commencer à partir du CV")
            await start_button.wait_for(state="visible", timeout=timeout)
            await start_button.click()
            await page.wait_for_timeout(1000)
            
            # Step 3: Upload XML file
            print("3. Uploading XML file...")
            file_button = page.get_by_role("button", name="Sélectionner un fichier")
            await file_button.wait_for(state="visible", timeout=timeout)
            
            async with page.expect_file_chooser() as fc_info:
                await file_button.click()
            file_chooser = await fc_info.value
            await file_chooser.set_files(str(xml_path))
            await page.wait_for_timeout(3000)
            
            # Step 4: Select standard CV builder
            print("4. Selecting standard CV builder...")
            builder_button = page.get_by_role("button", name="Use the standard CV builder")
            await builder_button.wait_for(state="visible", timeout=timeout)
            await builder_button.click()
            await page.wait_for_timeout(3000)
            
            # Step 5: Wait for CV editor to load and click Next
            print("5. Waiting for CV editor and clicking Next...")
            next_button = page.locator("#wizard-nav-next")
            await next_button.wait_for(state="visible", timeout=timeout)
            await page.wait_for_timeout(2000)
            await next_button.click()
            await page.wait_for_timeout(3000)
            
            # Step 6: Select template cv-3
            print("6. Selecting template cv-3...")
            template_btn = page.locator("#cv-3")
            await template_btn.wait_for(state="visible", timeout=timeout)
            await template_btn.click()
            await page.wait_for_timeout(1000)
            
            # Step 7: Click Next to go to save step
            print("7. Navigating to save step...")
            await next_button.click()
            await page.wait_for_timeout(2000)
            
            # Step 8: Wait for CV preview to render
            print("8. Waiting for CV preview to render...")
            # The preview iframe or container needs time to generate
            preview_container = page.locator(".cv-preview, .preview-container, iframe").first
            try:
                await preview_container.wait_for(state="visible", timeout=10000)
            except:
                pass  # Preview container might have different class
            await page.wait_for_timeout(5000)  # Extra time for PDF preview generation
            
            # Step 9: Enter CV name
            print("9. Entering CV name...")
            # The CV name input enables the download button
            name_input = page.locator("input:visible").first
            await name_input.wait_for(state="visible", timeout=timeout)
            await name_input.fill(output_path.stem)
            await page.wait_for_timeout(2000)
            
            # Step 10: Download PDF
            print("10. Downloading PDF...")
            download_button = page.locator("#action-button-cv-download")
            # Wait for button to be enabled (after name is entered)
            await download_button.wait_for(state="visible", timeout=timeout)
            await page.wait_for_timeout(2000)
            
            async with page.expect_download(timeout=timeout) as download_info:
                await download_button.click(force=True)
            
            download = await download_info.value
            await download.save_as(output_path)
            
            print(f"\n✓ PDF saved successfully: {output_path}")
            print(f"  Size: {output_path.stat().st_size:,} bytes")
            
            return True
            
        except Exception as e:
            print(f"\n✗ Error: {e}")
            screenshot_path = output_path.with_suffix('.error.png')
            await page.screenshot(path=screenshot_path)
            print(f"  Screenshot saved: {screenshot_path}")
            return False
            
        finally:
            await browser.close()


def main():
    parent_dir = Path(__file__).parent.parent
    xml_path = parent_dir / "europass-enriched.xml"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = parent_dir / f"CV-Europass-{timestamp}.pdf"
    
    if not xml_path.exists():
        print(f"Error: XML file not found: {xml_path}")
        sys.exit(1)
    
    headless = "--visible" not in sys.argv
    
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: python europass_playwright.py [--visible]")
        print("\nOptions:")
        print("  --visible    Run browser in visible mode (default: headless)")
        sys.exit(0)
    
    success = asyncio.run(generate_europass_pdf(
        xml_path=xml_path,
        output_path=output_path,
        headless=headless
    ))
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
