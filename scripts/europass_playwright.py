#!/usr/bin/env python3
"""
Europass CV PDF Generator using Playwright Automation

Automates the NEW Europass CV beta builder (/compact-cv-editor) to:
1. Import an XML file
2. Select template (default: cv-formal/Progrès)
3. Generate and download the PDF

Works without EU Login authentication using the guest editor.

Best Practices Applied:
- Polling with expect/wait_for instead of hardcoded sleeps
- Explicit wait conditions for UI state changes
- Retry logic for flaky network operations
- Structured logging with timing
- Graceful error handling with diagnostics
"""

import asyncio
import sys
import time
import logging
from pathlib import Path

try:
    from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeout
except ImportError:
    print("Installing playwright...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "playwright"])
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])
    from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeout

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# Template mapping for the beta builder
TEMPLATES = {
    "cv-academic": "cv-academic",
    "cv-creative": "cv-creative",
    "cv-elegant": "cv-elegant",
    "cv-formal": "cv-formal",           # P - Progrès ★ RECOMMENDED
    "cv-modern": "cv-modern",
    "cv-semi-formal": "cv-semi-formal",
}

DEFAULT_TEMPLATE = "cv-formal"
EUROPASS_URL = "https://europa.eu/europass/eportfolio/screen/cv-editor?lang=fr"


async def wait_for_network_idle(page: Page, timeout: int = 10000) -> None:
    """Wait for network to be idle (no pending requests)."""
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout)
    except PlaywrightTimeout:
        logger.warning("Network idle timeout - continuing anyway")


async def handle_resume_dialog(page: Page) -> None:
    """Handle the 'Resume last CV' dialog if present.
    
    Uses try/expect pattern instead of hardcoded waits.
    """
    try:
        # Check if resume dialog appears (with short timeout)
        resume_btn = page.get_by_role("button", name="Commencer à partir du CV Europass")
        
        try:
            await resume_btn.wait_for(state="visible", timeout=3000)
        except PlaywrightTimeout:
            return  # No dialog present
        
        await resume_btn.click()
        logger.info("  Dismissed 'Resume last CV' prompt")
        
        # Wait for page to stabilize after click
        await wait_for_network_idle(page, timeout=5000)
        
        # Wait for and click Continue if it appears
        continue_btn = page.get_by_role("button", name="Continuer")
        try:
            await continue_btn.wait_for(state="visible", timeout=3000)
            await continue_btn.click()
            logger.info("  Clicked 'Continuer'")
            await wait_for_network_idle(page, timeout=5000)
        except PlaywrightTimeout:
            pass  # No continue button needed
    except Exception as e:
        logger.debug(f"  No resume dialog or error: {e}")


async def upload_xml_file(page: Page, xml_path: Path, timeout: int) -> bool:
    """Upload XML file using file chooser.
    
    Uses expect_file_chooser for proper event handling.
    """
    try:
        file_button = page.get_by_role("button", name="Sélectionner un fichier")
        await file_button.wait_for(state="visible", timeout=timeout)
        
        # Use expect pattern for file chooser - proper async handling
        async with page.expect_file_chooser(timeout=timeout) as fc_info:
            await file_button.click()
        
        file_chooser = await fc_info.value
        await file_chooser.set_files(str(xml_path))
        
        # Wait for file to be processed - poll for builder button
        builder_button = page.get_by_role("button", name="Try the new CV builder (beta)")
        await builder_button.wait_for(state="visible", timeout=timeout)
        
        logger.info(f"✓ Uploaded: {xml_path.name}")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to upload file: {e}")
        return False


async def wait_for_preview_ready(page: Page, timeout: int = 30000) -> bool:
    """Wait for PDF preview to be fully rendered.
    
    Polls for specific indicators that preview is ready:
    1. Preview container exists
    2. No loading spinners
    3. Download button is enabled
    """
    try:
        # Wait for preview image/canvas to appear
        preview_selector = "img[alt], canvas, .preview-container"
        await page.wait_for_selector(preview_selector, state="visible", timeout=timeout)
        
        # Wait for any loading indicators to disappear
        loading_selectors = [".loading", ".spinner", "[class*='loading']", "[class*='spinner']"]
        for selector in loading_selectors:
            try:
                await page.wait_for_selector(selector, state="hidden", timeout=5000)
            except PlaywrightTimeout:
                pass  # Selector doesn't exist or already hidden
        
        # Wait for download button to be enabled (indicates preview is ready)
        download_btn = page.get_by_role("button", name="Télécharger")
        await download_btn.wait_for(state="visible", timeout=timeout)
        
        # Poll until button is not disabled
        await page.wait_for_function(
            """() => {
                const btn = [...document.querySelectorAll('button')].find(b => b.textContent.includes('Télécharger'));
                return btn && !btn.disabled;
            }""",
            timeout=timeout
        )
        
        logger.info("✓ Preview rendered")
        return True
    except PlaywrightTimeout:
        logger.warning("⚠ Preview timeout - attempting download anyway")
        return True  # Try to proceed
    except Exception as e:
        logger.error(f"✗ Preview error: {e}")
        return False


