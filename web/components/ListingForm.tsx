"use client";

import type { Options } from "@/lib/api";
import type { Form } from "@/lib/request";

type Props = {
  form: Form;
  options: Options;
  busy: boolean;
  onChange: (form: Form) => void;
  onSubmit: () => void;
};

const TYPE_LABELS: Record<string, string> = {
  detached: "Detached", semi_detached: "Semi-detached", townhouse: "Townhouse", condo_apartment: "Condo apartment",
};

export default function ListingForm({ form, options, busy, onChange, onSubmit }: Props) {
  const set = <K extends keyof Form>(key: K) => (value: Form[K]) => onChange({ ...form, [key]: value });

  const text = (key: keyof Form, label: string, hint?: string, inputMode: "decimal" | "numeric" = "decimal") => (
    <label>
      {label}
      <input
        inputMode={inputMode}
        value={form[key] as string}
        onChange={(e) => set(key)(e.target.value as never)}
        placeholder={hint}
      />
    </label>
  );

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <fieldset>
        <legend>The listing</legend>
        {text("asking", "Asking price ($)", "899,900")}
        <label>
          City
          <select value={form.city} onChange={(e) => set("city")(e.target.value)}>
            {options.cities.map((c) => <option key={c}>{c}</option>)}
          </select>
        </label>
        {form.city === "Toronto" && (
          <label>
            Neighbourhood
            <select value={form.neighbourhood} onChange={(e) => set("neighbourhood")(e.target.value)}>
              <option value="">Not sure</option>
              {options.neighbourhoods.map((n) => <option key={n}>{n}</option>)}
            </select>
          </label>
        )}
        <label>
          TRREB market area (GTA)
          <select value={form.district} onChange={(e) => set("district")(e.target.value)}>
            <option value="">Use the city</option>
            {options.districts.map((d) => <option key={d}>{d}</option>)}
          </select>
        </label>
        <label>
          Property type
          <select value={form.propertyType} onChange={(e) => set("propertyType")(e.target.value)}>
            {options.property_types.map((t) => <option key={t} value={t}>{TYPE_LABELS[t] ?? t}</option>)}
          </select>
        </label>
        <div className="row">
          {text("bedsAbove", "Bedrooms", "3", "numeric")}
          {text("bedsBelow", "Below grade", "0", "numeric")}
          {text("baths", "Bathrooms", "2")}
        </div>
        <div className="row">
          {text("sqft", "Square feet", "1,500", "numeric")}
          {text("lotSqft", "Lot (sq ft)", "4,000", "numeric")}
        </div>
        <div className="row">
          {text("yearBuilt", "Year built", "1990", "numeric")}
          {text("parking", "Parking spaces", "2", "numeric")}
        </div>
        <label>
          Basement
          <select value={form.basement} onChange={(e) => set("basement")(e.target.value)}>
            <option value="">Not stated</option>
            <option value="none">None</option>
            <option value="unfinished">Unfinished</option>
            <option value="finished">Finished</option>
            <option value="apartment">Apartment or separate entrance</option>
            <option value="walkout">Walkout</option>
          </select>
        </label>
        <label className="check">
          <input type="checkbox" checked={form.garage} onChange={(e) => set("garage")(e.target.checked)} />
          Garage
        </label>
        <label>
          Listing description
          <textarea
            rows={4}
            value={form.description}
            onChange={(e) => set("description")(e.target.value)}
            placeholder="Paste the agent's description: renovated kitchen, finished basement..."
          />
        </label>
        <div className="row">
          {text("daysOnMarket", "Days on market", "", "numeric")}
          {text("originalList", "Original list price ($)", "if it was cut")}
        </div>
      </fieldset>

      <fieldset>
        <legend>Your purchase</legend>
        <div className="row">
          {text("ratePercent", "Mortgage rate (%)", "4.5")}
          {text("amortization", "Amortization (years)", "25", "numeric")}
        </div>
        {text("downPayment", "Down payment ($)", "minimum if blank")}
        <label className="check">
          <input type="checkbox" checked={form.firstTime} onChange={(e) => set("firstTime")(e.target.checked)} />
          First-time buyer
        </label>
        <div className="row">
          {text("annualIncome", "Household income ($/yr)", "for the stress test")}
          {text("annualPropertyTax", "Property tax ($/yr)")}
        </div>
        <div className="row">
          {text("condoFees", "Condo fees ($/mo)")}
          {text("rent", "Expected rent ($/mo)", "CMHC average if blank")}
        </div>
      </fieldset>

      <button type="submit" disabled={busy}>{busy ? "Evaluating…" : "Is it a fair price?"}</button>
    </form>
  );
}
