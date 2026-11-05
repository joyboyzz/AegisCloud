#!/usr/bin/env python3
"""Build the AegisCloud LinkedIn document carousel and GitHub banner.

Uses actual, sanitized demo screenshots. All text is composed locally so that
metrics and the prototype boundary remain accurate. Requires Pillow and joblib.
"""
from pathlib import Path
import os
import joblib
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "media"
PAGES = MEDIA / "carousel"
PAGES.mkdir(parents=True, exist_ok=True)
W, H = 1350, 1688
BG = (6, 11, 21)
INK = (241, 247, 255)
MUT = (162, 179, 205)
DIM = (110, 134, 165)
CYAN = (48, 213, 232)
VIOLET = (159, 123, 255)
MINT = (76, 225, 177)
AMBER = (255, 203, 93)
PANEL = (15, 25, 43)
LINE = (42, 59, 86)
M = joblib.load(ROOT / "artifacts" / "champion.joblib")
T = M["test_metrics"]


def font(size, weight="regular"):
    styles = {"regular": "Inter-Regular.otf", "medium": "Inter-Medium.otf",
              "bold": "InterDisplay-Bold.otf", "heavy": "InterDisplay-ExtraBold.otf"}
    choices = [Path("/usr/share/fonts/opentype/inter") / styles[weight],
               Path("/usr/share/fonts/truetype/dejavu") /
               ("DejaVuSans-Bold.ttf" if weight in ("bold", "heavy") else "DejaVuSans.ttf"),
               Path("C:/Windows/Fonts/arial.ttf")]
    for candidate in choices:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default(size)


def base():
    # A subtle vertical gradient plus soft edge glows, no external resources.
    im = Image.new("RGB", (1, H))
    px = im.load()
    for y in range(H):
        t = y / H
        px[0, y] = (int(7 + 3*t), int(13 + 2*t), int(24 + 5*t))
    im = im.resize((W, H)).convert("RGBA")
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    g.ellipse((780, -320, 1600, 470), fill=(24, 118, 147, 34))
    g.ellipse((-480, 1200, 440, 2050), fill=(76, 48, 164, 30))
    im = Image.alpha_composite(im, glow.filter(ImageFilter.GaussianBlur(120)))
    return im


def header(im, label="PROJECT SHOWCASE"):
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((96, 75, 158, 137), radius=18, fill=CYAN)
    f = font(32, "heavy")
    box = d.textbbox((0, 0), "A", font=f)
    d.text((127 - (box[2]-box[0])/2, 105 - (box[3]-box[1])/2 - box[1]),
           "A", font=f, fill=BG)
    d.text((180, 83), "AEGISCLOUD", font=font(26, "bold"), fill=INK)
    d.text((180, 117), label, font=font(17, "medium"), fill=DIM)
    d.line((96, 169, 1254, 169), fill=(39, 57, 78), width=2)


def footer(im, page):
    d = ImageDraw.Draw(im)
    d.line((96, 1555, 1254, 1555), fill=(40, 57, 80), width=2)
    d.text((96, 1585), "PRAVEEN SUDIREDDY  /  AEGISCLOUD", font=font(20, "bold"), fill=MUT)
    txt = f"{page:02d}  /  06"
    d.text((1254 - d.textlength(txt, font=font(20, "medium")), 1585), txt,
           font=font(20, "medium"), fill=DIM)


def label(im, text, y):
    d = ImageDraw.Draw(im)
    d.text((96, y), text, font=font(21, "bold"), fill=CYAN)


def lines(im, xy, texts, size=88, color=INK, leading=105, weight="heavy"):
    d = ImageDraw.Draw(im)
    for j, s in enumerate(texts):
        d.text((xy[0], xy[1] + j * leading), s, font=font(size, weight), fill=color)


def body(im, xy, texts, size=32, color=MUT, leading=45, weight="regular"):
    d = ImageDraw.Draw(im)
    for j, s in enumerate(texts):
        d.text((xy[0], xy[1] + j * leading), s, font=font(size, weight), fill=color)


def pill(im, x, y, text, color=CYAN, size=20):
    d = ImageDraw.Draw(im)
    f = font(size, "bold")
    width = int(d.textlength(text, font=f)) + 43
    d.rounded_rectangle((x, y, x+width, y+48), radius=23, fill=(18, 36, 53), outline=color, width=2)
    d.text((x+21, y+11), text, font=f, fill=color)
    return width


