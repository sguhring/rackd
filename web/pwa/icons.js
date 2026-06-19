/* rackd machine icons — our own line illustrations (no logos, no brand likeness).
   Style: a simple person doing the movement + the machine's signature element
   (the way the instruction placard on the machine shows it) so a user can match the
   icon to the machine in front of them. viewBox 0 0 64 64, stroke = currentColor.
   Heads are filled; seats/pads/weight-stacks use a light currentColor fill.
   Iterate: edit a path → updates the app + icons-preview.html. */
window.ICON_VIEWBOX = '0 0 64 64';
window.ICON_STROKE = 3;

const HEAD = (x, y) => `<circle cx="${x}" cy="${y}" r="4.2" fill="currentColor" stroke="none"/>`;
const PAD  = (x, y, w, h, r=2) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="currentColor" opacity=".25" stroke="none"/>`;
const STACK = (x, y) => `${PAD(x,y,10,20,1.5)}<path d="M${x} ${y+5}h10M${x} ${y+10}h10M${x} ${y+15}h10" opacity=".55"/>`;

window.ICONS = {

  // chest press — upright seated figure pressing a handle forward; rear stack
  press: `
    <path d="M5 55h54"/>
    <path d="M20 51V30" opacity=".45"/>
    ${PAD(14,41,14,4)}
    ${HEAD(24,20)}
    <path d="M24 24v15"/>
    <path d="M24 28h15"/>
    <path d="M24 39l10 2v8"/>
    <path d="M41 22v18"/>
    ${STACK(47,24)}
  `,

  // shoulder press — seated figure pressing handles overhead
  shoulder: `
    <path d="M5 55h54"/>
    <path d="M22 51V30" opacity=".45"/>
    ${PAD(16,41,13,4)}
    ${HEAD(26,28)}
    <path d="M26 32v8"/>
    <path d="M26 33l10-9"/>
    <path d="M26 40l9 3"/>
    <path d="M36 22v-6"/>
    <path d="M30 18h12"/>
    ${STACK(47,24)}
  `,

  // lat pulldown — tall frame, bar on a cable up top, seated figure reaching up
  pulldown: `
    <path d="M5 55h54"/>
    <path d="M14 55V11h34"/>
    <path d="M40 11v6"/>
    <path d="M31 17h18"/>
    ${PAD(12,18,9,18,1.5)}
    <path d="M12 24h9M12 30h9" opacity=".55"/>
    ${PAD(24,42,15,4)}
    <path d="M33 42V32" opacity=".45"/>
    ${HEAD(33,28)}
    <path d="M33 32l7-13"/>
    <path d="M33 32l-1 9"/>
  `,

  // seated cable row — figure pulling a handle back; cable to a front stack
  row: `
    <path d="M5 55h54"/>
    ${PAD(34,42,15,4)}
    <path d="M43 42V31" opacity=".45"/>
    ${HEAD(43,27)}
    <path d="M43 31v8"/>
    <path d="M43 33L22 31"/>
    <path d="M43 39l-6 2"/>
    <path d="M22 31h-7"/>
    ${STACK(7,28)}
  `,

  // 45° leg press — reclined figure at lower-left pressing legs up the sled
  legpress: `
    <path d="M5 56h36"/>
    ${PAD(8,44,14,4)}
    ${HEAD(15,38)}
    <path d="M19 41l5 1"/>
    <path d="M24 42l9-7"/>
    <path d="M33 35l8-6"/>
    <path d="M30 48l22-17"/>
    ${PAD(44,18,12,9,1.5)}
  `,

  // leg extension — seated figure kicking lower legs up over the pad
  leg: `
    <path d="M5 55h54"/>
    <path d="M22 51V31" opacity=".45"/>
    ${PAD(16,41,13,4)}
    ${HEAD(26,21)}
    <path d="M26 25v14"/>
    <path d="M26 39l10-2"/>
    <path d="M36 37l6-9"/>
    ${PAD(40,24,7,5,2.5)}
    <path d="M26 28l9 2"/>
  `,

  // seated arm curl — upper arm down, forearm curling a weight up
  curl: `
    <path d="M5 55h54"/>
    <path d="M22 51V31" opacity=".45"/>
    ${PAD(16,41,13,4)}
    ${HEAD(25,20)}
    <path d="M25 24v15"/>
    <path d="M25 28l6 8"/>
    <path d="M31 36l7-10"/>
    <circle cx="39" cy="24" r="3.2" fill="currentColor" opacity=".4" stroke="none"/>
    <path d="M25 39l9 2v8"/>
  `,

  // pec deck fly — seated figure, two big arms swinging in to the front
  fly: `
    <path d="M5 55h54"/>
    ${PAD(26,42,12,4)}
    <path d="M32 42V24" opacity=".45"/>
    ${HEAD(32,20)}
    <path d="M32 26l-12 4"/>
    <path d="M32 26l12 4"/>
    <path d="M18 30V44"/>
    <path d="M46 30V44"/>
    ${PAD(15,28,4,16,2)}
    ${PAD(45,28,4,16,2)}
  `,

  // ab crunch — seated figure curling forward against a chest pad
  ab: `
    <path d="M5 55h54"/>
    ${PAD(18,42,14,4)}
    ${HEAD(24,22)}
    <path d="M24 26c2 6 5 9 12 10"/>
    <path d="M24 38l10 3"/>
    <path d="M38 18v18"/>
    ${PAD(34,20,4,14,2)}
  `,

  // standing calf raise — figure under shoulder pads, on a raised platform
  calf: `
    <path d="M5 55h54"/>
    ${PAD(20,46,20,4)}
    ${HEAD(30,16)}
    <path d="M30 20v18"/>
    <path d="M30 38l-4 8"/>
    <path d="M30 38l4 8"/>
    ${PAD(20,12,20,5,2.5)}
    <path d="M24 17v8M36 17v8" opacity=".5"/>
  `,

  // generic selectorized machine — seated figure, handle, weight stack
  machine: `
    <path d="M5 55h54"/>
    <path d="M21 51V31" opacity=".45"/>
    ${PAD(15,41,13,4)}
    ${HEAD(25,21)}
    <path d="M25 25v14"/>
    <path d="M25 30l13 1"/>
    <path d="M25 39l10 3"/>
    <path d="M40 22v20"/>
    ${STACK(46,22)}
  `,
};
