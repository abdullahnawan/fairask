// The form holds what the user typed; the API takes integer cents and shares.
// toRequest is the one place that converts between them.

export type Form = {
  asking: string;
  city: string;
  neighbourhood: string;
  district: string;
  propertyType: string;
  bedsAbove: string;
  bedsBelow: string;
  baths: string;
  sqft: string;
  lotSqft: string;
  yearBuilt: string;
  parking: string;
  basement: string;
  garage: boolean;
  description: string;
  daysOnMarket: string;
  originalList: string;
  downPayment: string;
  ratePercent: string;
  amortization: string;
  firstTime: boolean;
  annualIncome: string;
  annualPropertyTax: string;
  condoFees: string;
  rent: string;
};

export const emptyForm: Form = {
  asking: "", city: "Kitchener", neighbourhood: "", district: "", propertyType: "detached",
  bedsAbove: "", bedsBelow: "0", baths: "", sqft: "", lotSqft: "", yearBuilt: "", parking: "",
  basement: "", garage: false, description: "", daysOnMarket: "", originalList: "",
  downPayment: "", ratePercent: "", amortization: "25", firstTime: false,
  annualIncome: "", annualPropertyTax: "", condoFees: "", rent: "",
};

export class FormError extends Error {}

function number(value: string, label: string): number | null {
  const cleaned = value.replace(/[$,\s]/g, "");
  if (cleaned === "") return null;
  const n = Number(cleaned);
  if (!Number.isFinite(n) || n < 0) throw new FormError(`${label} must be a positive number.`);
  return n;
}

function required(value: string, label: string): number {
  const n = number(value, label);
  if (n === null) throw new FormError(`${label} is required.`);
  return n;
}

const cents = (dollars: number | null) => (dollars === null ? null : Math.round(dollars * 100));
const whole = (n: number | null) => (n === null ? null : Math.round(n));
const monthly = (annualDollars: number | null) => (annualDollars === null ? null : Math.round((annualDollars * 100) / 12));

export function toRequest(form: Form): Record<string, unknown> {
  const body: Record<string, unknown> = {
    asking_cents: cents(required(form.asking, "Asking price")),
    city: form.city,
    district: form.district || null,
    neighbourhood: form.city === "Toronto" ? form.neighbourhood || null : null,
    property_type: form.propertyType,
    beds_above: whole(required(form.bedsAbove, "Bedrooms")),
    beds_below: whole(number(form.bedsBelow, "Bedrooms below grade")) ?? 0,
    baths: required(form.baths, "Bathrooms"),
    sqft: whole(number(form.sqft, "Square feet")),
    lot_sqft: whole(number(form.lotSqft, "Lot size")),
    year_built: whole(number(form.yearBuilt, "Year built")),
    parking: whole(number(form.parking, "Parking")),
    basement: form.basement || null,
    garage: form.garage || null,
    description: form.description,
    days_on_market: whole(number(form.daysOnMarket, "Days on market")),
    original_list_cents: cents(number(form.originalList, "Original list price")),
    down_payment_cents: cents(number(form.downPayment, "Down payment")),
    mortgage_rate: required(form.ratePercent, "Mortgage rate") / 100,
    amortization_years: whole(required(form.amortization, "Amortization")),
    first_time_buyer: form.firstTime,
    monthly_income_cents: monthly(number(form.annualIncome, "Income")),
    monthly_property_tax_cents: monthly(number(form.annualPropertyTax, "Property tax")) ?? 0,
    monthly_condo_fees_cents: cents(number(form.condoFees, "Condo fees")) ?? 0,
    monthly_rent_cents: cents(number(form.rent, "Rent")),
  };
  // Leave unknowns out so the API applies its own defaults.
  return Object.fromEntries(Object.entries(body).filter(([, v]) => v !== null));
}