def screen(im, name, x, y, w):
    """Place one real screenshot in a rounded, bordered application frame."""
    source = Image.open(ROOT / "screenshots" / name).convert("RGB")
    h = int(w * source.height / source.width)
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((x-8, y-8, x+w+8, y+h+8), radius=25, fill=(0, 0, 0, 160))
    im.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(24)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((x-9, y-9, x+w+9, y+h+9), radius=25, fill=(24, 38, 60), outline=(76, 100, 131), width=2)
    source = source.resize((w, h), Image.Resampling.LANCZOS).convert("RGBA")
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w-1, h-1), radius=16, fill=255)
    im.paste(source, (x, y), mask)
    return h


def cover():
    source = Image.open(MEDIA / "design" / "cyber_background.png").convert("RGB")
    im = ImageOps.fit(source, (W, H), method=Image.Resampling.LANCZOS).convert("RGBA")
    # Darken left edge for high-contrast type without hiding the shield.
    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pix = grad.load()
    for x in range(W):
        a = max(0, min(205, int(205 * (1 - x / 870))))
        for y in range(H):
            pix[x, y] = (3, 8, 18, a)
    im = Image.alpha_composite(im, grad)
    header(im)
    label(im, "SECURITY  ·  MACHINE LEARNING  ·  CRYPTOGRAPHY", 246)
    lines(im, (96, 325), ["Adaptive", "security for", "cloud sessions."], size=92, leading=108)
    body(im, (100, 720), ["An educational prototype", "exploring identity, encryption", "and explainable session risk."], size=32, color=(195, 208, 225), leading=47)
    ww = pill(im, 100, 930, "SYNTHETIC DATA", CYAN)
    pill(im, 100 + ww + 18, 930, "EDUCATIONAL PROTOTYPE", VIOLET)
    body(im, (100, 1045), ["MFA  +  AES-256-GCM  +  ML"], size=27, color=INK, weight="bold")
    footer(im, 1)
    return im


def concept():
    im = base(); header(im); label(im, "THE IDEA", 230)
    lines(im, (96, 289), ["One console.", "Multiple layers."], size=88, leading=107)
    body(im, (100, 535), ["A practical workspace for exploring cloud-session security."], size=30)
    x = 100
    for txt, col in [("IDENTITY", MINT), ("RISK", CYAN), ("ENCRYPTION", VIOLET), ("AUDIT", AMBER)]:
        x += pill(im, x, 604, txt, col, size=19) + 16
    h = screen(im, "03_overview.png", 105, 723, 1140)
    body(im, (105, 723+h+40), ["Actual AegisCloud dashboard  ·  fictional demo data"], size=23, color=DIM)
    footer(im, 2)
    return im


def explain():
    im = base(); header(im); label(im, "EXPLAINABLE RISK", 230)
    lines(im, (96, 289), ["Risk you can", "explain."], size=90, leading=108)
    body(im, (100, 540), ["Model output + behavioral signals become a clear", "0–100 score with additive contributions."], size=30, leading=44)
    h = screen(im, "04_risk_console.png", 105, 706, 1140)
    body(im, (105, 706+h+39), ["ALLOW  /  STEP-UP  /  REVIEW  /  BLOCK", "Recommendations only; no cloud access is enforced."], size=24, color=MUT, leading=37, weight="medium")
    footer(im, 3)
    return im


def results():
    im = base(); header(im); label(im, "SYNTHETIC EXPERIMENT", 230)
    lines(im, (96, 289), ["Measured results.", "Honest boundaries."], size=81, leading=103)
    body(im, (100, 529), ["MLPClassifier  ·  1,350 synthetic holdout sessions"], size=29)
    d = ImageDraw.Draw(im)
    tiles = [
        (f"{T['accuracy']*100:.2f}%", "ACCURACY", "synthetic holdout", MINT),
        (f"{T['f1']:.4f}", "SUCCESS F1", "success = class 1", CYAN),
        (f"{T['roc_auc']:.4f}", "ROC-AUC", "synthetic outcomes", VIOLET),
    ]
    for i, (v, t, sub, col) in enumerate(tiles):
        x = 100 + i * 390
        d.rounded_rectangle((x, 650, x+365, 916), radius=24, fill=PANEL, outline=LINE, width=2)
        d.rounded_rectangle((x, 650, x+7, 916), radius=3, fill=col)
        d.text((x+25, 686), t, font=font(21, "bold"), fill=DIM)
        d.text((x+25, 745), v, font=font(70, "heavy"), fill=col)
        d.text((x+25, 857), sub, font=font(21, "regular"), fill=MUT)
    d.rounded_rectangle((100, 1000, 1250, 1268), radius=24, fill=PANEL, outline=LINE, width=2)
    d.text((136, 1036), "TRAINING DESIGN", font=font(21, "bold"), fill=CYAN)
    body(im, (136, 1083), ["9,000 generated sessions", "70% training   →   15% validation   →   15% holdout"], size=32, color=INK, leading=54, weight="medium")
    body(im, (104, 1332), ["Success is the positive class — not an attack label.", "26 isolated tests passed. LSTM/CNN training was not run."], size=25, color=MUT, leading=40)
    footer(im, 4)
    return im


