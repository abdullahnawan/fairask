// Shapes returned by the FastAPI app (api/main.py). Money is integer cents.

export type Options = {
  cities: string[];
  property_types: string[];
  neighbourhoods: string[];
  districts: string[];
};

export type Report = {
  valuation: {
    benchmark_cents: number;
    benchmark_month: string;
    fair_cents: number;
    low_cents: number;
    high_cents: number;
    reasons: { text: string; dollars_cents: number }[];
  };
  verdict: { label: "Great deal" | "Good" | "Fair" | "Overpriced"; gap_cents: number; gap_share: number };
  price_per_sqft_cents: number | null;
  fair_per_sqft_cents: number | null;
  market: {
    hpi: {
      month: string;
      benchmark_cents: number;
      change_1y: number | null;
      change_5y: number | null;
      peak_month: string;
      from_peak: number;
    };
    area: {
      area: string;
      month: string;
      snlr: number;
      balance: string;
      months_inventory: number;
      avg_days_on_market: number;
      sale_to_list: number;
    } | null;
  };
  costs: {
    down_payment_cents: number;
    cmhc_premium_cents: number;
    mortgage_cents: number;
    monthly_payment_cents: number;
    land_transfer_tax_cents: number;
    stress_test: { qualifying_rate: number; qualifying_payment_cents: number; gds: number; tds: number; passes: boolean } | null;
  };
  investor: {
    rent_cents: number;
    gross_yield: number;
    monthly_costs_cents: number;
    cash_flow_cents: number;
    rent_source: "you" | { centre: string; survey: string; reliability: string | null };
  } | null;
  red_flags: string[];
  notes: string[];
};

// Next.js rewrites /api/* to the FastAPI server (next.config.ts).
async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, init);
  } catch {
    throw new Error("Can't reach the FairAsk server. Is the API running?");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    // FastAPI sends a string for refused values and a list for invalid fields.
    const message = typeof detail === "string" ? detail
      : Array.isArray(detail) ? detail.map((d) => `${d.loc?.at(-1)}: ${d.msg}`).join("; ")
      : `The server answered ${response.status}.`;
    throw new Error(message);
  }
  return response.json();
}

export const getOptions = () => call<Options>("/options");

export const evaluate = (body: Record<string, unknown>) =>
  call<Report>("/evaluate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

const dollars = new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD", maximumFractionDigits: 0 });
export const money = (cents: number) => dollars.format(cents / 100);
export const percent = (share: number, digits = 1) => `${(share * 100).toFixed(digits)}%`;
