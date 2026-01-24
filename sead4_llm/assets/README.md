# Assets Directory

This directory contains static assets for the SEAD-4 Analyzer Demo UI.

## Required Logos

### DCSA Logo

To display the DCSA logo in the demo UI:

1. Obtain the official DCSA (Defense Counterintelligence and Security Agency) logo
2. Save it as `dcsa_logo.png` in this directory
3. Recommended dimensions: 400x400 pixels (will be displayed at 100px width)

```bash
# Place your logo file here:
assets/dcsa_logo.png
```

If no logo file is present, the UI will display a blue placeholder badge with "DCSA" text.

### DOHA Logo

To display the DOHA logo in the demo UI:

1. Obtain the official DOHA (Defense Office of Hearings and Appeals) logo
2. Save it as `doha_logo.png` in this directory
3. Recommended dimensions: 400x400 pixels (will be displayed at 100px width)

```bash
# Place your logo file here:
assets/doha_logo.png
```

If no logo file is present, the UI will display a green placeholder badge with "DOHA" text.

## Supported Formats

- PNG (recommended) - supports transparency
- JPG/JPEG - solid background
- SVG - scalable vector graphics

## Usage in Demo

The logo appears in the header of the Streamlit demo UI:
- Location: Top left of the main page
- Size: 120px width (auto height)
- Aligned next to the page title

## Official DCSA Branding

For official DCSA logo files and branding guidelines, refer to:
- DCSA Branding Guide (internal)
- DCSA Public Affairs Office
- DoD Visual Information Guidelines

## Note

Ensure you have proper authorization to use official government logos and branding materials in your application.