async def download_pdf_with_retry(
    page: Page,
    output_path: Path,
    timeout: int,
    max_retries: int = 3
) -> bool:
    """Download PDF with retry logic.
    
    Uses expect_download for proper async download handling.
    Beta builder needs extra time for server-side PDF generation.
    """
    download_btn = page.get_by_role("button", name="Télécharger")
    
    for attempt in range(1, max_retries + 1):
        try:
            await download_btn.wait_for(state="visible", timeout=timeout)
            
            # Beta builder generates PDF server-side, needs longer timeout
            download_timeout = timeout * 2  # Double timeout for download
            
            async with page.expect_download(timeout=download_timeout) as download_info:
                await download_btn.click()
            
            download = await download_info.value
            
            # Wait for download to complete (server-side PDF generation can be slow)
            await download.save_as(output_path)
            
            # Verify file was created and has content
            if output_path.exists() and output_path.stat().st_size > 0:
                return True
            else:
                logger.warning(f"  Attempt {attempt}: Downloaded file empty or missing")
                
        except PlaywrightTimeout:
            logger.warning(f"  Attempt {attempt}: Download timeout")
        except Exception as e:
            logger.warning(f"  Attempt {attempt}: {e}")
        
        if attempt < max_retries:
            await asyncio.sleep(2)  # Brief pause before retry
    
    return False


