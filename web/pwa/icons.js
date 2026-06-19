/* rackd machine icons — our own line illustrations (no logos, no brand likeness).
   Side-view gym-machine silhouettes. viewBox 0 0 64 64, stroke = currentColor.
   Pads / seats / weight-stacks use a light currentColor fill for richer reading.
   Iterate freely: edit a path here and it updates everywhere + in icons-preview.html. */
window.ICON_VIEWBOX = '0 0 64 64';
window.ICONS = {

  // seated chest press — seat + backrest, forward press arm + handle, rear weight stack
  press: `
    <path d="M6 55h52"/>
    <path d="M50 55V14"/>
    <rect x="43" y="17" width="11" height="24" rx="1.5" fill="currentColor" opacity=".22"/>
    <path d="M43 23h11M43 29h11M43 35h11"/>
    <path d="M21 55V41"/>
    <rect x="14" y="37" width="14" height="6" rx="2.5" fill="currentColor" opacity=".22"/>
    <path d="M28 43V21"/>
    <rect x="28" y="21" width="6" height="20" rx="2.5" fill="currentColor" opacity=".22"/>
    <path d="M34 31h11"/>
    <circle cx="35" cy="31" r="2.8"/>
  `,

  // shoulder press — near-vertical backrest, arms pressing up, rear stack
  shoulder: `
    <path d="M6 55h52"/>
    <path d="M50 55V14"/>
    <rect x="43" y="17" width="11" height="24" rx="1.5" fill="currentColor" opacity=".22"/>
    <path d="M43 23h11M43 29h11M43 35h11"/>
    <path d="M20 55V43"/>
    <rect x="14" y="39" width="13" height="5" rx="2.5" fill="currentColor" opacity=".22"/>
    <path d="M29 43V19"/>
    <rect x="29" y="19" width="6" height="24" rx="2.5" fill="currentColor" opacity=".22"/>
    <path d="M35 25l9-8M35 31l9-8"/>
    <circle cx="44" cy="16" r="2.8"/>
  `,

  // lat pulldown — tall frame, top pulley + bar on a cable, seat + thigh pad, stack
  pulldown: `
    <path d="M6 55h52"/>
    <path d="M16 55V11h32"/>
    <circle cx="44" cy="13" r="2.6"/>
    <path d="M44 16v9"/>
    <path d="M35 25h18"/>
    <path d="M40 25v4M48 25v4"/>
    <rect x="12" y="16" width="9" height="22" rx="1.5" fill="currentColor" opacity=".22"/>
    <path d="M12 22h9M12 28h9M12 34h9"/>
    <path d="M26 55V45"/>
    <rect x="22" y="41" width="15" height="5" rx="2.5" fill="currentColor" opacity=".22"/>
    <rect x="25" y="33" width="11" height="4" rx="2" fill="currentColor" opacity=".22"/>
  `,

  // seated cable row — chest pad, handle pulled back, cable to front stack, footplate
  row: `
    <path d="M6 55h52"/>
    <path d="M42 55V45"/>
    <rect x="36" y="41" width="14" height="5" rx="2.5" fill="currentColor" opacity=".22"/>
    <path d="M40 41V26"/>
    <rect x="37" y="24" width="5" height="16" rx="2.5" fill="currentColor" opacity=".22"/>
    <path d="M37 31H18"/>
    <circle cx="17" cy="31" r="2.8"/>
    <path d="M17 31h-5"/>
    <rect x="7" y="28" width="7" height="20" rx="1.5" fill="currentColor" opacity=".22"/>
    <path d="M7 34h7M7 40h7"/>
  `,

  // 45° leg press — reclined seat lower-left, angled sled rail, footplate + plate upper-right
  legpress: `
    <path d="M6 56h40"/>
    <path d="M13 56V44"/>
    <rect x="8" y="46" width="15" height="5" rx="2.5" fill="currentColor" opacity=".22"/>
    <path d="M21 50l5-6"/>
    <rect x="21" y="36" width="6" height="12" rx="2.5" transform="rotate(38 24 42)" fill="currentColor" opacity=".22"/>
    <path d="M24 44l24-18"/>
    <rect x="42" y="16" width="13" height="10" rx="1.5" fill="currentColor" opacity=".22"/>
    <path d="M48 26V40"/>
  `,

  // leg extension / curl — seat + backrest, pivoting lever with ankle pad
  leg: `
    <path d="M6 55h52"/>
    <path d="M20 55V41"/>
    <rect x="13" y="37" width="16" height="5" rx="2.5" fill="currentColor" opacity=".22"/>
    <path d="M29 41V22"/>
    <rect x="29" y="22" width="6" height="16" rx="2.5" fill="currentColor" opacity=".22"/>
    <circle cx="24" cy="41" r="2.4"/>
    <path d="M24 41l14 8"/>
    <rect x="36" y="46" width="10" height="5" rx="2.5" fill="currentColor" opacity=".22"/>
  `,

  // preacher / arm curl — angled arm pad over a seat, weighted bar at the bottom
  curl: `
    <path d="M6 55h52"/>
    <path d="M22 55V44"/>
    <rect x="15" y="40" width="14" height="5" rx="2.5" fill="currentColor" opacity=".22"/>
    <path d="M28 42l14-12"/>
    <rect x="30" y="28" width="14" height="6" rx="3" transform="rotate(-40 37 31)" fill="currentColor" opacity=".22"/>
    <path d="M30 50h16"/>
    <circle cx="30" cy="50" r="3.2" fill="currentColor" opacity=".22"/>
    <circle cx="46" cy="50" r="3.2" fill="currentColor" opacity=".22"/>
  `,

  // pec deck fly — central backrest, two arms swinging forward to handles
  fly: `
    <path d="M6 55h52"/>
    <path d="M32 55V42"/>
    <rect x="25" y="38" width="14" height="5" rx="2.5" fill="currentColor" opacity=".22"/>
    <path d="M32 38V20"/>
    <rect x="29" y="18" width="6" height="20" rx="2.5" fill="currentColor" opacity=".22"/>
    <path d="M32 24L20 31M32 24l12 7"/>
    <circle cx="19" cy="31" r="2.8"/>
    <circle cx="45" cy="31" r="2.8"/>
  `,

  // ab crunch machine — seat + back, chest pad and top handles
  ab: `
    <path d="M6 55h52"/>
    <path d="M22 55V42"/>
    <rect x="15" y="38" width="15" height="5" rx="2.5" fill="currentColor" opacity=".22"/>
    <path d="M30 42V16"/>
    <path d="M30 18h12"/>
    <circle cx="43" cy="18" r="2.6"/>
    <rect x="30" y="28" width="6" height="12" rx="2.5" fill="currentColor" opacity=".22"/>
  `,

  // standing calf raise — uprights with shoulder pads, raised foot platform
  calf: `
    <path d="M8 55h48"/>
    <path d="M22 55V20M34 55V20"/>
    <rect x="17" y="16" width="22" height="6" rx="3" fill="currentColor" opacity=".22"/>
    <rect x="20" y="46" width="16" height="5" rx="2" fill="currentColor" opacity=".22"/>
    <path d="M44 55V18"/>
    <rect x="40" y="22" width="9" height="20" rx="1.5" fill="currentColor" opacity=".22"/>
    <path d="M40 28h9M40 34h9"/>
  `,

  // generic selectorized machine — frame, seat, cable, weight stack
  machine: `
    <path d="M6 55h52"/>
    <path d="M48 55V14"/>
    <rect x="41" y="17" width="11" height="24" rx="1.5" fill="currentColor" opacity=".22"/>
    <path d="M41 23h11M41 29h11M41 35h11"/>
    <path d="M46 17v-4"/>
    <path d="M20 55V42"/>
    <rect x="13" y="38" width="14" height="5" rx="2.5" fill="currentColor" opacity=".22"/>
    <path d="M27 42V20"/>
    <rect x="27" y="20" width="6" height="20" rx="2.5" fill="currentColor" opacity=".22"/>
    <path d="M33 28h8"/>
  `,
};
