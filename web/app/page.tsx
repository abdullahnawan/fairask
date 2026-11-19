"use client";

import { useEffect, useState } from "react";
import ListingForm from "@/components/ListingForm";
import PasteImport from "@/components/PasteImport";
import ReportView from "@/components/ReportView";
import { evaluate, getOptions, type Options, type Report } from "@/lib/api";
import { emptyForm, toRequest, type Form } from "@/lib/request";

export default function Home() {
  const [options, setOptions] = useState<Options | null>(null);
  const [form, setForm] = useState<Form>(emptyForm);
  const [report, setReport] = useState<{ report: Report; askingCents: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getOptions().then(setOptions, (e: Error) => setError(e.message));
  }, []);

  async function submit() {
    setError(null);
    setReport(null);  // never leave the last listing's verdict next to a new error
    setBusy(true);
    try {
      const body = toRequest(form);
      setReport({ report: await evaluate(body), askingCents: body.asking_cents as number });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <header>
        <h1>FairAsk</h1>
        <p className="muted">Is the asking price fair? Homes in Waterloo Region and the GTA.</p>
      </header>
      <div className="layout">
        <div>
          {options ? (
            <>
              <PasteImport cities={options.cities} onParsed={(fields) => setForm((f) => ({ ...f, ...fields }))} />
              <ListingForm form={form} options={options} busy={busy} onChange={setForm} onSubmit={submit} />
            </>
          ) : (
            !error && <p aria-busy="true">Loading…</p>
          )}
        </div>
        <div aria-live="polite">
          {error && <p className="error" role="alert">{error}</p>}
          {report ? (
            <ReportView report={report.report} askingCents={report.askingCents} />
          ) : (
            options && <p className="empty">Fill in the listing and press the button. The report shows a fair value
              range, a verdict, the reasons behind it and what owning it would cost.</p>
          )}
        </div>
      </div>
    </main>
  );
}
