const paths = {
  grid: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  arrows: 'M4 7h15m-4-4 4 4-4 4M20 17H5m4-4-4 4 4 4',
  plug: 'm8 3 2 4m6-4-2 4M7 7h10v4a5 5 0 0 1-10 0zM12 16v5',
  wallet: 'M20 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0 0 4h15v13H5a2 2 0 0 1-2-2V5m17 7h-5v4h5',
  check: 'm7 12 3 3 7-7M21 12a9 9 0 1 1-5-8',
  refresh: 'M20 7v5h-5M4 17v-5h5M5 7a8 8 0 0 1 13-2l2 3M4 16l2 3a8 8 0 0 0 13-2',
  clock: 'M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
  'arrow-right': 'M4 12h16m-6-6 6 6-6 6',
  'chevron-right': 'm9 5 7 7-7 7',
  search: 'm16 16 5 5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
  filter: 'M4 7h16M7 12h10M10 17h4',
  receipt: 'M6 3h12v18l-3-2-3 2-3-2-3 2zM9 7h6M9 11h6M9 15h3',
  calendar: 'M4 5h16v16H4zM8 3v4m8-4v4M4 10h16m-12 4h2m4 0h2m-8 3h2',
  chart: 'M4 4v16h17M8 15l4-5 4 3 5-7',
  info: 'M12 11v6m0-10v.1M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
  lock: 'M5 10h14v11H5zM8 10V7a4 4 0 0 1 8 0v3m-4 5v2',
  shield: 'm12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6z m-4 10 3 3 5-6',
  rescue: 'M13 2 4 13h7l-1 9 10-12h-7z',
  sparkle: 'm12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z',
  code: 'm8 7-5 5 5 5m8-10 5 5-5 5m-3-14-2 18',
  menu: 'M4 6h16M4 12h16M4 18h16',
  close: 'm6 6 12 12M6 18 18 6',
  plus: 'M12 5v14M5 12h14',
}

export type IconName = keyof typeof paths

export function Icon({ name }: { name: IconName }) {
  return <svg className="icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>
}
