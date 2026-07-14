import os
import argparse
import cv2
import fitz  # PyMuPDF
import numpy as np
from tqdm import tqdm

# -------------------------
# Paths
# -------------------------
# Defaults are relative to the repository root. This script lives at
# src/pdf_segmentation/segment_pdf_logs.py, so ../../data resolves to
# <repo_root>/data.
# Override at runtime with --input-dir / --output-dir (see CLI in
# main() below), or by editing these two constants directly.
_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)

INPUT_DIR = os.path.join(_REPO_ROOT, "data", "raw_pdfs")
OUTPUT_DIR = os.path.join(_REPO_ROOT, "data", "segmented_images")

# -------------------------
# PDF render settings
# -------------------------
PDF_DPI = 200
PDF_PPM_MULTIPLIER = 1.0

# -------------------------
# Crop settings for PDF pages
# Adjust after debug previews
# -------------------------
PDF_CROP_LEFT = 112
PDF_CROP_RIGHT = 712

PDF_FIRST_PAGE_TOP = 77
PDF_OTHER_PAGE_TOP = 0
PDF_BOTTOM_CROP = 0  # pixels removed from bottom

SEGMENT_METERS = 3.0

# -------------------------
# Debug
# -------------------------
DEBUG_CROP = False
DEBUG_KEEP_DEPTH = False
PROCESS_ONLY_FIRST_PDF = True


def render_pdf_pages(pdf_path, dpi=200):
    doc = fitz.open(pdf_path)

    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)

    pages = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        pix = page.get_pixmap(matrix=mat, alpha=False)

        img = np.frombuffer(pix.samples, dtype=np.uint8)
        img = img.reshape(pix.height, pix.width, pix.n)

        # PyMuPDF gives RGB; OpenCV uses BGR
        img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

        pages.append((page_idx, img_bgr))

    doc.close()
    return pages


