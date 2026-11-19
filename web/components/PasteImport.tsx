"use client";

import { useState } from "react";
import { parseListing } from "@/lib/parse";
import type { Form } from "@/lib/request";

export default function PasteImport({ cities, onParsed }: { cities: string[]; onParsed: (fields: Partial<Form>) => void }) {
  const [text, setText] = useState("");
  const [status, setStatus] = useState<string | null>(null);

  function fill() {
    const fields = parseListing(text, cities);
    const found = Object.keys(fields).filter((k) => k !== "description").length;
    onParsed(fields);
    setStatus(found ? `Filled ${found} fields. Check them below before evaluating.`
      : "No fields found. The text was added to the description; fill the rest by hand.");
  }

  return (
    <fieldset>
      <legend>Paste a listing</legend>
      <label>
        Listing text
        <textarea
          rows={5}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Copy the whole listing page (price, beds, baths, size, description) and paste it here."
        />
      </label>
      <button type="button" className="secondary" onClick={fill} disabled={!text.trim()}>Fill the form</button>
      {status && <p className="muted" role="status">{status}</p>}
    </fieldset>
  );
}
