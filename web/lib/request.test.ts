import { describe, expect, it } from "vitest";
import { emptyForm, FormError, toRequest } from "./request";

const filled = {
  ...emptyForm, asking: "$899,900", bedsAbove: "3", baths: "2.5", ratePercent: "4.5",
};

describe("toRequest", () => {
  it("turns typed dollars into integer cents", () => {
    const body = toRequest({ ...filled, condoFees: "412.50" });
    expect(body.asking_cents).toBe(89_990_000);
    expect(body.monthly_condo_fees_cents).toBe(41_250);
    expect(Number.isInteger(body.asking_cents)).toBe(true);
  });

  it("sends the rate as a share, not a percentage", () => {
    expect(toRequest(filled).mortgage_rate).toBeCloseTo(0.045);
  });

  it("spreads annual tax and income over twelve months, in cents", () => {
    const body = toRequest({ ...filled, annualPropertyTax: "6,000", annualIncome: "120000" });
    expect(body.monthly_property_tax_cents).toBe(50_000);
    expect(body.monthly_income_cents).toBe(1_000_000);
  });

  it("leaves blanks out so the API uses its defaults", () => {
    const body = toRequest(filled);
    expect(body).not.toHaveProperty("sqft");
    expect(body).not.toHaveProperty("down_payment_cents");
    expect(body).not.toHaveProperty("garage");
  });

  it("only sends a neighbourhood for Toronto", () => {
    expect(toRequest({ ...filled, neighbourhood: "Annex" })).not.toHaveProperty("neighbourhood");
    expect(toRequest({ ...filled, city: "Toronto", neighbourhood: "Annex" }).neighbourhood).toBe("Annex");
  });

  it("names the field that is missing or wrong", () => {
    expect(() => toRequest({ ...filled, asking: "" })).toThrow(new FormError("Asking price is required."));
    expect(() => toRequest({ ...filled, baths: "two" })).toThrow("Bathrooms must be a positive number.");
  });
});