async def generate_europass_pdf(
    xml_path: Path,
    output_path: Path,
    template: str = DEFAULT_TEMPLATE,
    headless: bool = True,
    timeout: int = 60000
) -> bool:
    """Generate a Europass PDF from an XML file using browser automation.
    
    Args:
        xml_path: Path to the Europass XML file
        output_path: Path where the PDF will be saved
        template: Template name (cv-formal, cv-elegant, etc.)
        headless: Run browser in headless mode
        timeout: Operation timeout in milliseconds
    
    Returns:
        True if PDF was generated successfully, False otherwise
    """
    start_time = time.time()
    
    logger.info("=" * 60)
    logger.info("Europass CV PDF Generator (Beta Builder)")
    logger.info("=" * 60)
    logger.info(f"Input:    {xml_path}")
    logger.info(f"Output:   {output_path}")
    logger.info(f"Template: {template}")
    logger.info(f"Mode:     {'headless' if headless else 'visible'}")
    logger.info("=" * 60)
    
    if template not in TEMPLATES:
        logger.error(f"Unknown template: {template}")
        logger.error(f"Available: {', '.join(TEMPLATES.keys())}")
        return False
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            accept_downloads=True,
            locale='fr-FR',
            viewport={'width': 1280, 'height': 900}
        )
        page = await context.new_page()
        
        # Set default timeout for all operations
        page.set_default_timeout(timeout)
        
        try:
            # Step 1: Navigate to CV editor
            logger.info("1/7 Navigating to Europass...")
            await page.goto(EUROPASS_URL, wait_until="domcontentloaded")
            await wait_for_network_idle(page)
            
            # Step 2: Handle any resume dialogs
            logger.info("2/7 Handling dialogs...")
            await handle_resume_dialog(page)
            
            # Step 3: Upload XML file
            logger.info("3/7 Uploading XML...")
            if not await upload_xml_file(page, xml_path, timeout):
                raise Exception("Failed to upload XML file")
            
            # Step 4: Select new CV builder (beta)
            logger.info("4/7 Selecting beta builder...")
            builder_btn = page.get_by_role("button", name="Try the new CV builder (beta)")
            await builder_btn.click()
            
            # Handle "Continuer" dialog if it appears (for resume confirmation)
            try:
                continue_btn = page.get_by_role("button", name="Continuer")
                await continue_btn.wait_for(state="visible", timeout=3000)
                await continue_btn.click()
                logger.info("  Clicked 'Continuer' to confirm")
                await asyncio.sleep(1)
            except PlaywrightTimeout:
                pass
            
            # Wait for URL change (poll instead of hardcoded wait)
            await page.wait_for_url("**/compact-cv-editor**", timeout=timeout)
            await wait_for_network_idle(page)
            
            # Handle error dialog if present (e.g., validation warnings)
            try:
                ok_btn = page.get_by_role("button", name="OK")
                await ok_btn.wait_for(state="visible", timeout=3000)
                await ok_btn.click()
                logger.info("  Dismissed validation dialog")
            except PlaywrightTimeout:
                pass
            
            # Step 5: Select template by value (not index - order may change)
            logger.info(f"5/7 Selecting template: {template}...")
            await asyncio.sleep(1)  # Let the page stabilize
            
            # Select by value - stable regardless of option order
            template_select = page.locator("select.ecl-select").first
            await template_select.wait_for(state="visible", timeout=10000)
            await template_select.select_option(value=TEMPLATES[template])
            logger.info(f"  ✓ Selected template: {template}")
            
            # Wait for template to apply and preview to regenerate
            await asyncio.sleep(3)
            
            # Step 6: Enter CV name (REQUIRED before download)
            logger.info("6/7 Entering CV name...")
            name_input = page.get_by_role("textbox").first
            await name_input.wait_for(state="visible", timeout=5000)
            await name_input.click()
            await name_input.fill(output_path.stem)
            await name_input.press("Tab")  # Trigger blur/validation
            logger.info(f"  ✓ CV name set to: {output_path.stem}")
            
            # Wait for form validation and preview to update after name change
            await asyncio.sleep(2)
            
            # Wait for preview to be fully ready (polling)
            logger.info("  Waiting for preview to render...")
            await wait_for_preview_ready(page, timeout)
            
            # Extra wait for PDF to be ready server-side
            await asyncio.sleep(2)
            
            # Step 7: Download PDF
            logger.info("7/7 Downloading PDF...")
            if not await download_pdf_with_retry(page, output_path, timeout):
                raise Exception("Failed to download PDF after retries")
            
            # Success
            elapsed = time.time() - start_time
            file_size = output_path.stat().st_size
            
            logger.info("=" * 60)
            logger.info("✓ PDF generated successfully!")
            logger.info(f"  Path: {output_path}")
            logger.info(f"  Size: {file_size:,} bytes ({file_size/1024:.1f} KB)")
            logger.info(f"  Time: {elapsed:.1f}s")
            logger.info("=" * 60)
            
            return True
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error("=" * 60)
            logger.error(f"✗ Failed after {elapsed:.1f}s: {e}")
            
            # Save diagnostic screenshot
            screenshot_path = output_path.with_suffix('.error.png')
            try:
                await page.screenshot(path=screenshot_path, full_page=True)
                logger.error(f"  Screenshot: {screenshot_path}")
            except:
                pass
            
            # Save page HTML for debugging
            html_path = output_path.with_suffix('.error.html')
            try:
                html_content = await page.content()
                html_path.write_text(html_content)
                logger.error(f"  HTML dump: {html_path}")
            except:
                pass
            
            logger.error("=" * 60)
            return False
            
        finally:
            await context.close()
            await browser.close()


def main():
    parent_dir = Path(__file__).parent.parent
    xml_path = parent_dir / "europass-enriched.xml"
    output_path = parent_dir / "CV-Europass-Progres.pdf"
    
    if not xml_path.exists():
        logger.error(f"XML file not found: {xml_path}")
        sys.exit(1)
    
    # Parse arguments
    headless = "--visible" not in sys.argv
    template = DEFAULT_TEMPLATE
    
    for arg in sys.argv[1:]:
        if arg.startswith("--template="):
            template = arg.split("=", 1)[1]
        elif arg.startswith("--output="):
            output_path = Path(arg.split("=", 1)[1])
    
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: python europass_playwright.py [OPTIONS]")
        print("\nOptions:")
        print("  --visible              Run browser in visible mode (default: headless)")
        print("  --template=NAME        Select template (default: cv-formal)")
        print("  --output=PATH          Output PDF path")
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
