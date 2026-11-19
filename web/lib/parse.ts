// Reads a pasted listing (or OCR text from a screenshot) into form fields.
// Regexes cover the stock phrasing of Canadian listing pages; anything not
// found is left out so the form keeps what the user typed. The whole text also
// goes into the description, where the API looks for basement and garage words.

import type { Form } from "./request";

const NUM = (s: string) => s.replace(/,/g, "");
const SQFT = String.raw`(?:sq\.?\s*ft\.?|sqft|square\s+feet)`;
const CAR_WORDS: Record<string, string> = { single: "1", one: "1", double: "2", two: "2", triple: "3", three: "3" };

function first(text: string, patterns: RegExp[]): RegExpMatchArray | null {
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match) return match;
  }
  return null;
}

function askingPrice(text: string): string | undefined {
  // The first dollar amount big enough to be a home; skips taxes and condo fees.
  for (const match of text.matchAll(/\$\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})?/g)) {
    if (Number(NUM(match[1])) >= 50_000) return NUM(match[1]);
  }
}

function propertyType(text: string): string | undefined {
  if (/\bsemi[\s-]?detached\b|\bsemi\b/i.test(text)) return "semi_detached";
  if (/\btown\s?(?:house|home)s?\b|\brow\s?house\b/i.test(text)) return "townhouse";
  if (/\bcondo(?:minium)?\b|\bapartment\b(?!\s+with)/i.test(text) && !/basement\s+apartment/i.test(text)) return "condo_apartment";
  if (/\bdetached\b/i.test(text)) return "detached";
}

function basement(text: string): string | undefined {
  if (/\b(?:basement|bsmt)\s+apartment\b|\bin-?law\b|\bseparate\s+entrance\b/i.test(text)) return "apartment";
  if (/\bwalk-?\s?out\b/i.test(text)) return "walkout";
  if (/\bunfinished\s+(?:basement|bsmt)\b/i.test(text)) return "unfinished";
  if (/\bfinished\s+(?:basement|bsmt|lower\s+level)\b/i.test(text)) return "finished";
}

function city(text: string, cities: string[]): string | undefined {
  let best: { name: string; at: number } | undefined;
  for (const name of cities) {
    const at = text.search(new RegExp(`\\b${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "i"));
    if (at >= 0 && (!best || at < best.at)) best = { name, at };
  }
  return best?.name;
}

export function parseListing(raw: string, cities: string[]): Partial<Form> {
  const text = raw.trim();
  const out: Partial<Form> = {};

  out.asking = askingPrice(text);
  out.city = city(text, cities);
  out.propertyType = propertyType(text);
  out.basement = basement(text);

  // Labelled forms first ("Beds: 4"), so "$1,195,000 Beds" is never read as 000 beds.
  const beds = first(text, [
    /\bbed(?:room)?s?\s*:\s*(\d{1,2})(?:\s*\+\s*(\d{1,2}))?/i,
    /(?<![\d,.$])(\d{1,2})(?:\s*\+\s*(\d{1,2}))?\s*(?:bedrooms?|beds?|br)\b/i,
  ]);
  if (beds) {
    out.bedsAbove = beds[1];
    if (beds[2]) out.bedsBelow = beds[2];
  }
  out.baths = first(text, [
    /\bbath(?:room)?s?\s*:\s*(\d{1,2}(?:\.\d)?)/i,
    /(?<![\d,.$])(\d{1,2}(?:\.\d)?)\s*(?:bathrooms?|baths?|ba)\b/i,
  ])?.[1];

  // Lot first, then cut it out so its square feet are not read as the house's.
  let rest = text;
  const lotByFeet = text.match(/\blot(?:\s*size)?\s*:?\s*(\d+(?:\.\d+)?)\s*(?:ft|feet|')?\s*x\s*(\d+(?:\.\d+)?)/i);
  const lotByArea = text.match(new RegExp(String.raw`\blot(?:\s*size)?\s*:?\s*([\d,]+)\s*${SQFT}`, "i"));
  if (lotByFeet) {
    out.lotSqft = String(Math.round(Number(lotByFeet[1]) * Number(lotByFeet[2])));
    rest = rest.replace(lotByFeet[0], "");
  } else if (lotByArea) {
    out.lotSqft = NUM(lotByArea[1]);
    rest = rest.replace(lotByArea[0], "");
  }
  const sqftRange = rest.match(new RegExp(String.raw`([\d,]{3,6})\s*(?:-|–|to)\s*([\d,]{3,6})\s*${SQFT}`, "i"));
  const sqft = rest.match(new RegExp(String.raw`([\d,]{3,6})\s*${SQFT}`, "i"));
  if (sqftRange) out.sqft = String(Math.round((Number(NUM(sqftRange[1])) + Number(NUM(sqftRange[2]))) / 2));
  else if (sqft) out.sqft = NUM(sqft[1]);

  out.yearBuilt = text.match(/\b(?:year\s+built|built(?:\s+in)?)\s*:?\s*((?:18|19|20)\d{2})\b/i)?.[1];
  out.daysOnMarket = first(text, [
    /\b(?:days\s+on\s+market|dom)\s*:?\s*(\d{1,4})\b/i,
    /\b(\d{1,4})\s+days\s+on\s+market\b/i,
  ])?.[1];

  if (/\bgarage\b/i.test(text)) out.garage = true;
  out.parking = first(text, [/\bparking(?:\s+spaces?)?\s*:?\s*(\d{1,2})\b/i, /\b(\d{1,2})\s+parking\b/i])?.[1];
  const cars = text.match(/\b(\d|single|one|double|two|triple|three)[\s-]*car\s+garage\b/i);
  if (!out.parking && cars) out.parking = CAR_WORDS[cars[1].toLowerCase()] ?? cars[1];

  out.description = text;
  return Object.fromEntries(Object.entries(out).filter(([, v]) => v !== undefined)) as Partial<Form>;
}
