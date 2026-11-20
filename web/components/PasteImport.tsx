"use client";

import { useState } from "react";
import { parseListing } from "@/lib/parse";
import type { Form } from "@/lib/request";

export default function PasteImport({ cities, onParsed }: { cities: string[]; onParsed: (fields: Partial<Form>) => void }) {
  const [text, setText] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [reading, setReading] = useState(false);

  function fill(source: string) {
    const fields = parseListing(source, cities);
    const found = Object.keys(fields).filter((k) => k !== "description").length;
    onParsed(fields);
    setStatus(found ? `Filled ${found} fields. Check them below before evaluating.`
      : "No fields found. The text was added to the description; fill the rest by hand.");
  }

  // OCR runs in the browser: the image never leaves the device. Tesseract.js
  // fetches its engine and English data from a CDN the first time.
  async function readScreenshot(file: File) {
    setReading(true);
    setStatus("Reading the screenshot…");
    try {
      const { createWorker } = await import("tesseract.js");
      const worker = await createWorker("eng", 1, {
        logger: (m) => m.status === "recognizing text" && setStatus(`Reading the screenshot… ${Math.round(m.progress * 100)}%`),
      });
      let data;
      try {
        ({ data } = await worker.recognize(file));
      } finally {
        await worker.terminate();  // also on failure, or each bad image leaves an engine in memory
      }
      setText(data.text);
      fill(data.text);
    } catch {
      setStatus("Could not read that image. Try a sharper screenshot, or paste the text instead.");
    } finally {
      setReading(false);
    }
  }

  return (
    <section>
      <h2>Import a listing</h2>
      <label>
        Listing text
        <textarea
          rows={4}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Copy the whole listing page (price, beds, baths, size, description) and paste it here."
        />
      </label>
      <div className="actions">
        <button type="button" className="secondary" onClick={() => fill(text)} disabled={!text.trim() || reading}>
          Fill the form
        </button>
        <label className="file-button">
          <input
            type="file"
            accept="image/*"
            disabled={reading}
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";  // choosing the same file again still fires
              if (file) readScreenshot(file);
            }}
          />
          {reading ? "Reading…" : "Use a screenshot"}
        </label>
      </div>
      {status && <p className="muted" role="status">{status}</p>}
    </section>
  );
}