def vault():
    im = base(); header(im); label(im, "DATA PROTECTION", 230)
    lines(im, (96, 289), ["Security is more", "than a score."], size=87, leading=105)
    body(im, (100, 535), ["Authenticated file encryption, tamper checks", "and a hash-linked audit trail."], size=30, leading=44)
    x = 100
    for txt, col in [("AES-256-GCM", CYAN), ("TAMPER TEST", VIOLET), ("AUDIT", AMBER)]:
        x += pill(im, x, 652, txt, col, size=19) + 16
    h = screen(im, "06_vault.png", 105, 770, 1140)
    body(im, (105, 770+h+37), ["Secret-sharing is a separate demo; local keys are not a production KMS."], size=22, color=MUT)
    footer(im, 5)
    return im


def next_steps():
    im = base(); header(im); label(im, "LEARN  /  BUILD  /  IMPROVE", 230)
    lines(im, (96, 289), ["Built to learn.", "Ready to explore."], size=87, leading=105)
    body(im, (100, 543), ["A prototype for asking better security questions —", "not a production security product."], size=30, leading=44)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((100, 682, 1250, 1104), radius=28, fill=PANEL, outline=LINE, width=2)
    d.text((140, 722), "NEXT UP", font=font(23, "bold"), fill=CYAN)
    items = ["Evaluate with real, consented, labelled telemetry", "Integrate provider-side access enforcement", "Add secure MFA delivery and managed keys", "Run the LSTM / 1D-CNN experiment"]
    for i, t in enumerate(items):
        yy = 790 + 65*i
        d.ellipse((142, yy+12, 153, yy+23), fill=(CYAN if i < 2 else VIOLET))
        d.text((175, yy), t, font=font(28, "medium"), fill=INK)
    d.text((102, 1191), "EXPLORE THE PROJECT", font=font(21, "bold"), fill=DIM)
    d.text((102, 1241), "github.com/joyboyzz/AegisCloud", font=font(37, "bold"), fill=CYAN)
    d.text((102, 1350), "Feedback and ideas are welcome.", font=font(30, "regular"), fill=MUT)
    footer(im, 6)
    return im


def github_banner():
    width, height = 1600, 620
    im = Image.new("RGBA", (width, height), (7, 12, 23, 255))
    art = Image.open(MEDIA / "design" / "cyber_background.png").convert("RGB")
    art = art.resize((500, height), Image.Resampling.LANCZOS).convert("RGBA")
    im.alpha_composite(art, (1100, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((80, 62, 136, 118), radius=16, fill=CYAN)
    d.text((97, 69), "A", font=font(33, "heavy"), fill=BG)
    d.text((155, 76), "AEGISCLOUD", font=font(23, "bold"), fill=CYAN)
    d.text((80, 165), "Adaptive security", font=font(77, "heavy"), fill=INK)
    d.text((80, 255), "for cloud sessions.", font=font(77, "heavy"), fill=INK)
    d.text((83, 381), "MFA   /   AES-256-GCM   /   EXPLAINABLE RISK", font=font(24, "bold"), fill=MUT)
    d.text((83, 493), "EDUCATIONAL PROTOTYPE  ·  SYNTHETIC DATA  ·  NOT CLOUD ENFORCEMENT", font=font(18, "medium"), fill=DIM)
    im.convert("RGB").save(MEDIA / "GitHub_Banner.png", optimize=True)


def main():
    builders = [cover, concept, explain, results, vault, next_steps]
    pages = []
    for i, builder in enumerate(builders, 1):
        im = builder().convert("RGB")
        im.save(PAGES / f"{i:02d}.png", optimize=True)
        pages.append(im)
    pages[0].save(MEDIA / "LinkedIn_Cover.png", optimize=True)
    pages[0].save(MEDIA / "LinkedIn_Carousel.pdf", save_all=True, append_images=pages[1:],
                  resolution=144.0, quality=90,
                  title="AegisCloud — Project Showcase", author="Praveen Sudireddy")
    github_banner()
    print("saved LinkedIn_Carousel.pdf, LinkedIn_Cover.png, GitHub_Banner.png and 6 page images")


if __name__ == "__main__":
    main()
