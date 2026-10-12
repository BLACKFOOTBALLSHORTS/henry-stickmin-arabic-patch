import argparse
import os
import re
import math
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import arabic_reshaper
from bidi.algorithm import get_display

# =====================================================================
# ENGINE CONFIGURATION
# =====================================================================
SUPER_SAMPLING = 8      # Internal render resolution multiplier
ALPHA_THRESHOLD = 200   # Alpha cutoff to ignore anti-aliasing artifacts
EXPORT_SCALE = 3        # HD Export Multiplier to kill pixelation natively

def resolve_font(requested_font):
    """Safely resolves the requested font or falls back to system fonts."""
    try:
        ImageFont.truetype(requested_font, 10)
        return requested_font
    except OSError:
        fallbacks = ["arial.ttf", "tahoma.ttf", "segoeui.ttf"]
        for f in fallbacks:
            try:
                ImageFont.truetype(f, 10)
                return f
            except OSError: continue
        raise OSError("[!] Fatal: No valid fonts found on the system.")

def find_image_smart(folder, filename):
    """Case-insensitive file discovery."""
    if not os.path.exists(folder): return None
    for f in os.listdir(folder):
        if f.lower() == filename.lower(): return os.path.join(folder, f)
    return None

def reshape_text(text):
    """Applies complex text shaping for connected Arabic letters."""
    return get_display(arabic_reshaper.reshape(text))

def get_bottom_island_bounds(im):
    """Scans from bottom to top to isolate text from illustrations (@overlay)."""
    W, H = im.size
    alpha = im.getchannel("A").load()
    
    bottom_y = -1
    for y in range(H - 1, -1, -1):
        if any(alpha[x, y] > ALPHA_THRESHOLD for x in range(W)):
            bottom_y = y
            break
            
    if bottom_y == -1: return (0, 0, W, H)
    
    top_y = bottom_y
    for y in range(bottom_y, -1, -1):
        if all(alpha[x, y] < ALPHA_THRESHOLD for x in range(W)):
            top_y = y + 1
            break
            
    return (0, top_y, W, bottom_y + 1)

