# “An unsupervised workflow for pre-annotation of borehole breakout from acoustic image logs.”

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Code accompanying the paper:

> Jack M. Faustinoni, Argos B. S. Schrank, Guilherme F. Chinelatto, Mateus Basso, Alexandre C. Vidal, Mateus Roder]. "An unsupervised workflow for pre-annotation of borehole breakout from acoustic image logs." *[JOURNA]*, 2026. [DOI / arXiv link]

This repository provides two independent, standalone routines used in the study:

1. **PDF log segmentation** (`src/pdf_segmentation/segment_pdf_logs.py`) — renders borehole-image PDF logs to raster images, estimates the depth scale (pixels per meter) from the depth-track tick marks, and cuts the resulting image into fixed-length depth segments (default: 3 m) for downstream analysis.
2. **Breakout pre-annotation pipeline** (`notebooks/breakout_annotator.ipynb`) — an interpretable image-processing pipeline that detects candidate borehole breakouts in acoustic/resistivity image-log segments, produces QC panels, binary masks, overlays, an automatic detection table, and an interactive visual QC form for manual validation.

The two routines are **independent**: each operates on its own folder of input images and can be run on its own. They are not chained together automatically, though in the study the segmented images produced by tool 1 can be used as input to tool 2 if desired (see [Data flow](#data-flow)).

## Repository structure

```
.
├── README.md
├── LICENSE
├── CITATION.cff
├── requirements.txt
├── .gitignore
├── data/
│   ├── raw_pdfs/            # input PDF logs for segment_pdf_logs.py (not versioned)
│   ├── segmented_images/    # output of segment_pdf_logs.py (not versioned)
│   └── breakout_images/     # input images for breakout_annotator.ipynb (not versioned)
├── docs/                    # supplementary material, figures, notes
├── notebooks/
│   └── breakout_annotator.ipynb   # breakout pre-annotation + visual QC pipeline
└── src/
    └── pdf_segmentation/
        └── segment_pdf_logs.py    # PDF-to-image rendering, scaling, and segmentation
```

`data/` ships empty (only `.gitkeep` placeholders) because borehole-log data is typically proprietary or too large for version control. Populate it locally with your own files before running the code, or point the scripts at a different location (see below).

## Installation

Requires Python 3.9+.

```bash
git clone https://github.com/[USERNAME]/[REPO NAME].git
cd [REPO NAME]
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

### 1. PDF log segmentation

Renders each PDF page, estimates the pixel-per-meter scale from the major tick marks in the depth track, concatenates pages into one continuous image, and slices it into fixed-length (meters) segment images.

```bash
python src/pdf_segmentation/segment_pdf_logs.py \
    --input-dir data/raw_pdfs \
    --output-dir data/segmented_images \
    --all
```

Key options (edit the constants at the top of the script, or pass flags):

| Parameter | Default | Description |
|---|---|---|
| `--input-dir` | `data/raw_pdfs` | Folder containing input PDFs |
| `--output-dir` | `data/segmented_images` | Folder where segmented PNGs are written |
| `--file NAME.pdf` | — | Process a single named PDF (non-interactive) |
| `--all` | off | Process every PDF found in `--input-dir` (non-interactive) |
| `PDF_DPI` | 200 | Rasterization resolution |
| `PDF_CROP_LEFT` / `PDF_CROP_RIGHT` | 112 / 712 | Horizontal crop bounds of the log body |
| `SEGMENT_METERS` | 3.0 | Length (in meters) of each output image segment |
| `DEBUG_CROP` | `False` | If `True`, saves crop-boundary previews instead of segmenting (use to calibrate crop bounds for a new log format) |

Run with no flags for the original interactive mode (lists PDFs found in `INPUT_DIR` and prompts for a selection).

Output: one subfolder per PDF under `--output-dir`, containing sequentially numbered `*_seg####_3.0m.png` images.

### 2. Breakout pre-annotation pipeline

Open the notebook and run its single cell:

```bash
jupyter notebook notebooks/breakout_annotator.ipynb
```

By default it reads images from `data/breakout_images` (edit the `INPUT_FOLDER` variable near the top of the cell to point elsewhere). The pipeline:

1. Preprocesses each image (bilateral filtering).
2. Segments dark pixels via K-means clustering.
3. Suppresses laterally continuous layers and vertical-line artifacts to isolate breakout-like candidates.
4. Computes a 1D azimuth signal and searches for a valid breakout pair (or single-breakout / continuity-rescue fallback) using a cascade of quality gates (valley depth, peak-to-background ratio, pair balance, cave-rich vetoes, etc.).
5. Builds the final mask, QC panel, and overlay image for each input.
6. Writes an automatic detection table (CSV) summarizing results per image.
7. Launches an interactive `ipywidgets` visual QC form (`launch_visual_qc_form()`) for manual confirmation of automatic detections.
8. After manual QC, call `summarize_visual_qc()` to produce the final manual + visual-match summary table.

All tunable parameters (preprocessing, K-means, layer/artifact suppression, azimuth-pair gating, image-regime presets `cave_poor` / `cave_rich`, etc.) are declared as constants near the top of the cell. Outputs (QC panels, masks, overlays, CSV tables) are written under `<INPUT_FOLDER>/breakout_preannotator/`.

**Note:** `ipywidgets` is required only for the interactive QC form; install it (`pip install ipywidgets`) and restart the kernel if you see a warning that it is missing.

## Data flow

```
data/raw_pdfs/*.pdf
        │  segment_pdf_logs.py
        ▼
data/segmented_images/<pdf_stem>/*_seg####_3.0m.png
        │  (optional: copy/move into data/breakout_images/ for step 2)
        ▼
data/breakout_images/*.png
        │  breakout_annotator.ipynb
        ▼
data/breakout_images/breakout_preannotator/
    ├── <mode>_kmeans/           # QC panels, masks, overlays
    └── _automatic_qc_tables/    # automatic + manual visual-QC CSV tables
```

The two stages are decoupled by design: `breakout_annotator.ipynb` accepts any folder of appropriately scaled image-log segments, not only the output of `segment_pdf_logs.py`.

## Reproducing paper results

[Describe here which dataset(s), parameter presets (e.g. `IMAGE_REGIME = "cave_rich"` vs `"cave_poor"`), and QC tables correspond to the figures/tables in the paper.]

## Citation

If you use this code, please cite the paper (see [`CITATION.cff`](CITATION.cff)):

```bibtex
@article{[citekey],
  title   = {[PAPER TITLE HERE]},
  author  = {[AUTHOR NAMES HERE]},
  journal = {[JOURNAL / CONFERENCE]},
  year    = {2026},
  doi     = {[DOI]}
}
```

## License

Released under the [MIT License](LICENSE).

## Contact

[NAME] — [email] — [affiliation]
