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
    from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeout, expect
except ImportError:
    print("Installing playwright...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "playwright"])
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])
    from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeout, expect

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


async def wait_for_angular_stable(page: Page, timeout: int = 5000) -> bool:
    """Wait for Angular hydration to complete (event handlers attached).
    
    Uses expect.poll (Playwright 1.40+ best practice) to check for Angular
    context on elements, indicating hydration is complete.
    Works with both Zone.js and zoneless Angular apps.
    """
    try:
        # Best practice 2025: use expect.poll for custom conditions
        await expect(page.locator("button[aria-label='Télécharger']")).to_be_visible(timeout=timeout)
        
        # Poll for Angular hydration indicator
        async def check_hydration():
            return await page.evaluate("""() => {
                const btn = document.querySelector("button[aria-label='Télécharger']");
                return btn && (btn.__ngContext__ !== undefined || btn.hasAttribute('eclbutton'));
            }""")
        
        await expect.poll(check_hydration, timeout=timeout).to_be(True)
        return True
    except (PlaywrightTimeout, AssertionError):
        logger.debug("  Angular hydration check timeout - proceeding anyway")
        return False
    except Exception as e:
        logger.debug(f"  Angular check error: {e} - proceeding anyway")
        return False


async def download_pdf_with_retry(
    page: Page,
    output_path: Path,
    timeout: int,
    max_retries: int = 5
) -> bool:
    """Download PDF with retry-action pattern.
    
    Uses Playwright's retry mechanism instead of sleep() to handle
    Angular hydration timing. Clicks the button and checks for download,
    retrying with short intervals if the click was "dead" (pre-hydration).
    """
    download_btn = page.locator("button[aria-label='Télécharger']")
    
    # First, wait for Angular to stabilize (handlers attached)
    await wait_for_angular_stable(page, timeout=5000)
    
    # Retry-action pattern: click + expect download, retry on failure
    retry_intervals = [200, 300, 500, 1000, 2000]  # ms between retries
    
    for attempt in range(1, max_retries + 1):
        try:
            await download_btn.wait_for(state="visible", timeout=timeout)
            
            # Short timeout for each attempt - we'll retry quickly if it fails
            attempt_timeout = 5000 if attempt < max_retries else timeout * 2
            
            async with page.expect_download(timeout=attempt_timeout) as download_info:
                await download_btn.click()
            
            download = await download_info.value
            await download.save_as(output_path)
            
            if output_path.exists() and output_path.stat().st_size > 0:
                if attempt > 1:
                    logger.info(f"  ✓ Download succeeded on attempt {attempt}")
                return True
            else:
                logger.warning(f"  Attempt {attempt}: Downloaded file empty")
                
        except PlaywrightTimeout:
            if attempt < max_retries:
                interval = retry_intervals[min(attempt - 1, len(retry_intervals) - 1)]
                logger.debug(f"  Attempt {attempt}: No download, retrying in {interval}ms...")
                await asyncio.sleep(interval / 1000)
            else:
                logger.warning(f"  All {max_retries} attempts failed")
        except Exception as e:
            logger.warning(f"  Attempt {attempt}: {e}")
            if attempt < max_retries:
                interval = retry_intervals[min(attempt - 1, len(retry_intervals) - 1)]
                await asyncio.sleep(interval / 1000)
    
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
            viewport={'width': 1920, 'height': 1080}  # Full HD to avoid responsive mobile layout
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
                await wait_for_network_idle(page, timeout=5000)
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
            
            # Wait for template select to be visible and interactive
            template_select = page.locator("select.ecl-select").first
            await template_select.wait_for(state="visible", timeout=10000)
            await template_select.select_option(value=TEMPLATES[template])
            logger.info(f"  ✓ Selected template: {template}")
            
            # Wait for template change to take effect
            # Simply wait for network to settle after template selection
            await wait_for_network_idle(page, timeout=10000)
            
            # Step 6: Enter CV name (REQUIRED before download)
            logger.info("6/7 Entering CV name...")
            name_input = page.get_by_role("textbox", name="Nom")
            await name_input.wait_for(state="visible", timeout=5000)
            await name_input.fill(output_path.stem)
            await name_input.press("Enter")  # Validate form input
            
            # Wait for form validation to complete (network activity)
            await wait_for_network_idle(page, timeout=5000)
            logger.info(f"  ✓ CV name validated: {output_path.stem}")
            
            # Step 7: Download PDF (uses Angular stability check + retry-action pattern)
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
            
            logger.error("=" * 60)
            return False
            
        finally:
            await context.close()
            await browser.close()


def main():
    # Project root is parent of src/
    project_root = Path(__file__).parent.parent
    input_dir = project_root / "input"
    output_dir = project_root / "output"
    
    # Ensure directories exist
    input_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    
    xml_path = input_dir / "europass.xml"
    output_path = output_dir / "CV-Europass.pdf"
    
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