def save_debug_crop_previews(pdf_name, pages):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for page_idx, img in pages[:5]:
        h, w = img.shape[:2]

        top = PDF_FIRST_PAGE_TOP if page_idx == 0 else PDF_OTHER_PAGE_TOP
        bottom = h - PDF_BOTTOM_CROP if PDF_BOTTOM_CROP > 0 else h

        preview = img.copy()

        right_draw = min(PDF_CROP_RIGHT, w - 1)
        left_draw = min(PDF_CROP_LEFT, w - 1)
        bottom_draw = min(bottom, h - 1)

        cv2.line(preview, (0, top), (w - 1, top), (0, 0, 255), 2)
        cv2.line(preview, (0, bottom_draw), (w - 1, bottom_draw), (0, 0, 255), 2)
        cv2.line(preview, (left_draw, 0), (left_draw, h - 1), (0, 255, 0), 2)
        cv2.line(preview, (right_draw, 0), (right_draw, h - 1), (255, 0, 0), 2)

        # Save readable top/middle/bottom previews
        windows = {
            "top": preview[:1200, :],
            "middle": preview[h // 2:h // 2 + 1200, :],
            "bottom": preview[max(0, h - 1200):, :]
        }

        stem = os.path.splitext(pdf_name)[0]
        pdf_out_dir = os.path.join(OUTPUT_DIR, stem)
        os.makedirs(pdf_out_dir, exist_ok=True)

        for name, crop in windows.items():
            out = os.path.join(
                OUTPUT_DIR,
                f"DEBUG_{stem}_page{page_idx + 1:03d}_{name}.png"
            )
            cv2.imwrite(out, crop)
            print(f"Saved debug preview: {out}")


def estimate_pixels_per_meter_from_depth_column(img_bgr):
    """
    Estimate pixels per meter using only long major tick marks.
    This ignores shorter minor ticks.
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # depth column is left of the geology image
    depth_col = gray[:, :PDF_CROP_LEFT]

    # dark pixels = tick marks / text
    dark = depth_col < 80

    # use only far-left tick-mark strip, not the depth numbers
    # adjust 60 if needed
    tick_strip_width = min(60, depth_col.shape[1])
    tick_area = dark[:, :tick_strip_width]

    # count dark pixels per row
    row_dark_count = tick_area.sum(axis=1)

    # major ticks are the longest horizontal dark marks
    threshold = np.percentile(row_dark_count, 98)
    major_rows = np.where(row_dark_count >= threshold)[0]

    if len(major_rows) < 3:
        print("Could not find enough major tick rows.")
        return None

    # group nearby rows into one tick center
    groups = []
    current = [major_rows[0]]

    for r in major_rows[1:]:
        if r - current[-1] <= 5:
            current.append(r)
        else:
            groups.append(current)
            current = [r]
    groups.append(current)

    centers = np.array([int(np.mean(g)) for g in groups])

    if len(centers) < 3:
        print("Could not group enough major tick centers.")
        return None

    diffs = np.diff(centers)

    # remove bad intervals
    diffs = diffs[(diffs > 50) & (diffs < 2000)]

    if len(diffs) == 0:
        print("Could not estimate major tick spacing.")
        return None

    pixels_per_meter = float(np.median(diffs))

    print("Major tick centers:", centers[:10])
    print("Major tick diffs:", diffs[:10])
    print(f"Estimated pixels per meter from major ticks: {pixels_per_meter:.2f}")

    return pixels_per_meter


def crop_pdf_body_pages(pages):
    """
    Crop each rendered PDF page to the useful log body.
    Keeps depth column if DEBUG_KEEP_DEPTH=True.
    """
    cropped_pages = []

    for page_idx, img in pages:
        h, w = img.shape[:2]

        top = PDF_FIRST_PAGE_TOP if page_idx == 0 else PDF_OTHER_PAGE_TOP
        bottom = h - PDF_BOTTOM_CROP if PDF_BOTTOM_CROP > 0 else h

        if DEBUG_KEEP_DEPTH:
            left = 0
        else:
            left = PDF_CROP_LEFT

        right = PDF_CROP_RIGHT

        top = max(0, min(top, h))
        bottom = max(0, min(bottom, h))
        left = max(0, min(left, w))
        right = max(0, min(right, w))

        if bottom <= top or right <= left:
            print(f"Skipping page {page_idx + 1}: invalid crop")
            continue

        cropped = img[top:bottom, left:right].copy()
        cropped_pages.append(cropped)

    return cropped_pages


def concatenate_pages(cropped_pages):
    if len(cropped_pages) == 0:
        return None

    # force same width
    min_w = min(p.shape[1] for p in cropped_pages)

    aligned = []
    for p in cropped_pages:
        aligned.append(p[:, :min_w])

    return np.vstack(aligned)


def segment_concatenated_image(full_img, pdf_name, ppm):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    segment_px = int(round(SEGMENT_METERS * ppm))

    if segment_px <= 0:
        print("Invalid segment height.")
        return 0

    h, w = full_img.shape[:2]
    stem = os.path.splitext(pdf_name)[0]

    pdf_out_dir = os.path.join(OUTPUT_DIR, stem)
    os.makedirs(pdf_out_dir, exist_ok=True)

    saved = 0

    for i, y0 in enumerate(range(0, h - segment_px + 1, segment_px)):
        y1 = y0 + segment_px
        segment = full_img[y0:y1, :].copy()

        if DEBUG_KEEP_DEPTH:
            h_seg, w_seg = segment.shape[:2]

            cv2.line(segment, (0, 0), (w_seg - 1, 0), (0, 0, 255), 2)
            cv2.line(segment, (0, h_seg - 1), (w_seg - 1, h_seg - 1), (0, 0, 255), 2)

            cv2.putText(
                segment,
                f"3 m | ppm={ppm:.2f} | px={segment_px}",
                (10, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 255),
                2
            )

        out_name = f"{stem}_seg{i:04d}_{SEGMENT_METERS:.1f}m.png"
        out_path = os.path.join(pdf_out_dir, out_name)

        cv2.imwrite(out_path, segment)
        saved += 1

    print(f"{pdf_name}: ppm={ppm:.2f}, segment_px={segment_px}, saved={saved}")
    return saved


def process_pdf(pdf_name):
    pdf_path = os.path.join(INPUT_DIR, pdf_name)

    print(f"Rendering PDF: {pdf_name}")
    pages = render_pdf_pages(pdf_path, dpi=PDF_DPI)

    print(f"Rendered {len(pages)} pages")

    if DEBUG_CROP:
        save_debug_crop_previews(pdf_name, pages)
        print("DEBUG_CROP=True, stopping before segmentation.")
        return 0

    # First crop WITH depth column only for ppm estimation
    old_debug_keep_depth = DEBUG_KEEP_DEPTH

    globals()["DEBUG_KEEP_DEPTH"] = True
    cropped_pages_with_depth = crop_pdf_body_pages(pages)

    ppm = None
    for p in cropped_pages_with_depth:
        ppm = estimate_pixels_per_meter_from_depth_column(p)
        if ppm is not None:
            break

    globals()["DEBUG_KEEP_DEPTH"] = old_debug_keep_depth

    if ppm is None:
        print("Could not estimate pixels per meter.")
        return 0

    # Now crop according to requested output mode
    cropped_pages = crop_pdf_body_pages(pages)

    if len(cropped_pages) == 0:
        print("No valid cropped pages.")
        return 0

    if ppm is None:
        print("Could not estimate pixels per meter.")
        return 0

    full_img = concatenate_pages(cropped_pages)

    if full_img is None:
        print("Could not concatenate pages.")
        
        return 0

    return segment_concatenated_image(full_img, pdf_name, ppm)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Render borehole-log PDFs to images, estimate the pixel-per-meter "
            "scale from depth-track tick marks, and cut the log into fixed-"
            "length (meters) image segments."
        )
    )
    parser.add_argument(
        "--input-dir", default=INPUT_DIR,
        help=f"Folder containing input PDFs (default: {INPUT_DIR})"
    )
    parser.add_argument(
        "--output-dir", default=OUTPUT_DIR,
        help=f"Folder where segmented images are written (default: {OUTPUT_DIR})"
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Process every PDF found in --input-dir (non-interactive)."
    )
    parser.add_argument(
        "--file", default=None,
        help="Process only this single PDF filename (non-interactive)."
    )
    return parser.parse_args()


def main():
    args = parse_args()

    globals()["INPUT_DIR"] = args.input_dir
    globals()["OUTPUT_DIR"] = args.output_dir

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    files = [
        f for f in sorted(os.listdir(INPUT_DIR))
        if f.lower().endswith(".pdf")
    ]

    if len(files) == 0:
        print(f"No PDFs found in {INPUT_DIR}")
        return

    print("\nAvailable PDFs:\n")
    for i, f in enumerate(files):
        print(f"[{i}] {f}")

    if args.file:
        files = [args.file]
    elif args.all:
        pass  # keep all files
    elif PROCESS_ONLY_FIRST_PDF:
        files = files[:1]
    else:
        choice = input("\nEnter PDF number to segment, or ENTER for all: ").strip()
        if choice != "":
            idx = int(choice)
            files = [files[idx]]

    total = 0
    for f in tqdm(files, desc="Processing PDFs"):
        total += process_pdf(f)

    print(f"Done. Saved {total} segments.")


if __name__ == "__main__":
    main()