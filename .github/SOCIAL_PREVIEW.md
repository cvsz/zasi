# Social Preview Image — ZASI

> Repository: cvsz/zasi
> Upload at: Settings -> General -> Social preview

## Requirements

| Property | Value |
|---|---|
| Minimum size | 640x320px |
| Recommended size | 1280x640px |
| Format | PNG or JPG |
| Aspect ratio | 2:1 |

## Content Guidelines

The social preview appears on Google, Twitter/X, LinkedIn, Discord, GitHub.

### Recommended Content

- ZASI logo (transparent PNG, centered)
- Tagline: "Zero-Entropy Autonomous Superintelligence Infrastructure"
- Background: Dark theme matching ZASI brand
- Version: v32.0.0

## Brand Colors

| Color | Hex | Usage |
|---|---|---|
| Primary dark | #0a0f1a | Background |
| Cyan accent | #00d4ff | Logo glow, highlights |
| Cyan dim | #0088aa | Secondary elements |
| Text light | #e0e8f0 | Primary text |
| Text dim | #7a889a | Secondary text |

## Generation Methods

### Using ImageMagick

convert -size 1280x640 xc:'#0a0f1a' -fill '#00d4ff' -gravity center -pointsize 72 -font "DejaVu-Sans-Bold" -annotate +0+0 "ZASI" -pointsize 24 -fill '#7a889a' -font "DejaVu-Sans" -annotate +0+80 "Zero-Entropy Autonomous Superintelligence Infrastructure" -pointsize 16 -fill '#0088aa' -font "DejaVu-Sans" -annotate +0+120 "v32.0.0" zasi-social-preview.png

### Using Python (Pillow)

from PIL import Image, ImageDraw, ImageFont
img = Image.new('RGB', (1280, 640), '#0a0f1a')
draw = ImageDraw.Draw(img)
draw.text((640, 250), "ZASI", fill='#00d4ff', anchor='mm')
draw.text((640, 340), "Zero-Entropy Autonomous Superintelligence Infrastructure", fill='#e0e8f0', anchor='mm')
draw.text((640, 410), "v32.0.0", fill='#0088aa', anchor='mm')
img.save('zasi-social-preview.png')

## Validation

After upload:
1. Preview appears within 1-2 minutes
2. Validate with Open Graph debugger: https://developers.facebook.com/tools/debug/
3. Validate with Twitter Card validator: https://cards-dev.twitter.com/validator
4. GitHub preview updates automatically

## File Location

Upload at: Settings -> General -> Social preview -> Upload an image
URL: https://github.com/cvsz/zasi/settings/social-preview