def get_procedural_colors(im, mask_bbox):
    """Extracts procedural gradient colors and enforces HD contrast."""
    W, H = im.size
    rgb_im = im.convert("RGB")
    alpha = im.getchannel("A")
    pixels = []
    
    for y in range(mask_bbox[1], mask_bbox[3]):
        for x in range(mask_bbox[0], mask_bbox[2]):
            if alpha.getpixel((x, y)) > ALPHA_THRESHOLD:
                pixels.append(rgb_im.getpixel((x, y)))
    
    if not pixels: return (255, 255, 255), (200, 200, 200), (0, 0, 0)

    pixels.sort(key=lambda p: 0.299*p[0] + 0.587*p[1] + 0.114*p[2])
    
    # Outline Pitch Black Clamp
    outline_c = pixels[:max(1, len(pixels)//15)][0]
    if sum(outline_c)/3 < 100: outline_c = (0, 0, 0)
    
    # Top Color Highlight Clamp (User Tweak)
    top_c = pixels[-max(1, len(pixels)//10)]
    if sum(top_c)/3 > 160: top_c = (255, 255, 255)
    
    bottom_c = pixels[len(pixels)//2]
    
    # Remove gradient if the original image was solid
    if sum(top_c)/3 - sum(bottom_c)/3 < 15:
        bottom_c = top_c

    return top_c, bottom_c, outline_c

def blend_color(c1, c2, factor):
    """Interpolates between two RGB colors."""
    return tuple(int(c1[i] + (c2[i] - c1[i]) * factor) for i in range(3))

def render_fluid_hd_label(text, ref_path, font_path, is_overlay=False, manual_angle=None):
    ref = Image.open(ref_path).convert("RGBA")
    W, H = ref.size
    
    # 1. Determine Extraction Bounding Box
    if is_overlay:
        text_bbox = get_bottom_island_bounds(ref)
    else:
        text_bbox = ref.getchannel("A").getbbox() or (0, 0, W, H)

    top_c, bottom_c, outline_c = get_procedural_colors(ref, text_bbox)
    
    display_text = reshape_text(text)
    actual_font_path = resolve_font(font_path)
    
    sw, sh = W * SUPER_SAMPLING, H * SUPER_SAMPLING
    canvas = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    
    target_w = (text_bbox[2] - text_bbox[0]) * SUPER_SAMPLING * 0.82
    target_h = (text_bbox[3] - text_bbox[1]) * SUPER_SAMPLING * 0.82
    
    # Calculate Font Size dynamically based on text isolation area
    font_size = 10
    for s in range(10, 1000, 2):
        test_f = ImageFont.truetype(actual_font_path, s)
        l, t, r, b = draw.multiline_textbbox((0, 0), display_text, font=test_f, align="center")
        if (r-l) < target_w and (b-t) < target_h: font_size = s
        else: break
    
    font = ImageFont.truetype(actual_font_path, font_size)
    l, t, r, b = draw.multiline_textbbox((0, 0), display_text, font=font, align="center")
    
    # Center specifically inside the isolated area
    cx = (text_bbox[0] + text_bbox[2]) * SUPER_SAMPLING // 2 - (r + l) // 2
    cy = (text_bbox[1] + text_bbox[3]) * SUPER_SAMPLING // 2 - (b + t) // 2

    # =================================================================
    # FLUID MORPHOLOGICAL STROKE (Spike-Proof)
    # =================================================================
    raw_text_mask = Image.new("L", (sw, sh), 0)
    ImageDraw.Draw(raw_text_mask).multiline_text((cx, cy), display_text, font=font, fill=255, align="center")
    
    stroke_thickness_radius = font_size * 0.08
    expanded_mask = raw_text_mask.filter(ImageFilter.GaussianBlur(radius=stroke_thickness_radius))
    
    solid_stroke_mask = expanded_mask.point(lambda p: 255 if p > 15 else 0)
    final_stroke_mask = solid_stroke_mask.filter(ImageFilter.GaussianBlur(radius=3))
    
    stroke_layer = Image.new("RGBA", (sw, sh), outline_c + (255,))
    stroke_layer.putalpha(final_stroke_mask)
    
    # =================================================================
    # PROCEDURAL GRADIENT FILL
    # =================================================================
    fill_layer = Image.new("RGBA", (sw, sh))
    rendered_text_bbox = raw_text_mask.getbbox()
    if rendered_text_bbox:
        t_top, t_bottom = rendered_text_bbox[1], rendered_text_bbox[3]
        for y in range(t_top, t_bottom):
            factor = (y - t_top) / max(1, (t_bottom - t_top))
            current_color = blend_color(top_c, bottom_c, factor)
            ImageDraw.Draw(fill_layer).line([(rendered_text_bbox[0], y), (rendered_text_bbox[2], y)], fill=current_color + (255,))
    fill_layer.putalpha(raw_text_mask)
    
    canvas.alpha_composite(stroke_layer)
    canvas.alpha_composite(fill_layer)
    
    # Apply Manual Rotation if detected
    angle = manual_angle if manual_angle is not None else 0.0
    if abs(angle) > 0.5:
        canvas = canvas.rotate(angle, resample=Image.BICUBIC, expand=False)
    
    # =================================================================
    # HD EXPORT PIPELINE
    # Downsamples to EXPORT_SCALE and applies Unsharp Mask
    # =================================================================
    final_w, final_h = W * EXPORT_SCALE, H * EXPORT_SCALE
    hd_text_layer = canvas.resize((final_w, final_h), Image.Resampling.LANCZOS)
    hd_text_layer = hd_text_layer.filter(ImageFilter.UnsharpMask(radius=2.0, percent=180, threshold=3))
    
    if is_overlay:
        composite_result = ref.copy()
        # Erase English text using surgical bounds at 1x
        ImageDraw.Draw(composite_result).rectangle([text_bbox[0], text_bbox[1], text_bbox[2], text_bbox[3]], fill=(0, 0, 0, 0))
        # Upscale the artwork background to match the 3x HD Text
        composite_result = composite_result.resize((final_w, final_h), Image.Resampling.LANCZOS)
        # Paste HD Arabic text under HD artwork
        composite_result.alpha_composite(hd_text_layer)
        return composite_result
    else:
        return hd_text_layer

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sheet", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--font", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    if not os.path.exists(args.sheet): return

    with open(args.sheet, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()

    for line in lines:
        if "=" not in line or line.startswith("#"): continue
        key_part, text = line.split("=", 1)
        text = text.strip()
        
        # Parse logic flags from key
        is_overlay = False
        manual_angle = None
        
        if "@overlay" in key_part.lower():
            is_overlay = True
            key_part = re.sub(r'(?i)@overlay', '', key_part)
            
        if "@" in key_part:
            parts = key_part.split("@")
            key_part = parts[0]
            try:
                manual_angle = float(parts[1])
            except ValueError: pass
            
        key = re.sub(r'[^\w\-_]', '', key_part.strip())

        ref_path = find_image_smart(args.ref, f"{key}.png")
        if ref_path:
            try:
                result = render_fluid_hd_label(text, ref_path, args.font, is_overlay, manual_angle)
                result.save(os.path.join(args.out, f"{key}.png"))
                status = "[HD OVERLAY]" if is_overlay else "[HD VECTOR]"
                print(f"[+] {status} Generated: {key}.png")
            except Exception as e:
                print(f"[-] Failed {key}: {e}")

if __name__ == "__main__":
    main()