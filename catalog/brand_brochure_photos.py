"""Attach manufacturer brochure photos to marketplace-listed machines, per brand.

    python catalog/brand_brochure_photos.py technogym            # dry run + contact sheet
    python catalog/brand_brochure_photos.py technogym --write    # attach to catalog json + DB
    python catalog/brand_brochure_photos.py all --write

One registry entry per brand: the brochure PDF(s) in docs/, a PHOTOS map that
pins every product to (pdf, page, image xref) — checked by eye against the page
renders — and a MAP from our marketplace model string to that product. Only
rows still carrying a marketplace URL are touched.

Sources (all official, recovered from the manufacturers' sites or the Wayback
Machine — see docs/DATA_SOURCES.md):
  technogym  docs/technogym-strength-collection-2010.pdf  Selection / Element+ / Pure Strength
  matrix     docs/matrix-strength-brochure-2021.pdf       Ultra (G7) / Versa (VS) / Aura (G3)
  precor     docs/precor-2020-catalog.pdf                  Discovery Plate Loaded (DPL) / Vitality (C0xxES)
  nautilus   docs/nautilus-nitro-plus-brochure.pdf, -xpload-, -evo-
  keiser     docs/keiser-catalog-2007.pdf                  Air 250 / Air 300 / Infinity
"""
from __future__ import annotations

import base64
import io
import json
import re
import sqlite3
import sys
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
DB = ROOT / "api" / "rackd.db"
WWW_IMG = ROOT / "tools" / "cap" / "www" / "img"
MAX_PX, JPEG_Q = 512, 82

TG = "technogym-strength-collection-2010.pdf"
MX = "matrix-strength-brochure-2021.pdf"
PR = "precor-2020-catalog.pdf"
PR19 = "Precor-2019-Catalog-ENG.pdf"          # last catalog with the Discovery Selectorized (DSL) line
NP, NX, NE = "nautilus-nitro-plus-brochure.pdf", "nautilus-xpload-brochure.pdf", "nautilus-evo-brochure.pdf"
NC = "Nautilus Strength Catalog.pdf"          # ONE (S6) / EVO / NOVA (S8) / XPLoad — user-supplied
KS = "keiser-catalog-2007.pdf"
LF20 = "lifefitness_produktkatalog_2020.pdf"   # Optima (OS*) + Signature Cable Motion / Multi-Jungle
LF15 = "lifefitness-catalog-2015.pdf"          # Signature Series single stations (FZ*) + Pro2 (PS*SE) — Wayback
CX22 = "Cybex-Brochure_1649337819.pdf"         # Cybex product catalog 2022: Prestige VRS, Total Access, Bravo, Eagle NX

