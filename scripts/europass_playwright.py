#!/usr/bin/env python3
"""
Europass CV PDF Generator using Playwright Automation

Automates the NEW Europass CV beta builder (/compact-cv-editor) to:
1. Import an XML file
2. Select template cv-professional (optimal for ATS/AI/Human review)
3. Generate and download the PDF

Works without EU Login authentication using the guest editor.

Template choice rationale:
- cv-professional: Single-column, ATS-safe, clean parsing for AI screening,
  ALL CAPS job titles for instant recruiter recognition.
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

# Template mapping for the new beta builder combobox
# Uses value attribute for selection
TEMPLATES = {
    "cv-academic": "cv-academic",
    "cv-creative": "cv-creative",
    "cv-elegant": "cv-elegant",
    "cv-formal": "cv-formal",           # P - Progrès ★ RECOMMENDED
    "cv-modern": "cv-modern",
    "cv-semi-formal": "cv-semi-formal",
}

DEFAULT_TEMPLATE = "cv-formal"


async def generate_europass_pdf(
    xml_path: Path,
    output_path: Path,
    template: str = DEFAULT_TEMPLATE,
    headless: bool = True,
    timeout: int = 90000
) -> bool:
    """Generate a Europass PDF from an XML file using browser automation.
    
    Args:
        xml_path: Path to the Europass XML file
        output_path: Path where the PDF will be saved
        template: Template name (cv-professional, cv-elegant, etc.)
        headless: Run browser in headless mode
        timeout: Operation timeout in milliseconds
    """
    print(f"{'='*60}")
    print(f"Europass CV PDF Generator (Beta Builder)")
    print(f"{'='*60}")
    print(f"Input:    {xml_path}")
    print(f"Output:   {output_path}")
    print(f"Template: {template}")
    print(f"Mode:     {'headless' if headless else 'visible'}")
    print(f"{'='*60}\n")
    
    if template not in TEMPLATES:
        print(f"✗ Unknown template: {template}")
        print(f"  Available: {', '.join(TEMPLATES.keys())}")
        return False
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            accept_downloads=True,
            locale='fr-FR'
        )
        page = await context.new_page()
        
        try:
            # Step 1: Navigate to CV editor
            print("1/8 Navigating to Europass CV editor...")
            await page.goto(
                "https://europa.eu/europass/eportfolio/screen/cv-editor?lang=fr",
                wait_until="networkidle",
                timeout=timeout
            )
            await page.wait_for_timeout(2000)
            
            # Step 2: Handle "Resume last CV" dialog if present
            print("2/8 Handling dialogs...")
            try:
                resume_dialog = page.get_by_role("button", name="Commencer à partir du CV Europass")
                if await resume_dialog.is_visible(timeout=3000):
                    await resume_dialog.click()
                    await page.wait_for_timeout(1000)
                    # Click "Continuer" to dismiss
                    continue_btn = page.get_by_role("button", name="Continuer")
                    if await continue_btn.is_visible(timeout=2000):
                        await continue_btn.click()
                        await page.wait_for_timeout(1000)
            except:
                pass  # No resume dialog
            
            # Step 3: Upload XML file
            print("3/8 Uploading XML file...")
            file_button = page.get_by_role("button", name="Sélectionner un fichier")
            await file_button.wait_for(state="visible", timeout=timeout)
            
            async with page.expect_file_chooser() as fc_info:
                await file_button.click()
            file_chooser = await fc_info.value
            await file_chooser.set_files(str(xml_path))
            await page.wait_for_timeout(3000)
            
            # Step 4: Select new CV builder (beta)
            print("4/8 Selecting new CV builder (beta)...")
            builder_button = page.get_by_role("button", name="Try the new CV builder (beta)")
            await builder_button.wait_for(state="visible", timeout=timeout)
            await builder_button.click()
            
            # Wait for compact-cv-editor to load
            await page.wait_for_url("**/compact-cv-editor**", timeout=timeout)
            await page.wait_for_timeout(3000)
            
            # Step 5: Select template from dropdown
            print(f"5/8 Selecting template: {template}...")
            template_select = page.locator("select.ecl-select").first
            await template_select.wait_for(state="visible", timeout=timeout)
            await template_select.select_option(value=TEMPLATES[template])
            await page.wait_for_timeout(2000)
            
            # Step 6: Enter CV name
            print("6/8 Entering CV name...")
            name_input = page.get_by_role("textbox", name="Nom")
            await name_input.wait_for(state="visible", timeout=timeout)
            await name_input.fill(output_path.stem)
            await page.wait_for_timeout(1000)
            
            # Step 7: Wait for preview to render
            print("7/8 Waiting for PDF preview to render...")
            await page.wait_for_timeout(5000)
            
            # Step 8: Download PDF
            print("8/8 Downloading PDF...")
            download_button = page.get_by_role("button", name="Télécharger")
            await download_button.wait_for(state="visible", timeout=timeout)
            
            async with page.expect_download(timeout=timeout) as download_info:
                await download_button.click()
            
            download = await download_info.value
            await download.save_as(output_path)
            
            file_size = output_path.stat().st_size
            print(f"\n{'='*60}")
            print(f"✓ PDF saved successfully!")
            print(f"  Path: {output_path}")
            print(f"  Size: {file_size:,} bytes ({file_size/1024:.1f} KB)")
            print(f"{'='*60}")
            
            return True
            
        except Exception as e:
            print(f"\n{'='*60}")
            print(f"✗ Error: {e}")
            screenshot_path = output_path.with_suffix('.error.png')
            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"  Screenshot saved: {screenshot_path}")
            print(f"{'='*60}")
            return False
            
        finally:
            await browser.close()


def main():
    parent_dir = Path(__file__).parent.parent
    xml_path = parent_dir / "europass-enriched.xml"
    output_path = parent_dir / "CV-Europass-Professional.pdf"
    
    if not xml_path.exists():
        print(f"Error: XML file not found: {xml_path}")
        sys.exit(1)
    
    # Parse arguments
    headless = "--visible" not in sys.argv
    template = DEFAULT_TEMPLATE
    
    for arg in sys.argv[1:]:
        if arg.startswith("--template="):
            template = arg.split("=", 1)[1]
    
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: python europass_playwright.py [OPTIONS]")
        print("\nOptions:")
        print("  --visible              Run browser in visible mode (default: headless)")
        print("  --template=NAME        Select template (default: cv-professional)")
        print("\nAvailable templates:")
        for name in TEMPLATES:
            marker = " ★ (recommended)" if name == DEFAULT_TEMPLATE else ""
            print(f"  - {name}{marker}")
        sys.exit(0)
    
    success = asyncio.run(generate_europass_pdf(
        xml_path=xml_path,
        output_path=output_path,
        template=template,
        headless=headless
    ))
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
