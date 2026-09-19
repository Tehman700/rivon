// EU + EEA + Switzerland and the UK: Rivon's launch market and neighbours.
export const COUNTRIES: { code: string; name: string }[] = [
  ["AT", "Austria"], ["BE", "Belgium"], ["BG", "Bulgaria"], ["HR", "Croatia"], ["CY", "Cyprus"],
  ["CZ", "Czechia"], ["DK", "Denmark"], ["EE", "Estonia"], ["FI", "Finland"], ["FR", "France"],
  ["DE", "Germany"], ["GR", "Greece"], ["HU", "Hungary"], ["IS", "Iceland"], ["IE", "Ireland"],
  ["IT", "Italy"], ["LV", "Latvia"], ["LI", "Liechtenstein"], ["LT", "Lithuania"],
  ["LU", "Luxembourg"], ["MT", "Malta"], ["NL", "Netherlands"], ["NO", "Norway"], ["PL", "Poland"],
  ["PT", "Portugal"], ["RO", "Romania"], ["SK", "Slovakia"], ["SI", "Slovenia"], ["ES", "Spain"],
  ["SE", "Sweden"], ["CH", "Switzerland"], ["GB", "United Kingdom"],
].map(([code, name]) => ({ code, name }))

export const TIMEZONES = [
  "Europe/Amsterdam", "Europe/Athens", "Europe/Berlin", "Europe/Bratislava", "Europe/Brussels",
  "Europe/Bucharest", "Europe/Budapest", "Europe/Copenhagen", "Europe/Dublin", "Europe/Helsinki",
  "Europe/Lisbon", "Europe/Ljubljana", "Europe/London", "Europe/Luxembourg", "Europe/Madrid",
  "Europe/Malta", "Europe/Oslo", "Europe/Paris", "Europe/Prague", "Europe/Riga", "Europe/Rome",
  "Europe/Sofia", "Europe/Stockholm", "Europe/Tallinn", "Europe/Vaduz", "Europe/Vienna",
  "Europe/Vilnius", "Europe/Warsaw", "Europe/Zagreb", "Europe/Zurich", "Atlantic/Canary",
  "Atlantic/Madeira", "Atlantic/Reykjavik", "Asia/Nicosia", "UTC",
]