# brand -> {"dir": www image folder, "photos": {product: (pdf, page, xref)}, "map": {model: product}}
BRANDS: dict[str, dict] = {
    "Technogym": {
        "dir": "technogym",
        "photos": {
            # Selection (M9xx)
            "sel shoulder press": (TG, 24, 181), "sel delts machine": (TG, 24, 182), "sel chest press": (TG, 24, 183),
            "sel chest incline": (TG, 25, 187), "sel pectoral machine": (TG, 25, 188), "sel vertical traction": (TG, 25, 189),
            "sel pulldown": (TG, 26, 194), "sel pulley": (TG, 26, 195), "sel arm curl": (TG, 26, 196),
            "sel arm extension": (TG, 27, 200), "sel lat machine": (TG, 27, 201), "sel abdominal crunch": (TG, 27, 202),
            "sel total abdominal": (TG, 30, 1148), "sel lower back": (TG, 30, 1144), "sel rotary torso": (TG, 30, 1146),
            "sel upper back": (TG, 31, 1172), "sel low row": (TG, 31, 1170), "sel leg press": (TG, 31, 1168),
            "sel leg extension": (TG, 32, 230), "sel leg curl": (TG, 32, 228), "sel glute": (TG, 32, 229),
            "sel adductor": (TG, 33, 234), "sel abductor": (TG, 33, 235), "sel rotary calf": (TG, 33, 236),
            "sel multi hip": (TG, 36, 249), "sel cable jungle": (TG, 36, 251), "sel ercolina": (TG, 36, 250),
            "sel ercolina rehab": (TG, 37, 255), "sel crossover cables": (TG, 37, 256), "sel easy chin/dip": (TG, 37, 257),
            # Element+ (MBxxx)
            "el abductor": (TG, 54, 352), "el adductor": (TG, 54, 353), "el leg extension": (TG, 54, 354),
            "el leg curl": (TG, 55, 358), "el glute": (TG, 55, 359), "el leg press": (TG, 55, 360),
            "el chest press": (TG, 56, 365), "el pectoral machine": (TG, 56, 366), "el lower back": (TG, 56, 367),
            "el abdominal crunch": (TG, 57, 371), "el arm curl": (TG, 57, 372), "el low row": (TG, 57, 373),
            "el arm extension": (TG, 58, 958), "el shoulder press": (TG, 58, 956), "el vertical traction": (TG, 58, 954),
            "el lat machine": (TG, 59, 386), "el ercolina": (TG, 59, 384), "el ercolina rehab": (TG, 59, 385),
            # Pure Strength (MGxxxx)
            "pure chest press": (TG, 78, 509), "pure incline chest press": (TG, 78, 510), "pure wide chest press": (TG, 78, 511),
            "pure shoulder press": (TG, 79, 515), "pure pulldown": (TG, 79, 516), "pure row": (TG, 79, 517),
            "pure low row": (TG, 80, 521), "pure leg press": (TG, 80, 522), "pure calf": (TG, 80, 523),
            "pure rear kick": (TG, 81, 529),
        },
        "map": {
            "Selection Abdominal Crunch": "sel abdominal crunch", "Selection Arm Curl": "sel arm curl",
            "Selection Arm Tricep Extension": "sel arm extension", "Selection Chest Incline": "sel chest incline",
            "Selection Chest Press": "sel chest press", "Selection Chin / Dip Assist": "sel easy chin/dip",
            "Selection Delts Machine": "sel delts machine", "Selection Glute": "sel glute",
            "Selection Hip Abduction / Outer Thigh": "sel abductor", "Selection Hip Adduction / Inner Thigh": "sel adductor",
            "Selection Lat Pulldown": "sel lat machine", "Selection Leg Extension": "sel leg extension",
            "Selection Leg Press": "sel leg press", "Selection Low Row": "sel low row", "Selection Lower Back": "sel lower back",
            "Selection Pectoral Pec Fly Machine": "sel pectoral machine", "Selection Pulley": "sel pulley",
            "Selection Rotary Calf": "sel rotary calf", "Selection Rotary Torso Rotation": "sel rotary torso",
            "Selection Seated Leg Curl": "sel leg curl", "Selection Shoulder Press": "sel shoulder press",
            "Selection Total Abdominal": "sel total abdominal", "Selection Upper Back": "sel upper back",
            "Selection Vertical Traction": "sel vertical traction",
            "Element Abdominal Crunch": "el abdominal crunch", "Element Arm Curl": "el arm curl",
            "Element Chest Press": "el chest press", "Element Leg Extension": "el leg extension",
            "Element Leg Press": "el leg press", "Element Low Row": "el low row", "Element Lower Back": "el lower back",
            "Element Pectoral Machine": "el pectoral machine", "Element Shoulder Press": "el shoulder press",
            "Element Vertical Traction": "el vertical traction",
            "Pure Strength Linear Leg Press Plate Loaded": "pure leg press",
            "Pure Strength Plate Loaded Calf Press": "pure calf", "Pure Strength Plate Loaded Chest Press": "pure chest press",
            "Pure Strength Plate Loaded Row": "pure row", "Pure Strength Plate Loaded Shoulder Press": "pure shoulder press",
        },
    },
    "Matrix": {
        "dir": "matrix",
        "photos": {
            "ultra abdominal crunch": (MX, 28, 599), "ultra rotary torso": (MX, 28, 603), "ultra leg press": (MX, 29, 616),
            "versa leg press/calf": (MX, 44, 931),
            "aura shoulder press": (MX, 63, 1265), "aura rear delt/fly": (MX, 64, 1276), "aura dip/chin assist": (MX, 71, 1353),
            "aura leg press": (MX, 72, 1360), "aura rotary hip": (MX, 75, 1393), "aura functional trainer": (MX, 76, 1404),
            "aura 4-stack multi-station": (MX, 79, 1449),
        },
        "map": {
            "G7-S51 Abdominal Crunch": "ultra abdominal crunch", "G7-S55B Ultra Base Rotary Torso": "ultra rotary torso",
            "Ultra G7-S70 Leg Press": "ultra leg press", "Versa VS-S70 Leg Press / Calf Press": "versa leg press/calf",
            "G3 Overhead Shoulder Press": "aura shoulder press", "G3 Aura G3-S22 Rear Delt / Pec Fly": "aura rear delt/fly",
            "G3 Aura G3-S60 Dip / Chin Assist": "aura dip/chin assist", "G3-S70 Aura Leg Press": "aura leg press",
            "G3-S76 Aura Rotary Hip": "aura rotary hip", "Functional Trainer G3-MSFT300/400": "aura functional trainer",
            "G3-MS40 4 Stack Jungle Gym w/300 lb. Stack": "aura 4-stack multi-station",
        },
    },
    "Precor": {
        "dir": "precor",
        "photos": {
            "DPL0802": (PR, 41, 715), "DPL0603": (PR, 41, 708), "DPL0624": (PR, 41, 719), "DPL0601": (PR, 41, 712),
            "DPL0561": (PR, 42, 743), "DPL0560": (PR, 42, 747), "DPL0616": (PR, 42, 751),
            "DPL0550": (PR, 42, 762), "DPL0541": (PR, 42, 755), "DPL0540": (PR, 42, 759),
            "DPL0305": (PR, 43, 774), "DPL0308": (PR, 43, 778), "DPL0309": (PR, 43, 787),
            "DPL0520": (PR, 43, 782), "DPL0521": (PR, 43, 770), "DPL0311": (PR, 43, 785),
            "C003ES": (PR, 50, 927), "C001ES": (PR, 50, 937), "C002ES": (PR, 50, 925), "C019ES": (PR, 50, 923),
            "C012ES": (PR, 50, 939), "C023ES": (PR, 50, 931), "C005ES": (PR, 50, 921), "C007ES": (PR, 50, 929),
            "C014ES": (PR, 50, 933), "C011ES": (PR, 50, 935),
            "C024ES": (PR, 51, 949), "C027ES": (PR, 51, 955), "C015ES": (PR, 51, 947), "C010ES": (PR, 51, 945),
            "C026ES": (PR, 51, 953), "C008ES": (PR, 51, 959), "C025ES": (PR, 51, 951), "C028ES": (PR, 51, 957),
            # Discovery Selectorized (DSL) — 2019 catalog, code label under each photo
            "DSL0204": (PR19, 38, 618), "DSL0208": (PR19, 38, 620), "DSL0215": (PR19, 38, 616),
            "DSL0304": (PR19, 38, 614), "DSL0310": (PR19, 38, 612), "DSL0313": (PR19, 38, 606),
            "DSL0404": (PR19, 38, 608), "DSL0500": (PR19, 38, 610), "DSL0504": (PR19, 38, 622), "DSL0505": (PR19, 38, 604),
            "DSL0315": (PR19, 39, 630), "DSL0602": (PR19, 39, 638), "DSL0605": (PR19, 39, 634),
            "DSL0606": (PR19, 39, 632), "DSL0618": (PR19, 39, 636), "DSL0619": (PR19, 39, 628),
            "DSL0620": (PR19, 39, 640), "DSL0621": (PR19, 39, 642), "DSL0623": (PR19, 39, 644), "DSL0714": (PR19, 39, 646),
            "DSL0414": (PR19, 41, 668), "DSL0515": (PR19, 41, 661), "DSL0314": (PR19, 41, 665), "DSL0324": (PR19, 41, 657),
        },
        "map": {
            "DSL0204 Discovery Series Selectorized Biceps Curl": "DSL0204",
            "DSL0208 Discovery Series Selectorized Triceps Extension": "DSL0208",
            "DSL0313 Discovery Series Selectorized Back Extension": "DSL0313",
            "DSL0314 Discovery Series Selectorized Diverging Lat Pulldown": "DSL0314",
            "DSL0414 Discovery Series Selectorized Converging Chest Press": "DSL0414",
            "DSL0515 Discovery Series Selectorized Converging Shoulder Press": "DSL0515",
            "DSL0606 Discovery Series Selectorized Prone Leg Curl": "DSL0606",
            "DSL0619 Discovery Series Selectorized Seated Leg Curl": "DSL0619",
            "Discovery Abdominal Crunch - Current &": "DSL0714",
            "Discovery Diverging Bilateral Lat Pulldown - Current &": "DSL0314",
            "Discovery Glute Kickback - Clean": "DSL0618",
            "Discovery Leg Extension - Newest Series": "DSL0605",
            "Discovery Pec Fly & Rear Delt Combo - Current &": "DSL0505",
            "Discovery Pec Fly / Rear Delt DSL0505": "DSL0505",
            "Discovery Seated Leg Press - Current &": "DSL0602",
            "Discovery Seated Row - Current &": "DSL0310",
            "Discovery Series Selectorized Biceps Curl": "DSL0204",
            "Discovery Series Selectorized Glute Extension": "DSL0618",
            "Discovery Series Selectorized Leg Extension": "DSL0605",
            "Discovery Series Selectorized Line Inner Thigh": "DSL0620",
            "Discovery Series Selectorized Prone Leg Curl": "DSL0606",
            "Discovery Series Selectorized Seated Leg Curl": "DSL0619",
            "Discovery Tricep Extension": "DSL0208",
            "Discovery Series Plate Loaded Biceps Curl": "DPL0520", "Discovery Series Plate Loaded Calf Raise": "DPL0616",
            "Discovery Series Plate Loaded Chest Press": "DPL0540", "Discovery Series Plate Loaded Incline Press": "DPL0541",
            "Discovery Series Plate Loaded Low Row": "DPL0308", "Discovery Series Plate Loaded Seated Row": "DPL0309",
            "Discovery Series Plate Loaded Shoulder Press": "DPL0550",
            "Discovery Plate Loaded ISO Lateral Lat Pulldown": "DPL0305", "Discovery Linear Smith Machine": "DPL0802",
            "C010ES Vitality Leg Press / Calf Extension": "C010ES", "Vitality C027ES Leg Extension / Leg Curl": "C027ES",
            "Vitality Abductor/Adductor & Inner/Outer Thigh Combo": "C008ES", "Vitality Pec Fly & Rear Delt Combo": "C015ES",
            "Vitality S Line Dual Pulldown / Seated Row": "C026ES", "Vitality Series Chest Press": "C001ES",
            "Vitality Series Lat Pulldown": "C002ES", "Vitality Series Leg Extension": "C005ES",
            "Vitality Series Seated Leg Curl": "C007ES", "Vitality Series Shoulder Press": "C012ES",
        },
    },
    "Nautilus": {
        "dir": "nautilus",
        "photos": {
            # Nitro Plus (S5xxx) — photo sits beside its label on each page
            "S5VC": (NP, 4, 25), "S5IP": (NP, 4, 27), "S5PF": (NP, 4, 29), "S5RDPF": (NP, 4, 31),
            "S5OP": (NP, 5, 48), "S5LR": (NP, 5, 52), "S5MR": (NP, 5, 56), "S5PO": (NP, 5, 60), "S5CR": (NP, 5, 64),
            "S5LATP": (NP, 6, 106), "S5BC": (NP, 6, 108), "S5PC": (NP, 6, 110), "S5TE": (NP, 6, 112), "S5VTE": (NP, 6, 114),
            "S5SD": (NP, 7, 136), "S5AD": (NP, 7, 134), "S5LB": (NP, 7, 138), "S5RT": (NP, 7, 130),
            "S5LP": (NP, 8, 157), "S5LE": (NP, 8, 169), "S5LCP": (NP, 8, 161), "S5LC": (NP, 8, 165),
            "S5AA": (NP, 9, 204), "S5SC": (NP, 9, 200), "S5GRV": (NP, 9, 196), "F2FT": (NP, 9, 198),
            # XPLoad (P3xxx)
            "P3VC": (NX, 5, 28), "P3IP": (NX, 6, 41), "P3OP": (NX, 6, 43), "P3CR": (NX, 7, 60), "P3LATP": (NX, 7, 64),
            "P3BC": (NX, 8, 76), "P3TE": (NX, 8, 72), "P3SD": (NX, 8, 74), "P3LP": (NX, 9, 92), "P3ILP": (NX, 9, 94),
            "P3LE": (NX, 10, 104), "P3LCP": (NX, 10, 102), "P3SC": (NX, 10, 106), "P3DLS": (NX, 11, 120), "P3FWN": (NX, 11, 128),
            # EVO (S9xxx) — 2x2 / 2x3 tile grid
            "S9VC": (NE, 3, 124), "S9IP": (NE, 3, 128), "S9PF": (NE, 3, 132), "S9RDPF": (NE, 3, 120),
            "S9MR": (NE, 4, 166), "S9PO": (NE, 4, 170), "S9CR": (NE, 4, 174),
            "S9BC": (NE, 5, 205), "S9PC": (NE, 5, 209), "S9TE": (NE, 5, 213), "S9VTE": (NE, 5, 217),
            "S9OP": (NE, 6, 268), "S9LR": (NE, 6, 260), "S9SD": (NE, 6, 264), "S9LATP": (NE, 6, 256),
            "S9LB": (NE, 7, 319), "S9RT": (NE, 7, 315), "S9AB": (NE, 7, 311), "S9GRV": (NE, 7, 307),
            "S9LP": (NE, 8, 378), "S9LE": (NE, 8, 382), "S9LCP": (NE, 8, 362), "S9SC": (NE, 8, 370),
            "S9LC": (NE, 8, 366), "S9AA": (NE, 8, 374),
            # Nautilus ONE (S6) — strength catalog, p8
            "S6LE": (NC, 8, 196),
        },
        "map": {
            "ONE Leg Extension": "S6LE",
            "Nitro Plus Abductor & Adductor Combo Machine - Inner & Outer Thigh": "S5AA",
            "Nitro Plus BiLateral Overhead Tricep Extension": "S5VTE",
            "Nitro Plus Lat Pulldown": "S5LATP", "Nitro Plus Lateral Raise": "S5LR",
            "Nitro Plus Leg Extension": "S5LE", "Nitro Plus Low Back": "S5LB", "Nitro Plus Mid Row": "S5MR",
            "Nitro Plus Overhead Press": "S5OP", "Nitro Plus Pec Fly & Rear Delt Combo Machine": "S5RDPF",
            "Nitro Plus Pec Fly - RARE": "S5PF", "Nitro Plus Prone Lying Leg Curl - Original": "S5LCP",
            "Nitro Plus Pullover": "S5PO", "Nitro Plus Seated Dip - Immaculate": "S5SD",
            "Nitro Plus Seated Leg Curl": "S5LC", "Nitro Plus Seated Leg Press w/500 lb. Stack": "S5LP",
            "Nitro Plus V Bicep Preacher Curl Machine": "S5PC", "Nitro Plus Vertical Chest": "S5VC",
            "Nitro EVO Compound Row w / Swivel Handles": "S9CR", "Nitro EVO Overhead Bilateral Tricep Extension": "S9VTE",
            "Nitro EVO Seated Leg Press w/500 lb. Stack - Newest Series": "S9LP", "Nitro Evo Pullover": "S9PO",
            "XPLOAD Compound Plate Loaded Row": "P3CR", "XPLOAD ISO Lateral Overhead Tricep Extension - RARE": "P3TE",
            "XPLOAD ISO Lateral Plate Loaded Overhead Shoulder Press": "P3OP",
            "XPLOAD ISO Lateral Plate Loaded Vertical Chest Press": "P3VC",
            "XPLOAD Plate Loaded ISO Lateral Bicep": "P3BC", "XPLOAD Plate Loaded ISO Lateral Incline Chest Press": "P3IP",
            "XPLOAD Seated Calf Raise": "P3SC", "XPload ISO Lateral Plate Loaded Leverage Pulldown": "P3LATP",
            "Xpload 4 Way Neck": "P3FWN", "Xpload ISO Lateral Plate Loaded Vertical Chest Press - THE GOAT": "P3VC",
        },
    },
    "Life Fitness": {
        "dir": "lifefitness",
        "photos": {
            # Optima series, p38 — code label under each photo
            "OSCP": (LF20, 38, 1497), "OSRW": (LF20, 38, 1489), "OSSP": (LF20, 38, 1496), "OSPD": (LF20, 38, 1494),
            "OSBC": (LF20, 38, 1483), "OSTE": (LF20, 38, 1486), "OSLE": (LF20, 38, 1484), "OSLC": (LF20, 38, 1485),
            "OSLP": (LF20, 38, 1498), "OSAB": (LF20, 38, 1492),
            "OSLEC": (LF20, 38, 1499), "OSMP": (LF20, 38, 1501), "OSFLY": (LF20, 38, 1502), "OSLR": (LF20, 38, 1504),
            "OSBT": (LF20, 38, 1503), "OSHAA": (LF20, 38, 1505), "OP-DAP": (LF20, 38, 1482), "OP-SM": (LF20, 38, 1500),
            # Signature Series cable motion + multi-jungle, p36
            "CMDAP": (LF20, 36, 1426), "CMCC": (LF20, 36, 1424), "CMACO": (LF20, 36, 1425), "CMCP": (LF20, 36, 1427),
            "CMPD": (LF20, 36, 1428), "CMRW": (LF20, 36, 1429), "CMSP": (LF20, 36, 1430),
            "MJ4": (LF20, 36, 1422), "MJ5": (LF20, 36, 1423), "MJ8": (LF20, 36, 1420),
            # Signature Series benches, p35
            "SCDLR": (LF20, 35, 1414), "SBE": (LF20, 35, 1417),
            # Signature Series single stations (selectorized, FZ*), 2015 catalog p37-39
            "FZCP": (LF15, 37, 956), "FZPEC": (LF15, 37, 958), "FZFRD": (LF15, 37, 955),
            "FZRW": (LF15, 38, 980), "FZPD": (LF15, 38, 979), "FZSP": (LF15, 38, 982), "FZADC": (LF15, 38, 977),
            "FZSLP": (LF15, 38, 984), "FZLE": (LF15, 38, 983), "FZLR": (LF15, 38, 981), "FZBC": (LF15, 38, 974),
            "FZTP": (LF15, 38, 975), "FZLC": (LF15, 38, 985), "FZSLC": (LF15, 38, 978), "FZGL": (LF15, 38, 976),
            "FZHAD": (LF15, 39, 1001), "FZHAB": (LF15, 39, 996), "FZCE": (LF15, 39, 998),
            "FZAB": (LF15, 39, 1000), "FZBE": (LF15, 39, 997), "FZTR": (LF15, 39, 999),
            # Pro2 Series (selectorized, PS*SE), 2015 catalog p47-49
            "PSCPSE": (LF15, 47, 1152), "PSPECSE": (LF15, 47, 1150), "PSFLYSE": (LF15, 47, 1151),
            "PSRWSE": (LF15, 47, 1154), "PSPDSE": (LF15, 47, 1153), "PSFPDSE": (LF15, 47, 1155),
            "PSSPSE": (LF15, 48, 1184), "PSLRSE": (LF15, 48, 1175), "PSBCSE": (LF15, 48, 1180),
            "PSLESE": (LF15, 48, 1177), "PSLCSE": (LF15, 48, 1183), "PSSLCSE": (LF15, 48, 1174),
            "PSTESE": (LF15, 48, 1181), "PSADCSE": (LF15, 48, 1182), "PSSLPSE": (LF15, 48, 1173),
            "PSHGSE": (LF15, 48, 1176), "PSHADSE": (LF15, 48, 1179), "PSHABSE": (LF15, 48, 1178),
            "PSSCSE": (LF15, 49, 1196), "PSHCSE": (LF15, 49, 1192), "PSABCSE": (LF15, 49, 1194), "PSBESE": (LF15, 49, 1193),
        },
        "map": {
            "Signature Series Abdominal Ab Crunch Machine": "FZAB",
            "Signature Series Platinum Abdominal Ab Crunch Machine": "FZAB",
            "Signature Series Bilateral Bicep Curl": "FZBC",
            "Signature Series Platinum Bilateral Bicep Curl": "FZBC",
            "Signature Series Glute Kickback": "FZGL", "Signature Series Platinum Glute": "FZGL",
            "Signature Series Lat Pulldown w/300 lb. Stack": "FZPD",
            "Signature Series Leg Extension": "FZLE", "Signature Series Platinum Leg Extension": "FZLE",
            "Signature Series Overhead Shoulder Press": "FZSP", "Signature Series Platinum Shoulder Press": "FZSP",
            "Signature Series Platinum Back Extension": "FZBE", "Signature Series Platinum Calf": "FZCE",
            "Signature Series Platinum Chest Press w/300 lb. Stack": "FZCP",
            "Signature Series Platinum Seated Dip": "FZTP",
            "Signature Series Platinum Seated Leg Press w/400 lb. Stack": "FZSLP",
            "Signature Series Seated Leg Press w/400 lb. Stack": "FZSLP",
            "Signature Series Platinum Torso Rotation": "FZTR", "Signature Series Torso Rotation": "FZTR",
            "Signature Series Row & Rear Delt Combo w/300 lb. Stack": "FZRW",
            "Signature Series Seated Leg Curl": "FZSLC",
            "Pro 2 Abdominal": "PSABCSE", "Pro 2 Platinum Abdominal Crunch": "PSABCSE",
            "Pro 2 Assisted & Traditional Dip & Pull-up Combo": "PSADCSE",
            "Pro 2 Lat Pulldown w / 305 Lb Stack": "PSPDSE", "Pro 2 Lateral Raise": "PSLRSE",
            "Pro 2 Low Back Extension w / 305 Lb Stack": "PSBESE", "Pro 2 Platinum Low Back Extension": "PSBESE",
            "Pro 2 Platinum Seated Multi Grip Seated Row": "PSRWSE",
            "Pro 2 Platinum Shoulder Press": "PSSPSE", "Pro 2 SE Shoulder Press": "PSSPSE", "Pro 2 Shoulder Press": "PSSPSE",
            "Pro 2 Platinum Tricep Extension": "PSTESE", "Pro 2 Tricep Extension - Clean": "PSTESE",
            "Pro 2 SE Bicep Curl": "PSBCSE", "Pro 2 SE Platinum Bicep Curl": "PSBCSE",
            "Pro 2 SE Chest Press w/305 lb. Stack": "PSCPSE",
            "Pro 2 SE Horizontal Calf w/400 lb. Stack": "PSHCSE",
            "Pro 2 SE Leg Extension w/300 lb. Stack": "PSLESE",
            "Pro 2 SE Leg Press 400 lb. Stack": "PSSLPSE", "Pro 2 SE Platinum Leg Press 400 lb. Stack": "PSSLPSE",
            "Pro 2 Seated Leg Press": "PSSLPSE",
            "Pro 2 SE Pec Fly & Rear Delt Combo w/300 lb. Stack": "PSFLYSE",
            "Platinum Pro 2 Pec Fly & Rear Delt Combo Machine 300 lb. Stack": "PSFLYSE",
            "Pro 2 SE Seated Leg Curl w/300 lb. Stack": "PSSLCSE",
            "Optima Abductor/Adductor Inner/Outer Thigh Combo Machine": "OSHAA",
            "Optima Bicep & Tricep Combo Machine": "OSBT",
            "Optima Biceps/Triceps Dual Function Machine (OSBT)": "OSBT",
            "Optima Hip Abductor/Adductor Dual Function Machine (OSHAA)": "OSHAA",
            "Optima Lat Pulldown & Low Row Combo": "OSLR",
            "Optima Leg Extension & Prone Leg Curl Combo": "OSLEC",
            "Optima Leg Extension/Leg Curl Dual Function Machine": "OSLEC",
            "Optima Platinum Center Driven Leg Extension": "OSLE",
            "Optima Seated Leg Press - Current & - Clean": "OSLP",
            "Optima Seated Row": "OSRW",
            "Optima Series Pec Fly/Rear Delt Dual Function Machine": "OSFLY",
            "Optima Series Pec Fly/Rear Delt Dual Function Machine (OSFLY)": "OSFLY",
            "Optima Series Smith Machine Rack": "OP-SM",
            "Optima Triple Press Chest - Incline- Shoulder": "OSMP",
            "Signature Series MJ4 Multi Station": "MJ4",
            "Signature Series Dual Pulley MJ4 Multi Station": "MJ4",
            "Signature Series Dual Pulley Platinum MJ4 Multi Station": "MJ4",
            "Signature Series MJ4 Stack Jungle Gym W / 300 Lb Stack, Lat Pulldown, Low Row, Tricep Extension & Adjustable Pulley": "MJ4",
            "Signature Series Multi-Jungle MJ4": "MJ4",
            "Signature Series MJ5 Multi Stack Jungle Gym Cable Crossover - CLEAN": "MJ5",
            "Signature Series MJ8 Dual Adjustable Pulley 8 Station Jungle Gym": "MJ8",
            "Signature Series MJ8 Dual Adjustable Pulley 8 Station Jungle Gym w/Assisted Dip & Pull-up - 2019 Model": "MJ8",
            "Signature Series MJ8 Jungle Gym w/Dual Pulley Lat Pulldown Low Row": "MJ8",
            "Signature Series ISO Lateral Dual Pulley Lat Pulldown": "CMPD",
            "Signature Series ISO Lateral Dual Pulley & Traditional Lat Pulldown Combo": "CMPD",
            "Signature Series ISO Lateral & Traditional Low Cable Row Combo": "CMRW",
            "Signature Series Platinum VKR Dip Pull-up Leg Raise": "SCDLR",
            "Signature Series 45 Degree Adjustable Hyper Extension": "SBE",
        },
    },
    "Cybex": {
        "dir": "cybex",
        "photos": {
            # Prestige VRS selectorized, 2022 catalog p24-26 (heading left, photo to its right)
            "prestige chest press": (CX22, 24, 222), "prestige overhead press": (CX22, 24, 225),
            "prestige pulldown": (CX22, 24, 228), "prestige row": (CX22, 24, 231),
            "prestige arm curl": (CX22, 24, 237), "prestige arm extension": (CX22, 24, 234),
            "prestige triceps press": (CX22, 24, 240), "prestige lateral raise": (CX22, 24, 243),
            "prestige fly/rear delt": (CX22, 25, 249), "prestige dip/chin assist": (CX22, 25, 258),
            "prestige seated leg curl": (CX22, 25, 255), "prestige prone leg curl": (CX22, 25, 252),
            "prestige hip abduction": (CX22, 25, 261), "prestige hip adduction": (CX22, 25, 264),
            "prestige leg press": (CX22, 25, 270), "prestige leg extension": (CX22, 25, 267),
            "prestige standing calf": (CX22, 26, 285), "prestige glute": (CX22, 26, 276),
            "prestige abdominal": (CX22, 26, 279), "prestige back extension": (CX22, 26, 282),
            "prestige torso rotation": (CX22, 26, 288),
            # Prestige VRS Total Access, p34
            "ta chest press": (CX22, 34, 434), "ta overhead press": (CX22, 34, 437), "ta lat pull": (CX22, 34, 440),
            "ta row": (CX22, 34, 443), "ta cable column": (CX22, 34, 455), "ta leg press": (CX22, 34, 446),
            "ta leg extension": (CX22, 34, 449), "ta seated leg curl": (CX22, 34, 452),
            # Bravo functional trainers, p28
            "bravo pro": (CX22, 28, 300), "bravo advanced": (CX22, 28, 306), "bravo press": (CX22, 28, 303),
            "bravo lift": (CX22, 28, 309), "bravo pull": (CX22, 28, 315), "bravo basic": (CX22, 28, 312),
        },
        "map": {
            "Prestige Bicep": "prestige arm curl",
            "Prestige Chest Press": "prestige chest press",
            "Prestige Strength VRS Chest Press": "prestige chest press",
            "Prestige Glute Kickback - Current &": "prestige glute",
            "Prestige Lateral Raise": "prestige lateral raise",
            "Prestige Leg Extension - Latest Series": "prestige leg extension",
            "Prestige Platinum Assisted Dip & Pull-up Combo": "prestige dip/chin assist",
            "Prestige Platinum Pec Fly & Rear Delt Combo w300 lb. Stack": "prestige fly/rear delt",
            "Prestige Strength VRS Back Extension": "prestige back extension",
            "Prestige Strength VRS Leg Press": "prestige leg press",
            "Prestige Strength VRS Overhead Press": "prestige overhead press",
            "Prestige Strength VRS Standing Calf Raise 21110": "prestige standing calf",
            "Prestige Total Access Seated Leg Curl 21461": "ta seated leg curl",
            "Bravo 8800 Platinum Functional Trainer - Only 77″ Tall": "bravo advanced",
            "Bravo 8810 Tall Platinum w/Multi Grip Pull-up": "bravo advanced",
            "BRAVO 8840 HEAVY TALL CHIN-UP FUNCTIONAL TRAINER - MINT": "bravo advanced",
            "Bravo FT-450 Dual Adjustable Pulley Functional Trainer": "bravo advanced",
            "FT-450 Bravo Advanced Tall 8810-90 Functional Trainer": "bravo advanced",
            "Bravo Pro 18080": "bravo pro",
            "Bravo Pro Functional Trainer": "bravo pro",
        },
    },
    "Keiser": {
        "dir": "keiser",
        "photos": {
            "air250 leg press": (KS, 3, 9), "air300 leg press": (KS, 3, 7),
            "air300 leg extension": (KS, 4, 15), "air250 leg extension": (KS, 4, 17),
            "air250 standing hip": (KS, 5, 22), "air300 hip abductor": (KS, 5, 24), "air300 hip adductor": (KS, 5, 26),
            "air300 seated calf": (KS, 6, 32), "air300 squat": (KS, 6, 30),
            "air300 leg curl": (KS, 7, 38), "air250 seated leg curl": (KS, 7, 40),
            "air250 abdominal": (KS, 9, 46), "air250 lower back": (KS, 9, 48),
            "air250 upper back": (KS, 11, 59), "air250 lat pull down": (KS, 11, 57),
            "air250 seated chest press": (KS, 13, 70), "air350 seated butterfly": (KS, 13, 68),
            "air250 arm curl": (KS, 15, 79), "air250 triceps": (KS, 15, 77),
            "air300 lateral shoulder raise": (KS, 17, 90), "air250 military press": (KS, 17, 88),
            "infinity six pack": (KS, 21, 109), "infinity performance trainer": (KS, 21, 111),
        },
        "map": {
            "Air250 Abdominal Machine": "air250 abdominal", "Air250 Leg Press Machine": "air250 leg press",
            "Air250 Lower Back Machine": "air250 lower back", "Air250 Military Press Machine": "air250 military press",
            "Air250 Seated Chest Press Machine": "air250 seated chest press",
            "Air250 Seated Leg Curl Machine": "air250 seated leg curl", "Air250 Standing Hip Machine": "air250 standing hip",
            "Air300 Belt Squat Machine": "air300 squat", "Air300 Hip Abductor Machine": "air300 hip abductor",
            "Air300 Leg Extension Machine": "air300 leg extension", "Air300 Seated Calf Machine": "air300 seated calf",
            "Cable Machine Performance Trainer (Six Pack)": "infinity six pack",
        },
    },
}


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


