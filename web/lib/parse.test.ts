import { describe, expect, it } from "vitest";
import { parseListing } from "./parse";

const CITIES = ["Toronto", "Kitchener", "Waterloo", "Cambridge", "Mississauga"];

const REALTOR_STYLE = `
$849,900
123 Example Street, Kitchener, Ontario N2M 1A1
3 + 1 Bedrooms  2.5 Bathrooms
Detached  Built in 1998
1,800 sq ft  Lot: 40 x 120 ft
Parking: 3   Attached garage
Finished basement with walkout. Renovated kitchen, new roof 2021.
Days on market: 18
`;

describe("parseListing", () => {
  it("reads a typical listing page", () => {
    const form = parseListing(REALTOR_STYLE, CITIES);
    expect(form).toMatchObject({
      asking: "849900", city: "Kitchener", propertyType: "detached",
      bedsAbove: "3", bedsBelow: "1", baths: "2.5",
      sqft: "1800", lotSqft: "4800", yearBuilt: "1998", parking: "3",
      garage: true, basement: "walkout", daysOnMarket: "18",
    });
    expect(form.description).toBe(REALTOR_STYLE.trim());
  });

  it("takes the middle of a square-footage range", () => {
    expect(parseListing("Size: 1500-2000 sqft", CITIES).sqft).toBe("1750");
  });

  it("does not read the lot as the house size", () => {
    expect(parseListing("Lot size: 5,000 sq ft", CITIES)).toMatchObject({ lotSqft: "5000" });
    expect(parseListing("Lot size: 5,000 sq ft", CITIES).sqft).toBeUndefined();
  });

  it("reads compact field labels", () => {
    const form = parseListing("List Price: $1,195,000 Beds: 4 Baths: 3 Semi-Detached Year Built: 1925 DOM 41", CITIES);
    expect(form).toMatchObject({
      asking: "1195000", bedsAbove: "4", baths: "3", propertyType: "semi_detached",
      yearBuilt: "1925", daysOnMarket: "41",
    });
  });

  it("knows the property types", () => {
    expect(parseListing("Freehold townhouse", CITIES).propertyType).toBe("townhouse");
    expect(parseListing("Condo apartment, 2 bed", CITIES).propertyType).toBe("condo_apartment");
    expect(parseListing("Bright condo unit", CITIES).propertyType).toBe("condo_apartment");
  });

  it("separates basement kinds", () => {
    expect(parseListing("Unfinished basement", CITIES).basement).toBe("unfinished");
    expect(parseListing("Legal basement apartment with separate entrance", CITIES).basement).toBe("apartment");
    expect(parseListing("Fully finished basement", CITIES).basement).toBe("finished");
  });

  it("reads a car count from the garage", () => {
    expect(parseListing("Double car garage", CITIES)).toMatchObject({ garage: true, parking: "2" });
    expect(parseListing("2-car garage", CITIES)).toMatchObject({ garage: true, parking: "2" });
  });

  it("ignores small dollar amounts such as fees and taxes", () => {
    const form = parseListing("Taxes: $4,512/yr  Maintenance $450  Asking $629,000", CITIES);
    expect(form.asking).toBe("629000");
  });

  it("matches the first city named, as a whole word", () => {
    expect(parseListing("Waterloo Region home in Cambridge", CITIES).city).toBe("Waterloo");
    expect(parseListing("Near Kitchener-Waterloo airport", CITIES).city).toBe("Kitchener");
  });

  it("leaves out what it cannot find", () => {
    const form = parseListing("Lovely home, call for details", CITIES);
    expect(Object.keys(form)).toEqual(["description"]);
  });
});
