# VidDL design QA

Source: `ui.jpeg`, 1024 × 1536 px; inferred 1024 px CSS width, density 1.
Implementation: `docs/qa/desktop.png` (1024 × 1701 px), `docs/qa/mobile.png` (390 × 2119 px); production build served by FastAPI. Headless Chrome was explicitly approved after the in-app browser was unavailable. No rescaling was applied: one image pixel per CSS pixel.
State: home, blank URL, dark theme. Desktop viewport 1024 × 1536 CSS px, density 1; mobile 390 × 844 CSS px, density 1. Full-page images extend vertically with content. The screenshot is a website reference, not a mobile device frame.

## Comparison history

1. `docs/qa/desktop-first.png`: reference and full implementation opened together. P2: an added eyebrow and tall header pushed the primary form ~70 px down and the quality area ~120 px below the reference. P2: extra component padding increased overall density drift. Fixed by removing the eyebrow, matching the 60 px desktop header, reducing hero spacing, and aligning quality/feature panel dimensions. The reference form and quality area are now approximately aligned (form y312 versus y306; quality y453 versus y451). Additional limits text accounts for the remaining panel height.
2. Browser interactions found P0: changing link state removed `href` before the browser's default action, preventing saves. Fixed by keeping the download URL on the link. Verified with actual MDN media downloads on desktop and mobile, not a mocked file response.
3. Mobile check found P2: the duplicate header CTA wrapped onto two lines. It is now hidden on mobile; primary download action stays visible and the mobile navigation has its own toggle. Verified in the final `mobile.png` and `mobile-qualities.png` captures. No P0/P1/P2 findings remain.
4. Final full-view comparison opened the source and desktop/mobile captures together. Focused evidence: `desktop-hero.png` (1024 × 568), `mobile-hero.png` (390 × 530), and `mobile-qualities.png` (390 × 2363). The main form, labels, quality options and selected/confirmation state are legible with no overlapping controls. The extra desktop height comes from the limit note, availability note, fuller body text and footer; these are intentional product additions.

## Required fidelity surfaces

- Typography: Outfit headings and DM Sans body text preserve the geometric source style, two-line headline, weight hierarchy and centered alignment. Exact source font was not supplied. Font files are local, with no runtime font-provider dependency. Desktop/body copy is readable; mobile URL input is 16 px to avoid forced input zoom. Small source-like metadata remains secondary.
- Layout: two-line headline, central URL form, quality panel, four feature cards, eight platform tiles, three-step panel and purple-blue CTA follow the reference. Mobile uses two-column features, four-column platforms and stacked steps. Extra session/error/progress/permission states extend the selected reference appropriately.
- Colors: near-black background, indigo panels, thin blue-purple borders, violet controls, purple-blue accents and cyan privacy icon follow the reference palette.
- Assets: standard Simple Icons brand marks and Phosphor interface icons, not hand-drawn SVG substitutes. Raster-like dimensional lighting in the reference is simplified to branded icon tiles; no external thumbnails or generated marketing imagery are required for the empty state. This is accepted P3 styling variance, not missing product imagery.
- Copy: 4K/premium and app-install promises are replaced with the agreed free 1080p cap and browser downloads. MP4/WebM reflect real output containers. No unsupported “100% safe” or universal success promises. Availability, temporary storage and rights terms are exposed in relevant places.

## Interaction evidence

- Desktop/mobile invalid URL errors, dynamic quality choices, checkbox gating, progress, platform hints, keyboard dialog dismissal and navigation.
- Real MDN public sample checked and downloaded through actual backend on desktop and mobile: 540p MP4, 1,128,375 bytes. Browser filename `flower.mp4` verified.
- Generated media integration test verifies actual FFmpeg merge includes audio and uses selected 360p even when a 720p source is available.
- No browser page exceptions in tested flows; homepage console errors checked and absent. 320 px, 768 px tablet and 384 px zoom-equivalent viewport checks passed. The zoom check models the reduced CSS viewport of 200% browser zoom; it is not a claim of independently verified browser zoom or OS text scaling.
- Verification: 45 backend tests passed, including real generated-video/audio merging. Ten desktop/mobile browser scenarios passed across the final full run and the corrected zoom-equivalent test rerun. The original CSS `zoom` test was replaced because it does not change media-query breakpoints like browser zoom does; no production code was changed to suppress overflow.

## Final check

final result: passed

No actionable P0/P1/P2 findings remain. Follow-up P3 only: exact source-font matching and raster-style brand-tile lighting. No deployment or Docker execution is claimed by this visual report. Real download evidence is for the MDN public example, not a guarantee of social-platform availability.