_docs: dict[str, pymupdf.Document] = {}


def doc(name: str) -> pymupdf.Document:
    if name not in _docs:
        _docs[name] = pymupdf.open(ROOT / "docs" / name)
    return _docs[name]


def photo(pdf: str, xref: int) -> Image.Image:
    d = doc(pdf)
    pix = pymupdf.Pixmap(d, xref)
    if pix.colorspace and pix.colorspace.n > 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    smask = d.extract_image(xref).get("smask")
    im = Image.open(io.BytesIO(pix.tobytes("png")))
    if smask:                                           # soft mask may differ in size: composite in PIL
        mask = Image.open(io.BytesIO(pymupdf.Pixmap(d, smask).tobytes("png"))).convert("L")
        if mask.size != im.size:
            mask = mask.resize(im.size)
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im.convert("RGB"), mask=mask)
        return bg
    if im.mode == "RGBA":
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        return bg
    return im.convert("RGB")


def inline(path: Path) -> str:
    im = Image.open(path).convert("RGB")
    im.thumbnail((MAX_PX, MAX_PX))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=JPEG_Q, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def contact_sheet(files: list[tuple[str, Path]], dest: Path) -> None:
    W, cols = 170, 8
    rows = (len(files) + cols - 1) // cols
    d = pymupdf.open()
    page = d.new_page(width=W * cols, height=(W + 16) * max(rows, 1))
    for i, (label, fn) in enumerate(files):
        x, y = (i % cols) * W, (i // cols) * (W + 16)
        page.insert_image(pymupdf.Rect(x + 3, y + 3, x + W - 3, y + W - 3), filename=str(fn), keep_proportion=True)
        page.insert_text((x + 5, y + W + 10), label[:30], fontsize=7)
    page.get_pixmap(dpi=72).save(str(dest))


def run(brand: str, write: bool) -> None:
    spec = BRANDS[brand]
    out = WWW_IMG / spec["dir"]
    out.mkdir(parents=True, exist_ok=True)
    files: dict[str, Path] = {}
    for product, (pdf, pno, xref) in spec["photos"].items():
        fn = out / f"{slug(product)}.jpg"
        photo(pdf, xref).save(fn, "JPEG", quality=90)
        files[product] = fn
    contact_sheet(sorted(files.items()), out / f"_{slug(brand)}_sheet.png")

    resolved = json.loads(RESOLVED.read_text(encoding="utf-8"))
    by_model = {r["model"].strip().lower(): r for r in resolved if r["brand"] == brand}
    hits: list[tuple[dict, str]] = []
    for model, product in spec["map"].items():
        r = by_model.get(model.strip().lower())
        if r is None:
            print(f"   not in catalog json: {model}")
        elif product not in files:
            print(f"   no photo pinned for {product!r}: {model}")
        else:
            hits.append((r, product))
    for r, product in sorted(hits, key=lambda t: (t[1], t[0]["model"])):
        print(f"   {product:<30} <- {r['model'][:70]}")
    print(f"\n{brand}: {len(files)} photos -> {out.relative_to(ROOT)}, {len(hits)} rows matched")
    if not write:
        return

    for r, product in hits:
        r["image"] = f"img/{spec['dir']}/{slug(product)}.jpg"
    RESOLVED.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    con = sqlite3.connect(DB)
    (brand_id,) = con.execute("select id from brand where name=?", (brand,)).fetchone()
    uris = {p: inline(files[p]) for _, p in hits}
    updated = 0
    for r, product in hits:
        cur = con.execute(
            "update machine set image_url=? where brand_id=? and lower(trim(model))=lower(trim(?)) "
            "and (image_url is null or image_url like 'http%')",
            (uris[product], brand_id, r["model"]))
        updated += cur.rowcount
    con.commit()
    print(f"   attached {len(hits)} catalog rows, updated {updated} DB rows")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    write = "--write" in sys.argv
    if not args:
        raise SystemExit("usage: brand_brochure_photos.py <brand|all> [--write]   brands: " + ", ".join(BRANDS))
    brands = list(BRANDS) if args[0] == "all" else [next(b for b in BRANDS if b.lower() == args[0].lower())]
    for b in brands:
        run(b, write)
        print()


if __name__ == "__main__":
    main()
