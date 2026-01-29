# Europass PDF Generation - Reverse Engineering Analysis

## Discoveries

### 1. Technology Stack Used by Europass

Europass uses a **HTML-to-Image-to-PDF** approach, not structured PDF generation:

| Library | Purpose | GitHub |
|---------|---------|--------|
| **html2canvas** | Renders HTML to Canvas | html2canvas/html2canvas |
| **jsPDF** | Creates PDF from images | parallax/jsPDF |
| **svg2pdf.js** | Converts SVG to PDF paths | yWorks/svg2pdf.js |
| **canvg** | Renders SVG on canvas | canvg/canvg |

This explains why:
- PDFs are ~260KB (essentially images)
- Generation takes ~10-15s (rendering + canvas operations)
- Text isn't selectable in the PDF (it's rasterized)

### 2. Why Direct API Doesn't Work

| Endpoint | What It Returns | Note |
|----------|-----------------|------|
| `POST /api/eprofile/europass-cv` | Profile data (JSON) | Import XML |
| `POST /api/eprofile/cv` | `{"id": "uuid"}` | Create CV |
| `GET /api/eprofile/cv/{uuid}/xml` | XML (not PDF!) | Download XML |

**There is NO server-side PDF generation.** The PDF is created entirely in the browser using:
1. html2canvas to screenshot the rendered CV
2. jsPDF to wrap the image in a PDF

### 3. pdfMake vs jsPDF

Initial assumption was Europass uses **pdfMake** (structured JSON → PDF).  
Reality: They use **jsPDF** with **html2canvas** (screenshot → PDF).

This means we CANNOT:
- Generate PDF without rendering in a browser
- Skip the UI and directly create the PDF
- Speed up by avoiding the client-side rendering

### 4. Performance Comparison

| Method | Time | Notes |
|--------|------|-------|
| Python Playwright (original) | ~19s | Full browser, uses Europass download |
| Python Playwright (optimized) | ~29s | Blocking analytics slowed it down |
| Node.js Playwright (page.pdf) | ~15s | But captures whole page, not CV |
| Node.js Playwright (Europass download) | ~18s | Same as Python |

## Recommended Approach

Keep using `europass_playwright.py` which:
1. Uses Europass's own download button
2. Gets the properly formatted PDF
3. ~19s is acceptable for batch processing

## Alternative: Self-Render Approach

For faster generation (at quality tradeoff):

```javascript
// Capture just the CV preview element
const cvElement = await page.$('.cv-preview-container');
const pdfBuffer = await page.pdf({
    // ... settings
});
```

This would be faster but:
- May have different formatting
- Won't match official Europass output exactly
- Requires identifying the correct CSS selector

## Code Location

- `src/europass_playwright.py` - Main Python script (recommended)
- `src/europass_node.js` - Node.js version
- `src/europass_api.py` - API-only approach (doesn't work for PDF)

## Key JS Files in Europass

| File | Size | Contains |
|------|------|----------|
| `chunk-QE5EVJFI.js` | 3.5MB | jsPDF, html2canvas, svg2pdf, canvg |
| `compact-cv-editor.module-*.js` | 442KB | CV editor Angular module |
| `chunk-3GPY6WJU.js` | 1.7MB | PDF utilities |
